"""
Tests for the Collect Mode Service.

Tests cover:
- CollectItemType enum values
- CollectItem dataclass creation, serialization, and deserialization
- CollectSession dataclass properties and helper methods
- CollectService core functionality
- Session lifecycle (start, end, get, add items)
- Database persistence mocking
- Session timeout handling
- Trigger keyword detection
- Global instance management
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.collect_service import (
    TRIGGER_KEYWORDS,
    CollectItem,
    CollectItemType,
    CollectService,
    CollectSession,
    get_collect_service,
)

# =============================================================================
# CollectItemType Tests
# =============================================================================


class TestCollectItemType:
    """Tests for CollectItemType enum."""

    def test_all_item_types_exist(self):
        """Test that all expected item types are defined."""
        assert CollectItemType.TEXT.value == "text"
        assert CollectItemType.IMAGE.value == "image"
        assert CollectItemType.VOICE.value == "voice"
        assert CollectItemType.VIDEO.value == "video"
        assert CollectItemType.DOCUMENT.value == "document"
        assert CollectItemType.VIDEO_NOTE.value == "video_note"

    def test_item_type_count(self):
        """Test that we have expected number of item types."""
        assert len(CollectItemType) == 6


# =============================================================================
# CollectItem Tests
# =============================================================================


class TestCollectItem:
    """Tests for CollectItem dataclass."""

    def test_create_text_item(self):
        """Test creating a text CollectItem."""
        item = CollectItem(
            type=CollectItemType.TEXT,
            message_id=123,
            timestamp=datetime.now(),
            content="Hello world",
        )

        assert item.type == CollectItemType.TEXT
        assert item.message_id == 123
        assert item.content == "Hello world"
        assert item.caption is None
        assert item.file_name is None
        assert item.mime_type is None
        assert item.duration is None
        assert item.transcription is None

    def test_create_image_item(self):
        """Test creating an image CollectItem."""
        item = CollectItem(
            type=CollectItemType.IMAGE,
            message_id=124,
            timestamp=datetime.now(),
            content="file_id_123",
            caption="Photo caption",
            mime_type="image/jpeg",
        )

        assert item.type == CollectItemType.IMAGE
        assert item.content == "file_id_123"
        assert item.caption == "Photo caption"
        assert item.mime_type == "image/jpeg"

    def test_create_voice_item(self):
        """Test creating a voice CollectItem."""
        item = CollectItem(
            type=CollectItemType.VOICE,
            message_id=125,
            timestamp=datetime.now(),
            content="voice_file_id",
            duration=30,
            transcription="Hello, this is a voice message",
        )

        assert item.type == CollectItemType.VOICE
        assert item.duration == 30
        assert item.transcription == "Hello, this is a voice message"

    def test_create_document_item(self):
        """Test creating a document CollectItem."""
        item = CollectItem(
            type=CollectItemType.DOCUMENT,
            message_id=126,
            timestamp=datetime.now(),
            content="doc_file_id",
            file_name="report.pdf",
            mime_type="application/pdf",
        )

        assert item.type == CollectItemType.DOCUMENT
        assert item.file_name == "report.pdf"
        assert item.mime_type == "application/pdf"

    def test_create_video_item(self):
        """Test creating a video CollectItem."""
        item = CollectItem(
            type=CollectItemType.VIDEO,
            message_id=127,
            timestamp=datetime.now(),
            content="video_file_id",
            duration=120,
            caption="Video caption",
        )

        assert item.type == CollectItemType.VIDEO
        assert item.duration == 120
        assert item.caption == "Video caption"

    def test_create_video_note_item(self):
        """Test creating a video note CollectItem."""
        item = CollectItem(
            type=CollectItemType.VIDEO_NOTE,
            message_id=128,
            timestamp=datetime.now(),
            content="video_note_file_id",
            duration=15,
        )

        assert item.type == CollectItemType.VIDEO_NOTE
        assert item.duration == 15


class TestCollectItemSerialization:
    """Tests for CollectItem serialization."""

    def test_to_dict(self):
        """Test converting CollectItem to dictionary."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        item = CollectItem(
            type=CollectItemType.TEXT,
            message_id=123,
            timestamp=timestamp,
            content="Test content",
            caption="Test caption",
        )

        result = item.to_dict()

        assert result["type"] == "text"
        assert result["message_id"] == 123
        assert result["timestamp"] == "2024-01-15T10:30:00"
        assert result["content"] == "Test content"
        assert result["caption"] == "Test caption"
        assert result["file_name"] is None
        assert result["mime_type"] is None
        assert result["duration"] is None
        assert result["transcription"] is None

    def test_to_dict_all_fields(self):
        """Test to_dict with all fields populated."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        item = CollectItem(
            type=CollectItemType.VOICE,
            message_id=200,
            timestamp=timestamp,
            content="voice_file_id",
            caption=None,
            file_name="audio.ogg",
            mime_type="audio/ogg",
            duration=45,
            transcription="Transcribed text",
        )

        result = item.to_dict()

        assert result["type"] == "voice"
        assert result["file_name"] == "audio.ogg"
        assert result["mime_type"] == "audio/ogg"
        assert result["duration"] == 45
        assert result["transcription"] == "Transcribed text"

    def test_from_dict(self):
        """Test creating CollectItem from dictionary."""
        data = {
            "type": "text",
            "message_id": 123,
            "timestamp": "2024-01-15T10:30:00",
            "content": "Test content",
            "caption": None,
            "file_name": None,
            "mime_type": None,
            "duration": None,
            "transcription": None,
        }

        item = CollectItem.from_dict(data)

        assert item.type == CollectItemType.TEXT
        assert item.message_id == 123
        assert item.timestamp == datetime(2024, 1, 15, 10, 30, 0)
        assert item.content == "Test content"

    def test_from_dict_with_optional_fields(self):
        """Test from_dict with optional fields."""
        data = {
            "type": "voice",
            "message_id": 200,
            "timestamp": "2024-01-15T11:00:00",
            "content": "voice_123",
            "duration": 30,
            "transcription": "Hello world",
        }

        item = CollectItem.from_dict(data)

        assert item.type == CollectItemType.VOICE
        assert item.duration == 30
        assert item.transcription == "Hello world"
        assert item.caption is None  # Not in data

    def test_roundtrip_serialization(self):
        """Test that to_dict and from_dict are inverse operations."""
        original = CollectItem(
            type=CollectItemType.DOCUMENT,
            message_id=300,
            timestamp=datetime(2024, 2, 20, 14, 45, 0),
            content="doc_file_id",
            caption="Document caption",
            file_name="report.pdf",
            mime_type="application/pdf",
            duration=None,
            transcription=None,
        )

        serialized = original.to_dict()
        restored = CollectItem.from_dict(serialized)

        assert restored.type == original.type
        assert restored.message_id == original.message_id
        assert restored.timestamp == original.timestamp
        assert restored.content == original.content
        assert restored.caption == original.caption
        assert restored.file_name == original.file_name
        assert restored.mime_type == original.mime_type


# =============================================================================
# CollectSession Tests
# =============================================================================


class TestCollectSession:
    """Tests for CollectSession dataclass."""

    def test_create_empty_session(self):
        """Test creating an empty CollectSession."""
        session = CollectSession(
            chat_id=12345,
            user_id=67890,
        )

        assert session.chat_id == 12345
        assert session.user_id == 67890
        assert session.items == []
        assert session.pending_prompt is None
        assert session.started_at is not None

    def test_item_count_property(self):
        """Test item_count property."""
        session = CollectSession(chat_id=1, user_id=2)

        assert session.item_count == 0

        session.items.append(
            CollectItem(
                type=CollectItemType.TEXT,
                message_id=1,
                timestamp=datetime.now(),
                content="test",
            )
        )

        assert session.item_count == 1

    def test_age_seconds_property(self):
        """Test age_seconds property."""
        session = CollectSession(
            chat_id=1,
            user_id=2,
            started_at=datetime.now() - timedelta(seconds=30),
        )

        age = session.age_seconds
        assert 29 <= age <= 31  # Allow for some timing variance


class TestCollectSessionSummary:
    """Tests for CollectSession summary methods."""

    def test_summary_empty_session(self):
        """Test summary of empty session."""
        session = CollectSession(chat_id=1, user_id=2)

        assert session.summary() == {}

    def test_summary_single_type(self):
        """Test summary with single item type."""
        session = CollectSession(chat_id=1, user_id=2)
        session.items.append(
            CollectItem(
                type=CollectItemType.TEXT,
                message_id=1,
                timestamp=datetime.now(),
                content="test",
            )
        )

        assert session.summary() == {"text": 1}

    def test_summary_multiple_types(self):
        """Test summary with multiple item types."""
        session = CollectSession(chat_id=1, user_id=2)
        session.items.extend(
            [
                CollectItem(
                    type=CollectItemType.TEXT,
                    message_id=1,
                    timestamp=datetime.now(),
                    content="test1",
                ),
                CollectItem(
                    type=CollectItemType.TEXT,
                    message_id=2,
                    timestamp=datetime.now(),
                    content="test2",
                ),
                CollectItem(
                    type=CollectItemType.IMAGE,
                    message_id=3,
                    timestamp=datetime.now(),
                    content="img1",
                ),
                CollectItem(
                    type=CollectItemType.VOICE,
                    message_id=4,
                    timestamp=datetime.now(),
                    content="voice1",
                ),
            ]
        )

        summary = session.summary()
        assert summary["text"] == 2
        assert summary["image"] == 1
        assert summary["voice"] == 1

    def test_summary_text_empty(self):
        """Test summary_text for empty session."""
        session = CollectSession(chat_id=1, user_id=2)

        assert session.summary_text() == "empty"

    def test_summary_text_single_item(self):
        """Test summary_text with single item."""
        session = CollectSession(chat_id=1, user_id=2)
        session.items.append(
            CollectItem(
                type=CollectItemType.IMAGE,
                message_id=1,
                timestamp=datetime.now(),
                content="img",
            )
        )

        assert session.summary_text() == "1 image"

    def test_summary_text_multiple_items_pluralization(self):
        """Test summary_text with multiple items (pluralization)."""
        session = CollectSession(chat_id=1, user_id=2)
        session.items.extend(
            [
                CollectItem(
                    type=CollectItemType.IMAGE,
                    message_id=i,
                    timestamp=datetime.now(),
                    content=f"img{i}",
                )
                for i in range(3)
            ]
        )

        assert session.summary_text() == "3 images"

    def test_summary_text_mixed_types(self):
        """Test summary_text with mixed types."""
        session = CollectSession(chat_id=1, user_id=2)
        session.items.extend(
            [
                CollectItem(
                    type=CollectItemType.TEXT,
                    message_id=1,
                    timestamp=datetime.now(),
                    content="text1",
                ),
                CollectItem(
                    type=CollectItemType.IMAGE,
                    message_id=2,
                    timestamp=datetime.now(),
                    content="img1",
                ),
                CollectItem(
                    type=CollectItemType.IMAGE,
                    message_id=3,
                    timestamp=datetime.now(),
                    content="img2",
                ),
            ]
        )

        summary = session.summary_text()
        assert "1 text" in summary
        assert "2 images" in summary

    def test_summary_text_video_note_label(self):
        """Test that video_note has correct label."""
        session = CollectSession(chat_id=1, user_id=2)
        session.items.extend(
            [
                CollectItem(
                    type=CollectItemType.VIDEO_NOTE,
                    message_id=1,
                    timestamp=datetime.now(),
                    content="vn1",
                ),
                CollectItem(
                    type=CollectItemType.VIDEO_NOTE,
                    message_id=2,
                    timestamp=datetime.now(),
                    content="vn2",
                ),
            ]
        )

        assert "2 video notes" in session.summary_text()


class TestCollectSessionSerialization:
    """Tests for CollectSession serialization."""

    def test_to_items_json_empty(self):
        """Test JSON serialization of empty items."""
        session = CollectSession(chat_id=1, user_id=2)

        result = session.to_items_json()
        assert result == "[]"

    def test_to_items_json_with_items(self):
        """Test JSON serialization with items."""
        session = CollectSession(chat_id=1, user_id=2)
        session.items.append(
            CollectItem(
                type=CollectItemType.TEXT,
                message_id=123,
                timestamp=datetime(2024, 1, 15, 10, 0, 0),
                content="Test content",
            )
        )

        result = session.to_items_json()
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0]["type"] == "text"
        assert parsed[0]["message_id"] == 123
        assert parsed[0]["content"] == "Test content"

    def test_from_db_with_empty_items(self):
        """Test creating CollectSession from database model with empty items."""
        mock_db_session = MagicMock()
        mock_db_session.chat_id = 12345
        mock_db_session.user_id = 67890
        mock_db_session.started_at = datetime(2024, 1, 15, 10, 0, 0)
        mock_db_session.items_json = "[]"
        mock_db_session.pending_prompt = None

        session = CollectSession.from_db(mock_db_session)

        assert session.chat_id == 12345
        assert session.user_id == 67890
        assert session.items == []

    def test_from_db_with_items(self):
        """Test creating CollectSession from database model with items."""
        items_data = [
            {
                "type": "text",
                "message_id": 1,
                "timestamp": "2024-01-15T10:00:00",
                "content": "test",
                "caption": None,
                "file_name": None,
                "mime_type": None,
                "duration": None,
                "transcription": None,
            }
        ]

        mock_db_session = MagicMock()
        mock_db_session.chat_id = 12345
        mock_db_session.user_id = 67890
        mock_db_session.started_at = datetime(2024, 1, 15, 10, 0, 0)
        mock_db_session.items_json = json.dumps(items_data)
        mock_db_session.pending_prompt = "Test prompt"

        session = CollectSession.from_db(mock_db_session)

        assert len(session.items) == 1
        assert session.items[0].type == CollectItemType.TEXT
        assert session.pending_prompt == "Test prompt"

    def test_from_db_with_invalid_json(self):
        """Test from_db handles invalid JSON gracefully."""
        mock_db_session = MagicMock()
        mock_db_session.chat_id = 12345
        mock_db_session.user_id = 67890
        mock_db_session.started_at = datetime(2024, 1, 15, 10, 0, 0)
        mock_db_session.items_json = "invalid json {"
        mock_db_session.pending_prompt = None

        session = CollectSession.from_db(mock_db_session)

        # Should have empty items due to parse error
        assert session.items == []

    def test_from_db_handles_timezone_aware_datetime(self):
        """Test from_db handles timezone-aware datetime."""
        from datetime import timezone

        mock_db_session = MagicMock()
        mock_db_session.chat_id = 12345
        mock_db_session.user_id = 67890
        mock_db_session.started_at = datetime(
            2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc
        )
        mock_db_session.items_json = "[]"
        mock_db_session.pending_prompt = None

        session = CollectSession.from_db(mock_db_session)

        # Timezone should be stripped
        assert session.started_at.tzinfo is None


# =============================================================================
# CollectService Tests
# =============================================================================


class TestCollectServiceInit:
    """Tests for CollectService initialization."""

    def test_default_initialization(self):
        """Test default service initialization."""
        service = CollectService()

        assert service.SESSION_TIMEOUT == 3600
        assert service.MAX_ITEMS == 50
        assert service._sessions == {}
        assert service._db_loaded is False

    def test_session_constants(self):
        """Test that session constants are set correctly."""
        service = CollectService()

        assert service.SESSION_TIMEOUT == 3600  # 1 hour
        assert service.MAX_ITEMS == 50


class TestCollectServiceSessionLifecycle:
    """Tests for session lifecycle operations."""

    @pytest.mark.asyncio
    async def test_start_session(self):
        """Test starting a new collect session."""
        service = CollectService()
        service._db_loaded = True  # Skip DB loading

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            session = await service.start_session(chat_id=12345, user_id=67890)

        assert session.chat_id == 12345
        assert session.user_id == 67890
        assert session.items == []
        assert 12345 in service._sessions

    @pytest.mark.asyncio
    async def test_start_session_replaces_existing(self):
        """Test that starting a session replaces existing one."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            # Start first session
            session1 = await service.start_session(chat_id=12345, user_id=67890)
            session1.items.append(
                CollectItem(
                    type=CollectItemType.TEXT,
                    message_id=1,
                    timestamp=datetime.now(),
                    content="old item",
                )
            )

            # Start new session (should replace)
            session2 = await service.start_session(chat_id=12345, user_id=67890)

        # New session should be empty
        assert session2.items == []
        assert service._sessions[12345] is session2

    @pytest.mark.asyncio
    async def test_end_session(self):
        """Test ending a collect session."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

        with patch.object(service, "_delete_from_db", new_callable=AsyncMock):
            result = await service.end_session(chat_id=12345)

        assert result is not None
        assert result.chat_id == 12345
        assert 12345 not in service._sessions

    @pytest.mark.asyncio
    async def test_end_session_nonexistent(self):
        """Test ending a session that doesn't exist."""
        service = CollectService()
        service._db_loaded = True

        result = await service.end_session(chat_id=99999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test getting an existing session."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            created = await service.start_session(chat_id=12345, user_id=67890)

        result = await service.get_session(chat_id=12345)

        assert result is created

    @pytest.mark.asyncio
    async def test_get_session_nonexistent(self):
        """Test getting a session that doesn't exist."""
        service = CollectService()
        service._db_loaded = True

        result = await service.get_session(chat_id=99999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_expired(self):
        """Test getting an expired session returns None."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            session = await service.start_session(chat_id=12345, user_id=67890)

        # Make the session expired
        session.started_at = datetime.now() - timedelta(
            seconds=service.SESSION_TIMEOUT + 10
        )

        with patch.object(service, "_delete_from_db", new_callable=AsyncMock):
            result = await service.get_session(chat_id=12345)

        assert result is None
        assert 12345 not in service._sessions

    @pytest.mark.asyncio
    async def test_is_collecting_true(self):
        """Test is_collecting returns True for active session."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

        result = await service.is_collecting(chat_id=12345)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_collecting_false(self):
        """Test is_collecting returns False for no session."""
        service = CollectService()
        service._db_loaded = True

        result = await service.is_collecting(chat_id=99999)

        assert result is False


class TestCollectServiceAddItem:
    """Tests for adding items to sessions."""

    @pytest.mark.asyncio
    async def test_add_text_item(self):
        """Test adding a text item to session."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            item = await service.add_item(
                chat_id=12345,
                item_type=CollectItemType.TEXT,
                message_id=100,
                content="Hello world",
            )

        assert item is not None
        assert item.type == CollectItemType.TEXT
        assert item.content == "Hello world"
        assert len(service._sessions[12345].items) == 1

    @pytest.mark.asyncio
    async def test_add_image_item(self):
        """Test adding an image item to session."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            item = await service.add_item(
                chat_id=12345,
                item_type=CollectItemType.IMAGE,
                message_id=101,
                content="file_id_123",
                caption="Photo caption",
                mime_type="image/jpeg",
            )

        assert item is not None
        assert item.type == CollectItemType.IMAGE
        assert item.caption == "Photo caption"
        assert item.mime_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_add_voice_item_with_transcription(self):
        """Test adding a voice item with transcription."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            item = await service.add_item(
                chat_id=12345,
                item_type=CollectItemType.VOICE,
                message_id=102,
                content="voice_file_id",
                duration=30,
                transcription="Hello, this is transcribed text",
            )

        assert item is not None
        assert item.type == CollectItemType.VOICE
        assert item.duration == 30
        assert item.transcription == "Hello, this is transcribed text"

    @pytest.mark.asyncio
    async def test_add_item_no_session(self):
        """Test adding item when no session exists."""
        service = CollectService()
        service._db_loaded = True

        item = await service.add_item(
            chat_id=99999,
            item_type=CollectItemType.TEXT,
            message_id=100,
            content="test",
        )

        assert item is None

    @pytest.mark.asyncio
    async def test_add_item_max_capacity(self):
        """Test adding item when session is at max capacity."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            # Add items up to max
            session = service._sessions[12345]
            for i in range(service.MAX_ITEMS):
                session.items.append(
                    CollectItem(
                        type=CollectItemType.TEXT,
                        message_id=i,
                        timestamp=datetime.now(),
                        content=f"item {i}",
                    )
                )

            # Try to add one more
            item = await service.add_item(
                chat_id=12345,
                item_type=CollectItemType.TEXT,
                message_id=999,
                content="overflow item",
            )

        assert item is None
        assert len(service._sessions[12345].items) == service.MAX_ITEMS

    @pytest.mark.asyncio
    async def test_add_multiple_items(self):
        """Test adding multiple items in sequence."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            for i in range(5):
                await service.add_item(
                    chat_id=12345,
                    item_type=CollectItemType.TEXT,
                    message_id=100 + i,
                    content=f"Message {i}",
                )

        assert len(service._sessions[12345].items) == 5


class TestCollectServiceStatus:
    """Tests for session status retrieval."""

    @pytest.mark.asyncio
    async def test_get_status_existing_session(self):
        """Test getting status of existing session."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            await service.add_item(
                chat_id=12345,
                item_type=CollectItemType.TEXT,
                message_id=100,
                content="test",
            )
            await service.add_item(
                chat_id=12345,
                item_type=CollectItemType.IMAGE,
                message_id=101,
                content="img",
            )

        status = await service.get_status(chat_id=12345)

        assert status is not None
        assert status["active"] is True
        assert status["item_count"] == 2
        assert status["summary"] == {"text": 1, "image": 1}
        assert "text" in status["summary_text"]
        assert "image" in status["summary_text"]
        assert "started_at" in status
        assert "age_seconds" in status

    @pytest.mark.asyncio
    async def test_get_status_no_session(self):
        """Test getting status when no session exists."""
        service = CollectService()
        service._db_loaded = True

        status = await service.get_status(chat_id=99999)

        assert status is None


