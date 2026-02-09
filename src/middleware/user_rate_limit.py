"""
Per-user (Telegram user_id) rate limiter middleware for webhook requests.

Complements the per-IP rate limiter. Since all Telegram webhook traffic
arrives from Telegram's server IPs, per-IP limiting is ineffective for
user-level abuse. This middleware extracts the Telegram user_id from the
incoming update JSON and applies a per-user token bucket.

OWNER/ADMIN users receive a higher rate limit (configurable).
Returns 429 when a user exceeds their limit.
"""

import json
import logging
import time
from typing import Callable, Optional, Set

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Defaults (overridden by constructor args)
DEFAULT_USER_RPM = 30
DEFAULT_PRIVILEGED_RPM = 120


class UserTokenBucket:
    """Token-bucket rate limiter for a single Telegram user."""

    __slots__ = ("capacity", "tokens", "refill_rate", "last_refill")

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


def _extract_user_id(body: dict) -> Optional[int]:
    """Extract the Telegram user_id from a webhook update payload.

    Checks, in order:
      - message.from.id
      - callback_query.from.id
      - edited_message.from.id
      - channel_post.sender_chat.id  (channels, not a user — skip)
      - inline_query.from.id
      - chosen_inline_result.from.id
    """
    for key in ("message", "edited_message", "channel_post"):
        msg = body.get(key)
        if isinstance(msg, dict):
            sender = msg.get("from")
            if isinstance(sender, dict) and "id" in sender:
                return int(sender["id"])

    for key in ("callback_query", "inline_query", "chosen_inline_result"):
        obj = body.get(key)
        if isinstance(obj, dict):
            sender = obj.get("from")
            if isinstance(sender, dict) and "id" in sender:
                return int(sender["id"])

    return None


class UserRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-Telegram-user rate limiting middleware for webhook endpoints.

    Reads the JSON body of POST /webhook requests, extracts the sender's
    Telegram user_id, and applies a per-user token bucket. OWNER and ADMIN
    users (identified by their user IDs) receive a higher limit.

    The request body is re-injected after reading so downstream handlers
    can still access it.

    Args:
        app: The ASGI application.
        user_rpm: Requests per minute for regular users.
        privileged_rpm: Requests per minute for OWNER/ADMIN users.
        privileged_user_ids: Set of Telegram user IDs with elevated limits.
        webhook_path: URL path prefix for the webhook endpoint.
    """

    def __init__(
        self,
        app,
        user_rpm: int = DEFAULT_USER_RPM,
        privileged_rpm: int = DEFAULT_PRIVILEGED_RPM,
        privileged_user_ids: Optional[Set[int]] = None,
        webhook_path: str = "/webhook",
    ):
        super().__init__(app)
        self.user_rpm = user_rpm
        self.privileged_rpm = privileged_rpm
        self.user_refill_rate = user_rpm / 60.0
        self.privileged_refill_rate = privileged_rpm / 60.0
        self.privileged_user_ids: Set[int] = privileged_user_ids or set()
        self.webhook_path = webhook_path

        # Per-user buckets keyed by Telegram user_id
        self._buckets: dict[int, UserTokenBucket] = {}
        self._last_prune = time.monotonic()
        self._prune_interval = 300.0  # prune stale buckets every 5 minutes

    def _get_bucket(self, user_id: int) -> UserTokenBucket:
        """Get or create a token bucket for the given user."""
        bucket = self._buckets.get(user_id)
        if bucket is not None:
            return bucket

        if user_id in self.privileged_user_ids:
            bucket = UserTokenBucket(
                capacity=self.privileged_rpm,
                refill_rate=self.privileged_refill_rate,
            )
        else:
            bucket = UserTokenBucket(
                capacity=self.user_rpm,
                refill_rate=self.user_refill_rate,
            )
        self._buckets[user_id] = bucket
        return bucket

    def _maybe_prune(self) -> None:
        """Remove stale buckets to prevent memory growth."""
        now = time.monotonic()
        if now - self._last_prune < self._prune_interval:
            return
        self._last_prune = now
        stale_threshold = now - 120.0  # 2 minutes idle
        stale_keys = [
            uid
            for uid, bucket in self._buckets.items()
            if bucket.last_refill < stale_threshold
        ]
        for key in stale_keys:
            del self._buckets[key]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import os

        # Skip in test environment unless explicitly enabled
        if (
            os.getenv("ENVIRONMENT") == "test"
            and os.getenv("USER_RATE_LIMIT_TEST") != "1"
        ):
            return await call_next(request)

        # Only apply to webhook POST requests
        path = request.url.path
        if request.method != "POST" or not path.startswith(self.webhook_path):
            return await call_next(request)

        # Read the body to extract user_id
        try:
            body_bytes = await request.body()
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Let downstream handle invalid JSON
            return await call_next(request)

        user_id = _extract_user_id(body)
        if user_id is None:
            # No user_id found (e.g., channel_post) — skip user rate limiting
            return await call_next(request)

        bucket = self._get_bucket(user_id)

        if not bucket.consume():
            logger.warning(
                "Per-user rate limit exceeded for user_id=%d on %s %s",
                user_id,
                request.method,
                path,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(int(60 / max(self.user_refill_rate, 1)))},
            )

        self._maybe_prune()

        # Re-inject the body so downstream handlers can read it
        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]

        return await call_next(request)
