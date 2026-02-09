"""
Tests for upload MIME type validation — pre-download checks using Telegram metadata.

Covers:
- Valid MIME types accepted for each handler category
- Invalid/mismatched MIME types rejected
- Edge cases: missing MIME type, unknown handler, prefix matching
- Integration with MessageBuffer._create_buffered_message
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.media_validator import validate_upload_mime_type

# ---------------------------------------------------------------------------
# Unit tests for validate_upload_mime_type
# ---------------------------------------------------------------------------


class TestVoiceMimeValidation:
    """Voice handler accepts audio/* and video/ogg."""

    def test_audio_ogg_accepted(self):
        result = validate_upload_mime_type("audio/ogg", None, "voice")
        assert result.valid
        assert result.handler == "voice"

    def test_video_ogg_accepted(self):
        """Telegram voice notes use video/ogg with opus codec."""
        result = validate_upload_mime_type("video/ogg", None, "voice")
        assert result.valid

    def test_audio_mpeg_accepted(self):
        result = validate_upload_mime_type("audio/mpeg", None, "voice")
        assert result.valid

    def test_audio_mp4_accepted(self):
        result = validate_upload_mime_type("audio/mp4", None, "voice")
        assert result.valid

    def test_audio_wav_accepted(self):
        result = validate_upload_mime_type("audio/wav", None, "voice")
        assert result.valid

    def test_audio_webm_accepted(self):
        result = validate_upload_mime_type("audio/webm", None, "voice")
        assert result.valid

    def test_audio_prefix_fallback(self):
        """Unknown audio subtype should still be accepted via prefix match."""
        result = validate_upload_mime_type("audio/x-custom-format", None, "voice")
        assert result.valid

    def test_image_rejected_for_voice(self):
        result = validate_upload_mime_type("image/jpeg", None, "voice")
        assert not result.valid
        assert "voice" in result.reason

    def test_application_pdf_rejected_for_voice(self):
        result = validate_upload_mime_type("application/pdf", None, "voice")
        assert not result.valid

    def test_video_mp4_rejected_for_voice(self):
        """video/mp4 is not acceptable for voice (only video/ogg is)."""
        result = validate_upload_mime_type("video/mp4", None, "voice")
        assert not result.valid


class TestPhotoMimeValidation:
    """Photo handler accepts image/*."""

    def test_image_jpeg_accepted(self):
        result = validate_upload_mime_type("image/jpeg", None, "photo")
        assert result.valid

    def test_image_png_accepted(self):
        result = validate_upload_mime_type("image/png", None, "photo")
        assert result.valid

    def test_image_webp_accepted(self):
        result = validate_upload_mime_type("image/webp", None, "photo")
        assert result.valid

    def test_image_gif_accepted(self):
        result = validate_upload_mime_type("image/gif", None, "photo")
        assert result.valid

    def test_image_heic_accepted(self):
        result = validate_upload_mime_type("image/heic", None, "photo")
        assert result.valid

    def test_image_prefix_fallback(self):
        """Unknown image subtype should still be accepted via prefix match."""
        result = validate_upload_mime_type("image/x-custom", None, "photo")
        assert result.valid

    def test_audio_rejected_for_photo(self):
        result = validate_upload_mime_type("audio/mpeg", None, "photo")
        assert not result.valid
        assert "photo" in result.reason

    def test_application_rejected_for_photo(self):
        result = validate_upload_mime_type("application/pdf", None, "photo")
        assert not result.valid


class TestVideoMimeValidation:
    """Video handler accepts video/*."""

    def test_video_mp4_accepted(self):
        result = validate_upload_mime_type("video/mp4", None, "video")
        assert result.valid

    def test_video_quicktime_accepted(self):
        result = validate_upload_mime_type("video/quicktime", None, "video")
        assert result.valid

    def test_video_webm_accepted(self):
        result = validate_upload_mime_type("video/webm", None, "video")
        assert result.valid

    def test_video_prefix_fallback(self):
        """Unknown video subtype should still be accepted via prefix match."""
        result = validate_upload_mime_type("video/x-custom", None, "video")
        assert result.valid

    def test_audio_rejected_for_video(self):
        result = validate_upload_mime_type("audio/mpeg", None, "video")
        assert not result.valid

    def test_image_rejected_for_video(self):
        result = validate_upload_mime_type("image/jpeg", None, "video")
        assert not result.valid


class TestDocumentMimeValidation:
    """Document handler accepts a wide range of types."""

    def test_application_pdf_accepted(self):
        result = validate_upload_mime_type("application/pdf", None, "document")
        assert result.valid

    def test_text_plain_accepted(self):
        result = validate_upload_mime_type("text/plain", None, "document")
        assert result.valid

    def test_text_csv_accepted(self):
        result = validate_upload_mime_type("text/csv", None, "document")
        assert result.valid

    def test_application_json_accepted(self):
        result = validate_upload_mime_type("application/json", None, "document")
        assert result.valid

    def test_application_zip_accepted(self):
        result = validate_upload_mime_type("application/zip", None, "document")
        assert result.valid

    def test_application_octet_stream_accepted(self):
        """Generic binary type is allowed for documents."""
        result = validate_upload_mime_type("application/octet-stream", None, "document")
        assert result.valid

    def test_docx_accepted(self):
        result = validate_upload_mime_type(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document",
            None,
            "document",
        )
        assert result.valid

    def test_image_rejected_for_document(self):
        """Image MIME should not be processed as a generic document."""
        result = validate_upload_mime_type("image/jpeg", None, "document")
        assert not result.valid

    def test_video_rejected_for_document(self):
        result = validate_upload_mime_type("video/mp4", None, "document")
        assert not result.valid


class TestEdgeCases:
    """Edge cases: missing MIME, filename inference, etc."""

    def test_missing_mime_type_allowed(self):
        """Telegram sometimes omits MIME type -- be permissive."""
        result = validate_upload_mime_type(None, None, "voice")
        assert result.valid

    def test_missing_mime_with_filename_inference(self):
        """When MIME is missing, infer from filename extension."""
        result = validate_upload_mime_type(None, "recording.ogg", "voice")
        assert result.valid

    def test_missing_mime_filename_mismatch(self):
        """When MIME is inferred from filename and mismatches handler, reject."""
        result = validate_upload_mime_type(None, "photo.jpg", "voice")
        assert not result.valid

    def test_case_insensitive_mime(self):
        """MIME type comparison should be case-insensitive."""
        result = validate_upload_mime_type("Audio/OGG", None, "voice")
        assert result.valid

    def test_unknown_handler_allowed(self):
        """Unknown handler category should be permissive."""
        result = validate_upload_mime_type("anything/goes", None, "unknown_handler")
        assert result.valid

    def test_empty_string_mime_treated_as_missing(self):
        """Empty string MIME should be treated same as None (permissive)."""
        result = validate_upload_mime_type("", None, "voice")
        assert result.valid

    def test_result_contains_handler_info(self):
        """Result should contain the handler that was checked."""
        result = validate_upload_mime_type("audio/ogg", None, "voice")
        assert result.handler == "voice"

    def test_result_contains_mime_type(self):
        """Result should contain the MIME type that was checked."""
        result = validate_upload_mime_type("audio/ogg", None, "voice")
        assert result.mime_type == "audio/ogg"

    def test_rejection_reason_informative(self):
        """Rejection reason should mention both MIME type and handler."""
        result = validate_upload_mime_type("image/jpeg", None, "voice")
        assert not result.valid
        assert "image/jpeg" in result.reason
        assert "voice" in result.reason


# ---------------------------------------------------------------------------
# Integration tests: MessageBuffer._create_buffered_message
# ---------------------------------------------------------------------------


class TestMessageBufferMimeIntegration:
    """Test MIME validation wiring in MessageBuffer._create_buffered_message."""

    def _make_message_mock(
        self,
        msg_type="document",
        mime_type="application/pdf",
        file_name="report.pdf",
        file_id="file_abc123",
    ):
        """Create a minimal Telegram Message mock."""
        message = MagicMock()
        message.message_id = 42
        message.caption = None
        message.media_group_id = None
        message.chat = MagicMock()
        message.chat.id = 123

        # Clear all media attributes
        message.text = None
        message.photo = None
        message.voice = None
        message.audio = None
        message.video = None
        message.video_note = None
        message.document = None
        message.contact = None
        message.poll = None
        message.sticker = None
        message.animation = None
        message.forward_origin = None

        if msg_type == "document":
            message.document = MagicMock()
            message.document.file_id = file_id
            message.document.mime_type = mime_type
            message.document.file_name = file_name
        elif msg_type == "voice":
            message.voice = MagicMock()
            message.voice.file_id = file_id
            message.voice.mime_type = mime_type
            message.voice.file_name = None
        elif msg_type == "audio":
            message.audio = MagicMock()
            message.audio.file_id = file_id
            message.audio.mime_type = mime_type
            message.audio.file_name = file_name
        elif msg_type == "video":
            message.video = MagicMock()
            message.video.file_id = file_id
            message.video.mime_type = mime_type
            message.video.file_name = file_name

        return message

    def test_valid_document_accepted(self):
        """A PDF document should pass MIME validation."""
        from src.services.message_buffer import MessageBufferService

        buffer = MessageBufferService()
        update = MagicMock()
        context = MagicMock()
        message = self._make_message_mock(
            msg_type="document",
            mime_type="application/pdf",
            file_name="report.pdf",
        )

        buffered, rejection = buffer._create_buffered_message(update, context, message)
        assert buffered is not None
        assert rejection is None
        assert buffered.message_type == "document"

    def test_valid_voice_accepted(self):
        """A voice message with audio/ogg should pass."""
        from src.services.message_buffer import MessageBufferService

        buffer = MessageBufferService()
        update = MagicMock()
        context = MagicMock()
        message = self._make_message_mock(
            msg_type="voice",
            mime_type="audio/ogg",
        )

        buffered, rejection = buffer._create_buffered_message(update, context, message)
        assert buffered is not None
        assert rejection is None
        assert buffered.message_type == "voice"

    def test_mismatched_mime_rejected(self):
        """An exe file claiming to be a document should be rejected."""
        from src.services.message_buffer import MessageBufferService

        buffer = MessageBufferService()
        update = MagicMock()
        context = MagicMock()
        message = self._make_message_mock(
            msg_type="document",
            mime_type="image/jpeg",
            file_name="photo.jpg",
        )
        # The message_buffer classifies image/* documents as "photo"
        # so this will be routed to the photo handler correctly.
        # Let's test a genuinely mismatched case instead:
        # an executable claiming to be a document.
        message.document.mime_type = "application/x-executable"
        message.document.file_name = "malware.exe"

        buffered, rejection = buffer._create_buffered_message(update, context, message)
        assert buffered is None
        assert rejection is not None
        assert "application/x-executable" in rejection

    def test_audio_as_voice_accepted(self):
        """Audio files are treated as voice — their MIME should be validated."""
        from src.services.message_buffer import MessageBufferService

        buffer = MessageBufferService()
        update = MagicMock()
        context = MagicMock()
        message = self._make_message_mock(
            msg_type="audio",
            mime_type="audio/mpeg",
            file_name="recording.mp3",
        )

        buffered, rejection = buffer._create_buffered_message(update, context, message)
        assert buffered is not None
        assert rejection is None
        assert buffered.message_type == "voice"

    def test_video_accepted(self):
        """A video/mp4 file should pass MIME validation."""
        from src.services.message_buffer import MessageBufferService

        buffer = MessageBufferService()
        update = MagicMock()
        context = MagicMock()
        message = self._make_message_mock(
            msg_type="video",
            mime_type="video/mp4",
            file_name="clip.mp4",
        )

        buffered, rejection = buffer._create_buffered_message(update, context, message)
        assert buffered is not None
        assert rejection is None
        assert buffered.message_type == "video"

    def test_text_message_not_validated(self):
        """Text messages should not go through MIME validation."""
        from src.services.message_buffer import MessageBufferService

        buffer = MessageBufferService()
        update = MagicMock()
        context = MagicMock()
        message = self._make_message_mock()
        # Override to be a text message
        message.document = None
        message.text = "Hello world"

        buffered, rejection = buffer._create_buffered_message(update, context, message)
        assert buffered is not None
        assert rejection is None
        assert buffered.message_type == "text"

    @pytest.mark.asyncio
    async def test_add_message_sends_rejection_reply(self):
        """When MIME validation fails, add_message should reply to the user."""
        from src.services.message_buffer import MessageBufferService

        buffer = MessageBufferService()
        update = MagicMock()
        update.message = self._make_message_mock(
            msg_type="document",
            mime_type="application/x-executable",
            file_name="malware.exe",
        )
        update.message.reply_text = AsyncMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 123
        update.effective_user = MagicMock()
        update.effective_user.id = 456

        result = await buffer.add_message(update, MagicMock())
        assert result is False
        update.message.reply_text.assert_called_once()
        rejection_text = update.message.reply_text.call_args[0][0]
        assert "application/x-executable" in rejection_text
