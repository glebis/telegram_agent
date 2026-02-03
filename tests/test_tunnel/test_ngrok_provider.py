"""Tests for NgrokTunnelProvider."""

from unittest.mock import MagicMock, patch

import pytest

from src.tunnel.ngrok_provider import NgrokTunnelProvider


class TestNgrokTunnelProvider:
    """Test NgrokTunnelProvider wraps NgrokManager correctly."""

    def test_name(self):
        provider = NgrokTunnelProvider(port=8000)
        assert provider.name == "ngrok"

    def test_provides_stable_url_is_false(self):
        provider = NgrokTunnelProvider(port=8000)
        assert provider.provides_stable_url is False

    @pytest.mark.asyncio
    async def test_start_delegates_to_manager(self):
        provider = NgrokTunnelProvider(port=8000)
        mock_manager = MagicMock()
        mock_manager.start_tunnel.return_value = "https://abc123.ngrok.io"
        provider._manager = mock_manager

        url = await provider.start()

        assert url == "https://abc123.ngrok.io"
        mock_manager.start_tunnel.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_delegates_to_manager(self):
        provider = NgrokTunnelProvider(port=8000)
        mock_manager = MagicMock()
        provider._manager = mock_manager

        await provider.stop()

        mock_manager.stop_tunnel.assert_called_once()
        assert provider._url is None

    def test_get_url_delegates_to_manager(self):
        provider = NgrokTunnelProvider(port=8000)
        mock_manager = MagicMock()
        mock_manager.get_tunnel_url.return_value = "https://abc123.ngrok.io"
        provider._manager = mock_manager

        assert provider.get_url() == "https://abc123.ngrok.io"

    def test_get_url_without_manager(self):
        provider = NgrokTunnelProvider(port=8000)
        provider._url = "https://cached.ngrok.io"
        assert provider.get_url() == "https://cached.ngrok.io"

    def test_get_status_active(self):
        provider = NgrokTunnelProvider(port=8000)
        mock_manager = MagicMock()
        mock_manager.get_tunnel_url.return_value = "https://abc123.ngrok.io"
        provider._manager = mock_manager

        status = provider.get_status()

        assert status["provider"] == "ngrok"
        assert status["active"] is True
        assert status["url"] == "https://abc123.ngrok.io"
        assert status["provides_stable_url"] is False
        # Backward-compat keys
        assert status["ngrok_active"] is True
        assert status["ngrok_url"] == "https://abc123.ngrok.io"

    def test_get_status_inactive(self):
        provider = NgrokTunnelProvider(port=8000)
        mock_manager = MagicMock()
        mock_manager.get_tunnel_url.return_value = None
        provider._manager = mock_manager

        status = provider.get_status()

        assert status["active"] is False
        assert status["url"] is None

    @pytest.mark.asyncio
    async def test_health_check_active(self):
        provider = NgrokTunnelProvider(port=8000)
        mock_manager = MagicMock()
        mock_manager.get_tunnel_status.return_value = {
            "active": True,
            "url": "https://abc123.ngrok.io",
        }
        provider._manager = mock_manager

        healthy, msg = await provider.health_check()

        assert healthy is True
        assert "abc123.ngrok.io" in msg

    @pytest.mark.asyncio
    async def test_health_check_inactive_tries_api(self):
        provider = NgrokTunnelProvider(port=8000)
        mock_manager = MagicMock()
        mock_manager.get_tunnel_status.return_value = {"active": False}
        provider._manager = mock_manager

        with patch(
            "src.utils.ngrok_utils.NgrokManager.get_public_url_from_api",
            return_value=None,
        ):
            healthy, msg = await provider.health_check()
            assert healthy is False
