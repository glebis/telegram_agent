"""
Characterization tests for health and root endpoints.

These tests verify behavior is preserved when endpoints are extracted
from main.py into src/api/health.py (issue #152).
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked bot lifecycle."""
    with (
        patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": ""}),
        patch("src.lifecycle.validate_config", return_value=[]),
        patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
        patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
        patch("src.lifecycle.init_database", new_callable=AsyncMock),
        patch("src.lifecycle.close_database", new_callable=AsyncMock),
        patch("src.lifecycle.setup_services"),
        patch("src.lifecycle.get_plugin_manager") as mock_pm,
        patch("src.api.webhook_handler.get_bot") as mock_get_bot,
        patch("src.lifecycle.create_tracked_task") as mock_task,
        patch(
            "src.utils.ngrok_utils.check_and_recover_webhook",
            new_callable=AsyncMock,
        ),
        patch(
            "src.utils.ngrok_utils.run_periodic_webhook_check",
            new_callable=AsyncMock,
        ),
        patch("src.utils.cleanup.run_periodic_cleanup", new_callable=AsyncMock),
    ):
        mock_pm_instance = MagicMock()
        mock_pm_instance.load_plugins = AsyncMock(return_value={})
        mock_pm_instance.activate_plugins = AsyncMock()
        mock_pm_instance.shutdown = AsyncMock()
        mock_pm.return_value = mock_pm_instance

        mock_bot = MagicMock()
        mock_bot.process_update = AsyncMock(return_value=True)
        mock_get_bot.return_value = mock_bot

        def close_coro(coro, name=None):
            coro.close()
            return None

        mock_task.side_effect = close_coro

        from src.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestRootEndpoint:
    """Tests for GET / endpoint."""

    def test_root_returns_200(self, client):
        """Root endpoint should return 200."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_status(self, client):
        """Root endpoint should include status field."""
        response = client.get("/")
        data = response.json()
        assert data["status"] == "running"

    def test_root_returns_message(self, client):
        """Root endpoint should include message."""
        response = client.get("/")
        data = response.json()
        assert "message" in data


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_200_without_auth(self, client):
        """Health endpoint returns basic info without auth."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_status_field(self, client):
        """Health response always includes status field."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data

    def test_health_returns_service_name(self, client):
        """Health response includes service name."""
        response = client.get("/health")
        data = response.json()
        assert data["service"] == "telegram-agent"

    def test_health_no_details_without_auth(self, client):
        """Without auth, health should not include detailed stats."""
        response = client.get("/health")
        data = response.json()
        # Detailed fields should NOT be present without auth
        assert "telegram" not in data
        assert "stats" not in data
