"""Tests for tunnel provider factory."""

import os
from unittest.mock import patch

from src.tunnel.factory import get_tunnel_provider


class TestGetTunnelProvider:
    """Test get_tunnel_provider() resolution logic."""

    def test_explicit_ngrok(self):
        provider = get_tunnel_provider(provider_name="ngrok", port=9000)
        assert provider is not None
        assert provider.name == "ngrok"

    def test_explicit_cloudflare(self):
        provider = get_tunnel_provider(provider_name="cloudflare", port=9000)
        assert provider is not None
        assert provider.name == "cloudflare"

    def test_explicit_tailscale(self):
        provider = get_tunnel_provider(provider_name="tailscale", port=9000)
        assert provider is not None
        assert provider.name == "tailscale"

    def test_explicit_none_returns_none(self):
        provider = get_tunnel_provider(provider_name="none")
        assert provider is None

    def test_explicit_skip_returns_none(self):
        provider = get_tunnel_provider(provider_name="skip")
        assert provider is None

    def test_unknown_provider_returns_none(self):
        provider = get_tunnel_provider(provider_name="unknown_xyz")
        assert provider is None

    @patch.dict(os.environ, {"TUNNEL_PROVIDER": "cloudflare"}, clear=False)
    def test_env_var_cloudflare(self):
        provider = get_tunnel_provider(port=8000)
        assert provider is not None
        assert provider.name == "cloudflare"

    @patch.dict(os.environ, {"TUNNEL_PROVIDER": "tailscale"}, clear=False)
    def test_env_var_tailscale(self):
        provider = get_tunnel_provider(port=8000)
        assert provider is not None
        assert provider.name == "tailscale"

    @patch.dict(os.environ, {"TUNNEL_PROVIDER": "none"}, clear=False)
    def test_env_var_none(self):
        provider = get_tunnel_provider(port=8000)
        assert provider is None

    @patch.dict(
        os.environ,
        {"TUNNEL_PROVIDER": "", "ENVIRONMENT": "development"},
        clear=False,
    )
    def test_default_development_is_ngrok(self):
        provider = get_tunnel_provider(port=8000)
        assert provider is not None
        assert provider.name == "ngrok"

    @patch.dict(
        os.environ,
        {"TUNNEL_PROVIDER": "", "ENVIRONMENT": "production"},
        clear=False,
    )
    def test_default_production_is_cloudflare(self):
        provider = get_tunnel_provider(port=8000)
        assert provider is not None
        assert provider.name == "cloudflare"

    def test_explicit_arg_overrides_env(self):
        with patch.dict(os.environ, {"TUNNEL_PROVIDER": "cloudflare"}):
            provider = get_tunnel_provider(provider_name="ngrok", port=8000)
            assert provider.name == "ngrok"

    @patch.dict(
        os.environ,
        {"TUNNEL_PORT": "9999", "TUNNEL_PROVIDER": "ngrok"},
        clear=False,
    )
    def test_port_from_tunnel_port_env(self):
        provider = get_tunnel_provider()
        assert provider is not None
        assert provider._port == 9999

    @patch.dict(
        os.environ,
        {"NGROK_PORT": "7777", "TUNNEL_PROVIDER": "ngrok"},
        clear=False,
    )
    def test_port_fallback_to_ngrok_port(self):
        # Remove TUNNEL_PORT if set
        env = os.environ.copy()
        env.pop("TUNNEL_PORT", None)
        with patch.dict(os.environ, env, clear=True):
            # Re-set what we need
            os.environ["NGROK_PORT"] = "7777"
            os.environ["TUNNEL_PROVIDER"] = "ngrok"
            provider = get_tunnel_provider()
            assert provider is not None
            assert provider._port == 7777
