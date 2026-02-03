"""Tunnel provider abstraction for webhook URL tunneling.

Supports ngrok, Cloudflare Tunnel, and Tailscale Funnel.
"""

from .base import TunnelProvider
from .factory import get_tunnel_provider

__all__ = ["TunnelProvider", "get_tunnel_provider"]
