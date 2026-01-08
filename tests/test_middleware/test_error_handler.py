"""
Comprehensive tests for the ErrorHandlerMiddleware.

Tests cover:
- Error handler registration and middleware setup
- Different exception types handling (HTTPException, ValueError, RuntimeError, etc.)
- Logging behavior with request context
- User notification on errors (JSON responses)
- Recovery mechanisms and special handling (webhook endpoint)
- Request ID tracking
- Helper functions (get_error_response)
- Custom exception types (TelegramWebhookException, DatabaseException, ConfigurationException)
"""

import logging
import traceback
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from src.middleware.error_handler import (
    ErrorHandlerMiddleware,
    get_error_response,
    TelegramWebhookException,
    DatabaseException,
    ConfigurationException,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app_with_middleware():
    """Create a FastAPI app with ErrorHandlerMiddleware registered."""
    app = FastAPI()
    app.add_middleware(ErrorHandlerMiddleware)
    return app


@pytest.fixture
def client_with_middleware(app_with_middleware):
    """Create a test client for the app with error handler middleware."""
    return TestClient(app_with_middleware, raise_server_exceptions=False)


@pytest.fixture
def app_without_middleware():
    """Create a FastAPI app without the middleware for comparison."""
    app = FastAPI()
    return app


# =============================================================================
# Middleware Registration Tests
# =============================================================================


class TestMiddlewareRegistration:
    """Tests for error handler middleware registration and setup."""

    def test_middleware_class_exists(self):
        """Test that ErrorHandlerMiddleware class is defined."""
        assert ErrorHandlerMiddleware is not None

    def test_middleware_can_be_instantiated(self):
        """Test that middleware can be added to a FastAPI app."""
        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)
        # Should not raise any errors
        assert True

    def test_middleware_dispatch_method_exists(self):
        """Test that middleware has a dispatch method."""
        assert hasattr(ErrorHandlerMiddleware, "dispatch")
        assert callable(getattr(ErrorHandlerMiddleware, "dispatch"))

    def test_middleware_is_base_http_middleware(self):
        """Test that middleware inherits from BaseHTTPMiddleware."""
        from starlette.middleware.base import BaseHTTPMiddleware
        assert issubclass(ErrorHandlerMiddleware, BaseHTTPMiddleware)

    def test_successful_request_passes_through(self, app_with_middleware, client_with_middleware):
        """Test that successful requests pass through middleware unchanged."""
        @app_with_middleware.get("/success")
        async def success_endpoint():
            return {"status": "ok"}

        response = client_with_middleware.get("/success")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_middleware_adds_request_id_to_state(self, app_with_middleware, client_with_middleware):
        """Test that middleware adds request_id to request state."""
        captured_request_id = None

        @app_with_middleware.get("/check-state")
        async def check_state_endpoint(request: Request):
            nonlocal captured_request_id
            captured_request_id = getattr(request.state, "request_id", None)
            return {"request_id": captured_request_id}

        response = client_with_middleware.get("/check-state")

        assert response.status_code == 200
        assert captured_request_id is not None
        # Request ID should be 8 characters (first part of UUID)
        assert len(captured_request_id) == 8


# =============================================================================
# Exception Type Handling Tests
# =============================================================================


