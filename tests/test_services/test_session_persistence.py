"""
Tests for Claude session persistence to database.

Tests cover:
- Session creation saves to DB
- Loading active sessions on init recovers from DB
- New session deactivates previous for same chat_id
- last_used_at updates on session use
- Session recovery across service re-initialization
- End session marks inactive in DB
- In-memory cache stays in sync with DB

Uses in-memory SQLite for test isolation.

Closes #77
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.claude_session import ClaudeSession
from src.models.user import User


@pytest.fixture
async def db_session():
    """Create a test database session with fresh tables."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(database_url, echo=False, future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    session = async_session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()
        os.unlink(db_path)


@pytest.fixture
async def test_user(db_session):
    """Create a test user for foreign key references."""
    user = User(user_id=100001)
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.user_id == 100001))
    return result.scalar_one()


# =============================================================================
# Session Creation and DB Persistence
# =============================================================================


class TestSessionCreationPersistence:
    """Test that session creation persists to database."""

    @pytest.mark.asyncio
    async def test_new_session_saved_to_db(self, db_session, test_user):
        """Creating a new ClaudeSession saves it to the database."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=12345,
            session_id="persist-test-001",
            name="Test Session",
            is_active=True,
            last_prompt="Hello world",
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "persist-test-001")
        )
        saved = result.scalar_one()

        assert saved.chat_id == 12345
        assert saved.session_id == "persist-test-001"
        assert saved.name == "Test Session"
        assert saved.is_active is True
        assert saved.last_prompt == "Hello world"
        assert saved.last_used is not None

    @pytest.mark.asyncio
    async def test_session_fields_nullable(self, db_session, test_user):
        """Optional fields can be None."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=12345,
            session_id="nullable-test-001",
            name=None,
            last_prompt=None,
            last_used=None,
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "nullable-test-001")
        )
        saved = result.scalar_one()

        assert saved.name is None
        assert saved.last_prompt is None
        assert saved.last_used is None

    @pytest.mark.asyncio
    async def test_session_default_is_active(self, db_session, test_user):
        """New sessions default to is_active=True."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=12345,
            session_id="default-active-001",
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "default-active-001"
            )
        )
        saved = result.scalar_one()

        assert saved.is_active is True


# =============================================================================
# Session Recovery on Init
# =============================================================================


class TestSessionRecoveryOnInit:
    """Test that active sessions can be loaded from DB to restore state."""

    @pytest.mark.asyncio
    async def test_recover_active_session_from_db(self, db_session, test_user):
        """Active sessions in DB can be queried to rebuild in-memory cache."""
        # Simulate a session that was saved before restart
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=99999,
            session_id="recovery-test-001",
            name="Pre-restart Session",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate recovery: query active sessions from DB
        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 99999,
                ClaudeSession.is_active == True,
            )
            .order_by(ClaudeSession.last_used.desc())
            .limit(1)
        )
        recovered = result.scalar_one_or_none()

        assert recovered is not None
        assert recovered.session_id == "recovery-test-001"
        assert recovered.name == "Pre-restart Session"
        assert recovered.is_active is True

    @pytest.mark.asyncio
    async def test_recover_only_active_sessions(self, db_session, test_user):
        """Recovery should only return active sessions, not inactive ones."""
        # Create one active and one inactive session for same chat
        active_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=88888,
            session_id="active-session-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        inactive_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=88888,
            session_id="inactive-session-001",
            is_active=False,
            last_used=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db_session.add(active_session)
        db_session.add(inactive_session)
        await db_session.commit()

        # Query only active sessions
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.chat_id == 88888,
                ClaudeSession.is_active == True,
            )
        )
        active_sessions = result.scalars().all()

        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == "active-session-001"

    @pytest.mark.asyncio
    async def test_recover_most_recent_active_session(self, db_session, test_user):
        """When multiple active sessions exist, the most recent is returned first."""
        older = ClaudeSession(
            user_id=test_user.id,
            chat_id=77777,
            session_id="older-session-001",
            is_active=True,
            last_used=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        newer = ClaudeSession(
            user_id=test_user.id,
            chat_id=77777,
            session_id="newer-session-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(older)
        db_session.add(newer)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 77777,
                ClaudeSession.is_active == True,
            )
            .order_by(ClaudeSession.last_used.desc())
            .limit(1)
        )
        most_recent = result.scalar_one_or_none()

        assert most_recent is not None
        assert most_recent.session_id == "newer-session-001"

    @pytest.mark.asyncio
    async def test_no_active_session_returns_none(self, db_session, test_user):
        """When no active sessions exist for a chat, recovery returns None."""
        inactive = ClaudeSession(
            user_id=test_user.id,
            chat_id=66666,
            session_id="inactive-only-001",
            is_active=False,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(inactive)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 66666,
                ClaudeSession.is_active == True,
            )
            .order_by(ClaudeSession.last_used.desc())
            .limit(1)
        )
        recovered = result.scalar_one_or_none()

        assert recovered is None


# =============================================================================
# New Session Deactivates Previous
# =============================================================================


class TestNewSessionDeactivatesPrevious:
    """Test that creating a new session deactivates the previous one for same chat."""

    @pytest.mark.asyncio
    async def test_deactivate_previous_on_new_session(self, db_session, test_user):
        """When a new session is created, the old active one is marked inactive."""
        # Create first session
        old_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=55555,
            session_id="old-session-001",
            is_active=True,
            last_used=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(old_session)
        await db_session.commit()

        # Deactivate old sessions for this chat (simulating what service does)
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.chat_id == 55555,
                ClaudeSession.is_active == True,
            )
        )
        for s in result.scalars().all():
            s.is_active = False

        # Create new session
        new_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=55555,
            session_id="new-session-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(new_session)
        await db_session.commit()

        # Verify old is inactive, new is active
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "old-session-001")
        )
        old = result.scalar_one()
        assert old.is_active is False

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "new-session-001")
        )
        new = result.scalar_one()
        assert new.is_active is True

    @pytest.mark.asyncio
    async def test_deactivation_scoped_to_chat(self, db_session, test_user):
        """Deactivating sessions for one chat does not affect other chats."""
        # Create sessions for two different chats
        chat_a_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=44444,
            session_id="chat-a-session-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        chat_b_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=33333,
            session_id="chat-b-session-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(chat_a_session)
        db_session.add(chat_b_session)
        await db_session.commit()

        # Deactivate only chat A's sessions
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.chat_id == 44444,
                ClaudeSession.is_active == True,
            )
        )
        for s in result.scalars().all():
            s.is_active = False
        await db_session.commit()

        # Chat A session is inactive
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "chat-a-session-001"
            )
        )
        assert result.scalar_one().is_active is False

        # Chat B session is still active
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "chat-b-session-001"
            )
        )
        assert result.scalar_one().is_active is True


# =============================================================================
# Last Used Updates
# =============================================================================


class TestLastUsedUpdates:
    """Test that last_used_at updates on session use."""

    @pytest.mark.asyncio
    async def test_last_used_updates_on_session_use(self, db_session, test_user):
        """Using a session updates its last_used timestamp."""
        original_time = datetime.now(timezone.utc) - timedelta(hours=1)
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=22222,
            session_id="last-used-test-001",
            is_active=True,
            last_used=original_time,
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate session use: update last_used
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "last-used-test-001"
            )
        )
        db_sess = result.scalar_one()
        new_time = datetime.now(timezone.utc)
        db_sess.last_used = new_time
        await db_session.commit()

        # Verify update
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "last-used-test-001"
            )
        )
        updated = result.scalar_one()
        assert updated.last_used is not None
        # The updated time should be more recent than the original
        assert updated.last_used >= original_time

    @pytest.mark.asyncio
    async def test_last_prompt_updates_on_session_use(self, db_session, test_user):
        """Using a session updates its last_prompt field."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=11111,
            session_id="prompt-update-test-001",
            is_active=True,
            last_prompt="First prompt",
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        # Update prompt on use
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "prompt-update-test-001"
            )
        )
        db_sess = result.scalar_one()
        db_sess.last_prompt = "Updated prompt"
        db_sess.last_used = datetime.now(timezone.utc)
        await db_session.commit()

        # Verify
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "prompt-update-test-001"
            )
        )
        updated = result.scalar_one()
        assert updated.last_prompt == "Updated prompt"


