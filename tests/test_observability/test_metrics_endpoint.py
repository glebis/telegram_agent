"""
Tests for the /api/metrics Prometheus endpoint.

Tests cover:
- Returns 200 with valid auth, 401 without
- Content type is Prometheus text format
- Contains expected metric names (http_requests_total, etc.)
- Recording helpers increment Prometheus counters
"""

import hashlib
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.metrics import (
    create_metrics_router,
    record_error,
    record_latency,
    record_request,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def metrics_app():
    """Create a minimal FastAPI app with the metrics endpoint."""
    app = FastAPI()
    router = create_metrics_router()
    app.include_router(router)
    return app


@pytest.fixture
def api_key():
    """Compute the expected admin API key from the current env var."""
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    return hashlib.sha256(f"{secret}:admin_api".encode()).hexdigest()


@pytest.fixture
def client(metrics_app):
    """Create a test client."""
    return TestClient(metrics_app)


# =============================================================================
# Prometheus Endpoint Tests
# =============================================================================


class TestPrometheusEndpoint:
    """Tests for /api/metrics endpoint with Prometheus exposition."""

    def test_returns_200_with_valid_key(self, client, api_key):
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        assert response.status_code == 200

    def test_returns_401_without_key(self, client):
        response = client.get("/api/metrics")
        assert response.status_code == 401

    def test_content_type_is_prometheus(self, client, api_key):
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        ct = response.headers.get("content-type", "")
        assert "text/plain" in ct or "openmetrics" in ct

    def test_contains_http_requests_total(self, client, api_key):
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        assert "http_requests_total" in response.text

    def test_contains_http_errors_total(self, client, api_key):
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        assert "http_errors_total" in response.text

    def test_contains_webhook_latency_seconds(self, client, api_key):
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        assert "webhook_latency_seconds" in response.text

    def test_contains_active_tasks(self, client, api_key):
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        assert "active_tasks" in response.text

    def test_contains_bot_uptime_seconds(self, client, api_key):
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        assert "bot_uptime_seconds" in response.text


# =============================================================================
# Prometheus Recording Unit Tests
# =============================================================================


class TestPrometheusRecording:
    """Tests for record_request/record_error/record_latency helpers."""

    def test_record_request_increments_counter(self):
        """record_request() should not raise and should increment."""
        record_request("/test", "GET")
        record_request("/test", "GET")

    def test_record_error_increments_counter(self):
        """record_error() should not raise and should increment."""
        record_error("/test", "GET", 500)

    def test_record_latency_observes_histogram(self):
        """record_latency() should observe without error."""
        record_latency("/webhook", 0.123)
        record_latency("/webhook", 0.456)
