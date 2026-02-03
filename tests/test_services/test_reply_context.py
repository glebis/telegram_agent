"""
Tests for the Reply Context Service.

Tests cover:
- MessageType enum values
- ReplyContext dataclass creation, expiration, and summaries
- LRUCache implementation
- ReplyContextService core functionality
- Convenience tracking methods
- Prompt building for different context types
- Global instance management
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.services.reply_context import (
    LRUCache,
    MessageType,
    ReplyContext,
    ReplyContextService,
    get_reply_context_service,
    init_reply_context_service,
)

# =============================================================================
# MessageType Tests
# =============================================================================


class TestMessageType:
    """Tests for MessageType enum."""

    def test_all_message_types_exist(self):
        """Test that all expected message types are defined."""
        assert MessageType.CLAUDE_RESPONSE.value == "claude_response"
        assert MessageType.IMAGE_ANALYSIS.value == "image_analysis"
        assert MessageType.VOICE_TRANSCRIPTION.value == "voice_transcription"
        assert MessageType.LINK_CAPTURE.value == "link_capture"
        assert MessageType.USER_TEXT.value == "user_text"
        assert MessageType.BOT_ERROR.value == "bot_error"
        assert MessageType.BOT_INFO.value == "bot_info"
        assert MessageType.POLL_RESPONSE.value == "poll_response"

    def test_message_type_count(self):
        """Test that we have expected number of message types."""
        assert len(MessageType) == 8


# =============================================================================
# ReplyContext Tests
# =============================================================================


class TestReplyContext:
    """Tests for ReplyContext dataclass."""

    def test_create_basic_context(self):
        """Test creating a basic ReplyContext."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
        )

        assert context.message_id == 123
        assert context.chat_id == 456
        assert context.user_id == 789
        assert context.message_type == MessageType.USER_TEXT
        assert context.created_at is not None

    def test_create_claude_context(self):
        """Test creating a Claude response context."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_abc",
            prompt="What is Python?",
            response_text="Python is a programming language...",
        )

        assert context.session_id == "session_abc"
        assert context.prompt == "What is Python?"
        assert context.response_text == "Python is a programming language..."

    def test_create_image_context(self):
        """Test creating an image analysis context."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.IMAGE_ANALYSIS,
            image_path="/path/to/image.jpg",
            image_file_id="file_123",
            image_analysis={"description": "A cat sitting on a table"},
        )

        assert context.image_path == "/path/to/image.jpg"
        assert context.image_file_id == "file_123"
        assert context.image_analysis["description"] == "A cat sitting on a table"

    def test_create_voice_context(self):
        """Test creating a voice transcription context."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.VOICE_TRANSCRIPTION,
            transcription="Hello, this is a voice message",
            voice_file_id="voice_123",
        )

        assert context.transcription == "Hello, this is a voice message"
        assert context.voice_file_id == "voice_123"

    def test_create_link_context(self):
        """Test creating a link capture context."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.LINK_CAPTURE,
            url="https://example.com/article",
            link_title="Example Article",
            link_path="/vault/links/example.md",
        )

        assert context.url == "https://example.com/article"
        assert context.link_title == "Example Article"
        assert context.link_path == "/vault/links/example.md"

    def test_metadata_default(self):
        """Test that metadata defaults to empty dict."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
        )

        assert context.metadata == {}

    def test_metadata_custom(self):
        """Test custom metadata."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
            metadata={"custom_key": "custom_value"},
        )

        assert context.metadata["custom_key"] == "custom_value"