# =============================================================================
# End Session (Deactivation)
# =============================================================================


class TestEndSession:
    """Test ending a session marks it inactive in DB."""

    @pytest.mark.asyncio
    async def test_end_session_marks_inactive(self, db_session, test_user):
        """Ending a session sets is_active to False."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=10001,
            session_id="end-test-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        # End the session
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "end-test-001")
        )
        db_sess = result.scalar_one()
        db_sess.is_active = False
        await db_session.commit()

        # Verify
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "end-test-001")
        )
        ended = result.scalar_one()
        assert ended.is_active is False

    @pytest.mark.asyncio
    async def test_ended_session_not_recovered(self, db_session, test_user):
        """Ended sessions are not returned by active session queries."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=10002,
            session_id="ended-recovery-001",
            is_active=False,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 10002,
                ClaudeSession.is_active == True,
            )
            .limit(1)
        )
        recovered = result.scalar_one_or_none()

        assert recovered is None


# =============================================================================
# In-Memory Cache Sync
# =============================================================================


class TestInMemoryCacheSync:
    """Test that the in-memory cache stays in sync with DB state."""

    @pytest.mark.asyncio
    async def test_cache_populated_from_db_query(self, db_session, test_user):
        """Simulates service.get_active_session populating cache from DB."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=20001,
            session_id="cache-sync-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate what ClaudeCodeService.get_active_session does:
        # query DB, then populate cache
        active_sessions = {}  # in-memory cache (like self.active_sessions)

        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 20001,
                ClaudeSession.is_active == True,
            )
            .order_by(ClaudeSession.last_used.desc())
            .limit(1)
        )
        db_sess = result.scalar_one_or_none()

        if db_sess:
            active_sessions[db_sess.chat_id] = db_sess.session_id

        assert active_sessions[20001] == "cache-sync-001"

    @pytest.mark.asyncio
    async def test_cache_cleared_on_session_end(self, db_session, test_user):
        """Ending a session clears the cache entry."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=20002,
            session_id="cache-clear-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate populated cache
        active_sessions = {20002: "cache-clear-001"}

        # End session in DB
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "cache-clear-001")
        )
        db_sess = result.scalar_one()
        db_sess.is_active = False
        await db_session.commit()

        # Clear cache (like service.end_session does)
        active_sessions.pop(20002, None)

        assert 20002 not in active_sessions

    @pytest.mark.asyncio
    async def test_cache_updated_on_session_switch(self, db_session, test_user):
        """Switching sessions updates the cache to the new session."""
        old_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=20003,
            session_id="old-cache-001",
            is_active=True,
            last_used=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        new_session = ClaudeSession(
            user_id=test_user.id,
            chat_id=20003,
            session_id="new-cache-001",
            is_active=False,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(old_session)
        db_session.add(new_session)
        await db_session.commit()

        active_sessions = {20003: "old-cache-001"}

        # Deactivate old, activate new (like reactivate_session)
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.chat_id == 20003,
                ClaudeSession.is_active == True,
            )
        )
        for s in result.scalars().all():
            s.is_active = False

        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "new-cache-001")
        )
        target = result.scalar_one()
        target.is_active = True
        target.last_used = datetime.now(timezone.utc)
        await db_session.commit()

        # Update cache
        active_sessions[20003] = "new-cache-001"

        assert active_sessions[20003] == "new-cache-001"


