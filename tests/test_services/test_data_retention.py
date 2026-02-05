"""
Tests for data retention service (Issue #52).

The data retention service should only delete messages/poll responses belonging
to the user whose retention policy is being enforced, using the correct ID
column for each table:
- Message.chat_id -> FK to chats.id (database PK)
- PollResponse.chat_id -> Telegram chat ID (matches Chat.chat_id)
"""

from unittest.mock import MagicMock, patch

import pytest


class TestDataRetentionUserScoping:
    """Tests that data retention correctly scopes deletions to the target user."""

    def _make_mock_session(self, executed_statements):
        """Create a mock session that captures executed SQL statements."""

        class MockResult:
            rowcount = 0

            def scalars(self):
                return self

            def all(self):
                settings = MagicMock()
                settings.data_retention = "1_month"
                settings.user_id = 42
                return [settings]

        class MockSession:
            async def execute(self, stmt):
                executed_statements.append(str(stmt))
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        return MockSession()

    @pytest.mark.asyncio
    async def test_message_deletion_uses_db_pk(self):
        """Message deletion uses Chat.id (database PK) since Message.chat_id is FK to chats.id."""
        from src.services.data_retention_service import enforce_data_retention

        executed_statements = []
        mock_session = self._make_mock_session(executed_statements)

        with patch(
            "src.services.data_retention_service.get_db_session",
            return_value=mock_session,
        ):
            await enforce_data_retention()

        message_deletes = [
            s
            for s in executed_statements
            if "messages" in s.lower() and "DELETE" in s.upper()
        ]
        assert len(message_deletes) > 0, "Expected a message delete statement"

        stmt_str = message_deletes[0]
        assert (
            "chats" in stmt_str.lower()
        ), f"Message deletion must join to chats table, got: {stmt_str}"
        # Must use chats.id (database PK) since Message.chat_id is FK to chats.id
        assert (
            "chats.id" in stmt_str.lower()
        ), f"Message deletion must use chats.id (database PK), got: {stmt_str}"
        assert (
            "user_id" in stmt_str.lower()
        ), f"Message deletion must filter by user_id, got: {stmt_str}"

    @pytest.mark.asyncio
    async def test_poll_response_deletion_uses_telegram_chat_id(self):
        """Poll response deletion must use Chat.chat_id (Telegram ID), not Chat.id (PK).

        PollResponse.chat_id stores Telegram chat IDs (no FK), so the subquery
        must select Chat.chat_id to match correctly.
        """
        from src.services.data_retention_service import enforce_data_retention

        executed_statements = []
        mock_session = self._make_mock_session(executed_statements)

        with patch(
            "src.services.data_retention_service.get_db_session",
            return_value=mock_session,
        ):
            await enforce_data_retention()

        poll_deletes = [
            s
            for s in executed_statements
            if "poll_responses" in s.lower() and "DELETE" in s.upper()
        ]
        assert len(poll_deletes) > 0, "Expected a poll response delete statement"

        stmt_str = poll_deletes[0]
        assert (
            "chats" in stmt_str.lower()
        ), f"PollResponse deletion must join to chats table, got: {stmt_str}"
        # CRITICAL: Must use chats.chat_id (Telegram ID), NOT chats.id (database PK)
        assert "chats.chat_id" in stmt_str.lower(), (
            f"PollResponse deletion must use chats.chat_id (Telegram ID), "
            f"not chats.id (database PK). Got: {stmt_str}"
        )
        assert (
            "user_id" in stmt_str.lower()
        ), f"PollResponse deletion must filter by user_id, got: {stmt_str}"

    @pytest.mark.asyncio
    async def test_check_in_deletion_scoped_to_user(self):
        """Check-in deletion uses direct user_id filter."""
        from src.services.data_retention_service import enforce_data_retention

        executed_statements = []
        mock_session = self._make_mock_session(executed_statements)

        with patch(
            "src.services.data_retention_service.get_db_session",
            return_value=mock_session,
        ):
            await enforce_data_retention()

        checkin_deletes = [
            s
            for s in executed_statements
            if "check_ins" in s.lower() and "DELETE" in s.upper()
        ]
        assert len(checkin_deletes) > 0, "Expected a check-in delete statement"

        stmt_str = checkin_deletes[0]
        assert (
            "user_id" in stmt_str.lower()
        ), f"CheckIn deletion must filter by user_id, got: {stmt_str}"

    @pytest.mark.asyncio
    async def test_forever_retention_skips_deletion(self):
        """Users with 'forever' retention produce no DELETE statements."""
        from src.services.data_retention_service import enforce_data_retention

        executed_statements = []

        class MockResult:
            rowcount = 0

            def scalars(self):
                return self

            def all(self):
                return []  # No users with non-forever retention

        class MockSession:
            async def execute(self, stmt):
                executed_statements.append(str(stmt))
                return MockResult()

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch(
            "src.services.data_retention_service.get_db_session",
            return_value=MockSession(),
        ):
            result = await enforce_data_retention()

        assert result == {}
        delete_stmts = [s for s in executed_statements if "DELETE" in s.upper()]
        assert len(delete_stmts) == 0
