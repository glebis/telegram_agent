"""
Tests for the Message Buffer Service.

Tests cover:
- BufferedMessage dataclass creation and properties
- CombinedMessage dataclass properties and helper methods
- MessageBufferService core functionality
- Buffer timing, flush behavior, and limits
- Claude command handling
- Global instance management
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.services.message_buffer import (
    BufferedMessage,
    BufferEntry,
    CombinedMessage,
    MessageBufferService,
    get_message_buffer,
    init_message_buffer,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_message():
    """Create a mock Telegram Message."""
    message = MagicMock()
    message.message_id = 123
    message.text = "Hello world"
    message.caption = None
    message.photo = None
    message.voice = None
    message.audio = None
    message.video = None
    message.video_note = None
    message.document = None
    message.contact = None
    message.media_group_id = None
    message.reply_to_message = None
    message.forward_origin = None
    return message


@pytest.fixture
def mock_update(mock_message):
    """Create a mock Telegram Update."""
    update = MagicMock()
    update.message = mock_message
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.effective_user = MagicMock()
    update.effective_user.id = 67890
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram Context."""
    context = MagicMock()
    context.bot = MagicMock()
    return context


@pytest.fixture
def buffer_service():
    """Create a MessageBufferService with short timeout for testing."""
    return MessageBufferService(
        buffer_timeout=0.1,  # 100ms for fast tests
        max_messages=5,
        max_wait=1.0,
    )


@pytest.fixture
def buffered_message(mock_message, mock_update, mock_context):
    """Create a sample BufferedMessage."""
    return BufferedMessage(
        message_id=123,
        message=mock_message,
        update=mock_update,
        context=mock_context,
        timestamp=datetime.now(),
        message_type="text",
        text="Hello world",
    )


# =============================================================================
# BufferedMessage Tests
# =============================================================================


class TestBufferedMessage:
    """Tests for BufferedMessage dataclass."""

    def test_create_text_message(self, mock_message, mock_update, mock_context):
        """Test creating a text BufferedMessage."""
        msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
            text="Test message",
        )

        assert msg.message_id == 1
        assert msg.message_type == "text"
        assert msg.text == "Test message"
        assert msg.is_claude_command is False
        assert msg.is_forwarded is False

    def test_create_photo_message(self, mock_message, mock_update, mock_context):
        """Test creating a photo BufferedMessage."""
        msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="photo",
            file_id="photo_file_123",
            caption="Photo caption",
        )

        assert msg.message_type == "photo"
        assert msg.file_id == "photo_file_123"
        assert msg.caption == "Photo caption"

    def test_create_claude_command_message(
        self, mock_message, mock_update, mock_context
    ):
        """Test creating a Claude command BufferedMessage."""
        msg = BufferedMessage(
            message_id=3,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="claude_command",
            text="analyze this code",
            is_claude_command=True,
        )

        assert msg.message_type == "claude_command"
        assert msg.is_claude_command is True
        assert msg.text == "analyze this code"

    def test_forwarded_message_fields(self, mock_message, mock_update, mock_context):
        """Test BufferedMessage with forward info."""
        msg = BufferedMessage(
            message_id=4,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
            text="Forwarded content",
            is_forwarded=True,
            forward_from_username="original_user",
            forward_from_chat_title="Original Channel",
        )

        assert msg.is_forwarded is True
        assert msg.forward_from_username == "original_user"
        assert msg.forward_from_chat_title == "Original Channel"


# =============================================================================
# CombinedMessage Tests
# =============================================================================


