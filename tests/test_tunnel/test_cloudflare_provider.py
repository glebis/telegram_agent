"""Tests for CloudflareTunnelProvider."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tunnel.cloudflare_provider import CloudflareTunnelProvider


class TestCloudflareTunnelProvider:
    """Test CloudflareTunnelProvider."""

    def test_name(self):
        provider = CloudflareTunnelProvider(port=8000)
        assert provider.name == "cloudflare"

    def test_provides_stable_url(self):
        provider = CloudflareTunnelProvider(port=8000)
        assert provider.provides_stable_url is True

    @patch.dict(os.environ, {}, clear=False)
    def test_is_named_tunnel_without_config(self):
        os.environ.pop("CF_TUNNEL_NAME", None)
        os.environ.pop("CF_CREDENTIALS_FILE", None)
        provider = CloudflareTunnelProvider(port=8000)
        assert provider._is_named_tunnel() is False

    @patch.dict(
        os.environ,
        {
            "CF_TUNNEL_NAME": "my-tunnel",
            "CF_CREDENTIALS_FILE": "/path/to/creds.json",
        },
    )
    def test_is_named_tunnel_with_config(self):
        provider = CloudflareTunnelProvider(port=8000)
        assert provider._is_named_tunnel() is True

    @pytest.mark.asyncio
    async def test_start_raises_without_cloudflared(self):
        provider = CloudflareTunnelProvider(port=8000)
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="cloudflared not found"):
                await provider.start()

    @pytest.mark.asyncio
    async def test_named_tunnel_requires_webhook_base_url(self):
        provider = CloudflareTunnelProvider(port=8000)
        provider._tunnel_name = "my-tunnel"
        provider._credentials_file = "/path/to/creds.json"

        with patch("shutil.which", return_value="/usr/bin/cloudflared"):
            mock_process = AsyncMock()
            mock_process.returncode = None  # process still running
            with patch(
                "asyncio.create_subprocess_exec", return_value=mock_process
            ), patch("builtins.open", MagicMock()), patch(
                "asyncio.sleep", new_callable=AsyncMock
            ):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("WEBHOOK_BASE_URL", None)
                    with pytest.raises(RuntimeError, match="WEBHOOK_BASE_URL"):
                        await provider.start()
                    # cleanup
                    await provider.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        provider = CloudflareTunnelProvider(port=8000)
        # Should not raise when no process running
        await provider.stop()
        assert provider._url is None

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self):
        provider = CloudflareTunnelProvider(port=8000)
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=0)
        provider._process = mock_process
        provider._url = "https://test.trycloudflare.com"

        await provider.stop()

        mock_process.terminate.assert_called_once()
        assert provider._url is None
        assert provider._process is None

    def test_get_url(self):
        provider = CloudflareTunnelProvider(port=8000)
        assert provider.get_url() is None
        provider._url = "https://test.trycloudflare.com"
        assert provider.get_url() == "https://test.trycloudflare.com"

    @pytest.mark.asyncio
    async def test_health_check_no_process(self):
        provider = CloudflareTunnelProvider(port=8000)
        healthy, msg = await provider.health_check()
        assert healthy is False
        assert "not running" in msg

    @pytest.mark.asyncio
    async def test_health_check_exited(self):
        provider = CloudflareTunnelProvider(port=8000)
        mock_process = MagicMock()
        mock_process.returncode = 1
        provider._process = mock_process

        healthy, msg = await provider.health_check()
        assert healthy is False
        assert "exited" in msg

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        provider = CloudflareTunnelProvider(port=8000)
        mock_process = MagicMock()
        mock_process.returncode = None
        provider._process = mock_process
        provider._url = "https://test.trycloudflare.com"

        healthy, msg = await provider.health_check()
        assert healthy is True

    @patch.dict(os.environ, {}, clear=False)
    def test_get_status_inactive(self):
        os.environ.pop("CF_TUNNEL_NAME", None)
        os.environ.pop("CF_CREDENTIALS_FILE", None)
        provider = CloudflareTunnelProvider(port=8000)
        status = provider.get_status()

        assert status["provider"] == "cloudflare"
        assert status["active"] is False
        assert status["provides_stable_url"] is True
        assert status["mode"] == "quick"

    def test_get_status_active(self):
        provider = CloudflareTunnelProvider(port=8000)
        mock_process = MagicMock()
        mock_process.returncode = None
        provider._process = mock_process
        provider._url = "https://test.trycloudflare.com"

        status = provider.get_status()

        assert status["active"] is True
        assert status["url"] == "https://test.trycloudflare.com"
        # Backward-compat
        assert status["ngrok_active"] is True
        assert status["ngrok_url"] == "https://test.trycloudflare.com"