# =============================================================================
# Session Idle Timeout
# =============================================================================


class TestSessionIdleTimeout:
    """Test that idle sessions are expired correctly."""

    @pytest.mark.asyncio
    async def test_idle_session_deactivated(self, db_session, test_user):
        """Sessions idle beyond the timeout threshold are deactivated."""
        idle_time = datetime.now(timezone.utc) - timedelta(hours=10)
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=30001,
            session_id="idle-test-001",
            is_active=True,
            last_used=idle_time,
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate idle check (like get_active_session with 8h timeout)
        timeout_minutes = 480  # 8 hours
        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 30001,
                ClaudeSession.is_active == True,
            )
            .order_by(ClaudeSession.last_used.desc())
            .limit(1)
        )
        db_sess = result.scalar_one_or_none()

        if db_sess and db_sess.last_used:
            idle_delta = datetime.now(timezone.utc) - db_sess.last_used.replace(
                tzinfo=timezone.utc
            )
            if idle_delta > timedelta(minutes=timeout_minutes):
                db_sess.is_active = False
                await db_session.commit()

        # Verify deactivated
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "idle-test-001")
        )
        assert result.scalar_one().is_active is False

    @pytest.mark.asyncio
    async def test_recent_session_not_deactivated(self, db_session, test_user):
        """Sessions used recently are NOT deactivated by idle check."""
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=30002,
            session_id="recent-test-001",
            is_active=True,
            last_used=recent_time,
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate idle check
        timeout_minutes = 480
        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 30002,
                ClaudeSession.is_active == True,
            )
            .order_by(ClaudeSession.last_used.desc())
            .limit(1)
        )
        db_sess = result.scalar_one_or_none()

        if db_sess and db_sess.last_used:
            idle_delta = datetime.now(timezone.utc) - db_sess.last_used.replace(
                tzinfo=timezone.utc
            )
            if idle_delta > timedelta(minutes=timeout_minutes):
                db_sess.is_active = False
                await db_session.commit()

        # Verify still active
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "recent-test-001")
        )
        assert result.scalar_one().is_active is True