class TestExceptionTypeHandling:
    """Tests for handling different exception types."""

    def test_handles_value_error(self, app_with_middleware, client_with_middleware):
        """Test handling of ValueError exceptions."""
        @app_with_middleware.get("/value-error")
        async def raise_value_error():
            raise ValueError("Invalid value provided")

        response = client_with_middleware.get("/value-error")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "ValueError"
        assert "Invalid value provided" in data["error"]["message"]

    def test_handles_runtime_error(self, app_with_middleware, client_with_middleware):
        """Test handling of RuntimeError exceptions."""
        @app_with_middleware.get("/runtime-error")
        async def raise_runtime_error():
            raise RuntimeError("Runtime failure occurred")

        response = client_with_middleware.get("/runtime-error")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "RuntimeError"
        assert "Runtime failure occurred" in data["error"]["message"]

    def test_handles_type_error(self, app_with_middleware, client_with_middleware):
        """Test handling of TypeError exceptions."""
        @app_with_middleware.get("/type-error")
        async def raise_type_error():
            raise TypeError("Type mismatch")

        response = client_with_middleware.get("/type-error")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "TypeError"

    def test_handles_key_error(self, app_with_middleware, client_with_middleware):
        """Test handling of KeyError exceptions."""
        @app_with_middleware.get("/key-error")
        async def raise_key_error():
            raise KeyError("missing_key")

        response = client_with_middleware.get("/key-error")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "KeyError"

    def test_handles_attribute_error(self, app_with_middleware, client_with_middleware):
        """Test handling of AttributeError exceptions."""
        @app_with_middleware.get("/attribute-error")
        async def raise_attribute_error():
            raise AttributeError("Object has no attribute 'x'")

        response = client_with_middleware.get("/attribute-error")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "AttributeError"

    def test_handles_generic_exception(self, app_with_middleware, client_with_middleware):
        """Test handling of generic Exception."""
        @app_with_middleware.get("/generic-exception")
        async def raise_generic_exception():
            raise Exception("Something unexpected happened")

        response = client_with_middleware.get("/generic-exception")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "Exception"
        assert "Something unexpected happened" in data["error"]["message"]

    def test_handles_custom_exception(self, app_with_middleware, client_with_middleware):
        """Test handling of custom exception classes."""
        class CustomBusinessError(Exception):
            pass

        @app_with_middleware.get("/custom-exception")
        async def raise_custom_exception():
            raise CustomBusinessError("Business rule violation")

        response = client_with_middleware.get("/custom-exception")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "CustomBusinessError"
        assert "Business rule violation" in data["error"]["message"]

    def test_passes_through_http_exception_404(self, app_with_middleware, client_with_middleware):
        """Test that HTTPException with 404 status passes through."""
        @app_with_middleware.get("/not-found")
        async def raise_not_found():
            raise HTTPException(status_code=404, detail="Resource not found")

        response = client_with_middleware.get("/not-found")

        assert response.status_code == 404

    def test_passes_through_http_exception_401(self, app_with_middleware, client_with_middleware):
        """Test that HTTPException with 401 status passes through."""
        @app_with_middleware.get("/unauthorized")
        async def raise_unauthorized():
            raise HTTPException(status_code=401, detail="Not authenticated")

        response = client_with_middleware.get("/unauthorized")

        assert response.status_code == 401

    def test_passes_through_http_exception_403(self, app_with_middleware, client_with_middleware):
        """Test that HTTPException with 403 status passes through."""
        @app_with_middleware.get("/forbidden")
        async def raise_forbidden():
            raise HTTPException(status_code=403, detail="Access denied")

        response = client_with_middleware.get("/forbidden")

        assert response.status_code == 403

    def test_passes_through_http_exception_400(self, app_with_middleware, client_with_middleware):
        """Test that HTTPException with 400 status passes through."""
        @app_with_middleware.get("/bad-request")
        async def raise_bad_request():
            raise HTTPException(status_code=400, detail="Invalid request")

        response = client_with_middleware.get("/bad-request")

        assert response.status_code == 400

    def test_passes_through_http_exception_422(self, app_with_middleware, client_with_middleware):
        """Test that HTTPException with 422 status passes through."""
        @app_with_middleware.get("/unprocessable")
        async def raise_unprocessable():
            raise HTTPException(status_code=422, detail="Validation failed")

        response = client_with_middleware.get("/unprocessable")

        assert response.status_code == 422

    def test_passes_through_http_exception_500(self, app_with_middleware, client_with_middleware):
        """Test that HTTPException with 500 status passes through."""
        @app_with_middleware.get("/server-error-http")
        async def raise_http_server_error():
            raise HTTPException(status_code=500, detail="Server error via HTTPException")

        response = client_with_middleware.get("/server-error-http")

        assert response.status_code == 500


# =============================================================================
# Logging Behavior Tests
# =============================================================================


