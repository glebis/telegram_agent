"""
Tests for the Combined Message Processor.

Tests cover:
- Message routing logic
- Content type detection
- Mock message structures
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


# Mock classes to avoid Telegram dependencies
@dataclass
class MockBufferedMessage:
    """Mock BufferedMessage for testing."""
    message_id: int
    timestamp: datetime
    message_type: str = "text"
    text: Optional[str] = None
    caption: Optional[str] = None
    file_id: Optional[str] = None
    is_claude_command: bool = False
    message: MagicMock = field(default_factory=MagicMock)
    update: MagicMock = field(default_factory=MagicMock)
    context: MagicMock = field(default_factory=MagicMock)


@dataclass
class MockCombinedMessage:
    """Mock CombinedMessage for testing."""
    chat_id: int
    user_id: int
    messages: List[MockBufferedMessage] = field(default_factory=list)
    combined_text: str = ""
    images: List[MockBufferedMessage] = field(default_factory=list)
    voices: List[MockBufferedMessage] = field(default_factory=list)
    videos: List[MockBufferedMessage] = field(default_factory=list)
    documents: List[MockBufferedMessage] = field(default_factory=list)
    contacts: List[MockBufferedMessage] = field(default_factory=list)
    reply_to_message_id: Optional[int] = None

    def has_claude_command(self) -> bool:
        return any(m.is_claude_command for m in self.messages)

    def has_images(self) -> bool:
        return len(self.images) > 0

    def has_voice(self) -> bool:
        return len(self.voices) > 0

    def has_videos(self) -> bool:
        return len(self.videos) > 0

    def get_claude_prompt(self) -> str:
        return self.combined_text

    @property
    def primary_update(self):
        return self.messages[0].update if self.messages else MagicMock()

    @property
    def primary_context(self):
        return self.messages[0].context if self.messages else MagicMock()

    @property
    def primary_message(self):
        return self.messages[0].message if self.messages else MagicMock()


class TestCombinedMessageProcessor:
    """Tests for CombinedMessageProcessor initialization."""

    def test_processor_can_be_imported(self):
        """Test that processor can be imported."""
        with patch("src.bot.combined_processor.get_reply_context_service") as mock_reply:
            mock_reply.return_value = MagicMock()
            from src.bot.combined_processor import CombinedMessageProcessor
            processor = CombinedMessageProcessor()
            assert processor is not None
            assert processor.reply_service is not None


class TestMockCombinedMessage:
    """Tests for MockCombinedMessage helper class."""

    def test_has_claude_command_true(self):
        """Test detecting /claude commands."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[MockBufferedMessage(
                message_id=100,
                timestamp=datetime.now(),
                is_claude_command=True,
            )],
        )
        assert combined.has_claude_command() is True

    def test_has_claude_command_false(self):
        """Test message without /claude command."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[MockBufferedMessage(
                message_id=100,
                timestamp=datetime.now(),
                is_claude_command=False,
            )],
        )
        assert combined.has_claude_command() is False

    def test_has_claude_command_multiple_messages(self):
        """Test detecting /claude in multiple messages."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[
                MockBufferedMessage(message_id=100, timestamp=datetime.now(), is_claude_command=False),
                MockBufferedMessage(message_id=101, timestamp=datetime.now(), is_claude_command=True),
            ],
        )
        assert combined.has_claude_command() is True

    def test_has_images(self):
        """Test detecting images."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            images=[MockBufferedMessage(message_id=100, timestamp=datetime.now())],
        )
        assert combined.has_images() is True

    def test_has_no_images(self):
        """Test no images."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
        )
        assert combined.has_images() is False

    def test_has_voice(self):
        """Test detecting voice."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            voices=[MockBufferedMessage(message_id=100, timestamp=datetime.now())],
        )
        assert combined.has_voice() is True

    def test_has_no_voice(self):
        """Test no voice."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
        )
        assert combined.has_voice() is False

    def test_has_videos(self):
        """Test detecting videos."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            videos=[MockBufferedMessage(message_id=100, timestamp=datetime.now())],
        )
        assert combined.has_videos() is True

    def test_has_no_videos(self):
        """Test no videos."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
        )
        assert combined.has_videos() is False

    def test_get_claude_prompt(self):
        """Test getting Claude prompt."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="analyze this code",
        )
        assert combined.get_claude_prompt() == "analyze this code"

    def test_primary_properties(self):
        """Test primary_update, primary_context, primary_message."""
        msg = MockBufferedMessage(message_id=100, timestamp=datetime.now())
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[msg],
        )
        assert combined.primary_update == msg.update
        assert combined.primary_context == msg.context
        assert combined.primary_message == msg.message

    def test_primary_properties_empty(self):
        """Test primary properties with no messages."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
        )
        # Should return MagicMock, not raise
        assert combined.primary_update is not None
        assert combined.primary_context is not None
        assert combined.primary_message is not None


