"""Tests for services using repository abstraction (Slice 3).

Verifies that message_persistence_service and data_retention_service
can accept and use repository instances instead of direct DB access,
and that database.py utility functions delegate to repositories.
"""

from datetime import datetime
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.chat import Chat
from src.models.message import Message
from src.models.user import User

# ========================================================================
# In-memory fake repositories for testing
# ========================================================================


class FakeChatRepository:
    """In-memory chat repository for testing."""

    def __init__(self, chats: Optional[List[Chat]] = None):
        self._chats = {c.chat_id: c for c in (chats or [])}

    async def get_by_telegram_id(self, telegram_chat_id: int) -> Optional[Chat]:
        return self._chats.get(telegram_chat_id)

    async def get_by_user_id(self, user_id: int) -> List[Chat]:
        return [c for c in self._chats.values() if c.user_id == user_id]


class FakeUserRepository:
    """In-memory user repository for testing."""

    def __init__(self, users: Optional[List[User]] = None):
        self._by_telegram_id = {u.user_id: u for u in (users or [])}
        self._by_id = {u.id: u for u in (users or [])}

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        return self._by_telegram_id.get(telegram_user_id)

    async def get_by_id(self, user_id: int) -> Optional[User]:
        return self._by_id.get(user_id)


class FakeMessageRepository:
    """In-memory message repository for testing."""

    def __init__(self):
        self._messages: List[Message] = []
        self.add_called = False
        self.delete_count = 0

    async def add(self, message: Message) -> Message:
        self.add_called = True
        message.id = len(self._messages) + 1
        self._messages.append(message)
        return message

    async def get_latest_by_chat(self, chat_id: int, limit: int = 10) -> List[Message]:
        filtered = [m for m in self._messages if m.chat_id == chat_id]
        return sorted(filtered, key=lambda m: m.id, reverse=True)[:limit]

    async def delete_older_than(self, chat_id: int, cutoff: datetime) -> int:
        before = len(self._messages)
        self._messages = [
            m
            for m in self._messages
            if not (m.chat_id == chat_id and m.created_at and m.created_at < cutoff)
        ]
        self.delete_count = before - len(self._messages)
        return self.delete_count


# ========================================================================
# Fixtures
# ========================================================================


@pytest.fixture
def fake_chat():
    """A Chat ORM object for testing (with .id and .chat_id set)."""
    chat = MagicMock(spec=Chat)
    chat.id = 42
    chat.chat_id = 12345
    chat.user_id = 1
    return chat


@pytest.fixture
def fake_chat_repo(fake_chat):
    """FakeChatRepository pre-loaded with one chat."""
    return FakeChatRepository(chats=[fake_chat])


@pytest.fixture
def fake_message_repo():
    return FakeMessageRepository()


# ========================================================================
# Tests: message_persistence_service with repositories
# ========================================================================


