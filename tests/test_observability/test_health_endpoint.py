"""
Tests for the enhanced /health endpoint.

Tests cover:
- Returns 200 with expected fields
- Uptime included
- Version included
- Database connectivity status
- Bot status
"""

import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def health_app():
    """Create a minimal FastAPI app with the health endpoint."""
    from src.api.health import create_health_router, set_start_time

    app = FastAPI()
    # Set start time so uptime is computable
    set_start_time()
    router = create_health_router()
    app.include_router(router)
    return app


@pytest.fixture
def client(health_app):
    """Create a test client."""
    return TestClient(health_app)


# =============================================================================
# Basic Health Endpoint Tests
# =============================================================================


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_returns_200(self, client):
        """Test that /health returns 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_contains_status_field(self, client):
        """Test that response contains status field."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data

    def test_contains_uptime_field(self, client):
        """Test that response contains uptime_seconds field."""
        response = client.get("/health")
        data = response.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0

    def test_contains_version_field(self, client):
        """Test that response contains version field."""
        response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_contains_service_field(self, client):
        """Test that response contains service name."""
        response = client.get("/health")
        data = response.json()
        assert "service" in data
        assert data["service"] == "telegram-agent"

    def test_contains_database_field(self, client):
        """Test that response contains database status field."""
        response = client.get("/health")
        data = response.json()
        assert "database" in data

    def test_contains_bot_status_field(self, client):
        """Test that response contains bot_initialized field."""
        response = client.get("/health")
        data = response.json()
        assert "bot_initialized" in data

    def test_uptime_increases(self, client):
        """Test that uptime increases between requests."""
        resp1 = client.get("/health")
        time.sleep(0.1)
        resp2 = client.get("/health")
        uptime1 = resp1.json()["uptime_seconds"]
        uptime2 = resp2.json()["uptime_seconds"]
        assert uptime2 >= uptime1

    @patch("src.api.health.check_database_health")
    def test_database_connected(self, mock_db_check, client):
        """Test that database status is 'connected' when healthy."""
        mock_db_check.return_value = True
        response = client.get("/health")
        data = response.json()
        assert data["database"] == "connected"

    @patch("src.api.health.check_database_health")
    def test_database_disconnected(self, mock_db_check, client):
        """Test that database status is 'disconnected' when unhealthy."""
        mock_db_check.return_value = False
        response = client.get("/health")
        data = response.json()
        assert data["database"] == "disconnected"

    @patch("src.api.health.check_database_health")
    def test_degraded_status_on_db_failure(self, mock_db_check, client):
        """Test that status is 'degraded' when database check fails."""
        mock_db_check.return_value = False
        response = client.get("/health")
        data = response.json()
        assert data["status"] in ("degraded", "error")