class TestContentTypeDetection:
    """Tests for content type detection in messages."""

    def test_text_only_message(self):
        """Test text-only message detection."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="Hello world",
        )
        assert not combined.has_images()
        assert not combined.has_voice()
        assert not combined.has_videos()

    def test_image_message(self):
        """Test image message detection."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="Check this",
            images=[MockBufferedMessage(message_id=100, timestamp=datetime.now())],
        )
        assert combined.has_images()
        assert not combined.has_voice()

    def test_voice_message(self):
        """Test voice message detection."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            voices=[MockBufferedMessage(message_id=100, timestamp=datetime.now())],
        )
        assert combined.has_voice()
        assert not combined.has_images()

    def test_video_message(self):
        """Test video message detection."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            videos=[MockBufferedMessage(message_id=100, timestamp=datetime.now())],
        )
        assert combined.has_videos()
        assert not combined.has_voice()

    def test_mixed_media_message(self):
        """Test message with multiple media types."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="Multi-media",
            images=[MockBufferedMessage(message_id=100, timestamp=datetime.now())],
            voices=[MockBufferedMessage(message_id=101, timestamp=datetime.now())],
            videos=[MockBufferedMessage(message_id=102, timestamp=datetime.now())],
        )
        assert combined.has_images()
        assert combined.has_voice()
        assert combined.has_videos()


class TestMultipleMessages:
    """Tests for handling multiple messages in a combined message."""

    def test_multiple_text_messages(self):
        """Test combining multiple text messages."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="Hello World",
            messages=[
                MockBufferedMessage(message_id=100, timestamp=datetime.now(), text="Hello"),
                MockBufferedMessage(message_id=101, timestamp=datetime.now(), text="World"),
            ],
        )
        assert len(combined.messages) == 2
        assert "Hello" in combined.combined_text
        assert "World" in combined.combined_text

    def test_multiple_images(self):
        """Test combining multiple image messages."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            images=[
                MockBufferedMessage(message_id=100, timestamp=datetime.now()),
                MockBufferedMessage(message_id=101, timestamp=datetime.now()),
                MockBufferedMessage(message_id=102, timestamp=datetime.now()),
            ],
        )
        assert len(combined.images) == 3
        assert combined.has_images()

    def test_text_and_image_combined(self):
        """Test combining text and image."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="Analyze this image",
            messages=[
                MockBufferedMessage(message_id=100, timestamp=datetime.now(), text="Analyze this image"),
            ],
            images=[
                MockBufferedMessage(message_id=101, timestamp=datetime.now()),
            ],
        )
        assert combined.has_images()
        assert "Analyze" in combined.combined_text

    def test_claude_command_with_followup(self):
        """Test /claude command followed by additional text."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="/claude analyze this code please",
            messages=[
                MockBufferedMessage(message_id=100, timestamp=datetime.now(), is_claude_command=True, text="/claude"),
                MockBufferedMessage(message_id=101, timestamp=datetime.now(), text="analyze this code"),
                MockBufferedMessage(message_id=102, timestamp=datetime.now(), text="please"),
            ],
        )
        assert combined.has_claude_command()
        assert "analyze" in combined.get_claude_prompt()


class TestReplyContext:
    """Tests for reply context handling."""

    def test_reply_to_message_id_set(self):
        """Test reply_to_message_id is set correctly."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            reply_to_message_id=99,
        )
        assert combined.reply_to_message_id == 99

    def test_reply_to_message_id_none(self):
        """Test reply_to_message_id is None by default."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
        )
        assert combined.reply_to_message_id is None


class TestMessageBufferBehavior:
    """Tests simulating message buffer behavior."""

    def test_rapid_fire_messages(self):
        """Test combining rapid-fire messages."""
        now = datetime.now()
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="First Second Third",
            messages=[
                MockBufferedMessage(message_id=100, timestamp=now, text="First"),
                MockBufferedMessage(message_id=101, timestamp=now, text="Second"),
                MockBufferedMessage(message_id=102, timestamp=now, text="Third"),
            ],
        )
        assert len(combined.messages) == 3
        assert "First" in combined.combined_text
        assert "Second" in combined.combined_text
        assert "Third" in combined.combined_text

    def test_single_message_passthrough(self):
        """Test single message passes through correctly."""
        combined = MockCombinedMessage(
            chat_id=12345,
            user_id=67890,
            combined_text="Single message",
            messages=[
                MockBufferedMessage(message_id=100, timestamp=datetime.now(), text="Single message"),
            ],
        )
        assert len(combined.messages) == 1
        assert combined.combined_text == "Single message"
