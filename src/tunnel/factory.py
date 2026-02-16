"""Factory for tunnel provider instantiation."""

import logging
import os
from typing import Optional

from .base import TunnelProvider

logger = logging.getLogger(__name__)

# Singleton instance for global access to tunnel provider
_tunnel_provider_instance: Optional[TunnelProvider] = None


def get_tunnel_provider_instance() -> Optional[TunnelProvider]:
    """Get the currently active tunnel provider instance.

    Returns:
        The active tunnel provider, or None if not set.
    """
    return _tunnel_provider_instance


def set_tunnel_provider_instance(provider: Optional[TunnelProvider]) -> None:
    """Set the active tunnel provider instance.

    This should be called by the lifespan manager after creating the tunnel provider,
    and cleared (set to None) during shutdown.

    Args:
        provider: The tunnel provider instance to register, or None to clear.
    """
    global _tunnel_provider_instance
    _tunnel_provider_instance = provider


def get_tunnel_provider(
    provider_name: Optional[str] = None,
    port: Optional[int] = None,
) -> Optional[TunnelProvider]:
    """Create and return the appropriate tunnel provider.

    Resolution order:
    1. Explicit provider_name argument
    2. TUNNEL_PROVIDER environment variable
    3. Environment-based default: production=cloudflare, development=ngrok

    Returns None when:
    - provider is "none" or "skip"
    - WEBHOOK_BASE_URL is set and no explicit provider requested

    Args:
        provider_name: Explicit provider choice. Overrides env var.
        port: Port for the tunnel to forward to. Falls back to
              TUNNEL_PORT -> NGROK_PORT -> 8000.
    """
    # Resolve provider name
    if not provider_name:
        provider_name = os.getenv("TUNNEL_PROVIDER", "").lower().strip()

    if not provider_name:
        # Auto-detect from environment
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment in ("test", "testing"):
            provider_name = "none"
        elif environment == "production":
            provider_name = "cloudflare"
        else:
            provider_name = "ngrok"
        logger.info(
            f"TUNNEL_PROVIDER not set, defaulting to '{provider_name}' "
            f"for {environment} environment"
        )

    # Skip tunnel entirely
    if provider_name in ("none", "skip"):
        logger.info("Tunnel provider set to 'none' — skipping tunnel setup")
        return None

    # Resolve port
    if port is None:
        port = int(
            os.getenv(
                "TUNNEL_PORT",
                os.getenv("NGROK_PORT", "8000"),
            )
        )

    # Lazy import to avoid ImportError when CLI tool is not installed
    if provider_name == "ngrok":
        from .ngrok_provider import NgrokTunnelProvider

        return NgrokTunnelProvider(port=port)

    if provider_name == "cloudflare":
        from .cloudflare_provider import CloudflareTunnelProvider

        return CloudflareTunnelProvider(port=port)

    if provider_name == "tailscale":
        from .tailscale_provider import TailscaleTunnelProvider

        return TailscaleTunnelProvider(port=port)

    logger.warning(f"Unknown tunnel provider '{provider_name}', returning None")
    return None
