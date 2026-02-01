"""
Tests for data retention service (Issue #52).

The data retention service should only delete messages belonging to
the user whose retention policy is being enforced, not messages
from other users who share the same chat.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

from sqlalchemy import delete, select


class TestDataRetentionUserScoping:
    """Tests that data retention correctly scopes deletions to the target user."""

    @pytest.mark.asyncio
    async def test_message_deletion_filters_by_user(self):
        """Message deletion should only affect chats owned by the target user."""
        from src.services.data_retention_service import enforce_data_retention
        from src.models.chat import Chat

        # We'll capture the delete statement to verify it includes user filtering
        executed_statements = []

        class MockResult:
            rowcount = 0

            def scalars(self):
                return self

            def all(self):
                # Return a mock UserSettings with 1_month retention
                settings = MagicMock()
                settings.data_retention = "1_month"
                settings.user_id = 42
                return [settings]

        class MockSession:
            committed = False

            async def execute(self, stmt):
                executed_statements.append(stmt)
                return MockResult()

            async def commit(self):
                self.committed = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_session = MockSession()

        with patch(
            "src.services.data_retention_service.get_db_session",
            return_value=mock_session,
        ):
            await enforce_data_retention()

        # Find the delete(Message) statement
        message_deletes = []
        for stmt in executed_statements:
            # Check if this is a delete statement by examining its string representation
            stmt_str = str(stmt)
            if "messages" in stmt_str.lower() and "DELETE" in stmt_str.upper():
                message_deletes.append(stmt_str)

        # The delete statement should reference the chats table with user_id filter
        # not just self-reference Message.chat_id from Message
        assert (
            len(message_deletes) > 0
        ), "Expected at least one message delete statement"

        for stmt_str in message_deletes:
            assert "chats" in stmt_str.lower() or "user_id" in stmt_str.lower(), (
                f"Message deletion query must filter by user's chats, "
                f"but got: {stmt_str}"
            )

    @pytest.mark.asyncio
    async def test_poll_response_deletion_filters_by_user(self):
        """Poll response deletion should filter by user's chats, not delete globally."""
        from src.services.data_retention_service import enforce_data_retention

        executed_statements = []

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
                executed_statements.append(stmt)
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
            await enforce_data_retention()

        # Find the delete(PollResponse) statement
        poll_deletes = []
        for stmt in executed_statements:
            stmt_str = str(stmt)
            if "poll_responses" in stmt_str.lower() and "DELETE" in stmt_str.upper():
                poll_deletes.append(stmt_str)

        # Poll response deletion should include chat_id scoping to user's chats
        for stmt_str in poll_deletes:
            assert "chat_id" in stmt_str.lower(), (
                f"PollResponse deletion must scope to user's chats via chat_id, "
                f"but got: {stmt_str}"
            )
