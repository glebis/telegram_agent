"""
Comprehensive pytest tests for database models.

This module tests the User, Chat, and ClaudeSession models including:
- Model creation with default values
- Field constraints and validations
- Relationship mappings
- Model methods (__repr__)
- Edge cases and boundary conditions
"""

import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models.base import Base, TimestampMixin
from src.models.user import User
from src.models.chat import Chat
from src.models.claude_session import ClaudeSession


class TestUserModel:
    """Test suite for the User model."""

    @pytest.fixture
    async def db_session(self):
        """Create a test database session with fresh tables."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        session = async_session()
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_user_creation_with_required_fields(self, db_session):
        """Test creating a User with only required fields (user_id)."""
        user = User(user_id=12345)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 12345))
        saved_user = result.scalar_one()

        assert saved_user.user_id == 12345
        assert saved_user.id is not None
        assert saved_user.username is None
        assert saved_user.first_name is None
        assert saved_user.last_name is None
        assert saved_user.language_code is None

    @pytest.mark.asyncio
    async def test_user_creation_with_all_fields(self, db_session):
        """Test creating a User with all optional fields populated."""
        user = User(
            user_id=67890,
            username="testuser",
            first_name="John",
            last_name="Doe",
            language_code="en",
            banned=True,
            user_group="admin",
            admin_notes="Test admin notes",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 67890))
        saved_user = result.scalar_one()

        assert saved_user.user_id == 67890
        assert saved_user.username == "testuser"
        assert saved_user.first_name == "John"
        assert saved_user.last_name == "Doe"
        assert saved_user.language_code == "en"
        assert saved_user.banned is True
        assert saved_user.user_group == "admin"
        assert saved_user.admin_notes == "Test admin notes"

    @pytest.mark.asyncio
    async def test_user_banned_default(self, db_session):
        """Test that banned field defaults to False."""
        user = User(user_id=11111)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 11111))
        saved_user = result.scalar_one()

        assert saved_user.banned is False

    @pytest.mark.asyncio
    async def test_user_unique_user_id(self, db_session):
        """Test that user_id must be unique."""
        user1 = User(user_id=99999, username="user1")
        db_session.add(user1)
        await db_session.commit()

        user2 = User(user_id=99999, username="user2")
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_repr(self, db_session):
        """Test User __repr__ method returns correct format."""
        user = User(user_id=12345, username="testrepr")
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 12345))
        saved_user = result.scalar_one()

        repr_str = repr(saved_user)
        assert "User" in repr_str
        assert "12345" in repr_str
        assert "testrepr" in repr_str

    @pytest.mark.asyncio
    async def test_user_timestamp_mixin(self, db_session):
        """Test that User has created_at timestamp from TimestampMixin."""
        user = User(user_id=33333)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 33333))
        saved_user = result.scalar_one()

        assert saved_user.created_at is not None
        assert isinstance(saved_user.created_at, datetime)

    @pytest.mark.asyncio
    async def test_user_with_unicode_names(self, db_session):
        """Test User model handles unicode characters in name fields."""
        user = User(
            user_id=44444,
            username="unicode_user",
            first_name="Jean-Pierre",
            last_name="Mueller",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 44444))
        saved_user = result.scalar_one()

        assert saved_user.first_name == "Jean-Pierre"
        assert saved_user.last_name == "Mueller"

    @pytest.mark.asyncio
    async def test_user_with_emoji_in_admin_notes(self, db_session):
        """Test User model handles emoji in admin_notes."""
        user = User(
            user_id=55555,
            admin_notes="VIP user - priority support",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 55555))
        saved_user = result.scalar_one()

        assert "VIP" in saved_user.admin_notes


class TestChatModel:
    """Test suite for the Chat model."""

    @pytest.fixture
    async def db_session(self):
        """Create a test database session with fresh tables."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        session = async_session()
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()
            os.unlink(db_path)

    @pytest.fixture
    async def test_user(self, db_session):
        """Create a test user for Chat foreign key."""
        user = User(user_id=100000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 100000))
        return result.scalar_one()

    @pytest.mark.asyncio
    async def test_chat_creation_with_required_fields(self, db_session, test_user):
        """Test creating a Chat with only required fields."""
        chat = Chat(chat_id=-1001234567890, user_id=test_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(
            select(Chat).where(Chat.chat_id == -1001234567890)
        )
        saved_chat = result.scalar_one()

        assert saved_chat.chat_id == -1001234567890
        assert saved_chat.user_id == test_user.id
        assert saved_chat.id is not None

    @pytest.mark.asyncio
    async def test_chat_default_chat_type(self, db_session, test_user):
        """Test that chat_type defaults to 'private'."""
        chat = Chat(chat_id=12345, user_id=test_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(select(Chat).where(Chat.chat_id == 12345))
        saved_chat = result.scalar_one()

        assert saved_chat.chat_type == "private"

    @pytest.mark.asyncio
    async def test_chat_default_current_mode(self, db_session, test_user):
        """Test that current_mode defaults to 'default'."""
        chat = Chat(chat_id=23456, user_id=test_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(select(Chat).where(Chat.chat_id == 23456))
        saved_chat = result.scalar_one()

        assert saved_chat.current_mode == "default"

    @pytest.mark.asyncio
    async def test_chat_default_claude_mode(self, db_session, test_user):
        """Test that claude_mode defaults to False."""
        chat = Chat(chat_id=34567, user_id=test_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(select(Chat).where(Chat.chat_id == 34567))
        saved_chat = result.scalar_one()

        assert saved_chat.claude_mode is False

    @pytest.mark.asyncio
    async def test_chat_default_claude_model(self, db_session, test_user):
        """Test that claude_model defaults to 'sonnet'."""
        chat = Chat(chat_id=45678, user_id=test_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(select(Chat).where(Chat.chat_id == 45678))
        saved_chat = result.scalar_one()

        assert saved_chat.claude_model == "sonnet"

    @pytest.mark.asyncio
    async def test_chat_with_all_fields(self, db_session, test_user):
        """Test creating a Chat with all fields populated."""
        chat = Chat(
            chat_id=-1009876543210,
            user_id=test_user.id,
            chat_type="supergroup",
            title="Test Group Chat",
            current_mode="artistic",
            current_preset="vintage",
            claude_mode=True,
            claude_model="opus",
            settings='{"key": "value"}',
        )
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(
            select(Chat).where(Chat.chat_id == -1009876543210)
        )
        saved_chat = result.scalar_one()

        assert saved_chat.chat_type == "supergroup"
        assert saved_chat.title == "Test Group Chat"
        assert saved_chat.current_mode == "artistic"
        assert saved_chat.current_preset == "vintage"
        assert saved_chat.claude_mode is True
        assert saved_chat.claude_model == "opus"
        assert saved_chat.settings == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_chat_unique_chat_id(self, db_session, test_user):
        """Test that chat_id must be unique."""
        chat1 = Chat(chat_id=88888, user_id=test_user.id)
        db_session.add(chat1)
        await db_session.commit()

        chat2 = Chat(chat_id=88888, user_id=test_user.id)
        db_session.add(chat2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_chat_repr(self, db_session, test_user):
        """Test Chat __repr__ method returns correct format."""
        chat = Chat(
            chat_id=-1001111111111,
            user_id=test_user.id,
            current_mode="artistic",
        )
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(
            select(Chat).where(Chat.chat_id == -1001111111111)
        )
        saved_chat = result.scalar_one()

        repr_str = repr(saved_chat)
        assert "Chat" in repr_str
        assert "-1001111111111" in repr_str
        assert "artistic" in repr_str

    @pytest.mark.asyncio
    async def test_chat_all_chat_types(self, db_session, test_user):
        """Test Chat model accepts all valid chat_type values."""
        chat_types = ["private", "group", "supergroup", "channel"]
        base_chat_id = 70000

        for i, chat_type in enumerate(chat_types):
            chat = Chat(
                chat_id=base_chat_id + i,
                user_id=test_user.id,
                chat_type=chat_type,
            )
            db_session.add(chat)

        await db_session.commit()

        for i, chat_type in enumerate(chat_types):
            result = await db_session.execute(
                select(Chat).where(Chat.chat_id == base_chat_id + i)
            )
            saved_chat = result.scalar_one()
            assert saved_chat.chat_type == chat_type

    @pytest.mark.asyncio
    async def test_chat_user_relationship(self, db_session, test_user):
        """Test Chat has correct relationship with User."""
        chat = Chat(chat_id=60000, user_id=test_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(select(Chat).where(Chat.chat_id == 60000))
        saved_chat = result.scalar_one()

        # Load the user relationship
        await db_session.refresh(saved_chat, ["user"])
        assert saved_chat.user is not None
        assert saved_chat.user.id == test_user.id

    @pytest.mark.asyncio
    async def test_chat_timestamp_mixin(self, db_session, test_user):
        """Test that Chat has created_at timestamp from TimestampMixin."""
        chat = Chat(chat_id=50000, user_id=test_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(select(Chat).where(Chat.chat_id == 50000))
        saved_chat = result.scalar_one()

        assert saved_chat.created_at is not None
        assert isinstance(saved_chat.created_at, datetime)

    @pytest.mark.asyncio
    async def test_chat_settings_json_storage(self, db_session, test_user):
        """Test Chat can store JSON settings as text."""
        import json

        settings_dict = {
            "notifications": True,
            "language": "en",
            "features": ["image_analysis", "vector_search"],
        }
        chat = Chat(
            chat_id=40000,
            user_id=test_user.id,
            settings=json.dumps(settings_dict),
        )
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(select(Chat).where(Chat.chat_id == 40000))
        saved_chat = result.scalar_one()

        loaded_settings = json.loads(saved_chat.settings)
        assert loaded_settings == settings_dict


class TestClaudeSessionModel:
    """Test suite for the ClaudeSession model."""

    @pytest.fixture
    async def db_session(self):
        """Create a test database session with fresh tables."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        session = async_session()
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()
            os.unlink(db_path)

    @pytest.fixture
    async def test_user(self, db_session):
        """Create a test user for ClaudeSession foreign key."""
        user = User(user_id=200000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 200000))
        return result.scalar_one()

    @pytest.mark.asyncio
    async def test_claude_session_creation_with_required_fields(
        self, db_session, test_user
    ):
        """Test creating a ClaudeSession with only required fields."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=300000,
            session_id="abc123def456",
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "abc123def456")
        )
        saved_session = result.scalar_one()

        assert saved_session.user_id == test_user.id
        assert saved_session.chat_id == 300000
        assert saved_session.session_id == "abc123def456"
        assert saved_session.id is not None

    @pytest.mark.asyncio
    async def test_claude_session_default_is_active(self, db_session, test_user):
        """Test that is_active defaults to True."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=310000,
            session_id="session_active_test",
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "session_active_test")
        )
        saved_session = result.scalar_one()

        assert saved_session.is_active is True

    @pytest.mark.asyncio
    async def test_claude_session_with_all_fields(self, db_session, test_user):
        """Test creating a ClaudeSession with all fields populated."""
        last_used_time = datetime.now(timezone.utc)
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=320000,
            session_id="full_session_123456",
            name="My Claude Session",
            is_active=False,
            last_prompt="What is the meaning of life?",
            last_used=last_used_time,
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "full_session_123456")
        )
        saved_session = result.scalar_one()

        assert saved_session.name == "My Claude Session"
        assert saved_session.is_active is False
        assert saved_session.last_prompt == "What is the meaning of life?"
        assert saved_session.last_used is not None

    @pytest.mark.asyncio
    async def test_claude_session_unique_session_id(self, db_session, test_user):
        """Test that session_id must be unique."""
        session1 = ClaudeSession(
            user_id=test_user.id,
            chat_id=330000,
            session_id="duplicate_session",
        )
        db_session.add(session1)
        await db_session.commit()

        session2 = ClaudeSession(
            user_id=test_user.id,
            chat_id=340000,
            session_id="duplicate_session",
        )
        db_session.add(session2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_claude_session_repr(self, db_session, test_user):
        """Test ClaudeSession __repr__ method returns correct format."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=350000,
            session_id="repr_test_session_12345678",
            is_active=True,
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "repr_test_session_12345678"
            )
        )
        saved_session = result.scalar_one()

        repr_str = repr(saved_session)
        assert "ClaudeSession" in repr_str
        # The repr truncates session_id to first 8 characters
        assert "repr_tes" in repr_str
        assert "..." in repr_str
        assert "True" in repr_str

    @pytest.mark.asyncio
    async def test_claude_session_user_relationship(self, db_session, test_user):
        """Test ClaudeSession has correct relationship with User."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=360000,
            session_id="relationship_test_session",
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "relationship_test_session"
            )
        )
        saved_session = result.scalar_one()

        # Load the user relationship
        await db_session.refresh(saved_session, ["user"])
        assert saved_session.user is not None
        assert saved_session.user.id == test_user.id

    @pytest.mark.asyncio
    async def test_claude_session_timestamp_mixin(self, db_session, test_user):
        """Test that ClaudeSession has created_at timestamp from TimestampMixin."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=370000,
            session_id="timestamp_test_session",
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "timestamp_test_session"
            )
        )
        saved_session = result.scalar_one()

        assert saved_session.created_at is not None
        assert isinstance(saved_session.created_at, datetime)

    @pytest.mark.asyncio
    async def test_claude_session_long_prompt(self, db_session, test_user):
        """Test ClaudeSession can store long prompts."""
        long_prompt = "This is a very long prompt. " * 1000  # ~30000 characters

        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=380000,
            session_id="long_prompt_session",
            last_prompt=long_prompt,
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "long_prompt_session")
        )
        saved_session = result.scalar_one()

        assert saved_session.last_prompt == long_prompt
        assert len(saved_session.last_prompt) > 20000

    @pytest.mark.asyncio
    async def test_claude_session_update_last_used(self, db_session, test_user):
        """Test updating last_used timestamp."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=390000,
            session_id="update_last_used_session",
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "update_last_used_session"
            )
        )
        saved_session = result.scalar_one()

        # Initially last_used is None
        assert saved_session.last_used is None

        # Update last_used
        new_time = datetime.now(timezone.utc)
        saved_session.last_used = new_time
        await db_session.commit()

        # Refresh and verify
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "update_last_used_session"
            )
        )
        updated_session = result.scalar_one()
        assert updated_session.last_used is not None


class TestUserChatRelationship:
    """Test suite for User-Chat relationship and cascading operations."""

    @pytest.fixture
    async def db_session(self):
        """Create a test database session with fresh tables."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        session = async_session()
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_user_can_have_multiple_chats(self, db_session):
        """Test a User can have multiple Chat associations."""
        user = User(user_id=500000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 500000))
        saved_user = result.scalar_one()

        # Create multiple chats for the user
        chat_ids = [510000, 520000, 530000]
        for chat_id in chat_ids:
            chat = Chat(chat_id=chat_id, user_id=saved_user.id)
            db_session.add(chat)

        await db_session.commit()

        # Verify all chats are associated with the user
        result = await db_session.execute(
            select(Chat).where(Chat.user_id == saved_user.id)
        )
        user_chats = result.scalars().all()

        assert len(user_chats) == 3
        assert {chat.chat_id for chat in user_chats} == set(chat_ids)

    @pytest.mark.asyncio
    async def test_cascade_delete_user_removes_chats(self, db_session):
        """Test deleting a User cascades to remove associated Chats."""
        user = User(user_id=600000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 600000))
        saved_user = result.scalar_one()

        # Create chats for the user
        chat = Chat(chat_id=610000, user_id=saved_user.id)
        db_session.add(chat)
        await db_session.commit()

        # Delete the user
        await db_session.delete(saved_user)
        await db_session.commit()

        # Verify chat is also deleted (cascade)
        result = await db_session.execute(
            select(Chat).where(Chat.chat_id == 610000)
        )
        remaining_chats = result.scalars().all()
        assert len(remaining_chats) == 0


