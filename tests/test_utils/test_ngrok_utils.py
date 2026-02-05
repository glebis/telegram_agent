"""
Tests for ngrok utilities.

Tests cover:
- NgrokManager: Tunnel management, URL retrieval, configuration
- WebhookManager: Webhook operations (set, get, delete)
- Helper functions: setup_ngrok_webhook, auto_update_webhook_on_restart, etc.
- Error handling and edge cases
"""

import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pyngrok.exception import PyngrokNgrokError

from src.utils.ngrok_utils import (
    NgrokManager,
    WebhookManager,
    auto_update_webhook_on_restart,
    check_and_recover_webhook,
    run_periodic_webhook_check,
    setup_ngrok_webhook,
    setup_production_webhook,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def ngrok_manager():
    """Create an NgrokManager instance for testing."""
    return NgrokManager(
        auth_token="test_token",
        port=8000,
        region="us",
        tunnel_name="test-tunnel",
    )


@pytest.fixture
def webhook_manager():
    """Create a WebhookManager instance for testing."""
    return WebhookManager(bot_token="test:bot_token")


@pytest.fixture
def mock_tunnel():
    """Create a mock ngrok tunnel object."""
    tunnel = Mock()
    tunnel.public_url = "https://abc123.ngrok.io"
    tunnel.name = "test-tunnel"
    tunnel.config = {"addr": "http://localhost:8000"}
    return tunnel


@pytest.fixture(autouse=True)
def reset_env_vars():
    """Reset environment variables before each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


# =============================================================================
# NgrokManager Tests
# =============================================================================


class TestNgrokManagerInit:
    """Tests for NgrokManager initialization."""

    def test_default_initialization(self):
        """Test NgrokManager with default values."""
        manager = NgrokManager()

        assert manager.auth_token is None
        assert manager.port == 8000
        assert manager.region == "us"
        assert manager.tunnel_name == "telegram-agent"
        assert manager.tunnel is None
        assert manager._config is None

    def test_custom_initialization(self):
        """Test NgrokManager with custom values."""
        manager = NgrokManager(
            auth_token="custom_token",
            port=9000,
            region="eu",
            tunnel_name="custom-tunnel",
        )

        assert manager.auth_token == "custom_token"
        assert manager.port == 9000
        assert manager.region == "eu"
        assert manager.tunnel_name == "custom-tunnel"


class TestNgrokManagerConfig:
    """Tests for NgrokManager configuration."""

    def test_get_config_creates_config(self, ngrok_manager):
        """Test that _get_config creates a PyngrokConfig."""
        with patch("src.utils.ngrok_utils.PyngrokConfig") as mock_config_class:
            mock_config_class.return_value = Mock()

            config = ngrok_manager._get_config()

            mock_config_class.assert_called_once_with(
                auth_token="test_token",
                region="us",
            )
            assert config is not None

    def test_get_config_returns_cached_config(self, ngrok_manager):
        """Test that _get_config returns cached config on subsequent calls."""
        with patch("src.utils.ngrok_utils.PyngrokConfig") as mock_config_class:
            mock_config = Mock()
            mock_config_class.return_value = mock_config

            config1 = ngrok_manager._get_config()
            config2 = ngrok_manager._get_config()

            # Should only be called once (cached)
            assert mock_config_class.call_count == 1
            assert config1 is config2


class TestNgrokManagerStartTunnel:
    """Tests for NgrokManager.start_tunnel."""

    def test_start_tunnel_success(self, ngrok_manager, mock_tunnel):
        """Test successful tunnel start."""
        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_ngrok.connect.return_value = mock_tunnel

            with patch("builtins.print"):  # Suppress print output
                url = ngrok_manager.start_tunnel()

            assert url == "https://abc123.ngrok.io"
            assert ngrok_manager.tunnel == mock_tunnel
            mock_ngrok.set_auth_token.assert_called_once_with("test_token")
            mock_ngrok.connect.assert_called_once()

    def test_start_tunnel_without_auth_token(self):
        """Test tunnel start without auth token."""
        manager = NgrokManager(auth_token=None, port=8000)

        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_tunnel = Mock()
            mock_tunnel.public_url = "https://xyz789.ngrok.io"
            mock_ngrok.connect.return_value = mock_tunnel

            with patch("builtins.print"):
                url = manager.start_tunnel()

            assert url == "https://xyz789.ngrok.io"
            mock_ngrok.set_auth_token.assert_not_called()

    def test_start_tunnel_pyngrok_error(self, ngrok_manager):
        """Test tunnel start with PyngrokNgrokError."""
        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_ngrok.connect.side_effect = PyngrokNgrokError("Connection failed")

            with pytest.raises(PyngrokNgrokError, match="Connection failed"):
                ngrok_manager.start_tunnel()

    def test_start_tunnel_unexpected_error(self, ngrok_manager):
        """Test tunnel start with unexpected error."""
        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_ngrok.connect.side_effect = RuntimeError("Unexpected error")

            with pytest.raises(RuntimeError, match="Unexpected error"):
                ngrok_manager.start_tunnel()


class TestNgrokManagerStopTunnel:
    """Tests for NgrokManager.stop_tunnel."""

    def test_stop_tunnel_success(self, ngrok_manager, mock_tunnel):
        """Test successful tunnel stop."""
        ngrok_manager.tunnel = mock_tunnel

        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            ngrok_manager.stop_tunnel()

            mock_ngrok.disconnect.assert_called_once_with("https://abc123.ngrok.io")
            assert ngrok_manager.tunnel is None

    def test_stop_tunnel_no_tunnel(self, ngrok_manager):
        """Test stop tunnel when no tunnel exists."""
        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            ngrok_manager.stop_tunnel()

            mock_ngrok.disconnect.assert_not_called()
            assert ngrok_manager.tunnel is None

    def test_stop_tunnel_handles_error(self, ngrok_manager, mock_tunnel):
        """Test stop tunnel handles errors gracefully."""
        ngrok_manager.tunnel = mock_tunnel

        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_ngrok.disconnect.side_effect = Exception("Disconnect failed")

            # Should not raise
            ngrok_manager.stop_tunnel()


class TestNgrokManagerGetTunnelUrl:
    """Tests for NgrokManager.get_tunnel_url."""

    def test_get_tunnel_url_with_tunnel(self, ngrok_manager, mock_tunnel):
        """Test getting tunnel URL when tunnel exists."""
        ngrok_manager.tunnel = mock_tunnel

        url = ngrok_manager.get_tunnel_url()

        assert url == "https://abc123.ngrok.io"

    def test_get_tunnel_url_no_tunnel(self, ngrok_manager):
        """Test getting tunnel URL when no tunnel exists."""
        url = ngrok_manager.get_tunnel_url()

        assert url is None


class TestNgrokManagerIsTunnelActive:
    """Tests for NgrokManager.is_tunnel_active."""

    def test_is_tunnel_active_true(self, ngrok_manager, mock_tunnel):
        """Test tunnel is active when tunnel exists."""
        ngrok_manager.tunnel = mock_tunnel

        assert ngrok_manager.is_tunnel_active() is True

    def test_is_tunnel_active_false(self, ngrok_manager):
        """Test tunnel is not active when no tunnel."""
        assert ngrok_manager.is_tunnel_active() is False


class TestNgrokManagerGetTunnelStatus:
    """Tests for NgrokManager.get_tunnel_status."""

    def test_get_tunnel_status_no_tunnel(self, ngrok_manager):
        """Test status when no tunnel exists."""
        status = ngrok_manager.get_tunnel_status()

        assert status == {"active": False, "url": None}

    def test_get_tunnel_status_active_tunnel(self, ngrok_manager, mock_tunnel):
        """Test status when tunnel is active."""
        ngrok_manager.tunnel = mock_tunnel

        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_ngrok.get_tunnels.return_value = [mock_tunnel]

            status = ngrok_manager.get_tunnel_status()

            assert status["active"] is True
            assert status["url"] == "https://abc123.ngrok.io"
            assert status["name"] == "test-tunnel"

    def test_get_tunnel_status_tunnel_not_found_in_list(
        self, ngrok_manager, mock_tunnel
    ):
        """Test status when tunnel not found in ngrok tunnels list."""
        ngrok_manager.tunnel = mock_tunnel

        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            other_tunnel = Mock()
            other_tunnel.name = "other-tunnel"
            mock_ngrok.get_tunnels.return_value = [other_tunnel]

            status = ngrok_manager.get_tunnel_status()

            assert status == {"active": False, "url": None}

    def test_get_tunnel_status_api_error(self, ngrok_manager, mock_tunnel):
        """Test status when API call fails."""
        ngrok_manager.tunnel = mock_tunnel

        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_ngrok.get_tunnels.side_effect = Exception("API error")

            status = ngrok_manager.get_tunnel_status()

            assert status == {"active": False, "url": None}


class TestNgrokManagerKillExistingProcesses:
    """Tests for NgrokManager.kill_existing_ngrok_processes."""

    def test_kill_no_ngrok_processes(self):
        """Test when no ngrok processes exist."""
        with patch("src.utils.ngrok_utils.psutil") as mock_psutil:
            # Empty process list
            mock_psutil.process_iter.return_value = []

            killed = NgrokManager.kill_existing_ngrok_processes()

            assert killed == 0

    def test_kill_ngrok_processes(self):
        """Test killing ngrok processes."""
        with patch("src.utils.ngrok_utils.psutil") as mock_psutil:
            mock_proc1 = Mock()
            mock_proc1.info = {"pid": 1234, "name": "ngrok", "cmdline": []}
            mock_proc2 = Mock()
            mock_proc2.info = {"pid": 5678, "name": "ngrok", "cmdline": []}
            mock_proc3 = Mock()
            mock_proc3.info = {"pid": 9999, "name": "python", "cmdline": []}

            mock_psutil.process_iter.return_value = [mock_proc1, mock_proc2, mock_proc3]

            killed = NgrokManager.kill_existing_ngrok_processes()

            assert killed == 2
            mock_proc1.kill.assert_called_once()
            mock_proc2.kill.assert_called_once()
            mock_proc3.kill.assert_not_called()

    def test_kill_handles_no_such_process(self):
        """Test handling NoSuchProcess exception."""
        import psutil

        with patch("src.utils.ngrok_utils.psutil") as mock_psutil:
            mock_proc = Mock()
            mock_proc.info = {"pid": 1234, "name": "ngrok", "cmdline": []}
            mock_proc.kill.side_effect = psutil.NoSuchProcess(1234)

            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.NoSuchProcess = psutil.NoSuchProcess
            mock_psutil.AccessDenied = psutil.AccessDenied

            killed = NgrokManager.kill_existing_ngrok_processes()

            assert killed == 0

    def test_kill_handles_access_denied(self):
        """Test handling AccessDenied exception."""
        import psutil

        with patch("src.utils.ngrok_utils.psutil") as mock_psutil:
            mock_proc = Mock()
            mock_proc.info = {"pid": 1234, "name": "ngrok", "cmdline": []}
            mock_proc.kill.side_effect = psutil.AccessDenied(1234)

            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.NoSuchProcess = psutil.NoSuchProcess
            mock_psutil.AccessDenied = psutil.AccessDenied

            killed = NgrokManager.kill_existing_ngrok_processes()

            assert killed == 0


class TestNgrokManagerApiTunnels:
    """Tests for NgrokManager async API methods."""

    @pytest.mark.asyncio
    async def test_get_ngrok_api_tunnels_success(self):
        """Test getting tunnels from ngrok API."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "tunnels": [
                    {"name": "tunnel1", "public_url": "https://t1.ngrok.io"},
                    {"name": "tunnel2", "public_url": "https://t2.ngrok.io"},
                ]
            }
            mock_client.get = AsyncMock(return_value=mock_response)

            tunnels = await NgrokManager.get_ngrok_api_tunnels()

            assert len(tunnels) == 2
            assert tunnels[0]["name"] == "tunnel1"
            mock_client.get.assert_called_once_with("http://localhost:4040/api/tunnels")

    @pytest.mark.asyncio
    async def test_get_ngrok_api_tunnels_not_running(self):
        """Test when ngrok API is not available."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

            tunnels = await NgrokManager.get_ngrok_api_tunnels()

            assert tunnels == []

    @pytest.mark.asyncio
    async def test_get_ngrok_api_tunnels_non_200_status(self):
        """Test when ngrok API returns non-200 status."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.status_code = 500
            mock_client.get = AsyncMock(return_value=mock_response)

            tunnels = await NgrokManager.get_ngrok_api_tunnels()

            assert tunnels == []

    @pytest.mark.asyncio
    async def test_get_public_url_from_api_success(self):
        """Test getting public URL from ngrok API."""
        with patch.object(
            NgrokManager,
            "get_ngrok_api_tunnels",
            new_callable=AsyncMock,
            return_value=[
                {
                    "config": {"addr": "http://localhost:8000"},
                    "public_url": "https://matching.ngrok.io",
                },
                {
                    "config": {"addr": "http://localhost:9000"},
                    "public_url": "https://other.ngrok.io",
                },
            ],
        ):
            url = await NgrokManager.get_public_url_from_api(port=8000)

            assert url == "https://matching.ngrok.io"

    @pytest.mark.asyncio
    async def test_get_public_url_from_api_no_match(self):
        """Test when no matching tunnel found."""
        with patch.object(
            NgrokManager,
            "get_ngrok_api_tunnels",
            new_callable=AsyncMock,
            return_value=[
                {
                    "config": {"addr": "http://localhost:9000"},
                    "public_url": "https://other.ngrok.io",
                },
            ],
        ):
            url = await NgrokManager.get_public_url_from_api(port=8000)

            assert url is None

    @pytest.mark.asyncio
    async def test_get_public_url_from_api_empty_tunnels(self):
        """Test when no tunnels exist."""
        with patch.object(
            NgrokManager,
            "get_ngrok_api_tunnels",
            new_callable=AsyncMock,
            return_value=[],
        ):
            url = await NgrokManager.get_public_url_from_api(port=8000)

            assert url is None


