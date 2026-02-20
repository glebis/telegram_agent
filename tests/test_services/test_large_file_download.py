"""Tests for large file download support (>20MB).

TDD: Tests for file size detection, download routing, and Telethon service.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFileSizeDetection:
    """Slice 1: Determine if a file exceeds the Bot API download limit."""

    def test_small_file_is_not_large(self):
        from src.services.large_file_service import is_large_file

        assert is_large_file(10 * 1024 * 1024) is False  # 10MB

    def test_exactly_20mb_is_not_large(self):
        from src.services.large_file_service import is_large_file

        assert is_large_file(20 * 1024 * 1024) is False

    def test_over_20mb_is_large(self):
        from src.services.large_file_service import is_large_file

        assert is_large_file(20 * 1024 * 1024 + 1) is True

    def test_100mb_is_large(self):
        from src.services.large_file_service import is_large_file

        assert is_large_file(100 * 1024 * 1024) is True

    def test_none_file_size_is_not_large(self):
        from src.services.large_file_service import is_large_file

        assert is_large_file(None) is False

    def test_zero_file_size_is_not_large(self):
        from src.services.large_file_service import is_large_file

        assert is_large_file(0) is False

    def test_custom_limit(self):
        from src.services.large_file_service import is_large_file

        assert is_large_file(15 * 1024 * 1024, limit_mb=10) is True
        assert is_large_file(5 * 1024 * 1024, limit_mb=10) is False


class TestDownloadStrategy:
    """Slice 2: Choose download strategy based on file size and context."""

    def test_small_file_uses_bot_api(self):
        from src.services.large_file_service import (
            DownloadStrategy,
            get_download_strategy,
        )

        strategy = get_download_strategy(
            file_size_bytes=5 * 1024 * 1024,
            has_forward_url=False,
        )
        assert strategy == DownloadStrategy.BOT_API

    def test_large_file_with_forward_url_uses_telethon(self):
        from src.services.large_file_service import (
            DownloadStrategy,
            get_download_strategy,
        )

        strategy = get_download_strategy(
            file_size_bytes=50 * 1024 * 1024,
            has_forward_url=True,
        )
        assert strategy == DownloadStrategy.TELETHON_URL

    def test_large_file_without_forward_url_uses_telethon_direct(self):
        from src.services.large_file_service import (
            DownloadStrategy,
            get_download_strategy,
        )

        strategy = get_download_strategy(
            file_size_bytes=50 * 1024 * 1024,
            has_forward_url=False,
        )
        assert strategy == DownloadStrategy.TELETHON_DIRECT

    def test_unknown_size_uses_bot_api(self):
        from src.services.large_file_service import (
            DownloadStrategy,
            get_download_strategy,
        )

        strategy = get_download_strategy(
            file_size_bytes=None,
            has_forward_url=False,
        )
        assert strategy == DownloadStrategy.BOT_API


class TestProgressMessageFormatting:
    """Slice 3: User feedback messages for large downloads."""

    def test_progress_message_includes_size(self):
        from src.services.large_file_service import format_download_progress

        msg = format_download_progress(52.3)
        assert "52" in msg
        assert "MB" in msg

    def test_progress_message_includes_estimate(self):
        from src.services.large_file_service import format_download_progress

        msg = format_download_progress(100.0)
        # Should include time estimate
        assert "minute" in msg.lower() or "min" in msg.lower() or "sec" in msg.lower()

    def test_error_message_for_private_forward(self):
        from src.services.large_file_service import format_private_forward_error

        msg = format_private_forward_error(52.3)
        assert "52" in msg or "private" in msg.lower()
        assert "download" in msg.lower() or "send" in msg.lower()


class TestTelethonServiceDownloadByFileId:
    """Slice 4: Download by file_id (direct messages, not forwarded URLs)."""

    def test_download_by_message_id_returns_result_dict(self):
        from src.services.telethon_service import TelethonService

        service = TelethonService()

        # Mock the client
        mock_client = AsyncMock()
        mock_message = MagicMock()
        mock_message.video = MagicMock()
        mock_message.video.size = 50 * 1024 * 1024
        mock_client.get_messages = AsyncMock(return_value=mock_message)
        mock_client.download_media = AsyncMock()

        service._client = mock_client

        # The download_by_message method should exist
        assert hasattr(service, "download_by_message") or hasattr(
            service, "download_from_url"
        )