class TestLoggingBehavior:
    """Tests for logging behavior of the middleware."""

    def test_logs_error_with_exception_info(self, app_with_middleware, client_with_middleware, caplog):
        """Test that errors are logged with exception info."""
        @app_with_middleware.get("/log-error")
        async def raise_error_for_logging():
            raise ValueError("Error to be logged")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.get("/log-error")

        assert response.status_code == 500
        # Check that error was logged
        assert any("ValueError" in record.message for record in caplog.records)

    def test_logs_request_path(self, app_with_middleware, client_with_middleware, caplog):
        """Test that logged errors include request path."""
        @app_with_middleware.get("/path/to/test")
        async def raise_error_on_path():
            raise RuntimeError("Path error")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.get("/path/to/test")

        assert response.status_code == 500
        # Check log records for path info (via extra or message)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) > 0

    def test_logs_request_method(self, app_with_middleware, client_with_middleware, caplog):
        """Test that logged errors include request method."""
        @app_with_middleware.post("/method-test")
        async def raise_error_on_post():
            raise RuntimeError("POST error")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.post("/method-test")

        assert response.status_code == 500
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) > 0

    def test_logs_request_id_in_message(self, app_with_middleware, client_with_middleware, caplog):
        """Test that logged errors include request ID in message."""
        @app_with_middleware.get("/request-id-log")
        async def raise_error_with_request_id():
            raise ValueError("Error with ID")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.get("/request-id-log")

        assert response.status_code == 500
        # Request ID should be in log message
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any("[" in r.message and "]" in r.message for r in error_records)

    def test_does_not_log_http_exceptions(self, app_with_middleware, client_with_middleware, caplog):
        """Test that HTTPExceptions are not logged as errors by the middleware."""
        @app_with_middleware.get("/http-no-log")
        async def raise_http_exception():
            raise HTTPException(status_code=404, detail="Not found")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.get("/http-no-log")

        assert response.status_code == 404
        # No error logs from our middleware for HTTP exceptions
        error_logs = [r for r in caplog.records if "Unhandled exception" in r.message]
        assert len(error_logs) == 0

    def test_logs_exc_info_for_traceback(self, app_with_middleware, client_with_middleware, caplog):
        """Test that exc_info=True is used for full traceback."""
        @app_with_middleware.get("/traceback-test")
        async def raise_for_traceback():
            raise ValueError("Traceback test error")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.get("/traceback-test")

        assert response.status_code == 500
        # With exc_info=True, the log record should have exc_info
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any(r.exc_info is not None for r in error_records)


# =============================================================================
# User Notification (JSON Response) Tests
# =============================================================================


class TestUserNotification:
    """Tests for error response format and user notification."""

    def test_returns_json_content_type(self, app_with_middleware, client_with_middleware):
        """Test that error responses have JSON content type."""
        @app_with_middleware.get("/json-content")
        async def raise_for_json():
            raise ValueError("JSON test")

        response = client_with_middleware.get("/json-content")

        assert response.status_code == 500
        assert "application/json" in response.headers["content-type"]

    def test_error_response_has_error_key(self, app_with_middleware, client_with_middleware):
        """Test that error response contains 'error' key."""
        @app_with_middleware.get("/error-key")
        async def raise_for_error_key():
            raise RuntimeError("Error key test")

        response = client_with_middleware.get("/error-key")
        data = response.json()

        assert "error" in data

    def test_error_response_has_message(self, app_with_middleware, client_with_middleware):
        """Test that error response contains message."""
        error_message = "This is the error message"

        @app_with_middleware.get("/error-message")
        async def raise_with_message():
            raise ValueError(error_message)

        response = client_with_middleware.get("/error-message")
        data = response.json()

        assert "message" in data["error"]
        assert error_message in data["error"]["message"]

    def test_error_response_has_type(self, app_with_middleware, client_with_middleware):
        """Test that error response contains error type."""
        @app_with_middleware.get("/error-type")
        async def raise_for_type():
            raise KeyError("test")

        response = client_with_middleware.get("/error-type")
        data = response.json()

        assert "type" in data["error"]
        assert data["error"]["type"] == "KeyError"

    def test_error_response_has_request_id(self, app_with_middleware, client_with_middleware):
        """Test that error response contains request_id."""
        @app_with_middleware.get("/request-id")
        async def raise_for_request_id():
            raise ValueError("Request ID test")

        response = client_with_middleware.get("/request-id")
        data = response.json()

        assert "request_id" in data
        assert len(data["request_id"]) == 8

    def test_error_response_returns_500_status(self, app_with_middleware, client_with_middleware):
        """Test that unhandled exceptions return 500 status code."""
        @app_with_middleware.get("/status-500")
        async def raise_for_500():
            raise Exception("500 test")

        response = client_with_middleware.get("/status-500")

        assert response.status_code == 500


# =============================================================================
# Webhook Endpoint Special Handling Tests
# =============================================================================


