"""Tests that API error responses do not expose internal exception details.

Issue #213: HTTPException details included str(e), leaking internal info.
"""

import hashlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment before importing app
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test_webhook_secret_12345"
os.environ["TELEGRAM_BOT_TOKEN"] = "test:bot_token"


def get_test_admin_api_key() -> str:
    """Generate the expected admin API key for tests (legacy derivation)."""
    secret = os.environ["TELEGRAM_WEBHOOK_SECRET"]
    return hashlib.sha256(f"{secret}:admin_api".encode()).hexdigest()


# A distinctive string that should never appear in HTTP responses
SECRET_EXCEPTION_MSG = "SUPER_SECRET_DB_PASSWORD_leak_1234"


class TestWebhookErrorSanitization:
    """Webhook management endpoints must not expose exception details."""

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
    def admin_headers(self):
        """Return headers with valid admin API key."""
        return {"X-Api-Key": get_test_admin_api_key()}

    # -- /admin/webhook/update (500 path) --

    def test_update_webhook_500_hides_exception(self, client, admin_headers):
        """POST /admin/webhook/update: 500 must not contain exception text."""
        with patch("src.api.webhook.WebhookManager") as mock_wm:
            mock_wm.side_effect = RuntimeError(SECRET_EXCEPTION_MSG)

            response = client.post(
                "/admin/webhook/update",
                headers=admin_headers,
                json={"url": "https://example.com/webhook"},
            )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert SECRET_EXCEPTION_MSG not in detail

    # -- /admin/webhook/refresh (500 path) --

    def test_refresh_webhook_500_hides_exception(self, client, admin_headers):
        """POST /admin/webhook/refresh: 500 must not contain exception text."""
        with patch(
            "src.api.webhook.auto_update_webhook_on_restart",
            new_callable=AsyncMock,
        ) as mock_auto:
            mock_auto.side_effect = RuntimeError(SECRET_EXCEPTION_MSG)

            response = client.post(
                "/admin/webhook/refresh",
                headers=admin_headers,
                json={"port": 8000, "webhook_path": "/webhook"},
            )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert SECRET_EXCEPTION_MSG not in detail

    # -- /admin/webhook/status (500 path) --

    def test_get_status_500_hides_exception(self, client, admin_headers):
        """GET /admin/webhook/status: 500 must not contain exception text."""
        with patch("src.api.webhook.WebhookManager") as mock_wm:
            mock_wm.side_effect = RuntimeError(SECRET_EXCEPTION_MSG)

            response = client.get(
                "/admin/webhook/status",
                headers=admin_headers,
            )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert SECRET_EXCEPTION_MSG not in detail

    # -- /admin/webhook/ DELETE (500 path) --

    def test_delete_webhook_500_hides_exception(self, client, admin_headers):
        """DELETE /admin/webhook/: 500 must not contain exception text."""
        with patch("src.api.webhook.WebhookManager") as mock_wm:
            mock_wm.side_effect = RuntimeError(SECRET_EXCEPTION_MSG)

            response = client.delete(
                "/admin/webhook/",
                headers=admin_headers,
            )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert SECRET_EXCEPTION_MSG not in detail


class TestNgrokErrorSanitization:
    """Ngrok endpoints must not expose exception details."""

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
    def admin_headers(self):
        """Return headers with valid admin API key."""
        return {"X-Api-Key": get_test_admin_api_key()}

    # -- /admin/webhook/ngrok/start (500 path) --

    def test_ngrok_start_500_hides_exception(self, client, admin_headers):
        """POST /admin/webhook/ngrok/start: 500 must not expose exception."""
        with patch("src.api.webhook.NgrokManager") as mock_ng:
            mock_ng.side_effect = RuntimeError(SECRET_EXCEPTION_MSG)

            response = client.post(
                "/admin/webhook/ngrok/start",
                headers=admin_headers,
            )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert SECRET_EXCEPTION_MSG not in detail

    # -- /admin/webhook/ngrok/stop (500 path) --

    def test_ngrok_stop_500_hides_exception(self, client, admin_headers):
        """POST /admin/webhook/ngrok/stop: 500 must not expose exception."""
        with patch("src.api.webhook.NgrokManager") as mock_ng:
            mock_ng.side_effect = RuntimeError(SECRET_EXCEPTION_MSG)

            response = client.post(
                "/admin/webhook/ngrok/stop",
                headers=admin_headers,
            )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert SECRET_EXCEPTION_MSG not in detail

    # -- /admin/webhook/ngrok/tunnels (500 path) --

    def test_ngrok_tunnels_500_hides_exception(self, client, admin_headers):
        """GET /admin/webhook/ngrok/tunnels: 500 must not expose exception."""
        with patch(
            "src.api.webhook.NgrokManager.get_ngrok_api_tunnels",
            new_callable=AsyncMock,
        ) as mock_tunnels:
            mock_tunnels.side_effect = RuntimeError(SECRET_EXCEPTION_MSG)

            response = client.get(
                "/admin/webhook/ngrok/tunnels",
                headers=admin_headers,
            )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert SECRET_EXCEPTION_MSG not in detail