class TestCombinedMessage:
    """Tests for CombinedMessage dataclass."""

    def test_create_empty_combined_message(self, buffered_message):
        """Test creating a CombinedMessage with minimal data."""
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
        )

        assert combined.chat_id == 12345
        assert combined.user_id == 67890
        assert len(combined.messages) == 1
        assert combined.combined_text == ""

    def test_primary_properties(self, buffered_message):
        """Test primary_update, primary_context, primary_message properties."""
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
        )

        assert combined.primary_update == buffered_message.update
        assert combined.primary_context == buffered_message.context
        assert combined.primary_message == buffered_message.message

    def test_has_images(self, buffered_message):
        """Test has_images() helper."""
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
            images=[buffered_message],
        )

        assert combined.has_images() is True

        combined_no_images = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
        )
        assert combined_no_images.has_images() is False

    def test_has_voice(self, buffered_message):
        """Test has_voice() helper."""
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
            voices=[buffered_message],
        )

        assert combined.has_voice() is True

    def test_has_documents(self, buffered_message):
        """Test has_documents() helper."""
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
            documents=[buffered_message],
        )

        assert combined.has_documents() is True

    def test_has_videos(self, buffered_message):
        """Test has_videos() helper."""
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
            videos=[buffered_message],
        )

        assert combined.has_videos() is True

    def test_has_text_only(self, buffered_message):
        """Test has_text_only() helper."""
        # Text only - should be True
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
            combined_text="Some text",
        )
        assert combined.has_text_only() is True

        # Text + images - should be False
        combined_with_images = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
            combined_text="Some text",
            images=[buffered_message],
        )
        assert combined_with_images.has_text_only() is False

        # Empty text - should be False
        combined_empty = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[buffered_message],
        )
        assert combined_empty.has_text_only() is False

    def test_has_claude_command(self, mock_message, mock_update, mock_context):
        """Test has_claude_command() helper."""
        regular_msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
        )

        claude_msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="claude_command",
            is_claude_command=True,
        )

        # No Claude command
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg],
        )
        assert combined.has_claude_command() is False

        # With Claude command
        combined_with_claude = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, claude_msg],
        )
        assert combined_with_claude.has_claude_command() is True

    def test_get_claude_command_message(self, mock_message, mock_update, mock_context):
        """Test get_claude_command_message() helper."""
        regular_msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
        )

        claude_msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="claude_command",
            is_claude_command=True,
            text="do something",
        )

        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, claude_msg],
        )

        result = combined.get_claude_command_message()
        assert result is not None
        assert result.is_claude_command is True
        assert result.text == "do something"

    def test_has_forwarded_messages(self, mock_message, mock_update, mock_context):
        """Test has_forwarded_messages() helper."""
        regular_msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
        )

        forwarded_msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
            is_forwarded=True,
        )

        combined_no_forward = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg],
        )
        assert combined_no_forward.has_forwarded_messages() is False

        combined_with_forward = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, forwarded_msg],
        )
        assert combined_with_forward.has_forwarded_messages() is True


# =============================================================================
# MessageBufferService Tests
# =============================================================================


class TestMessageBufferServiceInit:
    """Tests for MessageBufferService initialization."""

    def test_default_initialization(self):
        """Test default buffer settings."""
        service = MessageBufferService()

        assert service.buffer_timeout == 2.5
        assert service.max_messages == 20
        assert service.max_wait == 30.0
        assert service._buffers == {}
        assert service._process_callback is None

    def test_custom_initialization(self):
        """Test custom buffer settings."""
        service = MessageBufferService(
            buffer_timeout=5.0,
            max_messages=20,
            max_wait=60.0,
        )

        assert service.buffer_timeout == 5.0
        assert service.max_messages == 20
        assert service.max_wait == 60.0

    def test_bypass_commands_configured(self):
        """Test that bypass commands are properly configured."""
        service = MessageBufferService()

        assert "/help" in service._bypass_commands
        assert "/start" in service._bypass_commands
        assert "/mode" in service._bypass_commands
        assert "/cancel" in service._bypass_commands
        # /claude should NOT be in bypass commands
        assert "/claude" not in service._bypass_commands

    def test_set_process_callback(self):
        """Test setting the process callback."""
        service = MessageBufferService()

        async def my_callback(combined: CombinedMessage):
            pass

        service.set_process_callback(my_callback)
        assert service._process_callback == my_callback


class TestMessageBufferServiceAddMessage:
    """Tests for add_message functionality."""

    @pytest.mark.asyncio
    async def test_add_text_message(self, buffer_service, mock_update, mock_context):
        """Test adding a text message to buffer."""
        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True

        # Check buffer status
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status is not None
        assert status["message_count"] == 1
        assert "text" in status["message_types"]

    @pytest.mark.asyncio
    async def test_add_photo_message(self, buffer_service, mock_update, mock_context):
        """Test adding a photo message to buffer."""
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert "photo" in status["message_types"]

    @pytest.mark.asyncio
    async def test_add_voice_message(self, buffer_service, mock_update, mock_context):
        """Test adding a voice message to buffer."""
        mock_update.message.text = None
        mock_update.message.voice = MagicMock(file_id="voice_123")

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert "voice" in status["message_types"]

    @pytest.mark.asyncio
    async def test_add_document_message(
        self, buffer_service, mock_update, mock_context
    ):
        """Test adding a document message to buffer."""
        mock_update.message.text = None
        mock_update.message.document = MagicMock(
            file_id="doc_123", mime_type="application/pdf"
        )

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert "document" in status["message_types"]

    @pytest.mark.asyncio
    async def test_add_video_message(self, buffer_service, mock_update, mock_context):
        """Test adding a video message to buffer."""
        mock_update.message.text = None
        mock_update.message.video = MagicMock(file_id="video_123")

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert "video" in status["message_types"]

    @pytest.mark.asyncio
    async def test_add_audio_as_voice(self, buffer_service, mock_update, mock_context):
        """Test that audio files are treated as voice messages."""
        mock_update.message.text = None
        mock_update.message.audio = MagicMock(
            file_id="audio_123", mime_type="audio/mpeg"
        )

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        # Audio should be treated as voice
        assert "voice" in status["message_types"]

    @pytest.mark.asyncio
    async def test_add_image_document_as_photo(
        self, buffer_service, mock_update, mock_context
    ):
        """Test that image documents are treated as photos."""
        mock_update.message.text = None
        mock_update.message.document = MagicMock(
            file_id="img_doc_123", mime_type="image/jpeg"
        )

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert "photo" in status["message_types"]

    @pytest.mark.asyncio
    async def test_bypass_command_not_buffered(
        self, buffer_service, mock_update, mock_context
    ):
        """Test that bypass commands are not buffered."""
        mock_update.message.text = "/help"

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is False  # Not buffered
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status is None

    @pytest.mark.asyncio
    async def test_bypass_command_with_bot_mention(
        self, buffer_service, mock_update, mock_context
    ):
        """Test bypass command with @bot mention."""
        mock_update.message.text = "/help@mybot"

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is False

    @pytest.mark.asyncio
    async def test_message_with_missing_update_fields(
        self, buffer_service, mock_context
    ):
        """Test handling of update with missing fields."""
        update = MagicMock()
        update.message = None

        result = await buffer_service.add_message(update, mock_context)

        assert result is False

    @pytest.mark.asyncio
    async def test_message_with_missing_chat(
        self, buffer_service, mock_update, mock_context
    ):
        """Test handling of update with missing chat."""
        mock_update.effective_chat = None

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is False

    @pytest.mark.asyncio
    async def test_message_with_missing_user(
        self, buffer_service, mock_update, mock_context
    ):
        """Test handling of update with missing user."""
        mock_update.effective_user = None

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is False

    @pytest.mark.asyncio
    async def test_claude_command_in_caption(
        self, buffer_service, mock_update, mock_context
    ):
        """Test /claude command detected in photo caption."""
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]
        mock_update.message.caption = "/claude analyze this image"

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 1