class TestCollectServiceTriggerKeywords:
    """Tests for trigger keyword detection."""

    def test_check_trigger_keywords_exact_match(self):
        """Test exact trigger keyword match."""
        service = CollectService()

        assert service.check_trigger_keywords("now respond") is True
        assert service.check_trigger_keywords("process this") is True
        assert service.check_trigger_keywords("go ahead") is True

    def test_check_trigger_keywords_case_insensitive(self):
        """Test trigger keywords are case insensitive."""
        service = CollectService()

        assert service.check_trigger_keywords("NOW RESPOND") is True
        assert service.check_trigger_keywords("Process This") is True
        assert service.check_trigger_keywords("GO AHEAD") is True

    def test_check_trigger_keywords_embedded(self):
        """Test trigger keywords embedded in text."""
        service = CollectService()

        assert service.check_trigger_keywords("Please now respond to all this") is True
        assert service.check_trigger_keywords("Can you process this data?") is True
        assert service.check_trigger_keywords("OK go ahead and do it") is True

    def test_check_trigger_keywords_russian(self):
        """Test Russian trigger keywords."""
        service = CollectService()

        assert service.check_trigger_keywords("обработай") is True
        assert service.check_trigger_keywords("ответь") is True
        assert service.check_trigger_keywords("Пожалуйста, обработай это") is True

    def test_check_trigger_keywords_no_match(self):
        """Test non-matching text."""
        service = CollectService()

        assert service.check_trigger_keywords("hello world") is False
        assert service.check_trigger_keywords("just a message") is False
        assert service.check_trigger_keywords("") is False

    def test_check_trigger_keywords_with_whitespace(self):
        """Test trigger keywords with surrounding whitespace."""
        service = CollectService()

        assert service.check_trigger_keywords("  now respond  ") is True
        assert service.check_trigger_keywords("\tgo ahead\n") is True

    def test_trigger_keywords_constant(self):
        """Test that TRIGGER_KEYWORDS constant has expected values."""
        assert "now respond" in TRIGGER_KEYWORDS
        assert "process this" in TRIGGER_KEYWORDS
        assert "go ahead" in TRIGGER_KEYWORDS
        assert "обработай" in TRIGGER_KEYWORDS
        assert "ответь" in TRIGGER_KEYWORDS


