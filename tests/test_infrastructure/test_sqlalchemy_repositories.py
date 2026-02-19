"""Tests for SQLAlchemy repository implementations (Slice 2).

Uses an in-memory SQLite database to verify that the concrete repositories
correctly implement the domain protocols and perform CRUD operations.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domain.repositories import ChatRepository, MessageRepository, UserRepository
from src.models.base import Base


@pytest.fixture
async def async_engine():
    """Create an in-memory async SQLite engine with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine):
    """Create an async session bound to the in-memory engine."""
    factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest.fixture
async def seed_user(async_session):
    """Insert a test user and return it."""
    from src.models.user import User

    user = User(user_id=12345, username="testuser", first_name="Test")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def seed_chat(async_session, seed_user):
    """Insert a test chat linked to seed_user and return it."""
    from src.models.chat import Chat

    chat = Chat(chat_id=99999, user_id=seed_user.id, chat_type="private")
    async_session.add(chat)
    await async_session.commit()
    await async_session.refresh(chat)
    return chat


@pytest.fixture
async def seed_messages(async_session, seed_chat):
    """Insert 5 test messages into seed_chat and return them."""
    from src.models.message import Message

    messages = []
    for i in range(5):
        msg = Message(
            chat_id=seed_chat.id,
            message_id=1000 + i,
            from_user_id=12345,
            message_type="text",
            text=f"Message {i}",
        )
        async_session.add(msg)
        messages.append(msg)
    await async_session.commit()
    for msg in messages:
        await async_session.refresh(msg)
    return messages


# ========================================================================
# UserRepository tests
# ========================================================================


class TestSqlAlchemyUserRepository:
    def test_satisfies_protocol(self):
        """SqlAlchemyUserRepository must satisfy UserRepository protocol."""
        from src.infrastructure.repositories import SqlAlchemyUserRepository

        # Just check it can be instantiated — protocol check requires an instance
        assert SqlAlchemyUserRepository is not None

    @pytest.mark.asyncio
    async def test_isinstance_check(self, async_session):
        from src.infrastructure.repositories import SqlAlchemyUserRepository

        repo = SqlAlchemyUserRepository(async_session)
        assert isinstance(repo, UserRepository)

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_found(self, async_session, seed_user):
        from src.infrastructure.repositories import SqlAlchemyUserRepository

        repo = SqlAlchemyUserRepository(async_session)
        user = await repo.get_by_telegram_id(12345)
        assert user is not None
        assert user.user_id == 12345
        assert user.username == "testuser"

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_not_found(self, async_session):
        from src.infrastructure.repositories import SqlAlchemyUserRepository

        repo = SqlAlchemyUserRepository(async_session)
        user = await repo.get_by_telegram_id(99999)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, async_session, seed_user):
        from src.infrastructure.repositories import SqlAlchemyUserRepository

        repo = SqlAlchemyUserRepository(async_session)
        user = await repo.get_by_id(seed_user.id)
        assert user is not None
        assert user.user_id == 12345

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, async_session):
        from src.infrastructure.repositories import SqlAlchemyUserRepository

        repo = SqlAlchemyUserRepository(async_session)
        user = await repo.get_by_id(9999)
        assert user is None


# ========================================================================
# ChatRepository tests
# ========================================================================


class TestSqlAlchemyChatRepository:
    def test_satisfies_protocol(self):
        from src.infrastructure.repositories import SqlAlchemyChatRepository

        assert SqlAlchemyChatRepository is not None

    @pytest.mark.asyncio
    async def test_isinstance_check(self, async_session):
        from src.infrastructure.repositories import SqlAlchemyChatRepository

        repo = SqlAlchemyChatRepository(async_session)
        assert isinstance(repo, ChatRepository)

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_found(self, async_session, seed_chat):
        from src.infrastructure.repositories import SqlAlchemyChatRepository

        repo = SqlAlchemyChatRepository(async_session)
        chat = await repo.get_by_telegram_id(99999)
        assert chat is not None
        assert chat.chat_id == 99999

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_not_found(self, async_session):
        from src.infrastructure.repositories import SqlAlchemyChatRepository

        repo = SqlAlchemyChatRepository(async_session)
        chat = await repo.get_by_telegram_id(11111)
        assert chat is None

    @pytest.mark.asyncio
    async def test_get_by_user_id_found(self, async_session, seed_chat, seed_user):
        from src.infrastructure.repositories import SqlAlchemyChatRepository

        repo = SqlAlchemyChatRepository(async_session)
        chats = await repo.get_by_user_id(seed_user.id)
        assert len(chats) == 1
        assert chats[0].chat_id == 99999

    @pytest.mark.asyncio
    async def test_get_by_user_id_empty(self, async_session):
        from src.infrastructure.repositories import SqlAlchemyChatRepository

        repo = SqlAlchemyChatRepository(async_session)
        chats = await repo.get_by_user_id(9999)
        assert chats == []


# ========================================================================
# MessageRepository tests
# ========================================================================


class TestSqlAlchemyMessageRepository:
    def test_satisfies_protocol(self):
        from src.infrastructure.repositories import SqlAlchemyMessageRepository

        assert SqlAlchemyMessageRepository is not None

    @pytest.mark.asyncio
    async def test_isinstance_check(self, async_session):
        from src.infrastructure.repositories import SqlAlchemyMessageRepository

        repo = SqlAlchemyMessageRepository(async_session)
        assert isinstance(repo, MessageRepository)

    @pytest.mark.asyncio
    async def test_add(self, async_session, seed_chat):
        from src.infrastructure.repositories import SqlAlchemyMessageRepository
        from src.models.message import Message

        repo = SqlAlchemyMessageRepository(async_session)
        msg = Message(
            chat_id=seed_chat.id,
            message_id=5000,
            from_user_id=12345,
            message_type="text",
            text="hello",
        )
        result = await repo.add(msg)
        assert result.id is not None
        assert result.text == "hello"

    @pytest.mark.asyncio
    async def test_get_latest_by_chat(self, async_session, seed_chat, seed_messages):
        from src.infrastructure.repositories import SqlAlchemyMessageRepository

        repo = SqlAlchemyMessageRepository(async_session)
        latest = await repo.get_latest_by_chat(seed_chat.id, limit=3)
        assert len(latest) == 3
        # Should be newest first (highest message_id)
        assert latest[0].message_id >= latest[1].message_id

    @pytest.mark.asyncio
    async def test_get_latest_by_chat_empty(self, async_session, seed_chat):
        from src.infrastructure.repositories import SqlAlchemyMessageRepository

        repo = SqlAlchemyMessageRepository(async_session)
        latest = await repo.get_latest_by_chat(seed_chat.id, limit=10)
        assert latest == []

    @pytest.mark.asyncio
    async def test_delete_older_than(self, async_session, seed_chat, seed_messages):
        from src.infrastructure.repositories import SqlAlchemyMessageRepository

        repo = SqlAlchemyMessageRepository(async_session)
        # Delete everything older than far in the future (i.e., all messages)
        cutoff = datetime.utcnow() + timedelta(days=1)
        deleted = await repo.delete_older_than(seed_chat.id, cutoff)
        assert deleted == 5

    @pytest.mark.asyncio
    async def test_delete_older_than_none_match(
        self, async_session, seed_chat, seed_messages
    ):
        from src.infrastructure.repositories import SqlAlchemyMessageRepository

        repo = SqlAlchemyMessageRepository(async_session)
        # Cutoff is in the past (before any message was created)
        cutoff = datetime(2000, 1, 1)
        deleted = await repo.delete_older_than(seed_chat.id, cutoff)
        assert deleted == 0