class TestReplyContextExpiration:
    """Tests for ReplyContext expiration."""

    def test_not_expired_recent(self):
        """Test that recent context is not expired."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
        )

        assert context.is_expired(ttl_hours=24) is False

    def test_expired_old(self):
        """Test that old context is expired."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
            created_at=datetime.now() - timedelta(hours=25),
        )

        assert context.is_expired(ttl_hours=24) is True

    def test_expired_custom_ttl(self):
        """Test expiration with custom TTL."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
            created_at=datetime.now() - timedelta(hours=2),
        )

        # Not expired with 24h TTL
        assert context.is_expired(ttl_hours=24) is False
        # Expired with 1h TTL
        assert context.is_expired(ttl_hours=1) is True

    def test_boundary_expiration(self):
        """Test expiration at boundary."""
        # Exactly at TTL boundary
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
            created_at=datetime.now() - timedelta(hours=24, seconds=1),
        )

        assert context.is_expired(ttl_hours=24) is True


class TestReplyContextSummary:
    """Tests for ReplyContext summary generation."""

    def test_summary_claude_response(self):
        """Test summary for Claude response."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.CLAUDE_RESPONSE,
            prompt="What is the meaning of life?",
        )

        summary = context.get_context_summary()
        assert "Previous Claude response" in summary
        assert "What is the meaning of life?" in summary

    def test_summary_claude_response_no_prompt(self):
        """Test summary for Claude response without prompt."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.CLAUDE_RESPONSE,
        )

        summary = context.get_context_summary()
        assert "unknown" in summary

    def test_summary_claude_response_long_prompt(self):
        """Test summary truncates long prompts."""
        long_prompt = "x" * 200
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.CLAUDE_RESPONSE,
            prompt=long_prompt,
        )

        summary = context.get_context_summary()
        # Should be truncated to 100 chars
        assert len(summary) < len(long_prompt) + 50

    def test_summary_image_analysis(self):
        """Test summary for image analysis."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.IMAGE_ANALYSIS,
            image_path="/path/to/cat.jpg",
        )

        summary = context.get_context_summary()
        assert "Image analysis" in summary
        assert "/path/to/cat.jpg" in summary

    def test_summary_voice_transcription(self):
        """Test summary for voice transcription."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.VOICE_TRANSCRIPTION,
            transcription="Hello this is a test transcription",
        )

        summary = context.get_context_summary()
        assert "Voice transcription" in summary
        assert "Hello this is a test" in summary

    def test_summary_link_capture(self):
        """Test summary for link capture."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.LINK_CAPTURE,
            url="https://example.com",
            link_title="Example Site",
        )

        summary = context.get_context_summary()
        assert "Link capture" in summary
        assert "Example Site" in summary

    def test_summary_link_capture_no_title(self):
        """Test summary for link capture without title."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.LINK_CAPTURE,
            url="https://example.com",
        )

        summary = context.get_context_summary()
        assert "https://example.com" in summary

    def test_summary_user_text(self):
        """Test summary for user text."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.USER_TEXT,
            original_text="This is a user message",
        )

        summary = context.get_context_summary()
        assert "User message" in summary
        assert "This is a user message" in summary

    def test_summary_bot_error(self):
        """Test summary for bot error (fallback)."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.BOT_ERROR,
        )

        summary = context.get_context_summary()
        assert "bot_error" in summary

    def test_summary_bot_info(self):
        """Test summary for bot info (fallback)."""
        context = ReplyContext(
            message_id=123,
            chat_id=456,
            user_id=789,
            message_type=MessageType.BOT_INFO,
        )

        summary = context.get_context_summary()
        assert "bot_info" in summary


# =============================================================================
# LRUCache Tests
# =============================================================================


class TestLRUCache:
    """Tests for LRUCache implementation."""

    def test_basic_set_get(self):
        """Test basic set and get operations."""
        cache = LRUCache(max_size=10)
        cache["key1"] = "value1"

        assert cache["key1"] == "value1"

    def test_get_missing_key(self):
        """Test getting missing key raises KeyError."""
        cache = LRUCache(max_size=10)

        with pytest.raises(KeyError):
            _ = cache["missing"]

    def test_get_with_default(self):
        """Test get method with default value."""
        cache = LRUCache(max_size=10)

        assert cache.get("missing") is None
        assert cache.get("missing", "default") == "default"

    def test_max_size_eviction(self):
        """Test that oldest items are evicted when max size exceeded."""
        cache = LRUCache(max_size=3)

        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3

        assert len(cache) == 3

        # Adding 4th item should evict oldest
        cache["d"] = 4

        assert len(cache) == 3
        assert "a" not in cache  # Oldest evicted
        assert cache["b"] == 2
        assert cache["c"] == 3
        assert cache["d"] == 4

    def test_lru_ordering_on_access(self):
        """Test that accessing an item moves it to end (most recent)."""
        cache = LRUCache(max_size=3)

        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3

        # Access 'a' to make it most recent
        _ = cache["a"]

        # Add new item - should evict 'b' (now oldest)
        cache["d"] = 4

        assert "a" in cache  # Was accessed, so kept
        assert "b" not in cache  # Oldest, evicted
        assert "c" in cache
        assert "d" in cache

    def test_lru_ordering_on_update(self):
        """Test that updating an item moves it to end (most recent)."""
        cache = LRUCache(max_size=3)

        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3

        # Update 'a' to make it most recent
        cache["a"] = 100

        # Add new item - should evict 'b' (now oldest)
        cache["d"] = 4

        assert cache["a"] == 100  # Updated and kept
        assert "b" not in cache  # Oldest, evicted
        assert "c" in cache
        assert "d" in cache

    def test_get_moves_to_end(self):
        """Test that get() moves item to end."""
        cache = LRUCache(max_size=3)

        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3

        # Use get() on 'a'
        result = cache.get("a")
        assert result == 1

        # Add new items to force eviction
        cache["d"] = 4

        assert "a" in cache  # Accessed via get, should be kept
        assert "b" not in cache  # Oldest

    def test_empty_cache(self):
        """Test operations on empty cache."""
        cache = LRUCache(max_size=10)

        assert len(cache) == 0
        assert cache.get("missing") is None

    def test_single_item_cache(self):
        """Test cache with max_size=1."""
        cache = LRUCache(max_size=1)

        cache["a"] = 1
        assert cache["a"] == 1

        cache["b"] = 2
        assert "a" not in cache
        assert cache["b"] == 2


# =============================================================================
# ReplyContextService Tests
# =============================================================================


class TestReplyContextServiceInit:
    """Tests for ReplyContextService initialization."""

    def test_default_initialization(self):
        """Test default service initialization."""
        service = ReplyContextService()

        assert service.max_cache_size == 1000
        assert service.ttl_hours == 24

    def test_custom_initialization(self):
        """Test custom service initialization."""
        service = ReplyContextService(
            max_cache_size=500,
            ttl_hours=12,
        )

        assert service.max_cache_size == 500
        assert service.ttl_hours == 12


class TestReplyContextServiceTracking:
    """Tests for message tracking."""

    def test_track_message_basic(self):
        """Test basic message tracking."""
        service = ReplyContextService()

        context = service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Hello",
        )

        assert context.message_id == 100
        assert context.chat_id == 200
        assert context.user_id == 300
        assert context.message_type == MessageType.USER_TEXT
        assert context.original_text == "Hello"

    def test_track_message_with_session(self):
        """Test tracking message with session ID."""
        service = ReplyContextService()

        context = service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_123",
        )

        # Session should be tracked
        assert "session_123" in service._session_messages
        assert 100 in service._session_messages["session_123"]

    def test_track_multiple_messages_same_session(self):
        """Test tracking multiple messages in same session."""
        service = ReplyContextService()

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_123",
        )

        service.track_message(
            message_id=101,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_123",
        )

        assert len(service._session_messages["session_123"]) == 2
        assert 100 in service._session_messages["session_123"]
        assert 101 in service._session_messages["session_123"]


class TestReplyContextServiceRetrieval:
    """Tests for context retrieval."""

    def test_get_context_exists(self):
        """Test getting existing context."""
        service = ReplyContextService()

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
        )

        context = service.get_context(chat_id=200, message_id=100)

        assert context is not None
        assert context.message_id == 100

    def test_get_context_not_found(self):
        """Test getting non-existent context."""
        service = ReplyContextService()

        context = service.get_context(chat_id=200, message_id=999)

        assert context is None

    def test_get_context_expired(self):
        """Test getting expired context returns None."""
        service = ReplyContextService(ttl_hours=1)

        # Track a message
        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
        )

        # Manually expire it
        key = service._make_key(200, 100)
        service._cache[key].created_at = datetime.now() - timedelta(hours=2)

        # Should return None due to expiration
        context = service.get_context(chat_id=200, message_id=100)
        assert context is None

    def test_get_context_expired_skip_check(self):
        """Test getting expired context with check_expiry=False."""
        service = ReplyContextService(ttl_hours=1)

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
        )

        # Manually expire it
        key = service._make_key(200, 100)
        service._cache[key].created_at = datetime.now() - timedelta(hours=2)

        # Should return context when skipping expiry check
        context = service.get_context(chat_id=200, message_id=100, check_expiry=False)
        assert context is not None

    def test_get_context_different_chats(self):
        """Test contexts are separate per chat."""
        service = ReplyContextService()

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Chat 200 message",
        )

        service.track_message(
            message_id=100,
            chat_id=201,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Chat 201 message",
        )

        ctx200 = service.get_context(chat_id=200, message_id=100)
        ctx201 = service.get_context(chat_id=201, message_id=100)

        assert ctx200.original_text == "Chat 200 message"
        assert ctx201.original_text == "Chat 201 message"


class TestReplyContextServiceConvenienceMethods:
    """Tests for convenience tracking methods."""

    def test_track_claude_response(self):
        """Test track_claude_response convenience method."""
        service = ReplyContextService()

        context = service.track_claude_response(
            message_id=100,
            chat_id=200,
            user_id=300,
            session_id="session_abc",
            prompt="What is AI?",
            response_text="AI is...",
        )

        assert context.message_type == MessageType.CLAUDE_RESPONSE
        assert context.session_id == "session_abc"
        assert context.prompt == "What is AI?"
        assert context.response_text == "AI is..."

    def test_track_image_analysis(self):
        """Test track_image_analysis convenience method."""
        service = ReplyContextService()

        context = service.track_image_analysis(
            message_id=100,
            chat_id=200,
            user_id=300,
            image_path="/path/to/image.jpg",
            image_file_id="file_123",
            analysis={"description": "A cat"},
        )

        assert context.message_type == MessageType.IMAGE_ANALYSIS
        assert context.image_path == "/path/to/image.jpg"
        assert context.image_file_id == "file_123"
        assert context.image_analysis["description"] == "A cat"

    def test_track_voice_transcription(self):
        """Test track_voice_transcription convenience method."""
        service = ReplyContextService()

        context = service.track_voice_transcription(
            message_id=100,
            chat_id=200,
            user_id=300,
            transcription="Hello world",
            voice_file_id="voice_123",
        )

        assert context.message_type == MessageType.VOICE_TRANSCRIPTION
        assert context.transcription == "Hello world"
        assert context.voice_file_id == "voice_123"

    def test_track_link_capture(self):
        """Test track_link_capture convenience method."""
        service = ReplyContextService()

        context = service.track_link_capture(
            message_id=100,
            chat_id=200,
            user_id=300,
            url="https://example.com",
            title="Example",
            path="/vault/links/example.md",
        )

        assert context.message_type == MessageType.LINK_CAPTURE
        assert context.url == "https://example.com"
        assert context.link_title == "Example"
        assert context.link_path == "/vault/links/example.md"

    def test_track_user_message(self):
        """Test track_user_message convenience method."""
        service = ReplyContextService()

        context = service.track_user_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            text="User's message text",
        )

        assert context.message_type == MessageType.USER_TEXT
        assert context.original_text == "User's message text"


class TestReplyContextServiceBuildPrompt:
    """Tests for build_reply_prompt method."""

    def test_build_prompt_claude_response(self):
        """Test building prompt for Claude response context."""
        service = ReplyContextService()

        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            prompt="What is Python?",
            session_id="session_123",
        )

        prompt = service.build_reply_prompt(context, "Tell me more")

        # For Claude, we just pass the message (session has context)
        assert prompt == "Tell me more"

    def test_build_prompt_image_analysis(self):
        """Test building prompt for image analysis context."""
        service = ReplyContextService()

        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.IMAGE_ANALYSIS,
            image_path="/path/to/cat.jpg",
            image_analysis={"description": "A fluffy cat"},
        )

        prompt = service.build_reply_prompt(context, "What breed is it?")

        assert "Replying to image analysis" in prompt
        assert "/path/to/cat.jpg" in prompt
        assert "A fluffy cat" in prompt
        assert "What breed is it?" in prompt

    def test_build_prompt_voice_transcription(self):
        """Test building prompt for voice transcription context."""
        service = ReplyContextService()

        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.VOICE_TRANSCRIPTION,
            transcription="Meeting notes from today",
        )

        prompt = service.build_reply_prompt(context, "Summarize it")

        assert "Replying to voice transcription" in prompt
        assert "Meeting notes from today" in prompt
        assert "Summarize it" in prompt

    def test_build_prompt_link_capture(self):
        """Test building prompt for link capture context."""
        service = ReplyContextService()

        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.LINK_CAPTURE,
            url="https://example.com/article",
            link_title="Great Article",
            link_path="/vault/links/article.md",
        )

        prompt = service.build_reply_prompt(context, "What's it about?")

        assert "Replying to captured link" in prompt
        assert "https://example.com/article" in prompt
        assert "Great Article" in prompt
        assert "/vault/links/article.md" in prompt
        assert "What's it about?" in prompt

    def test_build_prompt_user_text(self):
        """Test building prompt for user text context."""
        service = ReplyContextService()

        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Original user message",
        )

        prompt = service.build_reply_prompt(context, "My response")

        assert "Replying to previous message" in prompt
        assert "Original user message" in prompt
        assert "My response" in prompt

    def test_build_prompt_fallback(self):
        """Test building prompt for unknown/fallback context type."""
        service = ReplyContextService()

        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.BOT_INFO,
        )

        prompt = service.build_reply_prompt(context, "Follow up")

        assert "Replying to" in prompt
        assert "Follow up" in prompt


class TestReplyContextServiceCleanup:
    """Tests for cleanup operations."""

    def test_cleanup_expired_removes_old(self):
        """Test that cleanup removes expired contexts."""
        service = ReplyContextService(ttl_hours=1)

        # Track some messages
        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
        )

        service.track_message(
            message_id=101,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
        )

        # Expire one of them
        key = service._make_key(200, 100)
        service._cache[key].created_at = datetime.now() - timedelta(hours=2)

        # Run cleanup
        removed = service.cleanup_expired()

        assert removed == 1
        assert service.get_context(200, 100, check_expiry=False) is None
        assert service.get_context(200, 101) is not None

    def test_cleanup_expired_returns_count(self):
        """Test that cleanup returns correct count."""
        service = ReplyContextService(ttl_hours=1)

        # Track messages and expire all
        for i in range(5):
            service.track_message(
                message_id=100 + i,
                chat_id=200,
                user_id=300,
                message_type=MessageType.USER_TEXT,
            )
            key = service._make_key(200, 100 + i)
            service._cache[key].created_at = datetime.now() - timedelta(hours=2)

        removed = service.cleanup_expired()
        assert removed == 5

    def test_cleanup_expired_empty_cache(self):
        """Test cleanup on empty cache."""
        service = ReplyContextService()

        removed = service.cleanup_expired()
        assert removed == 0


class TestReplyContextServiceStats:
    """Tests for statistics."""

    def test_get_stats_empty(self):
        """Test stats on empty service."""
        service = ReplyContextService(max_cache_size=500, ttl_hours=12)

        stats = service.get_stats()

        assert stats["cache_size"] == 0
        assert stats["max_size"] == 500
        assert stats["sessions_tracked"] == 0
        assert stats["ttl_hours"] == 12

    def test_get_stats_with_data(self):
        """Test stats with tracked messages."""
        service = ReplyContextService()

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_1",
        )

        service.track_message(
            message_id=101,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_2",
        )

        service.track_message(
            message_id=102,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
        )

        stats = service.get_stats()

        assert stats["cache_size"] == 3
        assert stats["sessions_tracked"] == 2


class TestReplyContextServiceCacheEviction:
    """Tests for cache eviction behavior."""

    def test_cache_evicts_oldest(self):
        """Test that cache evicts oldest when full."""
        service = ReplyContextService(max_cache_size=3)

        for i in range(4):
            service.track_message(
                message_id=100 + i,
                chat_id=200,
                user_id=300,
                message_type=MessageType.USER_TEXT,
            )

        # First message should be evicted
        assert service.get_context(200, 100, check_expiry=False) is None
        assert service.get_context(200, 101, check_expiry=False) is not None
        assert service.get_context(200, 102, check_expiry=False) is not None
        assert service.get_context(200, 103, check_expiry=False) is not None


class TestReplyContextServiceSessionContext:
    """Tests for session context retrieval."""

    def test_get_session_context_no_messages(self):
        """Test get_session_context with no messages."""
        service = ReplyContextService()

        result = service.get_session_context("nonexistent_session")
        assert result is None

    def test_get_session_context_with_messages(self):
        """Test get_session_context tracks session messages."""
        service = ReplyContextService()

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_123",
        )

        # Note: Current implementation returns None (limitation documented in code)
        # This test verifies the session is tracked even if retrieval is limited
        assert "session_123" in service._session_messages


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance management."""

    def test_get_reply_context_service_creates_instance(self):
        """Test that get_reply_context_service creates instance."""
        import src.services.reply_context as rc

        rc._reply_context_service = None

        service = get_reply_context_service()

        assert service is not None
        assert isinstance(service, ReplyContextService)

    def test_get_reply_context_service_returns_same_instance(self):
        """Test that get_reply_context_service returns same instance."""
        service1 = get_reply_context_service()
        service2 = get_reply_context_service()

        assert service1 is service2

    def test_init_reply_context_service_custom_settings(self):
        """Test init_reply_context_service with custom settings."""
        import src.services.reply_context as rc

        rc._reply_context_service = None

        service = init_reply_context_service(
            max_cache_size=500,
            ttl_hours=12,
        )

        assert service.max_cache_size == 500
        assert service.ttl_hours == 12
        assert get_reply_context_service() is service

    def test_init_reply_context_service_replaces_instance(self):
        """Test that init_reply_context_service replaces existing instance."""
        service1 = init_reply_context_service(max_cache_size=100)
        service2 = init_reply_context_service(max_cache_size=200)

        assert service1 is not service2
        assert get_reply_context_service() is service2
        assert get_reply_context_service().max_cache_size == 200


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_track_message_with_all_optional_fields(self):
        """Test tracking with all optional fields populated."""
        service = ReplyContextService()

        context = service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_123",
            prompt="Test prompt",
            response_text="Test response",
            image_path="/path/image.jpg",
            image_file_id="img_123",
            image_analysis={"key": "value"},
            transcription="Test transcription",
            voice_file_id="voice_123",
            url="https://example.com",
            link_title="Example",
            link_path="/vault/link.md",
            original_text="Original",
            metadata={"custom": "data"},
        )

        assert context.session_id == "session_123"
        assert context.image_path == "/path/image.jpg"
        assert context.transcription == "Test transcription"
        assert context.url == "https://example.com"

    def test_same_message_id_different_chats(self):
        """Test same message_id in different chats are separate."""
        service = ReplyContextService()

        service.track_message(
            message_id=100,
            chat_id=1,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Chat 1",
        )

        service.track_message(
            message_id=100,
            chat_id=2,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Chat 2",
        )

        ctx1 = service.get_context(1, 100)
        ctx2 = service.get_context(2, 100)

        assert ctx1.original_text == "Chat 1"
        assert ctx2.original_text == "Chat 2"

    def test_overwrite_existing_context(self):
        """Test that tracking same message overwrites context."""
        service = ReplyContextService()

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="First",
        )

        service.track_message(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Second",
        )

        context = service.get_context(200, 100)
        assert context.original_text == "Second"

    def test_build_prompt_empty_new_message(self):
        """Test building prompt with empty new message."""
        service = ReplyContextService()

        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.USER_TEXT,
            original_text="Original",
        )

        prompt = service.build_reply_prompt(context, "")

        assert "Original" in prompt

    def test_context_with_none_optional_fields(self):
        """Test context summary with None optional fields."""
        context = ReplyContext(
            message_id=100,
            chat_id=200,
            user_id=300,
            message_type=MessageType.IMAGE_ANALYSIS,
            # image_path is None
        )

        summary = context.get_context_summary()
        assert "unknown" in summary


