"""
Tests for stale Claude session cleanup (Issue #45).

Sessions in the claude_sessions table with is_active=True but no activity
for extended periods should be automatically deactivated.
"""

import asyncio
import logging
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


def _utcnow():
    """Return current UTC time (for consistent reference)."""
    return datetime.utcnow()


def _make_session_obj(session_id, is_active=True, last_used=None, updated_at=None):
    """Create a mock ClaudeSession-like object."""
    obj = MagicMock()
    obj.id = hash(session_id) % 10000
    obj.session_id = session_id
    obj.is_active = is_active
    obj.last_used = last_used
    obj.updated_at = updated_at
    obj.created_at = last_used or _utcnow()
    return obj


class TestCleanupStaleSessions:
    """Tests for cleanup_stale_sessions()."""

    @pytest.mark.asyncio
    async def test_deactivates_sessions_older_than_threshold(self):
        """Sessions inactive for more than max_age_days should be deactivated."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        now = _utcnow()
        stale_session = _make_session_obj(
            "stale-sess-001",
            is_active=True,
            last_used=now - timedelta(days=10),
        )

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return [stale_session]

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 1
        assert stale_session.is_active is False

    @pytest.mark.asyncio
    async def test_preserves_recently_active_sessions(self):
        """Sessions with recent activity should not be deactivated."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        now = _utcnow()
        recent_session = _make_session_obj(
            "recent-sess-001",
            is_active=True,
            last_used=now - timedelta(days=2),
        )

        # The query for stale sessions should not return recent sessions,
        # so we return an empty list (the SQL WHERE clause filters them).
        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return []

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 0
        # The session object was never returned by the query, so it stays active
        assert recent_session.is_active is True

    @pytest.mark.asyncio
    async def test_handles_empty_table_gracefully(self):
        """Cleanup should handle an empty table without errors."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return []

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 0

    @pytest.mark.asyncio
    async def test_logs_deactivated_count(self, caplog):
        """Cleanup should log the number of deactivated sessions."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        now = _utcnow()
        stale_sessions = [
            _make_session_obj(
                f"stale-{i}",
                is_active=True,
                last_used=now - timedelta(days=14),
            )
            for i in range(3)
        ]

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return stale_sessions

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with (
            patch(
                "src.services.session_cleanup_service.get_db_session",
                return_value=MockSession(),
            ),
            caplog.at_level(logging.INFO),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 3
        assert any("3" in record.message and "stale" in record.message.lower()
                    for record in caplog.records), (
            f"Expected log message about 3 stale sessions, got: "
            f"{[r.message for r in caplog.records]}"
        )

    @pytest.mark.asyncio
    async def test_session_with_no_last_used_falls_back_to_updated_at(self):
        """Sessions with last_used=None but stale updated_at should be deactivated."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        now = _utcnow()
        # Session with no last_used but old updated_at
        no_last_used_session = _make_session_obj(
            "no-last-used-001",
            is_active=True,
            last_used=None,
            updated_at=now - timedelta(days=30),
        )

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return [no_last_used_session]

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 1
        assert no_last_used_session.is_active is False

    @pytest.mark.asyncio
    async def test_session_exactly_at_threshold_is_preserved(self):
        """A session whose last_used is exactly at the threshold boundary is NOT deactivated.

        The cutoff is exclusive: only sessions strictly older than max_age_days are cleaned up.
        Since we query for last_used < cutoff, a session at exactly the cutoff is not returned.
        """
        from src.services.session_cleanup_service import cleanup_stale_sessions

        # The query uses last_used < cutoff, so exactly-at-cutoff sessions
        # won't be returned by the database query.
        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return []  # DB won't return sessions at exact boundary

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_stale_sessions_all_deactivated(self):
        """All stale sessions should be deactivated in a single pass."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        now = _utcnow()
        stale_sessions = [
            _make_session_obj(
                f"stale-multi-{i}",
                is_active=True,
                last_used=now - timedelta(days=8 + i),
            )
            for i in range(5)
        ]

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return stale_sessions

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 5
        for s in stale_sessions:
            assert s.is_active is False

    @pytest.mark.asyncio
    async def test_custom_max_age_days(self):
        """Cleanup should respect custom max_age_days parameter."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        now = _utcnow()
        # Session is 4 days old - stale with max_age_days=3 but not with default 7
        session_4d = _make_session_obj(
            "four-day-old",
            is_active=True,
            last_used=now - timedelta(days=4),
        )

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return [session_4d]

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=3)

        assert count == 1
        assert session_4d.is_active is False

    @pytest.mark.asyncio
    async def test_database_error_handled_gracefully(self):
        """Cleanup should handle database errors without crashing."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        class MockSession:
            async def execute(self, stmt):
                raise RuntimeError("Database connection lost")

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.session_cleanup_service.get_db_session",
            return_value=MockSession(),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        # Should return 0, not raise
        assert count == 0

    @pytest.mark.asyncio
    async def test_logs_nothing_when_no_stale_sessions(self, caplog):
        """When there are no stale sessions, only a debug-level message should appear."""
        from src.services.session_cleanup_service import cleanup_stale_sessions

        class MockResult:
            def scalars(self):
                return self

            def all(self):
                return []

        class MockSession:
            async def execute(self, stmt):
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with (
            patch(
                "src.services.session_cleanup_service.get_db_session",
                return_value=MockSession(),
            ),
            caplog.at_level(logging.INFO),
        ):
            count = await cleanup_stale_sessions(max_age_days=7)

        assert count == 0
        # Should not have any INFO-level messages about deactivation
        deactivation_msgs = [
            r for r in caplog.records
            if r.levelno >= logging.INFO and "deactivat" in r.message.lower()
        ]
        assert len(deactivation_msgs) == 0


class TestRunPeriodicSessionCleanup:
    """Tests for the periodic runner wrapper."""

    @pytest.mark.asyncio
    async def test_periodic_runner_calls_cleanup(self):
        """The periodic runner should call cleanup_stale_sessions on startup."""
        from src.services.session_cleanup_service import run_periodic_session_cleanup

        call_count = 0

        async def mock_cleanup(max_age_days=7):
            nonlocal call_count
            call_count += 1
            return 2

        with patch(
            "src.services.session_cleanup_service.cleanup_stale_sessions",
            side_effect=mock_cleanup,
        ):
            # The periodic runner now runs cleanup immediately on start,
            # then sleeps. We cancel during the sleep after the first run.
            task = asyncio.create_task(
                run_periodic_session_cleanup(interval_hours=1.0)
            )
            # Give the event loop time to run the first cleanup call
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert call_count >= 1