class TestCollectServiceDatabaseLoading:
    """Tests for database loading behavior."""

    @pytest.mark.asyncio
    async def test_load_from_db_sets_flag(self):
        """Test that _load_from_db sets the loaded flag."""
        service = CollectService()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.core.database.get_db_session") as mock_get_db:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_session
            mock_context.__aexit__.return_value = None
            mock_get_db.return_value = mock_context

            await service._load_from_db()

        assert service._db_loaded is True

    @pytest.mark.asyncio
    async def test_load_from_db_skips_if_already_loaded(self):
        """Test that _load_from_db skips if already loaded."""
        service = CollectService()
        service._db_loaded = True

        # No need to patch - the method should return early
        await service._load_from_db()

        # Method should have returned early without changing state
        assert service._db_loaded is True

    @pytest.mark.asyncio
    async def test_load_from_db_skips_if_loading(self):
        """Test that _load_from_db skips if already loading."""
        service = CollectService()
        service._db_loading = True

        # No need to patch - the method should return early
        await service._load_from_db()

        # Method should have returned early
        assert service._db_loading is True
        assert service._db_loaded is False

    @pytest.mark.asyncio
    async def test_initialize_calls_load_from_db(self):
        """Test that initialize() calls _load_from_db()."""
        service = CollectService()

        with patch.object(
            service, "_load_from_db", new_callable=AsyncMock
        ) as mock_load:
            await service.initialize()

        mock_load.assert_called_once()