# =============================================================================
# WebhookManager Tests
# =============================================================================


class TestWebhookManagerInit:
    """Tests for WebhookManager initialization."""

    def test_initialization(self, webhook_manager):
        """Test WebhookManager initialization."""
        assert webhook_manager.bot_token == "test:bot_token"
        assert webhook_manager.base_url == "https://api.telegram.org/bottest:bot_token"


class TestWebhookManagerSetWebhook:
    """Tests for WebhookManager.set_webhook."""

    @pytest.mark.asyncio
    async def test_set_webhook_success(self, webhook_manager):
        """Test successful webhook set."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {"ok": True}
            mock_client.post = AsyncMock(return_value=mock_response)

            success, message = await webhook_manager.set_webhook(
                "https://example.ngrok.io/webhook"
            )

            assert success is True
            assert "successfully" in message.lower()
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_webhook_with_secret_token(self, webhook_manager):
        """Test webhook set with secret token."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {"ok": True}
            mock_client.post = AsyncMock(return_value=mock_response)

            success, message = await webhook_manager.set_webhook(
                "https://example.ngrok.io/webhook",
                secret_token="my_secret",
            )

            assert success is True
            # Verify secret_token was included in the request
            call_args = mock_client.post.call_args
            assert call_args.kwargs["json"]["secret_token"] == "my_secret"

    @pytest.mark.asyncio
    async def test_set_webhook_failure(self, webhook_manager):
        """Test webhook set failure."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {
                "ok": False,
                "description": "Bad Request: invalid URL",
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            success, message = await webhook_manager.set_webhook("invalid-url")

            assert success is False
            assert "invalid URL" in message

    @pytest.mark.asyncio
    async def test_set_webhook_exception(self, webhook_manager):
        """Test webhook set with exception."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=Exception("Network error"))

            success, message = await webhook_manager.set_webhook(
                "https://example.ngrok.io/webhook"
            )

            assert success is False
            assert "exception" in message.lower()


