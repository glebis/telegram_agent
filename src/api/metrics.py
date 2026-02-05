"""
Metrics endpoint for observability.

Provides /api/metrics endpoint protected by the admin API key.
Tracks in-memory counters: request count, error count, active tasks,
uptime, and webhook latency histogram (p50/p95/p99).
"""

import logging
import math
import threading
import time
from collections import deque
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

logger = logging.getLogger(__name__)

# Maximum number of latency samples to keep in the ring buffer
_MAX_LATENCY_SAMPLES = 10000


class MetricsCollector:
    """Thread-safe in-memory metrics collector.

    Tracks request count, error count, and webhook latency samples.
    No external dependencies (no Prometheus).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.request_count: int = 0
        self.error_count: int = 0
        self._latencies: deque = deque(maxlen=_MAX_LATENCY_SAMPLES)
        self._start_time: float = time.monotonic()

    def record_request(self) -> None:
        """Increment the request counter."""
        with self._lock:
            self.request_count += 1

    def record_error(self) -> None:
        """Increment the error counter."""
        with self._lock:
            self.error_count += 1

    def record_webhook_latency(self, seconds: float) -> None:
        """Record a webhook processing latency sample."""
        with self._lock:
            self._latencies.append(seconds)

    def get_latency_percentiles(self) -> Dict[str, float]:
        """Calculate p50, p95, p99 from recorded latency samples."""
        with self._lock:
            if not self._latencies:
                return {"p50": 0, "p95": 0, "p99": 0}

            sorted_latencies = sorted(self._latencies)
            n = len(sorted_latencies)

            def percentile(p: float) -> float:
                """Calculate the p-th percentile."""
                idx = (p / 100.0) * (n - 1)
                lower = int(math.floor(idx))
                upper = int(math.ceil(idx))
                if lower == upper:
                    return sorted_latencies[lower]
                # Linear interpolation
                frac = idx - lower
                return (
                    sorted_latencies[lower] * (1 - frac)
                    + sorted_latencies[upper] * frac
                )

            return {
                "p50": round(percentile(50), 4),
                "p95": round(percentile(95), 4),
                "p99": round(percentile(99), 4),
            }

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a full metrics snapshot."""
        active_tasks = _get_active_task_count()
        with self._lock:
            return {
                "request_count": self.request_count,
                "error_count": self.error_count,
                "active_tasks": active_tasks,
                "uptime_seconds": round(time.monotonic() - self._start_time, 2),
                "webhook_latency": self.get_latency_percentiles(),
            }


def _get_active_task_count() -> int:
    """Get the count of active tracked tasks.

    Returns 0 if the task tracker module is not loaded yet or unavailable.
    Uses sys.modules to avoid triggering imports that may create asyncio
    objects (e.g. asyncio.Lock) at module scope.
    """
    import sys

    mod = sys.modules.get("src.utils.task_tracker")
    if mod is None:
        return 0
    try:
        return mod.get_active_task_count()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Singleton collector
# ---------------------------------------------------------------------------

_collector: Optional[MetricsCollector] = None


def get_collector() -> MetricsCollector:
    """Return the global MetricsCollector singleton."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def _verify_metrics_key(
    x_api_key: Optional[str] = Header(
        None, description="Admin API key for authentication"
    ),
) -> bool:
    """Verify the admin API key for metrics access."""
    import hashlib
    import hmac
    import os

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth not configured",
        )

    expected = hashlib.sha256(f"{secret}:admin_api".encode()).hexdigest()
    if not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return True


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_metrics_router() -> APIRouter:
    """Create and return the metrics router."""
    router = APIRouter()

    @router.get(
        "/api/metrics",
        dependencies=[Depends(_verify_metrics_key)],
    )
    async def metrics_endpoint() -> Dict[str, Any]:
        """Return current metrics snapshot.

        Requires admin API key via X-Api-Key header.
        """
        collector = get_collector()
        return collector.get_snapshot()

    return router
