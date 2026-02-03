"""Cloudflare Tunnel provider — uses cloudflared CLI."""

import asyncio
import logging
import os
import re
import shutil
from typing import Dict, Optional, Tuple

from .base import TunnelProvider

logger = logging.getLogger(__name__)


class CloudflareTunnelProvider(TunnelProvider):
    """Tunnel provider using Cloudflare Tunnel (cloudflared).

    Two modes:
    - Named tunnel (prod): requires CF_TUNNEL_NAME + credentials.
      URL comes from WEBHOOK_BASE_URL since it's a stable domain.
    - Quick tunnel (dev): no config needed, parses trycloudflare.com URL from stdout.
    """

    def __init__(self, port: int = 8000):
        self._port = port
        self._process: Optional[asyncio.subprocess.Process] = None
        self._url: Optional[str] = None
        self._tunnel_name = os.getenv("CF_TUNNEL_NAME")
        self._credentials_file = os.getenv("CF_CREDENTIALS_FILE")
        self._config_file = os.getenv("CF_CONFIG_FILE")

    @property
    def name(self) -> str:
        return "cloudflare"

    @property
    def provides_stable_url(self) -> bool:
        return True

    def _is_named_tunnel(self) -> bool:
        return bool(self._tunnel_name and self._credentials_file)

    async def start(self) -> str:
        if not shutil.which("cloudflared"):
            raise RuntimeError(
                "cloudflared not found. Install: brew install cloudflared"
            )

        if self._is_named_tunnel():
            return await self._start_named_tunnel()
        return await self._start_quick_tunnel()

    async def _start_named_tunnel(self) -> str:
        cmd = ["cloudflared", "tunnel"]
        if self._config_file:
            cmd.extend(["--config", self._config_file])
        if self._credentials_file:
            cmd.extend(["--credentials-file", self._credentials_file])
        cmd.extend(["run", self._tunnel_name])

        logger.info(f"Starting named cloudflare tunnel: {self._tunnel_name}")
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Named tunnels use a configured domain — get from WEBHOOK_BASE_URL
        base_url = os.getenv("WEBHOOK_BASE_URL")
        if not base_url:
            raise RuntimeError(
                "WEBHOOK_BASE_URL must be set when using named Cloudflare tunnels"
            )
        self._url = base_url.rstrip("/")
        logger.info(f"Cloudflare named tunnel started: {self._url}")
        return self._url

    async def _start_quick_tunnel(self) -> str:
        cmd = [
            "cloudflared",
            "tunnel",
            "--url",
            f"http://localhost:{self._port}",
        ]

        logger.info(f"Starting cloudflare quick tunnel on port {self._port}")
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Parse the trycloudflare.com URL from stderr
        # cloudflared outputs the URL line to stderr
        url = await self._parse_quick_tunnel_url(timeout=30)
        if not url:
            await self.stop()
            raise RuntimeError(
                "Failed to parse cloudflare quick tunnel URL from output"
            )

        self._url = url
        logger.info(f"Cloudflare quick tunnel started: {self._url}")
        return self._url

    async def _parse_quick_tunnel_url(self, timeout: int = 30) -> Optional[str]:
        """Read cloudflared stderr to find the trycloudflare.com URL."""
        pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

        try:
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                if self._process is None or self._process.stderr is None:
                    return None
                try:
                    line = await asyncio.wait_for(
                        self._process.stderr.readline(), timeout=5
                    )
                except asyncio.TimeoutError:
                    continue

                if not line:
                    if self._process.returncode is not None:
                        return None
                    continue

                decoded = line.decode("utf-8", errors="replace")
                logger.debug(f"cloudflared: {decoded.strip()}")
                match = pattern.search(decoded)
                if match:
                    return match.group(0)
        except Exception as e:
            logger.error(f"Error parsing cloudflare tunnel URL: {e}")

        return None

    async def stop(self) -> None:
        if self._process:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass
            self._process = None
            self._url = None
            logger.info("Cloudflare tunnel stopped")

    def get_url(self) -> Optional[str]:
        return self._url

    async def health_check(self) -> Tuple[bool, str]:
        if self._process is None:
            return False, "cloudflared process not running"
        if self._process.returncode is not None:
            return False, f"cloudflared exited with code {self._process.returncode}"
        if self._url:
            return True, f"cloudflare tunnel healthy: {self._url}"
        return False, "cloudflare tunnel has no URL"

    def get_status(self) -> Dict:
        active = self._process is not None and self._process.returncode is None
        return {
            "provider": "cloudflare",
            "active": active,
            "url": self._url,
            "provides_stable_url": True,
            "mode": "named" if self._is_named_tunnel() else "quick",
            "tunnel_name": self._tunnel_name,
            # Backward-compat keys
            "ngrok_active": active,
            "ngrok_url": self._url,
        }
