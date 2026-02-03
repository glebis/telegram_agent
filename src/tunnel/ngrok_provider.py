"""Ngrok tunnel provider — wraps existing NgrokManager."""

import logging
import os
from typing import Dict, Optional, Tuple

from .base import TunnelProvider

logger = logging.getLogger(__name__)


class NgrokTunnelProvider(TunnelProvider):
    """Tunnel provider using ngrok via pyngrok.

    Delegates to the existing NgrokManager in src/utils/ngrok_utils.py.
    """

    def __init__(self, port: int = 8000):
        self._port = port
        self._manager = None  # lazy init
        self._url: Optional[str] = None

    def _get_manager(self):
        if self._manager is None:
            from ..utils.ngrok_utils import NgrokManager

            self._manager = NgrokManager(
                auth_token=os.getenv("NGROK_AUTHTOKEN"),
                port=self._port,
                region=os.getenv("NGROK_REGION", "us"),
                tunnel_name=os.getenv("NGROK_TUNNEL_NAME", "telegram-agent"),
            )
        return self._manager

    @property
    def name(self) -> str:
        return "ngrok"

    @property
    def provides_stable_url(self) -> bool:
        return False

    async def start(self) -> str:
        manager = self._get_manager()
        self._url = manager.start_tunnel()
        logger.info(f"ngrok tunnel started: {self._url}")
        return self._url

    async def stop(self) -> None:
        if self._manager:
            self._manager.stop_tunnel()
            self._url = None
            logger.info("ngrok tunnel stopped")

    def get_url(self) -> Optional[str]:
        if self._manager:
            return self._manager.get_tunnel_url()
        return self._url

    async def health_check(self) -> Tuple[bool, str]:
        manager = self._get_manager()
        status = manager.get_tunnel_status()
        if status.get("active"):
            return True, f"ngrok healthy: {status.get('url')}"
        # Try the API as fallback (tunnel may have been started externally)
        from ..utils.ngrok_utils import NgrokManager as NM

        api_url = await NM.get_public_url_from_api(self._port)
        if api_url:
            self._url = api_url
            return True, f"ngrok healthy (via API): {api_url}"
        return False, "ngrok tunnel not active"

    def get_status(self) -> Dict:
        url = self.get_url()
        active = url is not None
        # If manager wasn't initialized, try API check synchronously via cached url
        return {
            "provider": "ngrok",
            "active": active,
            "url": url,
            "provides_stable_url": False,
            # Backward-compat keys
            "ngrok_active": active,
            "ngrok_url": url,
        }