class TestUserClaudeSessionRelationship:
    """Test suite for User-ClaudeSession relationship and cascading operations."""

    @pytest.fixture
    async def db_session(self):
        """Create a test database session with fresh tables."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        session = async_session()
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_user_can_have_multiple_claude_sessions(self, db_session):
        """Test a User can have multiple ClaudeSession associations."""
        user = User(user_id=700000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 700000))
        saved_user = result.scalar_one()

        # Create multiple claude sessions for the user
        session_ids = ["session_a", "session_b", "session_c"]
        for i, session_id in enumerate(session_ids):
            claude_session = ClaudeSession(
                user_id=saved_user.id,
                chat_id=710000 + i,
                session_id=session_id,
            )
            db_session.add(claude_session)

        await db_session.commit()

        # Verify all sessions are associated with the user
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.user_id == saved_user.id)
        )
        user_sessions = result.scalars().all()

        assert len(user_sessions) == 3
        assert {s.session_id for s in user_sessions} == set(session_ids)

    @pytest.mark.asyncio
    async def test_cascade_delete_user_removes_claude_sessions(self, db_session):
        """Test deleting a User cascades to remove associated ClaudeSessions."""
        user = User(user_id=800000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 800000))
        saved_user = result.scalar_one()

        # Create claude session for the user
        claude_session = ClaudeSession(
            user_id=saved_user.id,
            chat_id=810000,
            session_id="cascade_delete_test_session",
        )
        db_session.add(claude_session)
        await db_session.commit()

        # Delete the user
        await db_session.delete(saved_user)
        await db_session.commit()

        # Verify claude session is also deleted (cascade)
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "cascade_delete_test_session"
            )
        )
        remaining_sessions = result.scalars().all()
        assert len(remaining_sessions) == 0


class TestEdgeCases:
    """Test suite for edge cases and boundary conditions."""

    @pytest.fixture
    async def db_session(self):
        """Create a test database session with fresh tables."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        session = async_session()
        try:
            yield session
        finally:
            await session.close()
            await engine.dispose()
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_user_id_max_value(self, db_session):
        """Test User model handles large user_id values (Telegram IDs can be large)."""
        large_user_id = 9_999_999_999  # Large but valid Telegram user ID
        user = User(user_id=large_user_id)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.user_id == large_user_id)
        )
        saved_user = result.scalar_one()

        assert saved_user.user_id == large_user_id

    @pytest.mark.asyncio
    async def test_chat_id_negative_value(self, db_session):
        """Test Chat model handles negative chat_id values (group chats)."""
        user = User(user_id=900000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 900000))
        saved_user = result.scalar_one()

        # Telegram group chat IDs are negative
        negative_chat_id = -1_001_234_567_890
        chat = Chat(chat_id=negative_chat_id, user_id=saved_user.id)
        db_session.add(chat)
        await db_session.commit()

        result = await db_session.execute(
            select(Chat).where(Chat.chat_id == negative_chat_id)
        )
        saved_chat = result.scalar_one()

        assert saved_chat.chat_id == negative_chat_id

    @pytest.mark.asyncio
    async def test_empty_string_fields(self, db_session):
        """Test models handle empty strings correctly."""
        user = User(
            user_id=910000,
            username="",  # Empty string
            first_name="",
            last_name="",
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 910000))
        saved_user = result.scalar_one()

        assert saved_user.username == ""
        assert saved_user.first_name == ""
        assert saved_user.last_name == ""

    @pytest.mark.asyncio
    async def test_session_id_64_characters(self, db_session):
        """Test ClaudeSession handles max length session_id (64 chars)."""
        user = User(user_id=920000)
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 920000))
        saved_user = result.scalar_one()

        # 64 character session_id (max allowed)
        max_length_session_id = "a" * 64
        session = ClaudeSession(
            user_id=saved_user.id,
            chat_id=920001,
            session_id=max_length_session_id,
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == max_length_session_id)
        )
        saved_session = result.scalar_one()

        assert len(saved_session.session_id) == 64

    @pytest.mark.asyncio
    async def test_multiple_users_same_chat_id_different_users(self, db_session):
        """Test different users can have different chats (no shared chat_id)."""
        user1 = User(user_id=930000)
        user2 = User(user_id=940000)
        db_session.add(user1)
        db_session.add(user2)
        await db_session.commit()

        result1 = await db_session.execute(select(User).where(User.user_id == 930000))
        saved_user1 = result1.scalar_one()
        result2 = await db_session.execute(select(User).where(User.user_id == 940000))
        saved_user2 = result2.scalar_one()

        # Each user has their own private chat with the bot
        chat1 = Chat(chat_id=930000, user_id=saved_user1.id)  # Private chat with user1
        chat2 = Chat(chat_id=940000, user_id=saved_user2.id)  # Private chat with user2
        db_session.add(chat1)
        db_session.add(chat2)
        await db_session.commit()

        # Verify both chats exist
        result = await db_session.execute(select(Chat))
        all_chats = result.scalars().all()
        assert len(all_chats) == 2

    @pytest.mark.asyncio
    async def test_null_optional_fields(self, db_session):
        """Test models handle None/NULL values for optional fields."""
        user = User(
            user_id=950000,
            username=None,
            first_name=None,
            last_name=None,
            language_code=None,
            user_group=None,
            admin_notes=None,
        )
        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.user_id == 950000))
        saved_user = result.scalar_one()

        assert saved_user.username is None
        assert saved_user.first_name is None
        assert saved_user.last_name is None
        assert saved_user.language_code is None
        assert saved_user.user_group is None
        assert saved_user.admin_notes is None
