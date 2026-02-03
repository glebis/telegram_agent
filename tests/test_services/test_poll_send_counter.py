"""
Tests for poll template send counter increment.

Verifies that the times_sent counter and last_sent_at timestamp
on PollTemplate records are updated when polls are sent via the
active code path (PollingService + poll_handlers).

GitHub issue #37: Poll template send counters never increment.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.poll_response import PollTemplate
from src.services.polling_service import PollingService


@pytest.fixture
def polling_service():
    """Create a PollingService with templates loaded from YAML."""
    with patch.object(PollingService, "_load_templates"):
        service = PollingService()
        service.templates = [
            {
                "id": "emotion_current",
                "type": "emotion",
                "category": "personal",
                "question": "How are you feeling right now?",
                "options": ["Great", "Okay", "Bad"],
                "frequency": "high",
            }
        ]
        service.config = {}
    return service


class TestIncrementSendCount:
    """Verify times_sent counter increments when polls are sent."""

    @pytest.mark.asyncio
    async def test_increment_updates_existing_template(self, polling_service):
        """Sending a poll should increment times_sent on an existing DB record."""
        existing_template = MagicMock(spec=PollTemplate)
        existing_template.times_sent = 3
        existing_template.last_sent_at = datetime(2025, 1, 1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_template

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.services.polling_service.get_db_session", return_value=mock_ctx
        ):
            await polling_service.increment_send_count("How are you feeling right now?")

        assert existing_template.times_sent == 4
        assert existing_template.last_sent_at is not None
        assert existing_template.last_sent_at > datetime(2025, 1, 1)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_increment_creates_template_if_missing(self, polling_service):
        """If template doesn't exist in DB yet, create it with times_sent=1."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.services.polling_service.get_db_session", return_value=mock_ctx
        ):
            await polling_service.increment_send_count("How are you feeling right now?")

        # Should have called session.add with a new PollTemplate
        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, PollTemplate)
        assert added_obj.times_sent == 1
        assert added_obj.question == "How are you feeling right now?"
        assert added_obj.last_sent_at is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_increment_updates_last_sent_at(self, polling_service):
        """last_sent_at should be set to current time when poll is sent."""
        old_time = datetime(2024, 6, 15, 12, 0, 0)
        existing_template = MagicMock(spec=PollTemplate)
        existing_template.times_sent = 0
        existing_template.last_sent_at = old_time

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_template

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        before = datetime.utcnow()
        with patch(
            "src.services.polling_service.get_db_session", return_value=mock_ctx
        ):
            await polling_service.increment_send_count("How are you feeling right now?")
        after = datetime.utcnow()

        assert existing_template.last_sent_at >= before
        assert existing_template.last_sent_at <= after

    @pytest.mark.asyncio
    async def test_increment_populates_type_and_category_from_yaml(
        self, polling_service
    ):
        """When creating a new PollTemplate, populate type/category from YAML."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.services.polling_service.get_db_session", return_value=mock_ctx
        ):
            await polling_service.increment_send_count("How are you feeling right now?")

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.poll_type == "emotion"
        assert added_obj.poll_category == "personal"
        assert added_obj.options == ["Great", "Okay", "Bad"]

    @pytest.mark.asyncio
    async def test_increment_handles_db_error_gracefully(self, polling_service):
        """DB errors during increment should be caught, not crash the send."""
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB connection failed"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.services.polling_service.get_db_session", return_value=mock_ctx
        ):
            # Should not raise
            await polling_service.increment_send_count("How are you feeling right now?")

    @pytest.mark.asyncio
    async def test_increment_with_unknown_question_creates_minimal_template(
        self, polling_service
    ):
        """A question not in YAML should still create a DB record."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.services.polling_service.get_db_session", return_value=mock_ctx
        ):
            await polling_service.increment_send_count("Unknown question not in YAML?")

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.question == "Unknown question not in YAML?"
        assert added_obj.times_sent == 1
        assert added_obj.poll_type == "unknown"
        assert added_obj.options == []