class TestMessageBufferServiceTiming:
    """Tests for buffer timing and flush behavior."""

    @pytest.mark.asyncio
    async def test_buffer_flush_after_timeout(self, mock_update, mock_context):
        """Test that buffer flushes after timeout."""
        service = MessageBufferService(buffer_timeout=0.05)  # 50ms

        callback_called = asyncio.Event()
        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)
            callback_called.set()

        service.set_process_callback(mock_callback)

        await service.add_message(mock_update, mock_context)

        # Wait for timeout + some buffer
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)

        assert len(received_combined) == 1
        assert received_combined[0].chat_id == 12345
        assert received_combined[0].user_id == 67890

    @pytest.mark.asyncio
    async def test_timer_reset_on_new_message(self, mock_update, mock_context):
        """Test that timer resets when new message arrives."""
        service = MessageBufferService(buffer_timeout=0.1)  # 100ms

        callback_called = asyncio.Event()
        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)
            callback_called.set()

        service.set_process_callback(mock_callback)

        # Add first message
        await service.add_message(mock_update, mock_context)

        # Wait 50ms (half the timeout)
        await asyncio.sleep(0.05)

        # Add second message (should reset timer)
        mock_update.message.message_id = 124
        mock_update.message.text = "Second message"
        await service.add_message(mock_update, mock_context)

        # Wait for flush
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)

        # Should have received both messages combined
        assert len(received_combined) == 1
        assert len(received_combined[0].messages) == 2

    @pytest.mark.asyncio
    async def test_max_messages_forces_flush(self, mock_update, mock_context):
        """Test that reaching max_messages forces immediate flush."""
        service = MessageBufferService(
            buffer_timeout=10.0,  # Long timeout
            max_messages=3,
        )

        callback_called = asyncio.Event()
        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)
            callback_called.set()

        service.set_process_callback(mock_callback)

        # Add messages up to max
        for i in range(3):
            mock_update.message.message_id = 100 + i
            mock_update.message.text = f"Message {i}"
            await service.add_message(mock_update, mock_context)

        # Should flush immediately without waiting for timeout
        await asyncio.wait_for(callback_called.wait(), timeout=0.5)

        assert len(received_combined) == 1
        assert len(received_combined[0].messages) == 3

    @pytest.mark.asyncio
    async def test_max_wait_forces_flush(self, mock_update, mock_context):
        """Test that max_wait time forces flush."""
        service = MessageBufferService(
            buffer_timeout=0.1,
            max_messages=100,  # High limit
            max_wait=0.05,  # 50ms max wait
        )

        callback_called = asyncio.Event()
        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)
            callback_called.set()

        service.set_process_callback(mock_callback)

        # Add first message
        await service.add_message(mock_update, mock_context)

        # Wait past max_wait
        await asyncio.sleep(0.06)

        # Add another message - should trigger flush due to max_wait
        mock_update.message.message_id = 124
        await service.add_message(mock_update, mock_context)

        # Should flush immediately
        await asyncio.wait_for(callback_called.wait(), timeout=0.5)

        assert len(received_combined) >= 1

    @pytest.mark.asyncio
    async def test_multiple_users_separate_buffers(self, mock_context):
        """Test that different users have separate buffers."""
        service = MessageBufferService(buffer_timeout=0.1)

        callback_results = []

        async def mock_callback(combined: CombinedMessage):
            callback_results.append((combined.chat_id, combined.user_id))

        service.set_process_callback(mock_callback)

        # User 1
        update1 = MagicMock()
        update1.message = MagicMock()
        update1.message.message_id = 1
        update1.message.text = "User 1 message"
        update1.message.caption = None
        update1.message.photo = None
        update1.message.voice = None
        update1.message.audio = None
        update1.message.video = None
        update1.message.video_note = None
        update1.message.document = None
        update1.message.contact = None
        update1.message.media_group_id = None
        update1.message.reply_to_message = None
        update1.message.forward_origin = None
        update1.effective_chat = MagicMock()
        update1.effective_chat.id = 100
        update1.effective_user = MagicMock()
        update1.effective_user.id = 1

        # User 2
        update2 = MagicMock()
        update2.message = MagicMock()
        update2.message.message_id = 2
        update2.message.text = "User 2 message"
        update2.message.caption = None
        update2.message.photo = None
        update2.message.voice = None
        update2.message.audio = None
        update2.message.video = None
        update2.message.video_note = None
        update2.message.document = None
        update2.message.contact = None
        update2.message.media_group_id = None
        update2.message.reply_to_message = None
        update2.message.forward_origin = None
        update2.effective_chat = MagicMock()
        update2.effective_chat.id = 100
        update2.effective_user = MagicMock()
        update2.effective_user.id = 2

        await service.add_message(update1, mock_context)
        await service.add_message(update2, mock_context)

        # Wait for both to flush
        await asyncio.sleep(0.2)

        # Should have two separate callbacks
        assert len(callback_results) == 2
        user_ids = [r[1] for r in callback_results]
        assert 1 in user_ids
        assert 2 in user_ids


