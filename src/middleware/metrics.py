"""
Prometheus metrics middleware.

Automatically records HTTP request count, error count, and webhook latency.
"""

import logging
import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that records Prometheus metrics for every request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from ..api.metrics import record_error, record_latency, record_request

        path = request.url.path
        method = request.method
        start = time.monotonic()

        response = await call_next(request)

        elapsed = time.monotonic() - start

        record_request(path, method)

        if response.status_code >= 400:
            record_error(path, method, response.status_code)

        # Record latency for webhook endpoint
        if path == "/webhook" or path.startswith("/webhook"):
            record_latency(path, elapsed)

        return response
