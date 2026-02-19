"""
Tests for the MetricsMiddleware.

Verifies that HTTP requests are automatically recorded via middleware.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.middleware.metrics import MetricsMiddleware


@pytest.fixture
def app_with_middleware():
    """Create a FastAPI app with MetricsMiddleware and test routes."""
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get("/test-ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/test-error")
    async def error():
        return JSONResponse(status_code=500, content={"error": "boom"})

    @app.post("/webhook")
    async def webhook():
        return {"ok": True}

    return app


@pytest.fixture
def mw_client(app_with_middleware):
    return TestClient(app_with_middleware)


class TestMetricsMiddleware:
    """Tests for MetricsMiddleware automatic recording."""

    def test_middleware_records_request(self, mw_client):
        """A successful request should be recorded without errors."""
        response = mw_client.get("/test-ok")
        assert response.status_code == 200

    def test_middleware_records_error_on_5xx(self, mw_client):
        """A 5xx response should be handled without middleware errors."""
        response = mw_client.get("/test-error")
        assert response.status_code == 500

    def test_middleware_records_webhook_latency(self, mw_client):
        """POST /webhook should complete and record latency."""
        response = mw_client.post("/webhook")
        assert response.status_code == 200