class TestMessageBufferServiceCombine:
    """Tests for message combining logic."""

    @pytest.mark.asyncio
    async def test_combine_multiple_text_messages(self, mock_update, mock_context):
        """Test combining multiple text messages."""
        service = MessageBufferService(buffer_timeout=0.05)

        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)

        service.set_process_callback(mock_callback)

        # Add multiple text messages
        texts = ["Hello", "World", "Test"]
        for i, text in enumerate(texts):
            mock_update.message.message_id = 100 + i
            mock_update.message.text = text
            await service.add_message(mock_update, mock_context)

        await asyncio.sleep(0.1)

        assert len(received_combined) == 1
        # Text should be joined with newlines
        assert received_combined[0].combined_text == "Hello\nWorld\nTest"

    @pytest.mark.asyncio
    async def test_combine_text_and_images(self, mock_update, mock_context):
        """Test combining text and image messages."""
        service = MessageBufferService(buffer_timeout=0.05)

        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)

        service.set_process_callback(mock_callback)

        # Add text message
        mock_update.message.message_id = 100
        mock_update.message.text = "Check this out"
        await service.add_message(mock_update, mock_context)

        # Add photo message
        mock_update.message.message_id = 101
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]
        mock_update.message.caption = "Photo caption"
        await service.add_message(mock_update, mock_context)

        await asyncio.sleep(0.1)

        assert len(received_combined) == 1
        combined = received_combined[0]
        assert combined.has_images() is True
        assert len(combined.images) == 1
        # Both text and caption should be combined
        assert "Check this out" in combined.combined_text
        assert "Photo caption" in combined.combined_text

    @pytest.mark.asyncio
    async def test_messages_sorted_by_message_id(self, mock_update, mock_context):
        """Test that messages are sorted by message_id before combining."""
        service = MessageBufferService(buffer_timeout=0.05)

        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)

        service.set_process_callback(mock_callback)

        # Add messages out of order
        for msg_id in [103, 101, 102]:
            mock_update.message.message_id = msg_id
            mock_update.message.text = f"Message {msg_id}"
            await service.add_message(mock_update, mock_context)

        await asyncio.sleep(0.1)

        assert len(received_combined) == 1
        # Should be sorted by message_id
        message_ids = [m.message_id for m in received_combined[0].messages]
        assert message_ids == [101, 102, 103]

    @pytest.mark.asyncio
    async def test_reply_context_captured(self, mock_update, mock_context):
        """Test that reply context is captured from messages."""
        service = MessageBufferService(buffer_timeout=0.05)

        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)

        service.set_process_callback(mock_callback)

        # Set up reply
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.message_id = 50

        await service.add_message(mock_update, mock_context)
        await asyncio.sleep(0.1)

        assert len(received_combined) == 1
        assert received_combined[0].reply_to_message_id == 50


