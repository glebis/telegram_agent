"""
Request body size limit middleware.

Rejects requests whose Content-Length exceeds MAX_REQUEST_BODY_BYTES (default: 1 MB).
When no Content-Length header is present, reads the body and checks its actual size.
Returns 413 (Payload Too Large) for oversized payloads.
"""

import logging
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# 1 MB default
DEFAULT_MAX_BODY_BYTES = 1048576


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces a maximum request body size.

    Applies to paths matching the configured prefixes.
    Skips in test environment unless BODY_SIZE_LIMIT_TEST=1 is set.

    Args:
        app: The ASGI application.
        max_bytes: Maximum allowed body size in bytes.
        path_prefixes: Tuple of path prefixes to enforce the limit on.
    """

    def __init__(
        self,
        app,
        max_bytes: int = DEFAULT_MAX_BODY_BYTES,
        path_prefixes: tuple = ("/webhook", "/api/", "/admin/"),
    ):
        super().__init__(app)
        self.max_bytes = max_bytes
        self.path_prefixes = path_prefixes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import os

        # Skip in test environment unless explicitly enabled
        if (
            os.getenv("ENVIRONMENT") == "test"
            and os.getenv("BODY_SIZE_LIMIT_TEST") != "1"
        ):
            return await call_next(request)

        path = request.url.path
        if not any(path.startswith(prefix) for prefix in self.path_prefixes):
            return await call_next(request)

        # Check Content-Length header first (fast path)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    logger.warning(
                        "Rejected oversized request: Content-Length=%s, max=%s, path=%s",
                        content_length,
                        self.max_bytes,
                        path,
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )

        # If no Content-Length, read body and check actual size
        if content_length is None and request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > self.max_bytes:
                logger.warning(
                    "Rejected oversized request: body_size=%d, max=%s, path=%s",
                    len(body),
                    self.max_bytes,
                    path,
                )
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )

            # Re-inject body so downstream can read it
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive  # type: ignore[attr-defined]

        return await call_next(request)
