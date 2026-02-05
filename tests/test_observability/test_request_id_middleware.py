"""
Tests for request ID middleware.

Tests cover:
- UUID request_id generation per request
- RequestContext contextvar propagation
- X-Request-ID response header
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.request_id import RequestIdMiddleware
from src.utils.logging import RequestContext

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app_with_middleware():
    """Create a FastAPI app with RequestIdMiddleware."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/test")
    async def test_endpoint():
        ctx = RequestContext.get()
        return {
            "request_id": ctx["request_id"],
            "chat_id": ctx["chat_id"],
            "task_id": ctx["task_id"],
        }

    return app


@pytest.fixture
def client(app_with_middleware):
    """Create a test client for the app."""
    return TestClient(app_with_middleware)


# =============================================================================
# Request ID Generation Tests
# =============================================================================


class TestRequestIdGeneration:
    """Tests for request ID generation."""

    def test_response_has_x_request_id_header(self, client):
        """Test that response includes X-Request-ID header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_request_id_is_uuid_format(self, client):
        """Test that request ID looks like a UUID."""
        response = client.get("/test")
        request_id = response.headers["X-Request-ID"]
        # UUID has 5 groups separated by hyphens: 8-4-4-4-12
        parts = request_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_unique_request_ids(self, client):
        """Test that each request gets a unique ID."""
        ids = set()
        for _ in range(10):
            response = client.get("/test")
            ids.add(response.headers["X-Request-ID"])
        assert len(ids) == 10

    def test_provided_request_id_is_used(self, client):
        """Test that a provided X-Request-ID header is used."""
        response = client.get("/test", headers={"X-Request-ID": "custom-req-id-12345"})
        assert response.headers["X-Request-ID"] == "custom-req-id-12345"


# =============================================================================
# Context Propagation Tests
# =============================================================================


class TestContextPropagation:
    """Tests for RequestContext propagation within request."""

    def test_request_id_in_context(self, client):
        """Test that request_id is available in RequestContext during request."""
        response = client.get("/test")
        data = response.json()
        # The request_id in the context should match the header
        assert data["request_id"] == response.headers["X-Request-ID"]

    def test_context_cleared_after_request(self, client):
        """Test that context is cleared after request completes."""
        client.get("/test")
        # After request, context should be clear
        ctx = RequestContext.get()
        assert ctx["request_id"] is None
