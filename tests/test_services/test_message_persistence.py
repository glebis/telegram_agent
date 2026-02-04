"""
Tests for the Message Persistence Service.

Tests cover:
- Persisting a text message to the database
- Persisting a voice message transcription
- Capturing message metadata (chat_id, user_id, message_id, timestamp)
- Persistence errors do not crash the message processing pipeline (fire-and-forget)
- Duplicate message_ids are handled gracefully
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.message_persistence_service import persist_message


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_chat():
    """Create a mock Chat ORM object with internal id=42."""
    chat = MagicMock()
    chat.id = 42  # internal DB primary key
    chat.chat_id = 12345  # Telegram chat ID
    return chat


@pytest.fixture
def mock_session(mock_chat):
    """Create a mock async DB session that returns our mock chat."""
    session = AsyncMock()

    # session.execute() returns a result whose .scalar_one_or_none() gives the chat
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_chat
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()

    return session


@pytest.fixture
def mock_db_context(mock_session):
    """Patch get_db_session to yield our mock session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_get_db_session():
        yield mock_session

    return fake_get_db_session


# =============================================================================
# Tests: Text message persistence
# =============================================================================


class TestPersistTextMessage:
    """Test that a text message is persisted to the database."""

    @pytest.mark.asyncio
    async def test_text_message_persisted(self, mock_db_context, mock_session):
        """A plain text message should create a Message row with correct fields."""
        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=1001,
                text="Hello, world!",
                message_type="text",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )

        # Verify session.add was called with a Message object
        mock_session.add.assert_called_once()
        msg_obj = mock_session.add.call_args[0][0]

        assert msg_obj.chat_id == 42  # internal FK, not telegram chat_id
        assert msg_obj.from_user_id == 99
        assert msg_obj.message_id == 1001
        assert msg_obj.text == "Hello, world!"
        assert msg_obj.message_type == "text"
        assert msg_obj.is_bot_message is False

        # Verify commit was called
        mock_session.commit.assert_awaited_once()


# =============================================================================
# Tests: Voice message transcription persistence
# =============================================================================


class TestPersistVoiceMessage:
    """Test that a voice message transcription is persisted."""

    @pytest.mark.asyncio
    async def test_voice_transcription_persisted(self, mock_db_context, mock_session):
        """A voice message should be stored with message_type='voice' and transcription text."""
        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=1002,
                text="This is the transcribed voice content",
                message_type="voice",
                timestamp=datetime(2026, 2, 4, 12, 1, 0),
            )

        mock_session.add.assert_called_once()
        msg_obj = mock_session.add.call_args[0][0]

        assert msg_obj.message_type == "voice"
        assert msg_obj.text == "This is the transcribed voice content"
        assert msg_obj.chat_id == 42


# =============================================================================
# Tests: Metadata capture
# =============================================================================


class TestMetadataCapture:
    """Test that message metadata is captured correctly."""

    @pytest.mark.asyncio
    async def test_all_metadata_fields(self, mock_db_context, mock_session):
        """All key metadata fields should be stored on the Message object."""
        ts = datetime(2026, 2, 4, 14, 30, 0)

        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=77,
                message_id=2001,
                text="metadata test",
                message_type="text",
                timestamp=ts,
            )

        msg_obj = mock_session.add.call_args[0][0]
        assert msg_obj.chat_id == 42
        assert msg_obj.from_user_id == 77
        assert msg_obj.message_id == 2001
        assert msg_obj.message_type == "text"

    @pytest.mark.asyncio
    async def test_none_text_allowed(self, mock_db_context, mock_session):
        """Messages without text (e.g. photo) should persist with text=None."""
        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=3001,
                text=None,
                message_type="photo",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )

        msg_obj = mock_session.add.call_args[0][0]
        assert msg_obj.text is None
        assert msg_obj.message_type == "photo"

    @pytest.mark.asyncio
    async def test_chat_not_found_skips_persist(self, mock_db_context, mock_session):
        """If the chat is not found in the DB, persist should skip without error."""
        # Override to return no chat
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            # Should NOT raise
            await persist_message(
                telegram_chat_id=99999,
                from_user_id=99,
                message_id=4001,
                text="orphan message",
                message_type="text",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )

        # session.add should NOT have been called
        mock_session.add.assert_not_called()


# =============================================================================
# Tests: Error resilience (fire-and-forget)
# =============================================================================


class TestErrorResilience:
    """Test that persistence errors do not crash the caller."""

    @pytest.mark.asyncio
    async def test_db_commit_error_swallowed(self, mock_db_context, mock_session):
        """If commit raises, persist_message should log and return without raising."""
        mock_session.commit = AsyncMock(
            side_effect=Exception("DB write failed")
        )

        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            # Should NOT raise even though commit fails
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=5001,
                text="will fail commit",
                message_type="text",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )

    @pytest.mark.asyncio
    async def test_session_execute_error_swallowed(self):
        """If the DB session itself errors, persist_message should not raise."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def broken_session():
            raise Exception("Cannot connect to DB")
            yield  # noqa: unreachable

        with patch(
            "src.services.message_persistence_service.get_db_session",
            broken_session,
        ):
            # Should NOT raise
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=6001,
                text="will fail session",
                message_type="text",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )


# =============================================================================
# Tests: Duplicate message_id handling
# =============================================================================


class TestDuplicateHandling:
    """Test that duplicate message_ids are handled gracefully."""

    @pytest.mark.asyncio
    async def test_duplicate_message_id_does_not_crash(
        self, mock_db_context, mock_session
    ):
        """If a duplicate message_id triggers an IntegrityError, it should be swallowed."""
        from sqlalchemy.exc import IntegrityError

        mock_session.commit = AsyncMock(
            side_effect=IntegrityError(
                "UNIQUE constraint failed", params=None, orig=Exception()
            )
        )

        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            # Should NOT raise
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=7001,
                text="duplicate message",
                message_type="text",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )

    @pytest.mark.asyncio
    async def test_persist_called_twice_same_id(self, mock_db_context, mock_session):
        """Calling persist_message twice with same message_id should not crash."""
        with patch(
            "src.services.message_persistence_service.get_db_session",
            mock_db_context,
        ):
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=8001,
                text="first call",
                message_type="text",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=8001,
                text="second call",
                message_type="text",
                timestamp=datetime(2026, 2, 4, 12, 0, 0),
            )

        # Both calls should have attempted to add
        assert mock_session.add.call_count == 2
