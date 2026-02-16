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
        # Log to file instead of PIPE to avoid buffer deadlock
        log_path = os.path.join(
            os.getenv("PROJECT_ROOT", "."), "logs", "cloudflared.log"
        )
        log_file = open(log_path, "a")
        self._log_file = log_file
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=log_file,
            stderr=log_file,
        )

        # Wait for tunnel to establish connection
        await asyncio.sleep(5)

        # Verify process is still running
        if self._process.returncode is not None:
            raise RuntimeError(
                f"cloudflared exited with code {self._process.returncode}"
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
            if hasattr(self, "_log_file") and self._log_file:
                self._log_file.close()
                self._log_file = None
            logger.info("Cloudflare tunnel stopped")

    def get_url(self) -> Optional[str]:
        return self._url

    async def restart(self) -> str:
        """Restart the tunnel without affecting the bot.

        Returns:
            The tunnel URL after restart

        Raises:
            RuntimeError: If restart fails
        """
        logger.info("Restarting cloudflare tunnel...")
        await self.stop()
        await asyncio.sleep(2)  # Brief pause before restart
        return await self.start()

    async def health_check(self) -> Tuple[bool, str]:
        """Check if tunnel is healthy.

        Checks:
        1. Process is running
        2. Process hasn't exited
        3. URL is available
        4. (Named tunnels only) Recent log errors

        Returns:
            Tuple of (is_healthy, status_message)
        """
        if self._process is None:
            return False, "cloudflared process not running"
        if self._process.returncode is not None:
            return False, f"cloudflared exited with code {self._process.returncode}"

        # For named tunnels, check for recent connection errors in logs
        if self._is_named_tunnel():
            recent_errors = await self._check_recent_log_errors()
            if recent_errors > 5:  # Threshold: 5 errors in last 2 minutes
                return False, f"Connection issues ({recent_errors} recent errors)"

        if self._url:
            return True, f"cloudflare tunnel healthy: {self._url}"
        return False, "cloudflare tunnel has no URL"

    async def _check_recent_log_errors(self, lookback_seconds: int = 120) -> int:
        """Count recent connection errors in cloudflared.log.

        Args:
            lookback_seconds: How far back to check (default: 2 minutes)

        Returns:
            Number of errors found in the lookback period
        """
        log_path = os.path.join(
            os.getenv("PROJECT_ROOT", "."), "logs", "cloudflared.log"
        )

        if not os.path.exists(log_path):
            return 0

        try:
            import time

            cutoff_time = time.time() - lookback_seconds
            error_count = 0

            # Read last 100 lines of log
            with open(log_path, "r") as f:
                # Seek to end and read backwards
                lines = f.readlines()[-100:]

            # Look for error patterns
            error_patterns = [
                "Connection terminated",
                "Unable to establish connection",
                "connection error",
                "Failed to connect",
                "authentication failed",
            ]

            for line in lines:
                # Check if line contains error pattern
                line_lower = line.lower()
                if any(pattern.lower() in line_lower for pattern in error_patterns):
                    # Try to extract timestamp (cloudflared logs include ISO timestamps)
                    # Format: 2026-02-15T19:22:00Z
                    import re
                    from datetime import datetime

                    timestamp_match = re.search(
                        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line
                    )
                    if timestamp_match:
                        try:
                            timestamp_str = timestamp_match.group(1)
                            dt = datetime.fromisoformat(timestamp_str)
                            if dt.timestamp() >= cutoff_time:
                                error_count += 1
                        except (ValueError, AttributeError):
                            # If we can't parse timestamp, count it anyway
                            error_count += 1
                    else:
                        # No timestamp found, count it anyway (assume recent)
                        error_count += 1

            return error_count

        except Exception as e:
            logger.debug(f"Error checking cloudflared logs: {e}")
            return 0  # Assume healthy if we can't read logs

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
