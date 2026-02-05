"""
Unified Error Handling Middleware for FastAPI.

Provides:
- Consistent JSON error responses
- Error logging with request context
- Special handling for webhook endpoints (return 200 to prevent retries)
- Request ID tracking
"""

import logging
import traceback
import uuid
from typing import Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Middleware that catches all unhandled exceptions and returns
    consistent JSON error responses.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and handle any errors."""
        request_id = str(uuid.uuid4())[:8]

        # Add request ID to state for access in handlers
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            return response

        except HTTPException:
            # Let HTTP exceptions pass through to FastAPI's handler
            raise

        except Exception as e:
            # Log the error with context
            logger.error(
                f"Unhandled exception [{request_id}]: {type(e).__name__}: {e}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            # Special handling for webhook endpoint
            if request.url.path == "/webhook":
                # Return 200 to prevent Telegram from retrying
                return JSONResponse(
                    status_code=200,
                    content={
                        "ok": False,
                        "error": {
                            "message": "Internal processing error",
                        },
                        "request_id": request_id,
                    },
                )

            # Standard error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": "Internal server error",
                    },
                    "request_id": request_id,
                },
            )


def get_error_response(
    error: Exception,
    request_id: str = None,
    include_traceback: bool = False,
) -> dict:
    """
    Build a standard error response dict.

    Args:
        error: The exception that occurred
        request_id: Optional request ID for tracking
        include_traceback: Whether to include full traceback (dev only)

    Returns:
        Error response dictionary
    """
    response = {
        "error": {
            "message": str(error),
            "type": type(error).__name__,
        },
    }

    if request_id:
        response["request_id"] = request_id

    if include_traceback:
        response["error"]["traceback"] = traceback.format_exc()

    return response


class TelegramWebhookException(Exception):
    """Exception during webhook processing - should return 200."""


class DatabaseException(Exception):
    """Database-related exception."""


class ConfigurationException(Exception):
    """Configuration or setup exception."""
