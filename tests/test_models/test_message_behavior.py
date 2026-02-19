"""
Tests for Message model domain behavior methods.

These test pure domain logic on model instances — no database needed.
"""

import pytest

from src.models.message import Message


class TestMessageGetContent:
    """Tests for Message.get_content() — returns text or caption."""

    def test_returns_text_when_present(self):
        msg = Message(
            chat_id=1, message_id=1, message_type="text", text="hello", caption=None
        )
        assert msg.get_content() == "hello"

    def test_returns_caption_when_no_text(self):
        msg = Message(
            chat_id=1,
            message_id=1,
            message_type="photo",
            text=None,
            caption="a photo",
        )
        assert msg.get_content() == "a photo"

    def test_prefers_text_over_caption(self):
        msg = Message(
            chat_id=1,
            message_id=1,
            message_type="text",
            text="main text",
            caption="caption text",
        )
        assert msg.get_content() == "main text"

    def test_returns_empty_string_when_neither(self):
        msg = Message(
            chat_id=1, message_id=1, message_type="voice", text=None, caption=None
        )
        assert msg.get_content() == ""


class TestMessageIsFromBot:
    """Tests for Message.is_from_bot()."""

    def test_false_by_default(self):
        msg = Message(chat_id=1, message_id=1, message_type="text")
        assert msg.is_from_bot() is False

    def test_true_when_set(self):
        msg = Message(
            chat_id=1, message_id=1, message_type="text", is_bot_message=True
        )
        assert msg.is_from_bot() is True


class TestMessageIsAdminSent:
    """Tests for Message.is_admin_sent()."""

    def test_false_by_default(self):
        msg = Message(chat_id=1, message_id=1, message_type="text")
        assert msg.is_admin_sent() is False

    def test_true_when_set(self):
        msg = Message(
            chat_id=1,
            message_id=1,
            message_type="text",
            admin_sent=True,
            admin_user="admin1",
        )
        assert msg.is_admin_sent() is True


class TestMessageIsMediaType:
    """Tests for Message.is_media_type()."""

    def test_photo_is_media(self):
        msg = Message(chat_id=1, message_id=1, message_type="photo")
        assert msg.is_media_type() is True

    def test_voice_is_media(self):
        msg = Message(chat_id=1, message_id=1, message_type="voice")
        assert msg.is_media_type() is True

    def test_video_is_media(self):
        msg = Message(chat_id=1, message_id=1, message_type="video")
        assert msg.is_media_type() is True

    def test_document_is_media(self):
        msg = Message(chat_id=1, message_id=1, message_type="document")
        assert msg.is_media_type() is True

    def test_text_is_not_media(self):
        msg = Message(chat_id=1, message_id=1, message_type="text")
        assert msg.is_media_type() is False

    def test_contact_is_not_media(self):
        msg = Message(chat_id=1, message_id=1, message_type="contact")
        assert msg.is_media_type() is False