class TestMessageBufferServiceClaudeCommand:
    """Tests for Claude command handling."""

    @pytest.mark.asyncio
    async def test_add_claude_command(self, buffer_service, mock_update, mock_context):
        """Test adding a /claude command to buffer."""
        await buffer_service.add_claude_command(
            mock_update, mock_context, "analyze this"
        )

        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status is not None
        assert status["message_count"] == 1
        assert "claude_command" in status["message_types"]

    @pytest.mark.asyncio
    async def test_claude_command_combined_with_follow_up(
        self, mock_update, mock_context
    ):
        """Test /claude command combined with follow-up messages."""
        service = MessageBufferService(buffer_timeout=0.05)

        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)

        service.set_process_callback(mock_callback)

        # Add /claude command
        await service.add_claude_command(mock_update, mock_context, "What is this?")

        # Add follow-up photo
        mock_update.message.message_id = 124
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]
        await service.add_message(mock_update, mock_context)

        await asyncio.sleep(0.1)

        assert len(received_combined) == 1
        combined = received_combined[0]
        assert combined.has_claude_command() is True
        assert combined.has_images() is True

    @pytest.mark.asyncio
    async def test_claude_command_inserted_at_beginning(
        self, mock_update, mock_context
    ):
        """Test that /claude command is inserted at buffer beginning."""
        service = MessageBufferService(buffer_timeout=0.05)

        # Add a regular message first
        mock_update.message.message_id = 100
        await service.add_message(mock_update, mock_context)

        # Then add /claude command
        await service.add_claude_command(mock_update, mock_context, "analyze")

        status = await service.get_buffer_status(12345, 67890)
        # Claude command should be at index 0
        assert status["message_types"][0] == "claude_command"


class TestMessageBufferServiceCancel:
    """Tests for buffer cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_buffer(self, buffer_service, mock_update, mock_context):
        """Test cancelling a buffer."""
        await buffer_service.add_message(mock_update, mock_context)

        # Verify buffer exists
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status is not None

        # Cancel
        result = await buffer_service.cancel_buffer(12345, 67890)
        assert result is True

        # Verify buffer is gone
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status is None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_buffer(self, buffer_service):
        """Test cancelling a buffer that doesn't exist."""
        result = await buffer_service.cancel_buffer(99999, 99999)
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_prevents_callback(self, mock_update, mock_context):
        """Test that cancelling buffer prevents callback from being called."""
        service = MessageBufferService(buffer_timeout=0.1)

        callback_called = False

        async def mock_callback(combined: CombinedMessage):
            nonlocal callback_called
            callback_called = True

        service.set_process_callback(mock_callback)

        await service.add_message(mock_update, mock_context)

        # Cancel before timeout
        await service.cancel_buffer(12345, 67890)

        # Wait past timeout
        await asyncio.sleep(0.2)

        assert callback_called is False


class TestMessageBufferServiceStatus:
    """Tests for buffer status."""

    @pytest.mark.asyncio
    async def test_get_buffer_status(self, buffer_service, mock_update, mock_context):
        """Test getting buffer status."""
        await buffer_service.add_message(mock_update, mock_context)

        status = await buffer_service.get_buffer_status(12345, 67890)

        assert status is not None
        assert status["message_count"] == 1
        assert "first_message_time" in status
        assert "media_groups" in status
        assert "message_types" in status

    @pytest.mark.asyncio
    async def test_get_status_nonexistent_buffer(self, buffer_service):
        """Test getting status for nonexistent buffer."""
        status = await buffer_service.get_buffer_status(99999, 99999)
        assert status is None

    @pytest.mark.asyncio
    async def test_media_group_tracking(
        self, buffer_service, mock_update, mock_context
    ):
        """Test that media groups are tracked."""
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_1")]
        mock_update.message.media_group_id = "group_123"

        await buffer_service.add_message(mock_update, mock_context)

        status = await buffer_service.get_buffer_status(12345, 67890)
        assert "group_123" in status["media_groups"]


class TestMessageBufferServiceForwarding:
    """Tests for forwarded message handling."""

    @pytest.mark.asyncio
    async def test_forward_from_user(self, buffer_service, mock_update, mock_context):
        """Test handling forward from user."""
        mock_update.message.forward_origin = MagicMock()
        mock_update.message.forward_origin.type = "user"
        mock_update.message.forward_origin.sender_user = MagicMock()
        mock_update.message.forward_origin.sender_user.username = "original_user"
        mock_update.message.forward_origin.sender_user.first_name = "John"

        await buffer_service.add_message(mock_update, mock_context)

        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 1

    @pytest.mark.asyncio
    async def test_forward_from_channel(
        self, buffer_service, mock_update, mock_context
    ):
        """Test handling forward from channel."""
        mock_update.message.forward_origin = MagicMock()
        mock_update.message.forward_origin.type = "channel"
        mock_update.message.forward_origin.chat = MagicMock()
        mock_update.message.forward_origin.chat.title = "Test Channel"
        mock_update.message.forward_origin.chat.username = "testchannel"
        mock_update.message.forward_origin.message_id = 999

        await buffer_service.add_message(mock_update, mock_context)

        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 1


class TestMessageBufferServiceErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_callback_error_logged(self, mock_update, mock_context):
        """Test that callback errors are logged but don't crash."""
        service = MessageBufferService(buffer_timeout=0.05)

        async def failing_callback(combined: CombinedMessage):
            raise ValueError("Test error")

        service.set_process_callback(failing_callback)

        await service.add_message(mock_update, mock_context)

        # Should not raise, error should be logged
        await asyncio.sleep(0.1)

        # Buffer should be cleared even after error
        status = await service.get_buffer_status(12345, 67890)
        assert status is None

    @pytest.mark.asyncio
    async def test_no_callback_warning(self, mock_update, mock_context):
        """Test warning when no callback is set."""
        service = MessageBufferService(buffer_timeout=0.05)

        # Don't set callback
        await service.add_message(mock_update, mock_context)

        # Should complete without error
        await asyncio.sleep(0.1)


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance management via DI container."""

    def _setup_container(self):
        from src.core.container import reset_container
        from src.core.services import setup_services

        reset_container()
        setup_services()

    def test_get_message_buffer_creates_instance(self):
        """Test that get_message_buffer creates instance if needed."""
        self._setup_container()

        service = get_message_buffer()

        assert service is not None
        assert isinstance(service, MessageBufferService)

    def test_get_message_buffer_returns_same_instance(self):
        """Test that get_message_buffer returns the same instance."""
        self._setup_container()

        service1 = get_message_buffer()
        service2 = get_message_buffer()

        assert service1 is service2

    def test_init_message_buffer_creates_custom_instance(self):
        """Test that init_message_buffer creates instance with custom settings."""
        self._setup_container()

        service = init_message_buffer(
            buffer_timeout=5.0,
            max_messages=20,
            max_wait=60.0,
        )

        assert service.buffer_timeout == 5.0
        assert service.max_messages == 20
        assert service.max_wait == 60.0

        # Should be returned by get_message_buffer
        assert get_message_buffer() is service

    def test_init_message_buffer_replaces_instance(self):
        """Test that init_message_buffer replaces existing instance."""
        self._setup_container()

        service1 = init_message_buffer(buffer_timeout=1.0)
        service2 = init_message_buffer(buffer_timeout=2.0)

        assert service1 is not service2
        assert get_message_buffer() is service2
        assert get_message_buffer().buffer_timeout == 2.0


# =============================================================================
# BufferEntry Tests
# =============================================================================


class TestBufferEntry:
    """Tests for BufferEntry dataclass."""

    def test_default_values(self):
        """Test BufferEntry default values."""
        entry = BufferEntry()

        assert entry.messages == []
        assert entry.timer_task is None
        assert entry.first_message_time is None
        assert entry.media_group_ids == set()

    def test_add_messages(self, buffered_message):
        """Test adding messages to entry."""
        entry = BufferEntry()
        entry.messages.append(buffered_message)

        assert len(entry.messages) == 1

    def test_media_group_tracking(self):
        """Test media group ID tracking."""
        entry = BufferEntry()
        entry.media_group_ids.add("group_1")
        entry.media_group_ids.add("group_2")
        entry.media_group_ids.add("group_1")  # Duplicate

        assert len(entry.media_group_ids) == 2


class TestCommandCaptionDetection:
    """Tests for /claude, /meta, and /dev command detection in captions."""

    @pytest.mark.asyncio
    async def test_claude_command_in_caption(
        self, buffer_service, mock_update, mock_context
    ):
        """Test /claude command detected in photo caption."""
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]
        mock_update.message.caption = "/claude analyze this image"

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 1

    @pytest.mark.asyncio
    async def test_meta_command_in_caption(
        self, buffer_service, mock_update, mock_context
    ):
        """Test /meta command detected in photo caption."""
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]
        mock_update.message.caption = "/meta look at this screenshot"

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 1

    @pytest.mark.asyncio
    async def test_dev_command_in_caption(
        self, buffer_service, mock_update, mock_context
    ):
        """Test /dev command detected in photo caption."""
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]
        mock_update.message.caption = "/dev analyze this code"

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 1

    @pytest.mark.asyncio
    async def test_command_caption_without_text(
        self, buffer_service, mock_update, mock_context
    ):
        """Test command in caption with no additional text."""
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_123")]
        mock_update.message.caption = "/meta"

        result = await buffer_service.add_message(mock_update, mock_context)

        assert result is True
        status = await buffer_service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 1

    @pytest.mark.asyncio
    async def test_has_meta_command(self, mock_message, mock_update, mock_context):
        """Test has_meta_command() helper."""
        regular_msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
        )

        meta_msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="photo",
            is_meta_command=True,
            command_type="meta",
        )

        # No meta command
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg],
        )
        assert combined.has_meta_command() is False

        # With meta command
        combined_with_meta = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, meta_msg],
        )
        assert combined_with_meta.has_meta_command() is True

    @pytest.mark.asyncio
    async def test_has_dev_command(self, mock_message, mock_update, mock_context):
        """Test has_dev_command() helper."""
        regular_msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
        )

        dev_msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="photo",
            is_dev_command=True,
            command_type="dev",
        )

        # No dev command
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg],
        )
        assert combined.has_dev_command() is False

        # With dev command
        combined_with_dev = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, dev_msg],
        )
        assert combined_with_dev.has_dev_command() is True

    @pytest.mark.asyncio
    async def test_has_command(self, mock_message, mock_update, mock_context):
        """Test has_command() helper for any command type."""
        regular_msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
        )

        claude_msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
            is_claude_command=True,
            command_type="claude",
        )

        meta_msg = BufferedMessage(
            message_id=3,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="photo",
            is_meta_command=True,
            command_type="meta",
        )

        # No commands
        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg],
        )
        assert combined.has_command() is False

        # With claude command
        combined_with_claude = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, claude_msg],
        )
        assert combined_with_claude.has_command() is True

        # With meta command
        combined_with_meta = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, meta_msg],
        )
        assert combined_with_meta.has_command() is True

    @pytest.mark.asyncio
    async def test_get_command_message(self, mock_message, mock_update, mock_context):
        """Test get_command_message() helper."""
        regular_msg = BufferedMessage(
            message_id=1,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="text",
        )

        meta_msg = BufferedMessage(
            message_id=2,
            message=mock_message,
            update=mock_update,
            context=mock_context,
            timestamp=datetime.now(),
            message_type="photo",
            is_meta_command=True,
            command_type="meta",
            text="do something",
        )

        combined = CombinedMessage(
            chat_id=12345,
            user_id=67890,
            messages=[regular_msg, meta_msg],
        )

        result = combined.get_command_message()
        assert result is not None
        assert result.is_meta_command is True
        assert result.command_type == "meta"
        assert result.text == "do something"

    @pytest.mark.asyncio
    async def test_command_type_stored_correctly(
        self, buffer_service, mock_update, mock_context
    ):
        """Test that command_type is stored correctly for all command types."""
        received_combined = []

        async def mock_callback(combined: CombinedMessage):
            received_combined.append(combined)

        buffer_service.set_process_callback(mock_callback)

        # Test /claude
        mock_update.message.message_id = 100
        mock_update.message.text = None
        mock_update.message.photo = [MagicMock(file_id="photo_1")]
        mock_update.message.caption = "/claude test"
        await buffer_service.add_message(mock_update, mock_context)
        await asyncio.sleep(0.15)

        assert len(received_combined) == 1
        cmd_msg = received_combined[0].get_command_message()
        assert cmd_msg.command_type == "claude"
        assert cmd_msg.is_claude_command is True

        received_combined.clear()

        # Test /meta
        mock_update.message.message_id = 101
        mock_update.message.photo = [MagicMock(file_id="photo_2")]
        mock_update.message.caption = "/meta test"
        await buffer_service.add_message(mock_update, mock_context)
        await asyncio.sleep(0.15)

        assert len(received_combined) == 1
        cmd_msg = received_combined[0].get_command_message()
        assert cmd_msg.command_type == "meta"
        assert cmd_msg.is_meta_command is True

        received_combined.clear()

        # Test /dev
        mock_update.message.message_id = 102
        mock_update.message.photo = [MagicMock(file_id="photo_3")]
        mock_update.message.caption = "/dev test"
        await buffer_service.add_message(mock_update, mock_context)
        await asyncio.sleep(0.15)

        assert len(received_combined) == 1
        cmd_msg = received_combined[0].get_command_message()
        assert cmd_msg.command_type == "dev"
        assert cmd_msg.is_dev_command is True


# =============================================================================
# Buffer Size Limit Tests (#182)
# =============================================================================


class TestMessageBufferSizeLimit:
    """Tests for the hard buffer size limit (security: prevent memory abuse)."""

    @pytest.mark.asyncio
    async def test_buffer_accepts_messages_up_to_limit(self, mock_update, mock_context):
        """Buffer accepts messages up to the max_buffer_size limit."""
        service = MessageBufferService(
            buffer_timeout=10.0,  # Long timeout so we don't flush
            max_messages=100,  # High flush threshold
            max_buffer_size=5,  # Low hard cap for testing
        )

        for i in range(5):
            mock_update.message.message_id = 100 + i
            mock_update.message.text = f"Message {i}"
            await service.add_message(mock_update, mock_context)

        status = await service.get_buffer_status(12345, 67890)
        assert status is not None
        assert status["message_count"] == 5

    @pytest.mark.asyncio
    async def test_messages_beyond_limit_are_dropped(self, mock_update, mock_context):
        """Messages beyond the max_buffer_size limit are dropped."""
        service = MessageBufferService(
            buffer_timeout=10.0,
            max_messages=100,
            max_buffer_size=3,
        )

        # Add 5 messages, only 3 should be kept
        for i in range(5):
            mock_update.message.message_id = 100 + i
            mock_update.message.text = f"Message {i}"
            await service.add_message(mock_update, mock_context)

        status = await service.get_buffer_status(12345, 67890)
        assert status is not None
        assert status["message_count"] == 3  # Only first 3 kept

    @pytest.mark.asyncio
    async def test_warning_logged_when_limit_reached(
        self, mock_update, mock_context, caplog
    ):
        """A warning is logged when the buffer size limit is reached."""
        import logging

        service = MessageBufferService(
            buffer_timeout=10.0,
            max_messages=100,
            max_buffer_size=2,
        )

        # Fill the buffer
        for i in range(2):
            mock_update.message.message_id = 100 + i
            mock_update.message.text = f"Message {i}"
            await service.add_message(mock_update, mock_context)

        # Next message should trigger warning
        with caplog.at_level(logging.WARNING, logger="src.services.message_buffer"):
            mock_update.message.message_id = 200
            mock_update.message.text = "Overflow message"
            await service.add_message(mock_update, mock_context)

        assert any("Buffer size limit reached" in msg for msg in caplog.messages)

        # Verify the message was dropped
        status = await service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 2

    @pytest.mark.asyncio
    async def test_warning_logged_only_once_per_window(
        self, mock_update, mock_context, caplog
    ):
        """Only first overflow triggers WARNING; rest use DEBUG."""
        import logging

        service = MessageBufferService(
            buffer_timeout=10.0,
            max_messages=100,
            max_buffer_size=1,
        )

        # Fill the buffer
        mock_update.message.message_id = 100
        mock_update.message.text = "First"
        await service.add_message(mock_update, mock_context)

        with caplog.at_level(logging.DEBUG, logger="src.services.message_buffer"):
            # Add 3 more overflow messages
            for i in range(3):
                mock_update.message.message_id = 200 + i
                mock_update.message.text = f"Overflow {i}"
                await service.add_message(mock_update, mock_context)

        warning_messages = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "Buffer size limit reached" in r.message
        ]
        debug_messages = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG and "Dropping message" in r.message
        ]

        assert len(warning_messages) == 1  # Only one WARNING
        assert len(debug_messages) == 2  # Remaining are DEBUG

    @pytest.mark.asyncio
    async def test_configurable_limit_works(self, mock_update, mock_context):
        """The max_buffer_size parameter is configurable."""
        for limit in [1, 5, 50]:
            service = MessageBufferService(
                buffer_timeout=10.0,
                max_messages=100,
                max_buffer_size=limit,
            )

            for i in range(limit + 5):
                mock_update.message.message_id = 100 + i
                mock_update.message.text = f"Message {i}"
                await service.add_message(mock_update, mock_context)

            status = await service.get_buffer_status(12345, 67890)
            assert status["message_count"] == limit

    @pytest.mark.asyncio
    async def test_overflow_flag_cleared_on_flush(self, mock_update, mock_context):
        """After a buffer flush, new messages can be accepted."""
        service = MessageBufferService(
            buffer_timeout=0.05,  # Short timeout to trigger flush
            max_messages=100,
            max_buffer_size=2,
        )

        received_combined = []

        async def mock_callback(combined):
            received_combined.append(combined)

        service.set_process_callback(mock_callback)

        # Fill to limit
        mock_update.message.message_id = 100
        mock_update.message.text = "First"
        await service.add_message(mock_update, mock_context)

        mock_update.message.message_id = 101
        mock_update.message.text = "Second"
        await service.add_message(mock_update, mock_context)

        # Wait for flush
        await asyncio.sleep(0.15)

        assert len(received_combined) == 1

        # After flush, buffer should accept new messages
        mock_update.message.message_id = 200
        mock_update.message.text = "After flush"
        await service.add_message(mock_update, mock_context)

        status = await service.get_buffer_status(12345, 67890)
        assert status is not None
        assert status["message_count"] == 1

    @pytest.mark.asyncio
    async def test_claude_command_respects_buffer_limit(
        self, mock_update, mock_context
    ):
        """add_claude_command also respects the buffer size limit."""
        service = MessageBufferService(
            buffer_timeout=10.0,
            max_messages=100,
            max_buffer_size=2,
        )

        # Fill buffer with regular messages
        for i in range(2):
            mock_update.message.message_id = 100 + i
            mock_update.message.text = f"Message {i}"
            await service.add_message(mock_update, mock_context)

        # Claude command should be dropped
        await service.add_claude_command(mock_update, mock_context, "analyze this")

        status = await service.get_buffer_status(12345, 67890)
        assert status["message_count"] == 2  # Claude cmd dropped

    @pytest.mark.asyncio
    async def test_default_max_buffer_size(self):
        """Default max_buffer_size is 20."""
        service = MessageBufferService()
        assert service.max_buffer_size == 20

    @pytest.mark.asyncio
    async def test_init_message_buffer_passes_max_buffer_size(self):
        """init_message_buffer passes max_buffer_size to service."""
        from src.core.container import reset_container
        from src.core.services import setup_services

        reset_container()
        setup_services()

        service = init_message_buffer(max_buffer_size=42)
        assert service.max_buffer_size == 42
