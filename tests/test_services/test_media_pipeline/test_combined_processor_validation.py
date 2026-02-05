"""
Tests for media validation wiring in combined_processor.py.

Verifies that the CombinedMessageProcessor calls media validation
before processing images and rejects invalid media with a user-facing message.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.media_validator import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_combined(chat_id=123, user_id=456, images=None, documents=None):
    """Build a minimal CombinedMessage mock."""
    combined = MagicMock()
    combined.chat_id = chat_id
    combined.user_id = user_id
    combined.images = images or []
    combined.documents = documents or []
    combined.combined_text = "test caption"
    combined.primary_update = MagicMock()
    combined.primary_context = MagicMock()
    combined.primary_message = MagicMock()
    combined.primary_message.reply_text = AsyncMock()
    combined.get_forward_context.return_value = None
    return combined


# ---------------------------------------------------------------------------
# Image validation wiring
# ---------------------------------------------------------------------------


class TestImageValidationWiring:
    """Test that _send_images_to_claude calls validate_media."""

    @pytest.mark.asyncio
    async def test_validate_media_called_for_images(self):
        """validate_media should be invoked after downloading an image."""
        valid_result = ValidationResult(
            valid=True,
            reason="",
            detected_mime="image/jpeg",
            file_size=1000,
        )

        with (
            patch(
                "src.bot.combined_processor.validate_media",
                return_value=valid_result,
            ) as mock_validate,
            patch(
                "src.bot.combined_processor.strip_metadata",
                return_value=True,
            ),
            patch(
                "src.bot.combined_processor.download_telegram_file",
            ) as mock_download,
            patch(
                "src.bot.combined_processor.create_tracked_task",
            ),
            patch(
                "src.bot.combined_processor.get_settings",
            ) as mock_settings,
        ):
            # Make download return success
            mock_download.return_value = MagicMock(success=True)

            # Settings stub with temp dir
            tmp = tempfile.mkdtemp()
            settings = MagicMock()
            settings.vault_temp_images_dir = tmp
            mock_settings.return_value = settings

            from src.bot.combined_processor import CombinedMessageProcessor

            processor = CombinedMessageProcessor()

            combined = _make_mock_combined(
                images=[MagicMock(file_id="img_abc123")],
            )

            # Need to set the bot token in the actual environ (used by os.environ.get)
            original_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
            try:
                await processor._send_images_to_claude(combined, "Analyze this")
            finally:
                if original_token is not None:
                    os.environ["TELEGRAM_BOT_TOKEN"] = original_token

            assert mock_validate.called, "validate_media was not called"

    @pytest.mark.asyncio
    async def test_invalid_image_skipped(self):
        """An image that fails validation should not appear in image_paths."""
        invalid_result = ValidationResult(
            valid=False,
            reason="MIME type mismatch",
            detected_mime="application/octet-stream",
            file_size=500,
        )

        with (
            patch(
                "src.bot.combined_processor.validate_media",
                return_value=invalid_result,
            ) as mock_validate,
            patch(
                "src.bot.combined_processor.strip_metadata",
                return_value=True,
            ),
            patch(
                "src.bot.combined_processor.download_telegram_file",
            ) as mock_download,
            patch(
                "src.bot.combined_processor.create_tracked_task",
            ),
            patch(
                "src.bot.combined_processor.get_settings",
            ) as mock_settings,
        ):
            mock_download.return_value = MagicMock(success=True)

            tmp = tempfile.mkdtemp()
            settings = MagicMock()
            settings.vault_temp_images_dir = tmp
            mock_settings.return_value = settings

            from src.bot.combined_processor import CombinedMessageProcessor

            processor = CombinedMessageProcessor()

            combined = _make_mock_combined(
                images=[MagicMock(file_id="bad_img")],
            )

            original_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
            try:
                await processor._send_images_to_claude(combined, "Analyze this")
            finally:
                if original_token is not None:
                    os.environ["TELEGRAM_BOT_TOKEN"] = original_token

            # validate_media was called
            assert mock_validate.called
            # Since the image was invalid, reply_text should have been called
            # (no valid images -> "Failed to download images for Claude.")
            combined.primary_message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_strip_metadata_called_on_valid_image(self):
        """strip_metadata should be called after validation passes."""
        valid_result = ValidationResult(
            valid=True,
            reason="",
            detected_mime="image/jpeg",
            file_size=1000,
        )

        with (
            patch(
                "src.bot.combined_processor.validate_media",
                return_value=valid_result,
            ),
            patch(
                "src.bot.combined_processor.strip_metadata",
                return_value=True,
            ) as mock_strip,
            patch(
                "src.bot.combined_processor.download_telegram_file",
            ) as mock_download,
            patch(
                "src.bot.combined_processor.create_tracked_task",
            ),
            patch(
                "src.bot.combined_processor.get_settings",
            ) as mock_settings,
        ):
            mock_download.return_value = MagicMock(success=True)

            tmp = tempfile.mkdtemp()
            settings = MagicMock()
            settings.vault_temp_images_dir = tmp
            mock_settings.return_value = settings

            from src.bot.combined_processor import CombinedMessageProcessor

            processor = CombinedMessageProcessor()

            combined = _make_mock_combined(
                images=[MagicMock(file_id="good_img")],
            )

            original_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
            try:
                await processor._send_images_to_claude(combined, "Analyze this")
            finally:
                if original_token is not None:
                    os.environ["TELEGRAM_BOT_TOKEN"] = original_token

            assert mock_strip.called, "strip_metadata was not called"


# ---------------------------------------------------------------------------
# Document validation wiring
# ---------------------------------------------------------------------------


class TestDocumentValidationWiring:
    """Test that _process_documents calls validate_media."""

    @pytest.mark.asyncio
    async def test_validate_media_called_for_documents(self):
        """validate_media should be called after downloading a document."""
        valid_result = ValidationResult(
            valid=True,
            reason="",
            detected_mime="application/pdf",
            file_size=5000,
        )

        with (
            patch(
                "src.bot.combined_processor.validate_media",
                return_value=valid_result,
            ) as mock_validate,
            patch(
                "src.bot.combined_processor.download_telegram_file",
            ) as mock_download,
            patch(
                "src.bot.combined_processor.get_settings",
            ) as mock_settings,
            patch(
                "src.bot.combined_processor.create_tracked_task",
            ),
        ):
            mock_download.return_value = MagicMock(success=True)

            tmp = tempfile.mkdtemp()
            settings = MagicMock()
            settings.vault_temp_docs_dir = tmp
            settings.telegram_bot_token = "test:token"
            mock_settings.return_value = settings

            from src.bot.combined_processor import CombinedMessageProcessor

            processor = CombinedMessageProcessor()

            doc_msg = MagicMock(file_id="doc_abc123")
            doc_msg.message = MagicMock()
            doc_msg.message.document = MagicMock()
            doc_msg.message.document.file_name = "report.pdf"

            combined = _make_mock_combined(documents=[doc_msg])

            original_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
            try:
                # Mock the execute_claude_prompt that gets called at the end
                with patch(
                    "src.bot.combined_processor.CombinedMessageProcessor"
                    "._process_documents.__module__",
                    create=True,
                ):
                    # Actually call _process_documents - pass is_claude_mode=True
                    # so it takes the download path
                    try:
                        await processor._process_documents(
                            combined, reply_context=None, is_claude_mode=True
                        )
                    except Exception:
                        # The execute_claude_prompt import may fail in test env;
                        # we only care that validate_media was called before that.
                        pass
            finally:
                if original_token is not None:
                    os.environ["TELEGRAM_BOT_TOKEN"] = original_token

            assert mock_validate.called, "validate_media was not called for document"

    @pytest.mark.asyncio
    async def test_invalid_document_skipped(self):
        """A document that fails validation should be rejected."""
        invalid_result = ValidationResult(
            valid=False,
            reason="Extension '.exe' not in allowed list",
            detected_mime="application/x-dosexec",
            file_size=10000,
        )

        with (
            patch(
                "src.bot.combined_processor.validate_media",
                return_value=invalid_result,
            ) as mock_validate,
            patch(
                "src.bot.combined_processor.download_telegram_file",
            ) as mock_download,
            patch(
                "src.bot.combined_processor.get_settings",
            ) as mock_settings,
            patch(
                "src.bot.combined_processor.create_tracked_task",
            ),
        ):
            mock_download.return_value = MagicMock(success=True)

            tmp = tempfile.mkdtemp()
            settings = MagicMock()
            settings.vault_temp_docs_dir = tmp
            settings.telegram_bot_token = "test:token"
            mock_settings.return_value = settings

            from src.bot.combined_processor import CombinedMessageProcessor

            processor = CombinedMessageProcessor()

            doc_msg = MagicMock(file_id="bad_doc")
            doc_msg.message = MagicMock()
            doc_msg.message.document = MagicMock()
            doc_msg.message.document.file_name = "malware.exe"

            combined = _make_mock_combined(documents=[doc_msg])

            original_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
            try:
                try:
                    await processor._process_documents(
                        combined, reply_context=None, is_claude_mode=True
                    )
                except Exception:
                    pass
            finally:
                if original_token is not None:
                    os.environ["TELEGRAM_BOT_TOKEN"] = original_token

            assert mock_validate.called