class TestCollectServiceConcurrency:
    """Tests for concurrent access handling."""

    @pytest.mark.asyncio
    async def test_concurrent_add_items(self):
        """Test adding items concurrently."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            # Add items concurrently
            tasks = [
                service.add_item(
                    chat_id=12345,
                    item_type=CollectItemType.TEXT,
                    message_id=100 + i,
                    content=f"Message {i}",
                )
                for i in range(10)
            ]
            await asyncio.gather(*tasks)

        # All items should be added
        assert len(service._sessions[12345].items) == 10


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance management."""

    def test_get_collect_service_creates_instance(self):
        """Test that get_collect_service creates instance if needed."""
        import src.services.collect_service as cs

        cs._collect_service = None

        service = get_collect_service()

        assert service is not None
        assert isinstance(service, CollectService)

    def test_get_collect_service_returns_same_instance(self):
        """Test that get_collect_service returns the same instance."""
        service1 = get_collect_service()
        service2 = get_collect_service()

        assert service1 is service2


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_session_with_pending_prompt(self):
        """Test session with pending prompt."""
        session = CollectSession(
            chat_id=12345,
            user_id=67890,
            pending_prompt="Analyze all collected items",
        )

        assert session.pending_prompt == "Analyze all collected items"

    def test_collect_item_all_optional_fields(self):
        """Test CollectItem with all optional fields populated."""
        item = CollectItem(
            type=CollectItemType.DOCUMENT,
            message_id=500,
            timestamp=datetime.now(),
            content="file_id",
            caption="Document caption",
            file_name="document.pdf",
            mime_type="application/pdf",
            duration=None,
            transcription=None,
        )

        assert item.caption == "Document caption"
        assert item.file_name == "document.pdf"

    @pytest.mark.asyncio
    async def test_multiple_chats_isolated(self):
        """Test that different chats have isolated sessions."""
        service = CollectService()
        service._db_loaded = True

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=111, user_id=1)
            await service.start_session(chat_id=222, user_id=2)

            await service.add_item(
                chat_id=111,
                item_type=CollectItemType.TEXT,
                message_id=1,
                content="Chat 111 message",
            )
            await service.add_item(
                chat_id=222,
                item_type=CollectItemType.IMAGE,
                message_id=2,
                content="Chat 222 image",
            )

        assert len(service._sessions[111].items) == 1
        assert service._sessions[111].items[0].type == CollectItemType.TEXT

        assert len(service._sessions[222].items) == 1
        assert service._sessions[222].items[0].type == CollectItemType.IMAGE

    @pytest.mark.asyncio
    async def test_add_item_preserves_timestamp(self):
        """Test that add_item sets timestamp on the item."""
        service = CollectService()
        service._db_loaded = True

        before = datetime.now()

        with patch.object(service, "_save_to_db", new_callable=AsyncMock):
            await service.start_session(chat_id=12345, user_id=67890)

            item = await service.add_item(
                chat_id=12345,
                item_type=CollectItemType.TEXT,
                message_id=100,
                content="test",
            )

        after = datetime.now()

        assert item is not None
        assert before <= item.timestamp <= after

    def test_from_dict_missing_optional_fields(self):
        """Test from_dict with minimal required fields."""
        data = {
            "type": "text",
            "message_id": 123,
            "timestamp": "2024-01-15T10:00:00",
            "content": "test",
        }

        item = CollectItem.from_dict(data)

        assert item.caption is None
        assert item.file_name is None
        assert item.mime_type is None
        assert item.duration is None
        assert item.transcription is None
