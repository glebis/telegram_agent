"""Tailscale Funnel tunnel provider — uses tailscale CLI."""

import asyncio
import json
import logging
import os
import shutil
from typing import Dict, Optional, Tuple

from .base import TunnelProvider

logger = logging.getLogger(__name__)


class TailscaleTunnelProvider(TunnelProvider):
    """Tunnel provider using Tailscale Funnel.

    Uses `tailscale funnel <port>` to expose a local port to the internet
    and `tailscale status --json` to determine the public URL.
    """

    def __init__(self, port: int = 8000):
        self._port = port
        self._process: Optional[asyncio.subprocess.Process] = None
        self._url: Optional[str] = None
        self._hostname = os.getenv("TAILSCALE_HOSTNAME")

    @property
    def name(self) -> str:
        return "tailscale"

    @property
    def provides_stable_url(self) -> bool:
        return True

    async def _get_tailscale_url(self) -> Optional[str]:
        """Get the HTTPS funnel URL from tailscale status."""
        if self._hostname:
            return f"https://{self._hostname}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "tailscale",
                "status",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            data = json.loads(stdout.decode())

            # Get the DNS name for this machine
            self_node = data.get("Self", {})
            dns_name = self_node.get("DNSName", "")
            if dns_name:
                # Remove trailing dot
                hostname = dns_name.rstrip(".")
                return f"https://{hostname}"
        except Exception as e:
            logger.error(f"Failed to get tailscale URL: {e}")

        return None

    async def start(self) -> str:
        if not shutil.which("tailscale"):
            raise RuntimeError(
                "tailscale CLI not found. Install: https://tailscale.com/download"
            )

        # Start funnel in background
        logger.info(f"Starting tailscale funnel on port {self._port}")
        self._process = await asyncio.create_subprocess_exec(
            "tailscale",
            "funnel",
            str(self._port),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Give it a moment to bind
        await asyncio.sleep(2)

        # Check if process is still running
        if self._process.returncode is not None:
            stderr = b""
            if self._process.stderr:
                stderr = await self._process.stderr.read()
            raise RuntimeError(
                f"tailscale funnel exited immediately: {stderr.decode(errors='replace')}"
            )

        url = await self._get_tailscale_url()
        if not url:
            await self.stop()
            raise RuntimeError("Failed to determine tailscale funnel URL")

        self._url = url
        logger.info(f"Tailscale funnel started: {self._url}")
        return self._url

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

        # Also explicitly turn off funnel
        try:
            proc = await asyncio.create_subprocess_exec(
                "tailscale",
                "funnel",
                "off",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:
            pass  # Best effort

        self._url = None
        logger.info("Tailscale funnel stopped")

    def get_url(self) -> Optional[str]:
        return self._url

    async def health_check(self) -> Tuple[bool, str]:
        if self._process is None:
            return False, "tailscale funnel process not running"
        if self._process.returncode is not None:
            return (
                False,
                f"tailscale funnel exited with code {self._process.returncode}",
            )
        if self._url:
            return True, f"tailscale funnel healthy: {self._url}"
        return False, "tailscale funnel has no URL"

    def get_status(self) -> Dict:
        active = self._process is not None and self._process.returncode is None
        return {
            "provider": "tailscale",
            "active": active,
            "url": self._url,
            "provides_stable_url": True,
            "hostname": self._hostname,
            # Backward-compat keys
            "ngrok_active": active,
            "ngrok_url": self._url,
        }
