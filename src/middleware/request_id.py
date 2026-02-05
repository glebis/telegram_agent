"""
Request ID Middleware for FastAPI.

Generates a UUID request_id for each incoming request, sets it in the
RequestContext contextvar so all logs within that request include it,
and adds an X-Request-ID response header.
"""

import logging
import uuid
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..utils.logging import RequestContext

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that assigns a unique request ID to each request.

    - If the incoming request already has an X-Request-ID header, that value
      is reused (useful for distributed tracing).
    - Otherwise a new UUID is generated.
    - The ID is stored in RequestContext so all log records within the
      request automatically include it.
    - The ID is returned in the X-Request-ID response header.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Use provided request ID or generate a new one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Set in contextvar for log propagation
        RequestContext.set(request_id=request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Clear context after request completes
            RequestContext.clear()