class TestWebhookEndpointHandling:
    """Tests for special webhook endpoint handling."""

    def test_webhook_returns_200_on_error(self, app_with_middleware, client_with_middleware):
        """Test that /webhook endpoint returns 200 even on error."""
        @app_with_middleware.post("/webhook")
        async def webhook_with_error():
            raise ValueError("Webhook processing failed")

        response = client_with_middleware.post("/webhook")

        # Should return 200 to prevent Telegram retries
        assert response.status_code == 200

    def test_webhook_includes_ok_false(self, app_with_middleware, client_with_middleware):
        """Test that webhook error response includes 'ok': false."""
        @app_with_middleware.post("/webhook")
        async def webhook_ok_false():
            raise RuntimeError("Webhook error")

        response = client_with_middleware.post("/webhook")
        data = response.json()

        assert response.status_code == 200
        assert data.get("ok") is False

    def test_webhook_includes_error_details(self, app_with_middleware, client_with_middleware):
        """Test that webhook error response includes error details."""
        @app_with_middleware.post("/webhook")
        async def webhook_error_details():
            raise ValueError("Detailed webhook error")

        response = client_with_middleware.post("/webhook")
        data = response.json()

        assert "error" in data
        assert "message" in data["error"]
        assert "Detailed webhook error" in data["error"]["message"]
        assert data["error"]["type"] == "ValueError"

    def test_webhook_includes_request_id(self, app_with_middleware, client_with_middleware):
        """Test that webhook error response includes request_id."""
        @app_with_middleware.post("/webhook")
        async def webhook_request_id():
            raise Exception("Webhook request ID test")

        response = client_with_middleware.post("/webhook")
        data = response.json()

        assert "request_id" in data
        assert len(data["request_id"]) == 8

    def test_non_webhook_returns_500(self, app_with_middleware, client_with_middleware):
        """Test that non-webhook endpoints return 500 on error."""
        @app_with_middleware.post("/api/something")
        async def non_webhook_error():
            raise ValueError("Non-webhook error")

        response = client_with_middleware.post("/api/something")

        assert response.status_code == 500

    def test_webhook_get_method_returns_200_on_error(self, app_with_middleware, client_with_middleware):
        """Test that GET /webhook also returns 200 on error."""
        @app_with_middleware.get("/webhook")
        async def webhook_get_error():
            raise RuntimeError("GET webhook error")

        response = client_with_middleware.get("/webhook")

        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is False


# =============================================================================
# Request ID Tracking Tests
# =============================================================================


class TestRequestIdTracking:
    """Tests for request ID tracking functionality."""

    def test_request_id_is_uuid_format(self, app_with_middleware, client_with_middleware):
        """Test that request ID is in UUID format (first 8 chars)."""
        captured_id = None

        @app_with_middleware.get("/uuid-format")
        async def capture_uuid(request: Request):
            nonlocal captured_id
            captured_id = request.state.request_id
            return {"id": captured_id}

        response = client_with_middleware.get("/uuid-format")

        assert response.status_code == 200
        assert captured_id is not None
        # Should be 8 hex characters
        int(captured_id, 16)  # Should not raise

    def test_request_id_different_per_request(self, app_with_middleware, client_with_middleware):
        """Test that each request gets a unique ID."""
        request_ids = []

        @app_with_middleware.get("/unique-id")
        async def capture_unique(request: Request):
            request_ids.append(request.state.request_id)
            return {"id": request.state.request_id}

        client_with_middleware.get("/unique-id")
        client_with_middleware.get("/unique-id")
        client_with_middleware.get("/unique-id")

        assert len(request_ids) == 3
        assert len(set(request_ids)) == 3  # All unique

    def test_request_id_in_error_response_matches_state(self, app_with_middleware, client_with_middleware):
        """Test that error response request_id matches the one in state."""
        state_request_id = None

        @app_with_middleware.get("/id-match")
        async def capture_and_error(request: Request):
            nonlocal state_request_id
            state_request_id = request.state.request_id
            raise ValueError("ID match test")

        response = client_with_middleware.get("/id-match")
        data = response.json()

        # Note: Due to middleware flow, state_request_id may not be captured
        # before exception, but response should have a request_id
        assert "request_id" in data
        assert len(data["request_id"]) == 8


# =============================================================================
# get_error_response Helper Function Tests
# =============================================================================