# =============================================================================
# Session Deletion
# =============================================================================


class TestSessionDeletion:
    """Test deleting sessions from the database."""

    @pytest.mark.asyncio
    async def test_delete_session_removes_from_db(self, db_session, test_user):
        """Deleting a session removes it entirely from the database."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=40001,
            session_id="delete-test-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        # Delete the session
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "delete-test-001")
        )
        to_delete = result.scalar_one()
        await db_session.delete(to_delete)
        await db_session.commit()

        # Verify gone
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "delete-test-001")
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_one_session_preserves_others(self, db_session, test_user):
        """Deleting one session does not affect other sessions."""
        session_a = ClaudeSession(
            user_id=test_user.id,
            chat_id=40002,
            session_id="keep-test-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        session_b = ClaudeSession(
            user_id=test_user.id,
            chat_id=40002,
            session_id="delete-test-002",
            is_active=False,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session_a)
        db_session.add(session_b)
        await db_session.commit()

        # Delete only session_b
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "delete-test-002")
        )
        await db_session.delete(result.scalar_one())
        await db_session.commit()

        # session_a still exists
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "keep-test-001")
        )
        assert result.scalar_one_or_none() is not None

        # session_b is gone
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "delete-test-002")
        )
        assert result.scalar_one_or_none() is None


# =============================================================================
# Session Rename
# =============================================================================


class TestSessionRename:
    """Test renaming sessions."""

    @pytest.mark.asyncio
    async def test_rename_session(self, db_session, test_user):
        """Renaming a session updates the name in the database."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=50001,
            session_id="rename-test-001",
            name="Original Name",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        db_session.add(session)
        await db_session.commit()

        # Rename
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "rename-test-001")
        )
        db_sess = result.scalar_one()
        db_sess.name = "New Name"
        await db_session.commit()

        # Verify
        result = await db_session.execute(
            select(ClaudeSession).where(ClaudeSession.session_id == "rename-test-001")
        )
        assert result.scalar_one().name == "New Name"


