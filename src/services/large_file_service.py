"""Large file download service.

Provides routing logic for downloading files that exceed the
Telegram Bot API 20MB limit. Routes to Telethon (MTProto) for
large files, Bot API for small ones.
"""

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

BOT_API_LIMIT_MB = 20


class DownloadStrategy(Enum):
    """Download method selection."""

    BOT_API = "bot_api"
    TELETHON_URL = "telethon_url"
    TELETHON_DIRECT = "telethon_direct"


def is_large_file(
    file_size_bytes: Optional[int], limit_mb: int = BOT_API_LIMIT_MB
) -> bool:
    """Check if a file exceeds the Bot API download limit.

    Args:
        file_size_bytes: File size in bytes (None = unknown, treated as small).
        limit_mb: Size limit in megabytes.

    Returns:
        True if file is larger than the limit.
    """
    if not file_size_bytes:
        return False
    return file_size_bytes > limit_mb * 1024 * 1024


def get_download_strategy(
    file_size_bytes: Optional[int],
    has_forward_url: bool = False,
) -> DownloadStrategy:
    """Choose the best download strategy based on file size and context.

    Args:
        file_size_bytes: File size in bytes (None = unknown).
        has_forward_url: Whether the message has a public forwarded URL.

    Returns:
        The recommended download strategy.
    """
    if not is_large_file(file_size_bytes):
        return DownloadStrategy.BOT_API

    if has_forward_url:
        return DownloadStrategy.TELETHON_URL

    return DownloadStrategy.TELETHON_DIRECT


def format_download_progress(size_mb: float) -> str:
    """Format a user-facing download progress message.

    Args:
        size_mb: File size in megabytes.

    Returns:
        Formatted message string.
    """
    est_seconds = int(size_mb * 2) + 60
    if est_seconds >= 120:
        est_str = f"~{est_seconds // 60} minutes"
    else:
        est_str = f"~{est_seconds} seconds"

    return (
        f"📥 Downloading {size_mb:.1f}MB video via Telethon...\n"
        f"⏱️ Estimated time: {est_str}"
    )


def format_private_forward_error(size_mb: float) -> str:
    """Format error message when a large file is from a private source.

    Args:
        size_mb: File size in megabytes.

    Returns:
        Formatted error message with workaround instructions.
    """
    return (
        f"⚠️ Cannot download this {size_mb:.1f}MB video: "
        f"forwarded from private chat.\n\n"
        f"To process:\n"
        f"1️⃣ Download it to your device\n"
        f"2️⃣ Send it directly to me (not as forward)"
    )