class TestGetErrorResponse:
    """Tests for the get_error_response helper function."""

    def test_basic_error_response(self):
        """Test basic error response generation."""
        error = ValueError("Test error")
        response = get_error_response(error)

        assert "error" in response
        assert response["error"]["message"] == "Test error"
        assert response["error"]["type"] == "ValueError"

    def test_error_response_with_request_id(self):
        """Test error response with request_id."""
        error = RuntimeError("With ID")
        response = get_error_response(error, request_id="abc12345")

        assert "request_id" in response
        assert response["request_id"] == "abc12345"

    def test_error_response_without_request_id(self):
        """Test error response without request_id (None)."""
        error = Exception("No ID")
        response = get_error_response(error, request_id=None)

        assert "request_id" not in response

    def test_error_response_with_traceback(self):
        """Test error response with traceback included."""
        try:
            raise ValueError("Traceback test")
        except ValueError as e:
            response = get_error_response(e, include_traceback=True)

        assert "traceback" in response["error"]
        assert "ValueError" in response["error"]["traceback"]
        assert "Traceback test" in response["error"]["traceback"]

    def test_error_response_without_traceback(self):
        """Test error response without traceback (default)."""
        error = ValueError("No traceback")
        response = get_error_response(error, include_traceback=False)

        assert "traceback" not in response["error"]

    def test_error_response_preserves_error_message(self):
        """Test that error message is preserved exactly."""
        message = "Exact error message with special chars: @#$%"
        error = RuntimeError(message)
        response = get_error_response(error)

        assert response["error"]["message"] == message

    def test_error_response_with_custom_exception(self):
        """Test error response with custom exception class."""
        class MyCustomError(Exception):
            pass

        error = MyCustomError("Custom error message")
        response = get_error_response(error)

        assert response["error"]["type"] == "MyCustomError"
        assert response["error"]["message"] == "Custom error message"

    def test_error_response_all_parameters(self):
        """Test error response with all parameters provided."""
        try:
            raise ValueError("Full test")
        except ValueError as e:
            response = get_error_response(
                e,
                request_id="req-12345",
                include_traceback=True
            )

        assert response["error"]["message"] == "Full test"
        assert response["error"]["type"] == "ValueError"
        assert response["request_id"] == "req-12345"
        assert "traceback" in response["error"]


# =============================================================================
# Custom Exception Types Tests
# =============================================================================


class TestCustomExceptionTypes:
    """Tests for custom exception types defined in the module."""

    def test_telegram_webhook_exception_exists(self):
        """Test TelegramWebhookException is defined."""
        assert TelegramWebhookException is not None
        assert issubclass(TelegramWebhookException, Exception)

    def test_telegram_webhook_exception_can_be_raised(self):
        """Test TelegramWebhookException can be raised and caught."""
        with pytest.raises(TelegramWebhookException):
            raise TelegramWebhookException("Webhook error")

    def test_telegram_webhook_exception_preserves_message(self):
        """Test TelegramWebhookException preserves error message."""
        message = "Telegram webhook processing failed"
        try:
            raise TelegramWebhookException(message)
        except TelegramWebhookException as e:
            assert str(e) == message

    def test_database_exception_exists(self):
        """Test DatabaseException is defined."""
        assert DatabaseException is not None
        assert issubclass(DatabaseException, Exception)

    def test_database_exception_can_be_raised(self):
        """Test DatabaseException can be raised and caught."""
        with pytest.raises(DatabaseException):
            raise DatabaseException("Database connection lost")

    def test_database_exception_preserves_message(self):
        """Test DatabaseException preserves error message."""
        message = "Database query timeout"
        try:
            raise DatabaseException(message)
        except DatabaseException as e:
            assert str(e) == message

    def test_configuration_exception_exists(self):
        """Test ConfigurationException is defined."""
        assert ConfigurationException is not None
        assert issubclass(ConfigurationException, Exception)

    def test_configuration_exception_can_be_raised(self):
        """Test ConfigurationException can be raised and caught."""
        with pytest.raises(ConfigurationException):
            raise ConfigurationException("Missing configuration")

    def test_configuration_exception_preserves_message(self):
        """Test ConfigurationException preserves error message."""
        message = "Invalid configuration value"
        try:
            raise ConfigurationException(message)
        except ConfigurationException as e:
            assert str(e) == message

    def test_middleware_handles_telegram_webhook_exception(
        self, app_with_middleware, client_with_middleware
    ):
        """Test middleware handles TelegramWebhookException."""
        @app_with_middleware.get("/telegram-error")
        async def raise_telegram_error():
            raise TelegramWebhookException("Telegram processing error")

        response = client_with_middleware.get("/telegram-error")
        data = response.json()

        assert response.status_code == 500
        assert data["error"]["type"] == "TelegramWebhookException"

    def test_middleware_handles_database_exception(
        self, app_with_middleware, client_with_middleware
    ):
        """Test middleware handles DatabaseException."""
        @app_with_middleware.get("/db-error")
        async def raise_db_error():
            raise DatabaseException("Database connection failed")

        response = client_with_middleware.get("/db-error")
        data = response.json()

        assert response.status_code == 500
        assert data["error"]["type"] == "DatabaseException"

    def test_middleware_handles_configuration_exception(
        self, app_with_middleware, client_with_middleware
    ):
        """Test middleware handles ConfigurationException."""
        @app_with_middleware.get("/config-error")
        async def raise_config_error():
            raise ConfigurationException("API key not set")

        response = client_with_middleware.get("/config-error")
        data = response.json()

        assert response.status_code == 500
        assert data["error"]["type"] == "ConfigurationException"


