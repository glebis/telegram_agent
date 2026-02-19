"""Tests that poll_service emits PollAnswered after persisting a response."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.events import EventBus, PollAnswered
from src.services.poll_service import PollService


class TestPollServiceEmitsEvents:
    """Verify handle_poll_answer publishes PollAnswered on the EventBus."""

    def _make_service(self, event_bus: EventBus) -> PollService:
        """Create a PollService wired to the given EventBus."""
        svc = PollService.__new__(PollService)
        svc._embedding_provider = MagicMock()
        svc._embedding_provider.generate_embedding = AsyncMock(return_value=[0.1, 0.2])
        svc._poll_tracker = {}
        svc._event_bus = event_bus
        return svc

    def _seed_tracker(self, svc: PollService, poll_id: str = "poll1") -> None:
        """Add a tracked poll so handle_poll_answer can find it."""
        svc._poll_tracker[poll_id] = {
            "template_id": 1,
            "chat_id": 100,
            "sent_at": datetime(2026, 1, 15, 10, 0),
            "question": "How are you?",
            "options": ["Great", "OK", "Bad"],
            "poll_type": "emotion",
            "poll_category": "personal",
            "message_id": 555,
            "context_data": {},
        }

    def test_handle_poll_answer_emits_poll_answered(self):
        bus = EventBus()
        received = []

        async def capture(event):
            received.append(event)

        bus.subscribe(PollAnswered, capture)

        svc = self._make_service(bus)
        self._seed_tracker(svc)

        # Mock database session to avoid real DB
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # We need to make flush set response.id
        async def fake_flush():
            pass

        mock_session.flush = AsyncMock(side_effect=fake_flush)

        with patch(
            "src.services.poll_service.get_db_session",
            return_value=mock_session,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                svc.handle_poll_answer("poll1", user_id=42, selected_option_id=0)
            )

        assert result is True
        assert len(received) == 1
        event = received[0]
        assert isinstance(event, PollAnswered)
        assert event.poll_id == "poll1"
        assert event.chat_id == 100
        assert event.poll_type == "emotion"
        assert event.poll_category == "personal"
        assert event.selected_option_id == 0
        assert event.selected_option_text == "Great"
        assert event.question == "How are you?"

    def test_handle_poll_answer_no_event_on_untracked_poll(self):
        bus = EventBus()
        received = []

        async def capture(event):
            received.append(event)

        bus.subscribe(PollAnswered, capture)

        svc = self._make_service(bus)
        # Do NOT seed tracker -- poll is unknown

        # PollNotTracked is now raised instead of returning False
        from src.domain.errors import PollNotTracked

        try:
            asyncio.get_event_loop().run_until_complete(
                svc.handle_poll_answer("unknown_poll", user_id=42, selected_option_id=0)
            )
        except PollNotTracked:
            pass

        assert len(received) == 0

    def test_event_includes_mood_types(self):
        """Mood-type polls should still produce PollAnswered with correct type."""
        bus = EventBus()
        received = []

        async def capture(event):
            received.append(event)

        bus.subscribe(PollAnswered, capture)

        svc = self._make_service(bus)
        svc._poll_tracker["mood1"] = {
            "template_id": 2,
            "chat_id": 200,
            "sent_at": datetime(2026, 2, 1, 8, 0),
            "question": "Current mood?",
            "options": ["Energized", "Calm", "Tired", "Anxious"],
            "poll_type": "emotion",
            "poll_category": "health",
            "message_id": 999,
            "context_data": {},
        }

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        with patch(
            "src.services.poll_service.get_db_session",
            return_value=mock_session,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                svc.handle_poll_answer("mood1", user_id=42, selected_option_id=3)
            )

        assert result is True
        assert len(received) == 1
        assert received[0].poll_type == "emotion"
        assert received[0].selected_option_text == "Anxious"