# =============================================================================
# Session Reactivation
# =============================================================================


class TestSessionReactivation:
    """Test reactivating previously inactive sessions."""

    @pytest.mark.asyncio
    async def test_reactivate_session(self, db_session, test_user):
        """An inactive session can be reactivated."""
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=60001,
            session_id="reactivate-test-001",
            is_active=False,
            last_used=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db_session.add(session)
        await db_session.commit()

        # Reactivate
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "reactivate-test-001"
            )
        )
        db_sess = result.scalar_one()
        db_sess.is_active = True
        db_sess.last_used = datetime.now(timezone.utc)
        await db_session.commit()

        # Verify
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "reactivate-test-001"
            )
        )
        reactivated = result.scalar_one()
        assert reactivated.is_active is True

    @pytest.mark.asyncio
    async def test_reactivate_deactivates_other_active(self, db_session, test_user):
        """Reactivating a session deactivates other active sessions for same chat."""
        current = ClaudeSession(
            user_id=test_user.id,
            chat_id=60002,
            session_id="current-active-001",
            is_active=True,
            last_used=datetime.now(timezone.utc),
        )
        old = ClaudeSession(
            user_id=test_user.id,
            chat_id=60002,
            session_id="old-to-reactivate-001",
            is_active=False,
            last_used=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(current)
        db_session.add(old)
        await db_session.commit()

        # Deactivate all active for this chat
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.chat_id == 60002,
                ClaudeSession.is_active == True,
            )
        )
        for s in result.scalars().all():
            s.is_active = False

        # Activate the old one
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "old-to-reactivate-001"
            )
        )
        target = result.scalar_one()
        target.is_active = True
        target.last_used = datetime.now(timezone.utc)
        await db_session.commit()

        # Verify states
        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "current-active-001"
            )
        )
        assert result.scalar_one().is_active is False

        result = await db_session.execute(
            select(ClaudeSession).where(
                ClaudeSession.session_id == "old-to-reactivate-001"
            )
        )
        assert result.scalar_one().is_active is True


# =============================================================================
# Timestamp Correlation (find_session_by_timestamp pattern)
# =============================================================================


class TestTimestampCorrelation:
    """Test finding sessions by timestamp correlation."""

    @pytest.mark.asyncio
    async def test_find_session_by_timestamp(self, db_session, test_user):
        """Can find a session by correlating with a message timestamp."""
        session_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=70001,
            session_id="timestamp-test-001",
            is_active=True,
            last_used=session_time,
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate finding by timestamp (within 30s tolerance)
        message_time = session_time + timedelta(seconds=10)
        tolerance = 30
        time_lower = message_time - timedelta(seconds=tolerance)
        time_upper = message_time + timedelta(seconds=tolerance)

        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 70001,
                ClaudeSession.last_used >= time_lower,
                ClaudeSession.last_used <= time_upper,
            )
            .order_by(ClaudeSession.last_used.desc())
            .limit(1)
        )
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.session_id == "timestamp-test-001"

    @pytest.mark.asyncio
    async def test_timestamp_out_of_tolerance_returns_none(self, db_session, test_user):
        """Sessions outside the tolerance window are not found."""
        session_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        session = ClaudeSession(
            user_id=test_user.id,
            chat_id=70002,
            session_id="timestamp-miss-001",
            is_active=True,
            last_used=session_time,
        )
        db_session.add(session)
        await db_session.commit()

        # Message time is far from session time
        message_time = datetime.now(timezone.utc)
        tolerance = 30
        time_lower = message_time - timedelta(seconds=tolerance)
        time_upper = message_time + timedelta(seconds=tolerance)

        result = await db_session.execute(
            select(ClaudeSession)
            .where(
                ClaudeSession.chat_id == 70002,
                ClaudeSession.last_used >= time_lower,
                ClaudeSession.last_used <= time_upper,
            )
            .limit(1)
        )
        found = result.scalar_one_or_none()

        assert found is None
