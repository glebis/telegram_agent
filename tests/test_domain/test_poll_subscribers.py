"""Tests for poll response processing subscriber."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from src.domain.events import EventBus, MoodCaptured, PollAnswered
from src.domain.subscribers import PollResponseProcessor


class TestPollResponseProcessor:
    """Verify subscriber flips processed_for flags on PollResponse rows."""

    def _make_event(self, **overrides) -> PollAnswered:
        defaults = dict(
            poll_id="p1",
            chat_id=100,
            poll_type="emotion",
            poll_category="personal",
            selected_option_id=0,
            selected_option_text="Happy",
            question="How are you?",
            response_id=7,
            timestamp=datetime(2026, 1, 15, 12, 0),
        )
        defaults.update(overrides)
        return PollAnswered(**defaults)

    # -- trails flag --------------------------------------------------------

    def test_sets_processed_for_trails(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        processor = PollResponseProcessor()
        event = self._make_event()

        with patch(
            "src.domain.subscribers.get_db_session",
            return_value=mock_session,
        ):
            asyncio.get_event_loop().run_until_complete(
                processor.on_poll_answered(event)
            )

        # Should have executed UPDATE setting processed_for_trails = 1
        calls = mock_session.execute.call_args_list
        sql_texts = [str(c[0][0]) for c in calls]
        assert any("processed_for_trails" in s for s in sql_texts)

    # -- todos flag ---------------------------------------------------------

    def test_sets_processed_for_todos(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        processor = PollResponseProcessor()
        event = self._make_event()

        with patch(
            "src.domain.subscribers.get_db_session",
            return_value=mock_session,
        ):
            asyncio.get_event_loop().run_until_complete(
                processor.on_poll_answered(event)
            )

        calls = mock_session.execute.call_args_list
        sql_texts = [str(c[0][0]) for c in calls]
        assert any("processed_for_todos" in s for s in sql_texts)

    # -- insights flag ------------------------------------------------------

    def test_sets_processed_for_insights(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        processor = PollResponseProcessor()
        event = self._make_event()

        with patch(
            "src.domain.subscribers.get_db_session",
            return_value=mock_session,
        ):
            asyncio.get_event_loop().run_until_complete(
                processor.on_poll_answered(event)
            )

        calls = mock_session.execute.call_args_list
        sql_texts = [str(c[0][0]) for c in calls]
        assert any("processed_for_insights" in s for s in sql_texts)

    # -- mood event ---------------------------------------------------------

    def test_emits_mood_captured_for_emotion_type(self):
        bus = EventBus()
        mood_events = []

        async def capture(ev):
            mood_events.append(ev)

        bus.subscribe(MoodCaptured, capture)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        processor = PollResponseProcessor(event_bus=bus)
        event = self._make_event(poll_type="emotion", selected_option_text="Joyful")

        with patch(
            "src.domain.subscribers.get_db_session",
            return_value=mock_session,
        ):
            asyncio.get_event_loop().run_until_complete(
                processor.on_poll_answered(event)
            )

        assert len(mood_events) == 1
        assert mood_events[0].mood_label == "Joyful"
        assert mood_events[0].poll_id == "p1"

    def test_no_mood_event_for_non_emotion_type(self):
        bus = EventBus()
        mood_events = []

        async def capture(ev):
            mood_events.append(ev)

        bus.subscribe(MoodCaptured, capture)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        processor = PollResponseProcessor(event_bus=bus)
        event = self._make_event(poll_type="energy")

        with patch(
            "src.domain.subscribers.get_db_session",
            return_value=mock_session,
        ):
            asyncio.get_event_loop().run_until_complete(
                processor.on_poll_answered(event)
            )

        assert len(mood_events) == 0

    # -- wiring with EventBus -----------------------------------------------

    def test_register_wires_handler_to_bus(self):
        bus = EventBus()
        processor = PollResponseProcessor(event_bus=bus)
        processor.register(bus)

        # After register, PollAnswered should have the handler
        assert len(bus._subscribers.get(PollAnswered, [])) == 1

    def test_end_to_end_bus_to_processor(self):
        """Publish PollAnswered on bus -> processor flips flags."""
        bus = EventBus()
        processor = PollResponseProcessor(event_bus=bus)
        processor.register(bus)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        event = self._make_event()

        with patch(
            "src.domain.subscribers.get_db_session",
            return_value=mock_session,
        ):
            asyncio.get_event_loop().run_until_complete(bus.publish(event))

        assert mock_session.execute.call_count >= 1
        assert mock_session.commit.call_count >= 1
