"""
Tests for the /api/metrics endpoint.

Tests cover:
- Returns 200 with valid auth
- Returns 401 without auth
- Contains expected counter fields
- Counters increment correctly
"""

import hashlib
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.metrics import MetricsCollector, create_metrics_router

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def collector():
    """Create a fresh MetricsCollector."""
    return MetricsCollector()


@pytest.fixture
def metrics_app():
    """Create a minimal FastAPI app with the metrics endpoint."""
    app = FastAPI()
    router = create_metrics_router()
    app.include_router(router)
    return app


@pytest.fixture
def api_key():
    """Compute the expected admin API key from the current env var.

    The conftest sets TELEGRAM_WEBHOOK_SECRET=test-secret but load_dotenv
    in project modules may override it, so we read the actual env value.
    """
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    return hashlib.sha256(f"{secret}:admin_api".encode()).hexdigest()


@pytest.fixture
def client(metrics_app):
    """Create a test client."""
    return TestClient(metrics_app)


# =============================================================================
# MetricsCollector Unit Tests
# =============================================================================


class TestMetricsCollector:
    """Tests for MetricsCollector in-memory counters."""

    def test_initial_request_count_is_zero(self, collector):
        """Test that request count starts at 0."""
        assert collector.request_count == 0

    def test_initial_error_count_is_zero(self, collector):
        """Test that error count starts at 0."""
        assert collector.error_count == 0

    def test_increment_request_count(self, collector):
        """Test incrementing request count."""
        collector.record_request()
        collector.record_request()
        collector.record_request()
        assert collector.request_count == 3

    def test_increment_error_count(self, collector):
        """Test incrementing error count."""
        collector.record_error()
        collector.record_error()
        assert collector.error_count == 2

    def test_record_latency(self, collector):
        """Test recording webhook latency."""
        collector.record_webhook_latency(0.1)
        collector.record_webhook_latency(0.5)
        collector.record_webhook_latency(0.2)
        assert len(collector._latencies) == 3

    def test_latency_percentiles(self, collector):
        """Test latency percentile calculation."""
        # Add 100 samples: 0.01, 0.02, ..., 1.00
        for i in range(1, 101):
            collector.record_webhook_latency(i / 100.0)

        percentiles = collector.get_latency_percentiles()
        assert "p50" in percentiles
        assert "p95" in percentiles
        assert "p99" in percentiles

        # p50 should be around 0.50
        assert 0.45 <= percentiles["p50"] <= 0.55
        # p95 should be around 0.95
        assert 0.90 <= percentiles["p95"] <= 1.00
        # p99 should be around 0.99
        assert 0.95 <= percentiles["p99"] <= 1.00

    def test_latency_percentiles_empty(self, collector):
        """Test latency percentiles when no data."""
        percentiles = collector.get_latency_percentiles()
        assert percentiles["p50"] == 0
        assert percentiles["p95"] == 0
        assert percentiles["p99"] == 0

    def test_get_snapshot(self, collector):
        """Test getting a full metrics snapshot."""
        collector.record_request()
        collector.record_request()
        collector.record_error()
        collector.record_webhook_latency(0.123)

        snapshot = collector.get_snapshot()

        assert snapshot["request_count"] == 2
        assert snapshot["error_count"] == 1
        assert "uptime_seconds" in snapshot
        assert "webhook_latency" in snapshot
        assert "active_tasks" in snapshot

    def test_uptime_in_snapshot(self, collector):
        """Test that uptime is present and positive in snapshot."""
        snapshot = collector.get_snapshot()
        assert snapshot["uptime_seconds"] >= 0

    def test_latency_ring_buffer_limit(self, collector):
        """Test that latency buffer doesn't grow unbounded."""
        for i in range(20000):
            collector.record_webhook_latency(0.1)
        # Should be capped at max size (10000)
        assert len(collector._latencies) <= 10000


# =============================================================================
# Metrics Endpoint Auth Tests
# =============================================================================


class TestMetricsEndpointAuth:
    """Tests for /api/metrics endpoint authentication."""

    def test_returns_401_without_api_key(self, client):
        """Test that /api/metrics returns 401 without API key."""
        response = client.get("/api/metrics")
        assert response.status_code == 401

    def test_returns_401_with_wrong_key(self, client):
        """Test that /api/metrics returns 401 with wrong API key."""
        response = client.get("/api/metrics", headers={"X-Api-Key": "wrong-key"})
        assert response.status_code == 401

    def test_returns_200_with_valid_key(self, client, api_key):
        """Test that /api/metrics returns 200 with valid API key."""
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        assert response.status_code == 200


# =============================================================================
# Metrics Endpoint Response Tests
# =============================================================================


class TestMetricsEndpointResponse:
    """Tests for /api/metrics endpoint response shape."""

    def test_contains_request_count(self, client, api_key):
        """Test that response contains request_count."""
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        data = response.json()
        assert "request_count" in data

    def test_contains_error_count(self, client, api_key):
        """Test that response contains error_count."""
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        data = response.json()
        assert "error_count" in data

    def test_contains_uptime(self, client, api_key):
        """Test that response contains uptime_seconds."""
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        data = response.json()
        assert "uptime_seconds" in data

    def test_contains_active_tasks(self, client, api_key):
        """Test that response contains active_tasks."""
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        data = response.json()
        assert "active_tasks" in data

    def test_contains_webhook_latency(self, client, api_key):
        """Test that response contains webhook_latency histogram."""
        response = client.get("/api/metrics", headers={"X-Api-Key": api_key})
        data = response.json()
        assert "webhook_latency" in data
        latency = data["webhook_latency"]
        assert "p50" in latency
        assert "p95" in latency
        assert "p99" in latency
