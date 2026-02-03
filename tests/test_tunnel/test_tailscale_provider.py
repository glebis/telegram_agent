"""Tests for TailscaleTunnelProvider."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tunnel.tailscale_provider import TailscaleTunnelProvider


class TestTailscaleTunnelProvider:
    """Test TailscaleTunnelProvider."""

    def test_name(self):
        provider = TailscaleTunnelProvider(port=8000)
        assert provider.name == "tailscale"

    def test_provides_stable_url(self):
        provider = TailscaleTunnelProvider(port=8000)
        assert provider.provides_stable_url is True

    @pytest.mark.asyncio
    async def test_start_raises_without_tailscale(self):
        provider = TailscaleTunnelProvider(port=8000)
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="tailscale CLI not found"):
                await provider.start()

    @pytest.mark.asyncio
    async def test_get_tailscale_url_from_hostname_env(self):
        provider = TailscaleTunnelProvider(port=8000)
        provider._hostname = "myhost.tailnet.ts.net"

        url = await provider._get_tailscale_url()
        assert url == "https://myhost.tailnet.ts.net"

    @pytest.mark.asyncio
    async def test_get_tailscale_url_from_status(self):
        provider = TailscaleTunnelProvider(port=8000)
        provider._hostname = None

        status_json = json.dumps(
            {"Self": {"DNSName": "myhost.tailnet.ts.net."}}
        ).encode()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(status_json, b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            url = await provider._get_tailscale_url()
            assert url == "https://myhost.tailnet.ts.net"

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        provider = TailscaleTunnelProvider(port=8000)
        # Should not raise when no process running
        await provider.stop()
        assert provider._url is None

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self):
        provider = TailscaleTunnelProvider(port=8000)
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=0)
        provider._process = mock_process

        # Mock the "tailscale funnel off" subprocess
        mock_off = AsyncMock()
        mock_off.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_off):
            await provider.stop()

        mock_process.terminate.assert_called_once()
        assert provider._url is None

    def test_get_url(self):
        provider = TailscaleTunnelProvider(port=8000)
        assert provider.get_url() is None
        provider._url = "https://myhost.tailnet.ts.net"
        assert provider.get_url() == "https://myhost.tailnet.ts.net"

    @pytest.mark.asyncio
    async def test_health_check_no_process(self):
        provider = TailscaleTunnelProvider(port=8000)
        healthy, msg = await provider.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        provider = TailscaleTunnelProvider(port=8000)
        mock_process = MagicMock()
        mock_process.returncode = None
        provider._process = mock_process
        provider._url = "https://myhost.tailnet.ts.net"

        healthy, msg = await provider.health_check()
        assert healthy is True
        assert "myhost.tailnet.ts.net" in msg

    def test_get_status_inactive(self):
        provider = TailscaleTunnelProvider(port=8000)
        status = provider.get_status()

        assert status["provider"] == "tailscale"
        assert status["active"] is False
        assert status["provides_stable_url"] is True

    def test_get_status_active(self):
        provider = TailscaleTunnelProvider(port=8000)
        mock_process = MagicMock()
        mock_process.returncode = None
        provider._process = mock_process
        provider._url = "https://myhost.tailnet.ts.net"

        status = provider.get_status()

        assert status["active"] is True
        assert status["url"] == "https://myhost.tailnet.ts.net"
        # Backward-compat
        assert status["ngrok_active"] is True
        assert status["ngrok_url"] == "https://myhost.tailnet.ts.net"
