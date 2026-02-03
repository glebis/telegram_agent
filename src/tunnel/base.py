"""Abstract base class for tunnel providers."""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple


class TunnelProvider(ABC):
    """Base class for tunnel providers (ngrok, cloudflare, tailscale)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name: 'ngrok', 'cloudflare', or 'tailscale'."""

    @property
    @abstractmethod
    def provides_stable_url(self) -> bool:
        """Whether this provider gives a stable URL across restarts.

        Stable providers (cloudflare, tailscale) skip periodic webhook recovery.
        Unstable providers (ngrok free tier) need periodic URL checks.
        """

    @abstractmethod
    async def start(self) -> str:
        """Start the tunnel and return the public HTTPS URL.

        Raises:
            RuntimeError: If the tunnel fails to start.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the tunnel. Idempotent — safe to call multiple times."""

    @abstractmethod
    def get_url(self) -> Optional[str]:
        """Return the current public URL, or None if not running."""

    @abstractmethod
    async def health_check(self) -> Tuple[bool, str]:
        """Check if the tunnel is healthy.

        Returns:
            Tuple of (is_healthy, status_message).
        """

    @abstractmethod
    def get_status(self) -> Dict:
        """Return a status dict for admin/health endpoints.

        Must include at least:
            - provider: str
            - active: bool
            - url: Optional[str]
            - provides_stable_url: bool
        """
