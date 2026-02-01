"""Test that error responses don't leak internal details."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from starlette.testclient import TestClient


def test_error_handler_sanitizes_webhook_errors():
    """Verify webhook error responses don't contain exception details."""
    from src.middleware.error_handler import ErrorHandlerMiddleware

    # The middleware should return generic messages, not str(exception)
    import inspect
    source = inspect.getsource(ErrorHandlerMiddleware.dispatch)

    # Check that error responses use generic messages
    assert '"Internal processing error"' in source or "'Internal processing error'" in source, (
        "Webhook error response should use 'Internal processing error', not str(e)"
    )
    assert '"Internal server error"' in source or "'Internal server error'" in source, (
        "500 error response should use 'Internal server error', not str(e)"
    )

    # Verify exception type is NOT exposed
    assert '"type": type(e).__name__' not in source, (
        "Error responses should not expose exception type"
    )


def test_error_handler_preserves_logging():
    """Verify detailed errors are still logged (just not returned)."""
    from src.middleware.error_handler import ErrorHandlerMiddleware
    import inspect
    source = inspect.getsource(ErrorHandlerMiddleware.dispatch)

    # Logging should still contain details
    assert "exc_info=True" in source, (
        "Error handler should log with exc_info=True for debugging"
    )
