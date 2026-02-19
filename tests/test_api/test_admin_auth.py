"""Tests for admin endpoint authentication."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment before importing app
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test_webhook_secret_12345"
os.environ["TELEGRAM_BOT_TOKEN"] = "test:bot_token"


def get_test_admin_api_key() -> str:
    """Generate the expected admin API key for tests.

    Uses the centralized derive_api_key() so the test key always matches
    the application's derivation logic (HMAC or legacy fallback).
    """
    from src.core.security import derive_api_key

    return derive_api_key("admin_api")


class TestWebhookAdminAuth:
    """Test webhook admin endpoint authentication."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        # Mock the bot initialization and database
        with (
            patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
            patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
            patch("src.lifecycle.init_database", new_callable=AsyncMock),
            patch("src.lifecycle.close_database", new_callable=AsyncMock),
            patch("src.lifecycle.setup_services"),
            patch("src.lifecycle.get_plugin_manager") as mock_pm,
            patch("src.main.get_bot") as mock_get_bot,
        ):

            # Configure plugin manager mock
            mock_pm_instance = MagicMock()
            mock_pm_instance.load_plugins = AsyncMock(return_value={})
            mock_pm_instance.activate_plugins = AsyncMock()
            mock_pm_instance.shutdown = AsyncMock()
            mock_pm.return_value = mock_pm_instance

            # Configure bot mock
            mock_bot = MagicMock()
            mock_bot.application = MagicMock()
            mock_get_bot.return_value = mock_bot

            from fastapi.testclient import TestClient

            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.fixture
    def admin_api_key(self):
        """Get valid admin API key for tests."""
        return get_test_admin_api_key()

    def test_webhook_status_no_auth_returns_401(self, client):
        """Endpoints require X-Api-Key header."""
        response = client.get("/admin/webhook/status")
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json().get("detail", "")

    def test_webhook_status_invalid_key_returns_401(self, client):
        """Invalid API key is rejected."""
        response = client.get(
            "/admin/webhook/status", headers={"X-Api-Key": "invalid_key_12345"}
        )
        assert response.status_code == 401

    def test_webhook_status_valid_key_returns_200(self, client, admin_api_key):
        """Valid API key grants access."""
        with (
            patch("src.api.webhook.WebhookManager") as mock_wm,
            patch("src.api.webhook.NgrokManager") as mock_ngrok,
        ):
            # Mock webhook manager
            mock_wm_instance = MagicMock()
            mock_wm_instance.get_webhook_info = AsyncMock(
                return_value={"url": "https://test.com"}
            )
            mock_wm.return_value = mock_wm_instance

            # Mock ngrok manager
            mock_ngrok_instance = MagicMock()
            mock_ngrok_instance.get_tunnel_status.return_value = {"active": True}
            mock_ngrok.return_value = mock_ngrok_instance

            response = client.get(
                "/admin/webhook/status", headers={"X-Api-Key": admin_api_key}
            )
            assert response.status_code == 200

    def test_ngrok_start_no_auth_returns_401(self, client):
        """ngrok endpoints require authentication."""
        response = client.post("/admin/webhook/ngrok/start")
        assert response.status_code == 401

    def test_ngrok_stop_no_auth_returns_401(self, client):
        """ngrok stop endpoint requires authentication."""
        response = client.post("/admin/webhook/ngrok/stop")
        assert response.status_code == 401

    def test_ngrok_tunnels_no_auth_returns_401(self, client):
        """ngrok tunnels endpoint requires authentication."""
        response = client.get("/admin/webhook/ngrok/tunnels")
        assert response.status_code == 401