class TestWebhookManagerGetWebhookInfo:
    """Tests for WebhookManager.get_webhook_info."""

    @pytest.mark.asyncio
    async def test_get_webhook_info_success(self, webhook_manager):
        """Test successful webhook info retrieval."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {
                "ok": True,
                "result": {
                    "url": "https://example.ngrok.io/webhook",
                    "has_custom_certificate": False,
                    "pending_update_count": 0,
                },
            }
            mock_client.get = AsyncMock(return_value=mock_response)

            info = await webhook_manager.get_webhook_info()

            assert info["url"] == "https://example.ngrok.io/webhook"
            assert info["pending_update_count"] == 0

    @pytest.mark.asyncio
    async def test_get_webhook_info_failure(self, webhook_manager):
        """Test webhook info failure."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {
                "ok": False,
                "description": "Unauthorized",
            }
            mock_client.get = AsyncMock(return_value=mock_response)

            info = await webhook_manager.get_webhook_info()

            assert info == {}

    @pytest.mark.asyncio
    async def test_get_webhook_info_exception(self, webhook_manager):
        """Test webhook info with exception."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=Exception("Connection timeout"))

            info = await webhook_manager.get_webhook_info()

            assert info == {}


class TestWebhookManagerDeleteWebhook:
    """Tests for WebhookManager.delete_webhook."""

    @pytest.mark.asyncio
    async def test_delete_webhook_success(self, webhook_manager):
        """Test successful webhook deletion."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {"ok": True}
            mock_client.post = AsyncMock(return_value=mock_response)

            success, message = await webhook_manager.delete_webhook()

            assert success is True
            assert "deleted successfully" in message.lower()

    @pytest.mark.asyncio
    async def test_delete_webhook_failure(self, webhook_manager):
        """Test webhook deletion failure."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {
                "ok": False,
                "description": "Unauthorized",
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            success, message = await webhook_manager.delete_webhook()

            assert success is False
            assert "Unauthorized" in message

    @pytest.mark.asyncio
    async def test_delete_webhook_exception(self, webhook_manager):
        """Test webhook deletion with exception."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=Exception("Server error"))

            success, message = await webhook_manager.delete_webhook()

            assert success is False
            assert "exception" in message.lower()


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestSetupNgrokWebhook:
    """Tests for setup_ngrok_webhook helper function."""

    @pytest.mark.asyncio
    async def test_setup_ngrok_webhook_success(self):
        """Test successful ngrok webhook setup."""
        with patch("src.utils.ngrok_utils.NgrokManager") as mock_ngrok_class:
            with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
                mock_ngrok = Mock()
                mock_ngrok.start_tunnel.return_value = "https://test.ngrok.io"
                mock_ngrok_class.return_value = mock_ngrok

                mock_webhook = AsyncMock()
                mock_webhook.set_webhook = AsyncMock(
                    return_value=(True, "Webhook set successfully")
                )
                mock_webhook_class.return_value = mock_webhook

                success, message, url = await setup_ngrok_webhook(
                    bot_token="test:token",
                    auth_token="ngrok_auth",
                    port=8000,
                    webhook_path="/webhook",
                )

                assert success is True
                assert "https://test.ngrok.io/webhook" in url

    @pytest.mark.asyncio
    async def test_setup_ngrok_webhook_tunnel_failure(self):
        """Test ngrok webhook setup when tunnel fails."""
        with patch("src.utils.ngrok_utils.NgrokManager") as mock_ngrok_class:
            mock_ngrok = Mock()
            mock_ngrok.start_tunnel.side_effect = PyngrokNgrokError("Tunnel failed")
            mock_ngrok_class.return_value = mock_ngrok

            success, message, url = await setup_ngrok_webhook(
                bot_token="test:token",
            )

            assert success is False
            assert url is None

    @pytest.mark.asyncio
    async def test_setup_ngrok_webhook_webhook_failure(self):
        """Test ngrok webhook setup when webhook set fails."""
        with patch("src.utils.ngrok_utils.NgrokManager") as mock_ngrok_class:
            with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
                mock_ngrok = Mock()
                mock_ngrok.start_tunnel.return_value = "https://test.ngrok.io"
                mock_ngrok_class.return_value = mock_ngrok

                mock_webhook = AsyncMock()
                mock_webhook.set_webhook = AsyncMock(
                    return_value=(False, "Invalid token")
                )
                mock_webhook_class.return_value = mock_webhook

                success, message, url = await setup_ngrok_webhook(
                    bot_token="test:token",
                )

                assert success is False
                assert url is None
                mock_ngrok.stop_tunnel.assert_called_once()