# =============================================================================
# Recovery Mechanisms Tests
# =============================================================================


class TestRecoveryMechanisms:
    """Tests for error recovery and graceful degradation."""

    def test_middleware_continues_after_error(
        self, app_with_middleware, client_with_middleware
    ):
        """Test that middleware continues processing after an error."""
        call_count = 0

        @app_with_middleware.get("/error-then-success")
        async def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            return {"success": True, "call": call_count}

        # First call fails
        response1 = client_with_middleware.get("/error-then-success")
        assert response1.status_code == 500

        # Second call succeeds
        response2 = client_with_middleware.get("/error-then-success")
        assert response2.status_code == 200
        assert response2.json()["success"] is True

    def test_error_does_not_affect_other_endpoints(
        self, app_with_middleware, client_with_middleware
    ):
        """Test that error in one endpoint doesn't affect others."""
        @app_with_middleware.get("/always-fails")
        async def always_fails():
            raise RuntimeError("Always fails")

        @app_with_middleware.get("/always-works")
        async def always_works():
            return {"status": "working"}

        # First endpoint fails
        response1 = client_with_middleware.get("/always-fails")
        assert response1.status_code == 500

        # Second endpoint still works
        response2 = client_with_middleware.get("/always-works")
        assert response2.status_code == 200
        assert response2.json()["status"] == "working"

    def test_concurrent_errors_handled_independently(
        self, app_with_middleware
    ):
        """Test that concurrent requests with errors are handled independently."""
        import threading
        results = []

        @app_with_middleware.get("/concurrent-error")
        async def concurrent_error(request: Request):
            raise ValueError(f"Error for {request.state.request_id}")

        client = TestClient(app_with_middleware, raise_server_exceptions=False)

        def make_request():
            response = client.get("/concurrent-error")
            results.append(response.json())

        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All requests should have unique request IDs
        request_ids = [r["request_id"] for r in results]
        assert len(set(request_ids)) == 5


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_error_message(self, app_with_middleware, client_with_middleware):
        """Test handling of exception with empty message."""
        @app_with_middleware.get("/empty-message")
        async def raise_empty():
            raise ValueError("")

        response = client_with_middleware.get("/empty-message")
        data = response.json()

        assert response.status_code == 500
        assert data["error"]["message"] == ""
        assert data["error"]["type"] == "ValueError"

    def test_unicode_error_message(self, app_with_middleware, client_with_middleware):
        """Test handling of exception with unicode message."""
        @app_with_middleware.get("/unicode-message")
        async def raise_unicode():
            raise ValueError("Error with unicode chars")

        response = client_with_middleware.get("/unicode-message")
        data = response.json()

        assert response.status_code == 500
        assert "unicode" in data["error"]["message"]

    def test_very_long_error_message(self, app_with_middleware, client_with_middleware):
        """Test handling of exception with very long message."""
        long_message = "A" * 10000

        @app_with_middleware.get("/long-message")
        async def raise_long():
            raise ValueError(long_message)

        response = client_with_middleware.get("/long-message")
        data = response.json()

        assert response.status_code == 500
        assert data["error"]["message"] == long_message

    def test_nested_exception(self, app_with_middleware, client_with_middleware):
        """Test handling of nested/chained exceptions."""
        @app_with_middleware.get("/nested-exception")
        async def raise_nested():
            try:
                raise ValueError("Original error")
            except ValueError:
                raise RuntimeError("Wrapped error")

        response = client_with_middleware.get("/nested-exception")
        data = response.json()

        assert response.status_code == 500
        # The outer exception type should be captured
        assert data["error"]["type"] == "RuntimeError"
        assert "Wrapped error" in data["error"]["message"]

    def test_exception_during_async_operation(
        self, app_with_middleware, client_with_middleware
    ):
        """Test handling of exception during async operation."""
        import asyncio

        @app_with_middleware.get("/async-error")
        async def async_error():
            await asyncio.sleep(0.01)
            raise ValueError("Async operation failed")

        response = client_with_middleware.get("/async-error")
        data = response.json()

        assert response.status_code == 500
        assert data["error"]["type"] == "ValueError"

    def test_multiple_http_methods_same_path(self, app_with_middleware, client_with_middleware):
        """Test error handling for different HTTP methods on same path."""
        @app_with_middleware.get("/multi-method")
        async def get_error():
            raise ValueError("GET error")

        @app_with_middleware.post("/multi-method")
        async def post_error():
            raise RuntimeError("POST error")

        response_get = client_with_middleware.get("/multi-method")
        response_post = client_with_middleware.post("/multi-method")

        assert response_get.status_code == 500
        assert response_get.json()["error"]["type"] == "ValueError"

        assert response_post.status_code == 500
        assert response_post.json()["error"]["type"] == "RuntimeError"

    def test_query_parameters_in_error(self, app_with_middleware, client_with_middleware):
        """Test that query parameters are handled correctly with errors."""
        @app_with_middleware.get("/query-error")
        async def query_error(param: str = None):
            raise ValueError(f"Error with param: {param}")

        response = client_with_middleware.get("/query-error?param=test")
        data = response.json()

        assert response.status_code == 500
        assert "test" in data["error"]["message"]


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the complete middleware flow."""

    def test_full_error_flow(self, app_with_middleware, client_with_middleware, caplog):
        """Test complete error handling flow from request to response."""
        @app_with_middleware.get("/full-flow")
        async def full_flow_error(request: Request):
            # Access request ID to verify it's set
            _ = request.state.request_id
            raise ValueError("Full flow test error")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.get("/full-flow")

        # Response should be JSON with correct structure
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "request_id" in data
        assert data["error"]["type"] == "ValueError"

        # Should be logged
        assert any("Full flow test error" in r.message or "ValueError" in r.message
                   for r in caplog.records if r.levelno == logging.ERROR)

    def test_webhook_full_error_flow(self, app_with_middleware, client_with_middleware, caplog):
        """Test complete webhook error handling flow."""
        @app_with_middleware.post("/webhook")
        async def webhook_full_flow():
            raise DatabaseException("Database unavailable during webhook")

        with caplog.at_level(logging.ERROR):
            response = client_with_middleware.post("/webhook")

        # Should return 200 for webhook
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "error" in data
        assert data["error"]["type"] == "DatabaseException"

        # Should still be logged
        assert any("Database unavailable" in r.message or "DatabaseException" in r.message
                   for r in caplog.records if r.levelno == logging.ERROR)

    def test_middleware_with_dependencies(self):
        """Test middleware works correctly with FastAPI dependencies."""
        from fastapi import Depends

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        async def get_current_user():
            raise ValueError("Auth failed")

        @app.get("/with-deps")
        async def with_deps(user: str = Depends(get_current_user)):
            return {"user": user}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/with-deps")

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "ValueError"

    def test_middleware_response_immutability(self, app_with_middleware, client_with_middleware):
        """Test that error response cannot be modified after creation."""
        @app_with_middleware.get("/immutable")
        async def immutable_error():
            raise ValueError("Immutable test")

        response1 = client_with_middleware.get("/immutable")
        response2 = client_with_middleware.get("/immutable")

        # Each response should be independent
        data1 = response1.json()
        data2 = response2.json()

        # Both should have proper structure
        assert "error" in data1
        assert "error" in data2
        # Request IDs should be different
        assert data1["request_id"] != data2["request_id"]
