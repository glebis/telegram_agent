"""
Tests that poll_service raises typed domain errors
instead of silently returning None/False.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.errors import EmbeddingFailure, PollNotTracked, PollSendFailure

# ---------------------------------------------------------------------------
# send_poll
# ---------------------------------------------------------------------------


class TestSendPollErrors:
    """send_poll must raise PollSendFailure, not return None."""

    @pytest.mark.asyncio
    async def test_raises_poll_send_failure_on_telegram_error(self):
        """When poll_sender.send_poll raises, wrap in PollSendFailure."""
        mock_embedding = MagicMock()
        mock_event_bus = MagicMock()

        from src.services.poll_service import PollService

        service = PollService(
            embedding_provider=mock_embedding,
            event_bus=mock_event_bus,
        )

        poll_sender = MagicMock()
        poll_sender.send_poll = AsyncMock(side_effect=RuntimeError("Telegram 429"))

        template = MagicMock()
        template.question = "How are you?"
        template.options = ["Good", "Bad"]

        with pytest.raises(PollSendFailure) as exc_info:
            await service.send_poll(
                poll_sender=poll_sender, chat_id=123, template=template
            )
        assert "429" in str(exc_info.value)


# ---------------------------------------------------------------------------
# handle_poll_answer
# ---------------------------------------------------------------------------


class TestHandlePollAnswerErrors:
    """handle_poll_answer must raise typed errors, not return False."""

    @pytest.mark.asyncio
    async def test_raises_poll_not_tracked(self):
        """Unknown poll_id raises PollNotTracked."""
        mock_embedding = MagicMock()
        mock_event_bus = MagicMock()

        from src.services.poll_service import PollService

        service = PollService(
            embedding_provider=mock_embedding,
            event_bus=mock_event_bus,
        )
        # _poll_tracker is empty, so any poll_id is untracked

        with pytest.raises(PollNotTracked) as exc_info:
            await service.handle_poll_answer(
                poll_id="unknown_id", user_id=1, selected_option_id=0
            )
        assert exc_info.value.poll_id == "unknown_id"

    @pytest.mark.asyncio
    async def test_raises_embedding_failure(self):
        """When embedding generation fails, raise EmbeddingFailure."""
        mock_embedding = MagicMock()
        mock_embedding.generate_embedding = AsyncMock(
            side_effect=RuntimeError("model not loaded")
        )
        mock_event_bus = MagicMock()

        from src.services.poll_service import PollService

        service = PollService(
            embedding_provider=mock_embedding,
            event_bus=mock_event_bus,
        )
        # Seed the tracker with a known poll
        service._poll_tracker["poll_123"] = {
            "template_id": 1,
            "chat_id": 100,
            "sent_at": MagicMock(),
            "question": "How do you feel?",
            "options": ["Great", "OK", "Bad"],
            "poll_type": "emotion",
            "poll_category": "personal",
            "message_id": 42,
            "context_data": {},
        }

        with pytest.raises(EmbeddingFailure) as exc_info:
            await service.handle_poll_answer(
                poll_id="poll_123", user_id=1, selected_option_id=0
            )
        assert "model not loaded" in str(exc_info.value)
