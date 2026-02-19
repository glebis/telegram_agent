"""Tests for domain events and EventBus."""

import asyncio
from datetime import datetime

from src.domain.events import EventBus, MoodCaptured, PollAnswered


class TestPollAnsweredEvent:
    """PollAnswered event dataclass tests."""

    def test_create_poll_answered(self):
        event = PollAnswered(
            poll_id="abc123",
            chat_id=42,
            poll_type="emotion",
            poll_category="personal",
            selected_option_id=2,
            selected_option_text="Happy",
            question="How do you feel?",
            response_id=7,
            timestamp=datetime(2026, 1, 1, 12, 0),
        )
        assert event.poll_id == "abc123"
        assert event.chat_id == 42
        assert event.poll_type == "emotion"
        assert event.poll_category == "personal"
        assert event.selected_option_id == 2
        assert event.selected_option_text == "Happy"
        assert event.question == "How do you feel?"
        assert event.response_id == 7
        assert event.timestamp == datetime(2026, 1, 1, 12, 0)

    def test_poll_answered_defaults_timestamp(self):
        before = datetime.utcnow()
        event = PollAnswered(
            poll_id="x",
            chat_id=1,
            poll_type="energy",
            poll_category=None,
            selected_option_id=0,
            selected_option_text="Low",
            question="Energy?",
            response_id=1,
        )
        after = datetime.utcnow()
        assert before <= event.timestamp <= after


class TestMoodCapturedEvent:
    """MoodCaptured event dataclass tests."""

    def test_create_mood_captured(self):
        event = MoodCaptured(
            poll_id="m1",
            chat_id=42,
            mood_label="Happy",
            poll_type="emotion",
            response_id=5,
            timestamp=datetime(2026, 2, 1),
        )
        assert event.poll_id == "m1"
        assert event.chat_id == 42
        assert event.mood_label == "Happy"
        assert event.poll_type == "emotion"
        assert event.response_id == 5

    def test_mood_captured_defaults_timestamp(self):
        before = datetime.utcnow()
        event = MoodCaptured(
            poll_id="m2",
            chat_id=1,
            mood_label="Sad",
            poll_type="emotion",
            response_id=2,
        )
        after = datetime.utcnow()
        assert before <= event.timestamp <= after


class TestEventBus:
    """EventBus subscribe/publish tests."""

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(PollAnswered, handler)

        event = PollAnswered(
            poll_id="p1",
            chat_id=1,
            poll_type="emotion",
            poll_category=None,
            selected_option_id=0,
            selected_option_text="Good",
            question="Mood?",
            response_id=1,
        )
        asyncio.get_event_loop().run_until_complete(bus.publish(event))
        assert len(received) == 1
        assert received[0] is event

    def test_publish_no_subscribers(self):
        bus = EventBus()
        event = PollAnswered(
            poll_id="p2",
            chat_id=1,
            poll_type="energy",
            poll_category=None,
            selected_option_id=0,
            selected_option_text="Low",
            question="Energy?",
            response_id=1,
        )
        # Should not raise
        asyncio.get_event_loop().run_until_complete(bus.publish(event))

    def test_multiple_subscribers(self):
        bus = EventBus()
        calls_a = []
        calls_b = []

        async def handler_a(event):
            calls_a.append(event)

        async def handler_b(event):
            calls_b.append(event)

        bus.subscribe(PollAnswered, handler_a)
        bus.subscribe(PollAnswered, handler_b)

        event = PollAnswered(
            poll_id="p3",
            chat_id=1,
            poll_type="emotion",
            poll_category=None,
            selected_option_id=0,
            selected_option_text="OK",
            question="How?",
            response_id=1,
        )
        asyncio.get_event_loop().run_until_complete(bus.publish(event))
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_different_event_types_isolated(self):
        bus = EventBus()
        poll_calls = []
        mood_calls = []

        async def poll_handler(event):
            poll_calls.append(event)

        async def mood_handler(event):
            mood_calls.append(event)

        bus.subscribe(PollAnswered, poll_handler)
        bus.subscribe(MoodCaptured, mood_handler)

        mood_event = MoodCaptured(
            poll_id="m1",
            chat_id=1,
            mood_label="Great",
            poll_type="emotion",
            response_id=1,
        )
        asyncio.get_event_loop().run_until_complete(bus.publish(mood_event))

        assert len(poll_calls) == 0
        assert len(mood_calls) == 1

    def test_subscriber_error_does_not_block_others(self):
        bus = EventBus()
        calls = []

        async def bad_handler(event):
            raise ValueError("boom")

        async def good_handler(event):
            calls.append(event)

        bus.subscribe(PollAnswered, bad_handler)
        bus.subscribe(PollAnswered, good_handler)

        event = PollAnswered(
            poll_id="p4",
            chat_id=1,
            poll_type="emotion",
            poll_category=None,
            selected_option_id=0,
            selected_option_text="Fine",
            question="Feel?",
            response_id=1,
        )
        asyncio.get_event_loop().run_until_complete(bus.publish(event))
        assert len(calls) == 1

    def test_get_event_bus_singleton(self):
        from src.domain.events import get_event_bus

        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_event_bus(self):
        from src.domain.events import get_event_bus, reset_event_bus

        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2
