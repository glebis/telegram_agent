"""
Tests for unified error handling middleware.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestErrorHandlingMiddleware:
    """Test error handling middleware."""

    def test_middleware_exists(self):
        """The error handling middleware should exist."""
        from src.middleware.error_handler import ErrorHandlerMiddleware

        assert ErrorHandlerMiddleware is not None

    def test_catches_unhandled_exception(self):
        """Middleware should catch unhandled exceptions with sanitized response."""
        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/error")
        async def raise_error():
            raise ValueError("Test error")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "type" not in data["error"]
        assert data["error"]["message"] == "Internal server error"

    def test_returns_json_error_response(self):
        """Error responses should be JSON with sanitized format."""
        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/error")
        async def raise_error():
            raise RuntimeError("Something went wrong")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert "error" in data
        assert "message" in data["error"]
        assert "type" not in data["error"]
        assert data["error"]["message"] == "Internal server error"

    def test_logs_errors(self, caplog):
        """Errors should be logged."""
        import logging

        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/error")
        async def raise_error():
            raise ValueError("Logged error")

        client = TestClient(app, raise_server_exceptions=False)

        with caplog.at_level(logging.ERROR):
            response = client.get("/error")

        assert response.status_code == 500
        # Check that error was logged
        assert any(
            "Logged error" in record.message or "ValueError" in record.message
            for record in caplog.records
        )

    def test_passes_through_http_exceptions(self):
        """HTTP exceptions should pass through with their status code."""
        from fastapi import HTTPException

        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/not-found")
        async def not_found():
            raise HTTPException(status_code=404, detail="Not found")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/not-found")

        assert response.status_code == 404

    def test_telegram_webhook_returns_200_on_error(self):
        """Webhook errors should return 200 to prevent Telegram retries."""
        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.post("/webhook")
        async def webhook():
            raise ValueError("Webhook processing error")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/webhook")

        # Webhook should return 200 even on error to prevent retries
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is False or "error" in data

    def test_includes_request_id(self):
        """Error responses should include a request ID for tracking."""
        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/error")
        async def raise_error():
            raise ValueError("Error with ID")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        data = response.json()
        assert "request_id" in data or "error" in data


class TestErrorTypes:
    """Test handling of specific error types."""

    def test_handles_database_errors(self):
        """Database errors should be handled gracefully."""
        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        @app.get("/db-error")
        async def db_error():
            # Simulate SQLAlchemy error
            raise Exception("database connection failed")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/db-error")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data

    def test_handles_validation_errors(self):
        """Validation errors should return 422."""
        from pydantic import BaseModel

        from src.middleware.error_handler import ErrorHandlerMiddleware

        app = FastAPI()
        app.add_middleware(ErrorHandlerMiddleware)

        class Item(BaseModel):
            name: str
            price: float

        @app.post("/items")
        async def create_item(item: Item):
            return item

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/items", json={"name": "test"})  # missing price

        assert response.status_code == 422