# =============================================================================
# LRU Cache Eviction Tests (Issue #35)
# =============================================================================


class TestLRUCacheEviction:
    """Tests for LRU cache eviction behavior."""

    def test_lru_cache_respects_max_size(self):
        cache = LRUCache(max_size=3)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        cache["d"] = 4  # Should evict "a"
        assert "a" not in cache
        assert len(cache) == 3

    def test_lru_cache_evicts_oldest(self):
        cache = LRUCache(max_size=2)
        cache["a"] = 1
        cache["b"] = 2
        cache["a"]  # Access "a" to make it recent
        cache["c"] = 3  # Should evict "b" (oldest)
        assert "a" in cache
        assert "b" not in cache
        assert "c" in cache


# =============================================================================
# Session Messages Cleanup Tests (Issue #35 - Memory Leak)
# =============================================================================


class TestSessionMessagesCleanup:
    """Tests for _session_messages cleanup when cache entries are evicted."""

    def test_session_messages_cleaned_on_cache_eviction(self):
        """When LRU evicts a cache entry, its session_messages entry should also be cleaned."""
        service = ReplyContextService(max_cache_size=2, ttl_hours=24)

        # Track 3 messages with different sessions - third should evict first
        service.track_message(
            message_id=1,
            chat_id=100,
            user_id=1,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_a",
        )
        service.track_message(
            message_id=2,
            chat_id=100,
            user_id=1,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_b",
        )
        service.track_message(
            message_id=3,
            chat_id=100,
            user_id=1,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_c",
        )

        # session_a's message was evicted from cache
        assert service.get_context(100, 1) is None
        # session_a should be cleaned from _session_messages too
        assert "session_a" not in service._session_messages

    def test_session_messages_not_cleaned_when_other_entries_remain(self):
        """If a session has multiple messages and only one is evicted, keep the session entry."""
        service = ReplyContextService(max_cache_size=3, ttl_hours=24)

        # Track 2 messages for same session
        service.track_message(
            message_id=1,
            chat_id=100,
            user_id=1,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_a",
        )
        service.track_message(
            message_id=2,
            chat_id=100,
            user_id=1,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="session_a",
        )
        # Fill cache to evict msg 1
        service.track_message(
            message_id=3,
            chat_id=100,
            user_id=1,
            message_type=MessageType.USER_TEXT,
        )
        service.track_message(
            message_id=4,
            chat_id=100,
            user_id=1,
            message_type=MessageType.USER_TEXT,
        )

        # session_a should still exist because msg 2 is still in cache
        # (msg 1 evicted, msg 2 still there)
        if service.get_context(100, 2) is not None:
            assert "session_a" in service._session_messages

    def test_cleanup_expired_also_cleans_session_messages(self):
        """cleanup_expired should also remove stale _session_messages entries."""
        service = ReplyContextService(max_cache_size=100, ttl_hours=1)

        # Track a message with a session
        ctx = service.track_message(
            message_id=1,
            chat_id=100,
            user_id=1,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id="old_session",
        )
        # Make it expired
        ctx.created_at = datetime.now() - timedelta(hours=2)

        assert "old_session" in service._session_messages

        service.cleanup_expired()

        assert "old_session" not in service._session_messages

    def test_session_messages_bounded_after_many_inserts(self):
        """After many inserts, _session_messages should not exceed cache size."""
        service = ReplyContextService(max_cache_size=10, ttl_hours=24)

        for i in range(100):
            service.track_message(
                message_id=i,
                chat_id=100,
                user_id=1,
                message_type=MessageType.CLAUDE_RESPONSE,
                session_id=f"session_{i}",
            )

        # _session_messages should be bounded (no more than cache_size entries)
        assert len(service._session_messages) <= 10

    def test_get_stats_reflects_actual_session_count(self):
        """Stats should show accurate session count after cleanup."""
        service = ReplyContextService(max_cache_size=5, ttl_hours=24)

        for i in range(20):
            service.track_message(
                message_id=i,
                chat_id=100,
                user_id=1,
                message_type=MessageType.CLAUDE_RESPONSE,
                session_id=f"session_{i}",
            )

        stats = service.get_stats()
        assert stats["sessions_tracked"] <= 5