class TestPersistMessageWithRepository:
    """Test persist_message accepts and uses repository objects."""

    @pytest.mark.asyncio
    async def test_persist_uses_chat_repo(self, fake_chat_repo, fake_message_repo):
        """persist_message should use injected ChatRepository to find chat."""
        from src.services.message_persistence_service import persist_message

        await persist_message(
            telegram_chat_id=12345,
            from_user_id=99,
            message_id=1001,
            text="Hello via repo",
            message_type="text",
            chat_repo=fake_chat_repo,
            message_repo=fake_message_repo,
        )

        assert fake_message_repo.add_called

    @pytest.mark.asyncio
    async def test_persist_skips_when_chat_not_found(self, fake_message_repo):
        """When chat is not in the repo, persist should skip without error."""
        from src.services.message_persistence_service import persist_message

        empty_chat_repo = FakeChatRepository(chats=[])

        await persist_message(
            telegram_chat_id=99999,
            from_user_id=99,
            message_id=1002,
            text="no chat found",
            message_type="text",
            chat_repo=empty_chat_repo,
            message_repo=fake_message_repo,
        )

        assert not fake_message_repo.add_called

    @pytest.mark.asyncio
    async def test_persist_message_fields_correct(
        self, fake_chat_repo, fake_message_repo, fake_chat
    ):
        """Message created via repos should have correct field values."""
        from src.services.message_persistence_service import persist_message

        await persist_message(
            telegram_chat_id=12345,
            from_user_id=77,
            message_id=2001,
            text="field check",
            message_type="voice",
            chat_repo=fake_chat_repo,
            message_repo=fake_message_repo,
        )

        assert len(fake_message_repo._messages) == 1
        msg = fake_message_repo._messages[0]
        assert msg.chat_id == 42  # internal FK, not telegram ID
        assert msg.from_user_id == 77
        assert msg.message_id == 2001
        assert msg.text == "field check"
        assert msg.message_type == "voice"
        assert msg.is_bot_message is False

    @pytest.mark.asyncio
    async def test_backward_compat_without_repos(self):
        """persist_message still works without repo params (backward compat)."""
        from src.services.message_persistence_service import persist_message

        mock_chat = MagicMock()
        mock_chat.id = 42
        mock_chat.chat_id = 12345

        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_chat
        mock_session.execute = AsyncMock(return_value=result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_get_db_session():
            yield mock_session

        with patch(
            "src.services.message_persistence_service.get_db_session",
            fake_get_db_session,
        ):
            await persist_message(
                telegram_chat_id=12345,
                from_user_id=99,
                message_id=3001,
                text="backward compat",
                message_type="text",
            )

        mock_session.add.assert_called_once()


# ========================================================================
# Tests: database.py utility functions with repositories
# ========================================================================


class TestDatabaseUtilsWithRepository:
    """Test that get_user_by_telegram_id and get_chat_by_telegram_id
    accept optional repository params."""

    @pytest.mark.asyncio
    async def test_get_user_by_telegram_id_with_repo(self):
        """get_user_by_telegram_id should use UserRepository when provided."""
        from src.core.database import get_user_by_telegram_id

        user = MagicMock(spec=User)
        user.id = 1
        user.user_id = 12345
        fake_repo = FakeUserRepository(users=[user])

        result = await get_user_by_telegram_id(
            session=MagicMock(),  # session unused when repo provided
            telegram_user_id=12345,
            user_repo=fake_repo,
        )
        assert result is not None
        assert result.user_id == 12345

    @pytest.mark.asyncio
    async def test_get_user_by_telegram_id_not_found_with_repo(self):
        from src.core.database import get_user_by_telegram_id

        fake_repo = FakeUserRepository(users=[])
        result = await get_user_by_telegram_id(
            session=MagicMock(),
            telegram_user_id=99999,
            user_repo=fake_repo,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_chat_by_telegram_id_with_repo(self):
        """get_chat_by_telegram_id should use ChatRepository when provided."""
        from src.core.database import get_chat_by_telegram_id

        chat = MagicMock(spec=Chat)
        chat.id = 1
        chat.chat_id = 55555
        fake_repo = FakeChatRepository(chats=[chat])

        result = await get_chat_by_telegram_id(
            session=MagicMock(),
            telegram_chat_id=55555,
            chat_repo=fake_repo,
        )
        assert result is not None
        assert result.chat_id == 55555

    @pytest.mark.asyncio
    async def test_get_chat_by_telegram_id_not_found_with_repo(self):
        from src.core.database import get_chat_by_telegram_id

        fake_repo = FakeChatRepository(chats=[])
        result = await get_chat_by_telegram_id(
            session=MagicMock(),
            telegram_chat_id=99999,
            chat_repo=fake_repo,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_backward_compat_without_repo(self):
        """Functions still work without repo param (backward compat)."""
        from src.core.database import get_user_by_telegram_id

        mock_session = AsyncMock()
        result = MagicMock()
        user = MagicMock(spec=User)
        user.user_id = 12345
        result.scalar_one_or_none.return_value = user
        mock_session.execute = AsyncMock(return_value=result)

        found = await get_user_by_telegram_id(
            session=mock_session,
            telegram_user_id=12345,
        )
        assert found is not None
        assert found.user_id == 12345
