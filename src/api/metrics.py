"""
Prometheus metrics endpoint for observability.

Exposes /api/metrics in Prometheus text exposition format, protected
by the admin API key. Provides module-level helpers for recording
request counts, error counts, and webhook latency.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom registry (avoids conflicts with default global registry)
# ---------------------------------------------------------------------------

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["path", "method"],
    registry=REGISTRY,
)

HTTP_ERRORS = Counter(
    "http_errors_total",
    "Total HTTP error responses (4xx/5xx)",
    ["path", "method", "status_code"],
    registry=REGISTRY,
)

WEBHOOK_LATENCY = Histogram(
    "webhook_latency_seconds",
    "Webhook processing latency in seconds",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

ACTIVE_TASKS = Gauge(
    "active_tasks",
    "Number of currently active tracked tasks",
    registry=REGISTRY,
)

BOT_UPTIME = Gauge(
    "bot_uptime_seconds",
    "Seconds since the bot process started",
    registry=REGISTRY,
)

_start_time = time.monotonic()


# ---------------------------------------------------------------------------
# Recording helpers
# ---------------------------------------------------------------------------


def record_request(path: str, method: str = "GET") -> None:
    """Increment the HTTP request counter."""
    HTTP_REQUESTS.labels(path=path, method=method).inc()


def record_error(path: str, method: str = "GET", status_code: int = 500) -> None:
    """Increment the HTTP error counter."""
    HTTP_ERRORS.labels(path=path, method=method, status_code=str(status_code)).inc()


def record_latency(path: str, seconds: float) -> None:
    """Record a webhook latency observation."""
    WEBHOOK_LATENCY.observe(seconds)


# ---------------------------------------------------------------------------
# Auth dependency (unchanged)
# ---------------------------------------------------------------------------


async def _verify_metrics_key(
    x_api_key: Optional[str] = Header(
        None, description="Admin API key for authentication"
    ),
) -> bool:
    """Verify the admin API key for metrics access."""
    import hmac

    from ..core.security import derive_api_key

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    try:
        expected = derive_api_key("admin_api")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth not configured",
        )

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
    async def metrics_endpoint() -> Response:
        """Return Prometheus metrics in text exposition format."""
        # Update dynamic gauges
        BOT_UPTIME.set(time.monotonic() - _start_time)
        ACTIVE_TASKS.set(_get_active_task_count())

        body = generate_latest(REGISTRY)
        return Response(
            content=body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return router


def _get_active_task_count() -> int:
    """Get the count of active tracked tasks."""
    import sys

    mod = sys.modules.get("src.utils.task_tracker")
    if mod is None:
        return 0
    try:
        return mod.get_active_task_count()
    except Exception:
        return 0