class TestCleanupAuth:
    """Test cleanup endpoint authentication."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        with (
            patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
            patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
            patch("src.lifecycle.init_database", new_callable=AsyncMock),
            patch("src.lifecycle.close_database", new_callable=AsyncMock),
            patch("src.lifecycle.setup_services"),
            patch("src.lifecycle.get_plugin_manager") as mock_pm,
            patch("src.main.get_bot") as mock_get_bot,
        ):

            mock_pm_instance = MagicMock()
            mock_pm_instance.load_plugins = AsyncMock(return_value={})
            mock_pm_instance.activate_plugins = AsyncMock()
            mock_pm_instance.shutdown = AsyncMock()
            mock_pm.return_value = mock_pm_instance

            mock_bot = MagicMock()
            mock_bot.application = MagicMock()
            mock_get_bot.return_value = mock_bot

            from fastapi.testclient import TestClient

            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.fixture
    def admin_api_key(self):
        """Get valid admin API key for tests."""
        return get_test_admin_api_key()

    def test_cleanup_no_auth_returns_401(self, client):
        """Cleanup endpoint requires authentication."""
        response = client.post("/cleanup")
        assert response.status_code == 401

    def test_cleanup_invalid_key_returns_401(self, client):
        """Invalid API key is rejected."""
        response = client.post("/cleanup", headers={"X-Api-Key": "wrong_key"})
        assert response.status_code == 401

    def test_cleanup_valid_key_returns_200(self, client, admin_api_key):
        """Valid API key grants access to cleanup."""
        with patch("src.main.cleanup_all_temp_files") as mock_cleanup:
            mock_cleanup.return_value = {"deleted": 0, "errors": []}

            response = client.post(
                "/cleanup?dry_run=true", headers={"X-Api-Key": admin_api_key}
            )
            assert response.status_code == 200


class TestHealthEndpoint:
    """Test health endpoint auth behavior."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        with (
            patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
            patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
            patch("src.lifecycle.init_database", new_callable=AsyncMock),
            patch("src.lifecycle.close_database", new_callable=AsyncMock),
            patch("src.lifecycle.setup_services"),
            patch("src.lifecycle.get_plugin_manager") as mock_pm,
            patch("src.main.get_bot") as mock_get_bot,
        ):

            mock_pm_instance = MagicMock()
            mock_pm_instance.load_plugins = AsyncMock(return_value={})
            mock_pm_instance.activate_plugins = AsyncMock()
            mock_pm_instance.shutdown = AsyncMock()
            mock_pm.return_value = mock_pm_instance

            mock_bot = MagicMock()
            mock_bot.application = MagicMock()
            mock_get_bot.return_value = mock_bot

            from fastapi.testclient import TestClient

            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.fixture
    def admin_api_key(self):
        """Get valid admin API key for tests."""
        return get_test_admin_api_key()

    def test_health_no_auth_returns_basic(self, client):
        """Without auth, only basic health info returned."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        # Should NOT have detailed info
        assert "database" not in data or data.get("database") is None
        assert "telegram" not in data
        assert "stats" not in data

    def test_health_invalid_key_returns_basic(self, client):
        """Invalid auth gracefully falls back to basic info."""
        response = client.get("/health", headers={"X-Api-Key": "invalid_key"})
        assert response.status_code == 200
        data = response.json()
        # Should still return basic info, not 401
        assert "status" in data
        assert "telegram" not in data

    def test_health_with_auth_returns_details(self, client, admin_api_key):
        """With valid auth, full details returned."""
        with (
            patch("src.core.database.health_check", new_callable=AsyncMock) as mock_hc,
            patch(
                "src.core.database.get_user_count", new_callable=AsyncMock
            ) as mock_uc,
            patch(
                "src.core.database.get_chat_count", new_callable=AsyncMock
            ) as mock_cc,
            patch(
                "src.core.database.get_image_count", new_callable=AsyncMock
            ) as mock_ic,
            patch(
                "src.core.database.get_embedding_stats", new_callable=AsyncMock
            ) as mock_es,
            patch("src.core.database.get_database_url") as mock_db_url,
        ):

            mock_hc.return_value = True
            mock_uc.return_value = 10
            mock_cc.return_value = 5
            mock_ic.return_value = 100
            mock_es.return_value = {"total": 50}
            mock_db_url.return_value = "sqlite:///test.db"

            response = client.get("/health", headers={"X-Api-Key": admin_api_key})
            assert response.status_code == 200
            data = response.json()
            # With auth, should have detailed info
            assert "database" in data
            assert "telegram" in data
            assert "stats" in data
