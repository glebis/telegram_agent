"""Telethon service for downloading large Telegram files (>20MB).

The Telegram Bot API has a 20MB file download limit. For larger files,
we use Telethon (MTProto client) which supports up to 2GB.

This service reuses the existing Telethon session from the transcribe-telegram-video skill.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy import to avoid loading Telethon unless needed
TelegramClient = None
_telethon_imported = False


def _import_telethon():
    """Lazy import of Telethon to avoid startup overhead."""
    global TelegramClient, _telethon_imported
    if _telethon_imported:
        return

    try:
        from telethon import TelegramClient as TC

        TelegramClient = TC
        _telethon_imported = True
    except ImportError:
        logger.error(
            "Telethon not installed. Large video downloads (>20MB) will fail. "
            "Install with: pip install telethon"
        )
        raise


class TelethonService:
    """Singleton service for downloading large files via Telethon MTProto."""

    def __init__(self):
        self._client: Optional[Any] = None
        self._lock = asyncio.Lock()
        self._config: Optional[Dict[str, Any]] = None
        self._session_path: Optional[Path] = None

    def _load_config(self) -> Dict[str, Any]:
        """Load Telethon config from transcribe-telegram-video skill location."""
        # Reuse existing config from transcribe skill
        config_path = Path.home() / ".telegram_dl" / "config.json"
        session_path = Path.home() / ".telegram_dl" / "user.session"

        if not config_path.exists():
            raise RuntimeError(
                f"Telethon config not found at {config_path}. "
                f"Run setup first: python3 ~/.claude/skills/telegram-telethon/scripts/tg.py setup"
            )

        if not session_path.exists():
            raise RuntimeError(
                f"Telethon session not found at {session_path}. "
                f"Authentication required. Run: python3 ~/.claude/skills/telegram-telethon/scripts/tg.py setup"
            )

        with open(config_path) as f:
            config = json.load(f)

        self._session_path = session_path
        return config

    async def _ensure_client(self):
        """Ensure Telethon client is connected and authenticated."""
        if self._client:
            return  # Already connected

        _import_telethon()  # Lazy import

        if not self._config:
            self._config = self._load_config()

        # Create client with existing session
        self._client = TelegramClient(
            str(self._session_path), self._config["api_id"], self._config["api_hash"]
        )

        await self._client.connect()

        if not await self._client.is_user_authorized():
            raise RuntimeError(
                "Telethon session expired or not authorized. "
                "Re-authenticate with: python3 ~/.claude/skills/telegram-telethon/scripts/tg.py setup"
            )

        logger.info("Telethon client connected and authorized")

    async def download_from_url(
        self,
        url: str,
        output_path: Path,
        timeout: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Download video from Telegram channel URL using Telethon.

        Args:
            url: Telegram message URL (e.g., https://t.me/channel/123)
            output_path: Where to save the video
            timeout: Max seconds to wait (auto-calculated if None: 2s per MB + 60s base)
            progress_callback: Called with (current_bytes, total_bytes)

        Returns:
            dict with keys: success, file_path, size_mb, error

        Example:
            >>> service = get_telethon_service()
            >>> result = await service.download_from_url(
            ...     "https://t.me/ACT_Russia/3902",
            ...     Path("/tmp/video.mp4")
            ... )
            >>> if result["success"]:
            ...     print(f"Downloaded {result['size_mb']:.1f} MB")
        """
        async with self._lock:
            try:
                await self._ensure_client()

                # Parse URL: https://t.me/ACT_Russia/3902
                parts = url.rstrip("/").split("/")
                if len(parts) < 2:
                    return {"success": False, "error": f"Invalid URL format: {url}"}

                channel_username = parts[-2]
                try:
                    msg_id = int(parts[-1])
                except ValueError:
                    return {
                        "success": False,
                        "error": f"Invalid message ID in URL: {parts[-1]}",
                    }

                # Get message
                logger.info(f"Fetching message from @{channel_username}/{msg_id}...")
                try:
                    entity = await self._client.get_entity(channel_username)
                    message = await self._client.get_messages(entity, ids=msg_id)
                except Exception as e:
                    return {"success": False, "error": f"Failed to fetch message: {e}"}

                if not message or not message.video:
                    return {"success": False, "error": "No video found in message"}

                # Calculate timeout and size
                size_mb = message.video.size / (1024 * 1024)
                if timeout is None:
                    timeout = int((size_mb * 2) + 60)  # 2s per MB + 60s base

                logger.info(
                    f"Downloading {size_mb:.1f} MB from @{channel_username}/{msg_id} (timeout: {timeout}s)..."
                )

                # Download with timeout
                try:

                    async def do_download():
                        await self._client.download_media(
                            message.video,
                            file=str(output_path),
                            progress_callback=progress_callback,
                        )

                    await asyncio.wait_for(do_download(), timeout=timeout)

                except asyncio.TimeoutError:
                    return {
                        "success": False,
                        "error": f"Download timed out after {timeout}s ({size_mb:.1f} MB)",
                    }

                # Verify file exists
                if not output_path.exists():
                    return {
                        "success": False,
                        "error": "Download completed but file not found",
                    }

                actual_size_mb = output_path.stat().st_size / (1024 * 1024)
                logger.info(f"✅ Downloaded {actual_size_mb:.1f} MB via Telethon")

                return {
                    "success": True,
                    "file_path": str(output_path),
                    "size_mb": actual_size_mb,
                    "error": None,
                }

            except Exception as e:
                logger.error(f"Telethon download failed: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    async def disconnect(self):
        """Disconnect Telethon client (cleanup)."""
        if self._client:
            await self._client.disconnect()
            self._client = None
            logger.info("Telethon client disconnected")


# Singleton instance
_service: Optional[TelethonService] = None


def get_telethon_service() -> TelethonService:
    """Get the singleton TelethonService instance."""
    global _service
    if _service is None:
        _service = TelethonService()
    return _service