class TestAutoUpdateWebhookOnRestart:
    """Tests for auto_update_webhook_on_restart helper function."""

    @pytest.mark.asyncio
    async def test_auto_update_production_environment(self):
        """Test auto update in production environment."""
        os.environ["ENVIRONMENT"] = "production"
        os.environ["WEBHOOK_BASE_URL"] = "https://production.example.com"

        with patch(
            "src.utils.ngrok_utils.setup_production_webhook",
            new_callable=AsyncMock,
        ) as mock_setup:
            mock_setup.return_value = (
                True,
                "Webhook set",
                "https://production.example.com/webhook",
            )

            success, message, url = await auto_update_webhook_on_restart(
                bot_token="test:token",
                port=8000,
            )

            assert success is True
            mock_setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_update_development_success(self):
        """Test auto update in development environment."""
        os.environ["ENVIRONMENT"] = "development"

        with patch.object(
            NgrokManager,
            "get_public_url_from_api",
            new_callable=AsyncMock,
            return_value="https://dev.ngrok.io",
        ):
            with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
                mock_webhook = AsyncMock()
                mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
                mock_webhook_class.return_value = mock_webhook

                with patch("asyncio.sleep", new_callable=AsyncMock):
                    success, message, url = await auto_update_webhook_on_restart(
                        bot_token="test:token",
                        port=8000,
                        max_retries=1,
                    )

                    assert success is True
                    assert "https://dev.ngrok.io" in url

    @pytest.mark.asyncio
    async def test_auto_update_development_retries_exhausted(self):
        """Test auto update exhausts retries."""
        os.environ["ENVIRONMENT"] = "development"

        with patch.object(
            NgrokManager,
            "get_public_url_from_api",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                success, message, url = await auto_update_webhook_on_restart(
                    bot_token="test:token",
                    port=8000,
                    max_retries=2,
                )

                assert success is False
                assert url is None
                assert "retries" in message.lower()


class TestSetupProductionWebhook:
    """Tests for setup_production_webhook helper function."""

    @pytest.mark.asyncio
    async def test_setup_production_webhook_success(self):
        """Test successful production webhook setup."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
            mock_webhook_class.return_value = mock_webhook

            with patch("builtins.print"):  # Suppress print output
                success, message, url = await setup_production_webhook(
                    bot_token="test:token",
                    base_url="https://production.example.com",
                    webhook_path="/webhook",
                    secret_token="secret123",
                )

                assert success is True
                assert url == "https://production.example.com/webhook"

    @pytest.mark.asyncio
    async def test_setup_production_webhook_trailing_slash_handling(self):
        """Test production webhook handles trailing slash in base_url."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
            mock_webhook_class.return_value = mock_webhook

            with patch("builtins.print"):
                success, message, url = await setup_production_webhook(
                    bot_token="test:token",
                    base_url="https://example.com/",  # trailing slash
                    webhook_path="/webhook",
                )

                assert url == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_setup_production_webhook_missing_leading_slash(self):
        """Test production webhook adds leading slash to path."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
            mock_webhook_class.return_value = mock_webhook

            with patch("builtins.print"):
                success, message, url = await setup_production_webhook(
                    bot_token="test:token",
                    base_url="https://example.com",
                    webhook_path="webhook",  # no leading slash
                )

                assert url == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_setup_production_webhook_failure(self):
        """Test production webhook setup failure."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.set_webhook = AsyncMock(return_value=(False, "Unauthorized"))
            mock_webhook_class.return_value = mock_webhook

            with patch("builtins.print"):
                success, message, url = await setup_production_webhook(
                    bot_token="invalid:token",
                    base_url="https://example.com",
                )

                assert success is False
                assert url is None


class TestCheckAndRecoverWebhook:
    """Tests for check_and_recover_webhook helper function."""

    @pytest.mark.asyncio
    async def test_check_webhook_healthy(self):
        """Test webhook health check when webhook is healthy."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.get_webhook_info = AsyncMock(
                return_value={"url": "https://test.ngrok.io/webhook"}
            )
            mock_webhook_class.return_value = mock_webhook

            with patch.object(
                NgrokManager,
                "get_public_url_from_api",
                new_callable=AsyncMock,
                return_value="https://test.ngrok.io",
            ):
                is_healthy, message = await check_and_recover_webhook(
                    bot_token="test:token",
                    port=8000,
                )

                assert is_healthy is True
                assert "healthy" in message.lower()

    @pytest.mark.asyncio
    async def test_check_webhook_url_mismatch_recovery(self):
        """Test webhook recovery when URL mismatch detected."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.get_webhook_info = AsyncMock(
                return_value={"url": "https://old.ngrok.io/webhook"}
            )
            mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
            mock_webhook_class.return_value = mock_webhook

            with patch.object(
                NgrokManager,
                "get_public_url_from_api",
                new_callable=AsyncMock,
                return_value="https://new.ngrok.io",
            ):
                is_healthy, message = await check_and_recover_webhook(
                    bot_token="test:token",
                    port=8000,
                )

                assert is_healthy is True
                assert "recovered" in message.lower()

    @pytest.mark.asyncio
    async def test_check_webhook_no_webhook_set(self):
        """Test webhook recovery when no webhook is set."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.get_webhook_info = AsyncMock(return_value={"url": ""})
            mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
            mock_webhook_class.return_value = mock_webhook

            with patch.object(
                NgrokManager,
                "get_public_url_from_api",
                new_callable=AsyncMock,
                return_value="https://new.ngrok.io",
            ):
                is_healthy, message = await check_and_recover_webhook(
                    bot_token="test:token",
                    port=8000,
                )

                assert is_healthy is True
                assert "recovered" in message.lower()

    @pytest.mark.asyncio
    async def test_check_webhook_no_ngrok_no_webhook(self):
        """Test when no webhook and no ngrok tunnel."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.get_webhook_info = AsyncMock(return_value={"url": ""})
            mock_webhook_class.return_value = mock_webhook

            with patch.object(
                NgrokManager,
                "get_public_url_from_api",
                new_callable=AsyncMock,
                return_value=None,
            ):
                is_healthy, message = await check_and_recover_webhook(
                    bot_token="test:token",
                    port=8000,
                )

                assert is_healthy is False

    @pytest.mark.asyncio
    async def test_check_webhook_exception_handling(self):
        """Test webhook check handles exceptions."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.get_webhook_info = AsyncMock(
                side_effect=Exception("API error")
            )
            mock_webhook_class.return_value = mock_webhook

            is_healthy, message = await check_and_recover_webhook(
                bot_token="test:token",
            )

            assert is_healthy is False
            assert "failed" in message.lower()


class TestRunPeriodicWebhookCheck:
    """Tests for run_periodic_webhook_check helper function."""

    @pytest.mark.asyncio
    async def test_periodic_check_runs_and_cancels(self):
        """Test periodic webhook check runs and can be cancelled."""
        call_count = 0
        sleep_call_count = 0

        async def mock_check(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return True, "Healthy"

        original_sleep = asyncio.sleep

        async def fast_sleep(seconds):
            nonlocal sleep_call_count
            sleep_call_count += 1
            # Use very short sleep to speed up test
            await original_sleep(0.001)

        with patch(
            "src.utils.ngrok_utils.check_and_recover_webhook",
            side_effect=mock_check,
        ):
            with patch("src.utils.ngrok_utils.asyncio.sleep", side_effect=fast_sleep):
                task = asyncio.create_task(
                    run_periodic_webhook_check(
                        bot_token="test:token",
                        interval_minutes=0.001,
                    )
                )

                # Let it run briefly
                await original_sleep(0.05)

                # Cancel the task
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

                # Should have been called at least once
                assert call_count >= 1

    @pytest.mark.asyncio
    async def test_periodic_check_handles_unhealthy(self):
        """Test periodic check logs warning for unhealthy webhook."""
        original_sleep = asyncio.sleep

        async def fast_sleep(seconds):
            await original_sleep(0.001)

        with patch(
            "src.utils.ngrok_utils.check_and_recover_webhook",
            new_callable=AsyncMock,
            return_value=(False, "Webhook unhealthy"),
        ):
            with patch("src.utils.ngrok_utils.logger") as mock_logger:
                with patch(
                    "src.utils.ngrok_utils.asyncio.sleep", side_effect=fast_sleep
                ):
                    task = asyncio.create_task(
                        run_periodic_webhook_check(
                            bot_token="test:token",
                            interval_minutes=0.001,
                        )
                    )

                    await original_sleep(0.05)
                    task.cancel()

                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                    # Check that warning was logged
                    mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_periodic_check_handles_exceptions(self):
        """Test periodic check handles exceptions gracefully."""
        call_count = 0
        original_sleep = asyncio.sleep

        async def failing_check(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Check failed")

        async def fast_sleep(seconds):
            await original_sleep(0.001)

        with patch(
            "src.utils.ngrok_utils.check_and_recover_webhook",
            side_effect=failing_check,
        ):
            with patch("src.utils.ngrok_utils.logger"):
                with patch(
                    "src.utils.ngrok_utils.asyncio.sleep", side_effect=fast_sleep
                ):
                    task = asyncio.create_task(
                        run_periodic_webhook_check(
                            bot_token="test:token",
                            interval_minutes=0.001,
                        )
                    )

                    await original_sleep(0.05)
                    task.cancel()

                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                    # Should have attempted multiple checks despite exceptions
                    assert call_count >= 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_development_workflow(self):
        """Test complete development workflow: start tunnel, set webhook."""
        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_tunnel = Mock()
            mock_tunnel.public_url = "https://dev.ngrok.io"
            mock_tunnel.name = "test-tunnel"
            mock_tunnel.config = {}
            mock_ngrok.connect.return_value = mock_tunnel
            mock_ngrok.get_tunnels.return_value = [mock_tunnel]

            with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # Mock successful webhook set
                mock_response = Mock()
                mock_response.json.return_value = {"ok": True}
                mock_client.post = AsyncMock(return_value=mock_response)

                with patch("builtins.print"):
                    success, message, url = await setup_ngrok_webhook(
                        bot_token="test:token",
                        auth_token="ngrok_auth",
                        port=8000,
                        webhook_path="/webhook",
                        secret_token="secret123",
                    )

                    assert success is True
                    assert url == "https://dev.ngrok.io/webhook"

    @pytest.mark.asyncio
    async def test_full_production_workflow(self):
        """Test complete production workflow."""
        os.environ["ENVIRONMENT"] = "production"
        os.environ["WEBHOOK_BASE_URL"] = "https://api.production.com"

        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {"ok": True}
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch("builtins.print"):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    success, message, url = await auto_update_webhook_on_restart(
                        bot_token="prod:token",
                        port=8000,
                        webhook_path="/webhook",
                        secret_token="prod_secret",
                    )

                    assert success is True
                    assert url == "https://api.production.com/webhook"

    @pytest.mark.asyncio
    async def test_recovery_after_tunnel_restart(self):
        """Test webhook recovery after ngrok tunnel restarts."""
        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.get_webhook_info = AsyncMock(
                return_value={"url": "https://old.ngrok.io/webhook"}
            )
            mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
            mock_webhook_class.return_value = mock_webhook

            with patch.object(
                NgrokManager,
                "get_public_url_from_api",
                new_callable=AsyncMock,
                return_value="https://new.ngrok.io",
            ):
                # First check should detect mismatch and recover
                is_healthy, message = await check_and_recover_webhook(
                    bot_token="test:token",
                    port=8000,
                    webhook_path="/webhook",
                    secret_token="secret",
                )

                assert is_healthy is True
                assert "recovered" in message.lower()

                # Verify webhook was updated with new URL
                mock_webhook.set_webhook.assert_called_once()
                call_args = mock_webhook.set_webhook.call_args
                assert "https://new.ngrok.io/webhook" in call_args.args


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_ngrok_manager_with_empty_string_auth_token(self):
        """Test NgrokManager with empty string auth token."""
        manager = NgrokManager(auth_token="")

        # Empty string is falsy, so should not set auth token
        with patch("src.utils.ngrok_utils.ngrok") as mock_ngrok:
            mock_tunnel = Mock()
            mock_tunnel.public_url = "https://test.ngrok.io"
            mock_ngrok.connect.return_value = mock_tunnel

            with patch("builtins.print"):
                manager.start_tunnel()

            mock_ngrok.set_auth_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_webhook_manager_special_characters_in_token(self):
        """Test WebhookManager with special characters in bot token."""
        manager = WebhookManager(bot_token="123:ABC_def-GHI")

        assert "123:ABC_def-GHI" in manager.base_url

    @pytest.mark.asyncio
    async def test_very_long_webhook_url(self):
        """Test handling of very long webhook URLs."""
        long_path = "/" + "a" * 500

        with patch("src.utils.ngrok_utils.WebhookManager") as mock_webhook_class:
            mock_webhook = AsyncMock()
            mock_webhook.set_webhook = AsyncMock(return_value=(True, "Webhook set"))
            mock_webhook_class.return_value = mock_webhook

            with patch("builtins.print"):
                success, message, url = await setup_production_webhook(
                    bot_token="test:token",
                    base_url="https://example.com",
                    webhook_path=long_path,
                )

                assert success is True
                assert len(url) > 500

    @pytest.mark.asyncio
    async def test_unicode_in_error_message(self):
        """Test handling of unicode in error messages."""
        with patch("src.utils.ngrok_utils.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.json.return_value = {
                "ok": False,
                "description": "Error: Неверный токен",  # Russian text
            }
            mock_client.post = AsyncMock(return_value=mock_response)

            webhook_manager = WebhookManager(bot_token="test:token")
            success, message = await webhook_manager.set_webhook("https://test.com")

            assert success is False
            assert "Неверный токен" in message

    def test_kill_processes_with_ngrok_in_name_case_insensitive(self):
        """Test that ngrok process detection is case insensitive."""
        with patch("src.utils.ngrok_utils.psutil") as mock_psutil:
            mock_proc1 = Mock()
            mock_proc1.info = {"pid": 1, "name": "NGROK", "cmdline": []}
            mock_proc2 = Mock()
            mock_proc2.info = {"pid": 2, "name": "NgRoK", "cmdline": []}
            mock_proc3 = Mock()
            mock_proc3.info = {"pid": 3, "name": "ngrok", "cmdline": []}

            mock_psutil.process_iter.return_value = [mock_proc1, mock_proc2, mock_proc3]

            killed = NgrokManager.kill_existing_ngrok_processes()

            assert killed == 3
