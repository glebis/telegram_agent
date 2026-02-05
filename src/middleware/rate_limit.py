"""
Per-IP token-bucket rate limiter middleware.

In-memory implementation with no external dependencies.
Configurable via RATE_LIMIT_REQUESTS_PER_MINUTE env var (default: 60).
Returns 429 when a client exceeds the limit.
"""

import logging
import time
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class TokenBucket:
    """Simple token-bucket rate limiter for a single client."""

    __slots__ = ("capacity", "tokens", "refill_rate", "last_refill")

    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: Maximum burst size (tokens).
            refill_rate: Tokens added per second.
        """
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed, False if rate-limited."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP rate limiting middleware using an in-memory token bucket.

    Applies to paths matching the configured prefixes (default: /webhook, /api/, /admin/).
    Skips rate limiting when ENVIRONMENT=test unless RATE_LIMIT_TEST=1 is set.

    Args:
        app: The ASGI application.
        requests_per_minute: Maximum sustained requests per minute per IP.
        path_prefixes: Tuple of path prefixes to rate-limit.
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        path_prefixes: tuple = ("/webhook", "/api/", "/admin/"),
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.refill_rate = requests_per_minute / 60.0  # tokens per second
        self.path_prefixes = path_prefixes
        # Per-IP buckets; lightweight dict — old entries are pruned periodically
        self._buckets: dict[str, TokenBucket] = {}
        self._last_prune = time.monotonic()
        self._prune_interval = 300.0  # prune stale buckets every 5 minutes

    def _get_bucket(self, client_ip: str) -> TokenBucket:
        """Get or create a token bucket for the given IP."""
        bucket = self._buckets.get(client_ip)
        if bucket is None:
            bucket = TokenBucket(
                capacity=self.requests_per_minute, refill_rate=self.refill_rate
            )
            self._buckets[client_ip] = bucket
        return bucket

    def _maybe_prune(self) -> None:
        """Remove stale buckets to prevent memory growth."""
        now = time.monotonic()
        if now - self._last_prune < self._prune_interval:
            return
        self._last_prune = now
        stale_threshold = now - 120.0  # 2 minutes idle
        stale_keys = [
            ip
            for ip, bucket in self._buckets.items()
            if bucket.last_refill < stale_threshold
        ]
        for key in stale_keys:
            del self._buckets[key]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import os

        # Skip in test environment unless explicitly enabled
        if os.getenv("ENVIRONMENT") == "test" and os.getenv("RATE_LIMIT_TEST") != "1":
            return await call_next(request)

        path = request.url.path
        if not any(path.startswith(prefix) for prefix in self.path_prefixes):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket = self._get_bucket(client_ip)

        if not bucket.consume():
            logger.warning(
                "Rate limit exceeded for IP %s on %s %s",
                client_ip,
                request.method,
                path,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(int(60 / max(self.refill_rate, 1)))},
            )

        self._maybe_prune()
        return await call_next(request)
