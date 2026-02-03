"""
Tests for Poll Lifecycle Tracker.

Tests cover:
- State persistence (save/load from JSON)
- Poll recording (sent, answered, expired)
- Backpressure logic (consecutive misses)
- should_send() gating logic
- Unanswered count tracking
- Last sent time tracking
- Startup cleanup (get_expired_polls)
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.poll_lifecycle import (
    PollLifecycleTracker,
    DEFAULT_POLL_TTL_MINUTES,
    DEFAULT_MAX_UNANSWERED,
    DEFAULT_BACKPRESSURE_THRESHOLD,
)


@pytest.fixture
def temp_state_file(tmp_path):
    """Create a temporary state file for testing."""
    state_file = tmp_path / "poll_lifecycle_state.json"
    return state_file


@pytest.fixture
def tracker(temp_state_file):
    """Create a tracker with a temporary state file."""
    with patch('src.services.poll_lifecycle._STATE_FILE', temp_state_file):
        tracker = PollLifecycleTracker(
            ttl_minutes=45,
            max_unanswered=2,
            backpressure_threshold=2,
        )
        yield tracker


class TestPollLifecycleTracker:
    """Tests for PollLifecycleTracker class."""

    def test_initialization_defaults(self, tracker):
        """Test tracker initializes with correct defaults."""
        assert tracker.ttl_minutes == 45
        assert tracker.max_unanswered == 2
        assert tracker.backpressure_threshold == 2
        assert tracker._sent_polls == {}
        assert tracker._chat_state == {}

    def test_record_sent(self, tracker):
        """Test recording a sent poll."""
        poll_id = "test_poll_123"
        chat_id = 161427550
        message_id = 12345
        template_id = "emotion_current"
        question = "How are you feeling?"

        tracker.record_sent(poll_id, chat_id, message_id, template_id, question)

        # Check poll was recorded
        assert poll_id in tracker._sent_polls
        poll_info = tracker._sent_polls[poll_id]
        assert poll_info["chat_id"] == chat_id
        assert poll_info["message_id"] == message_id
        assert poll_info["template_id"] == template_id
        assert poll_info["question"] == question
        assert "sent_at" in poll_info
        assert "expires_at" in poll_info

        # Check chat state was updated
        chat_key = str(chat_id)
        assert chat_key in tracker._chat_state
        assert tracker._chat_state[chat_key]["last_sent_at"] is not None

    def test_record_sent_updates_last_sent_time(self, tracker):
        """Test that recording sent polls updates last_sent_at."""
        chat_id = 161427550

        # Send first poll
        tracker.record_sent("poll_1", chat_id, 1, "temp_1", "Q1")
        first_time = tracker._chat_state[str(chat_id)]["last_sent_at"]

        # Wait a tiny bit and send second poll
        import time
        time.sleep(0.01)

        tracker.record_sent("poll_2", chat_id, 2, "temp_2", "Q2")
        second_time = tracker._chat_state[str(chat_id)]["last_sent_at"]

        # Second time should be after first
        assert second_time > first_time

    def test_record_answered(self, tracker):
        """Test recording a poll answer resets backpressure."""
        chat_id = 161427550
        poll_id = "poll_123"

        # Send a poll
        tracker.record_sent(poll_id, chat_id, 1, "temp", "Q")

        # Set up some consecutive misses
        tracker._chat_state[str(chat_id)]["consecutive_misses"] = 2
        tracker._chat_state[str(chat_id)]["backpressure_active"] = True

        # Answer the poll
        tracker.record_answered(poll_id)

        # Check poll was removed
        assert poll_id not in tracker._sent_polls

        # Check backpressure was reset
        chat_state = tracker._chat_state[str(chat_id)]
        assert chat_state["consecutive_misses"] == 0
        assert chat_state["backpressure_active"] is False
        assert chat_state["last_answered_at"] is not None

    def test_record_expired(self, tracker):
        """Test recording a poll expiration increments consecutive misses."""
        chat_id = 161427550
        poll_id = "poll_123"

        # Send a poll
        tracker.record_sent(poll_id, chat_id, 1, "temp", "Q")

        # Expire it
        poll_info = tracker.record_expired(poll_id)

        # Check poll was removed and info returned
        assert poll_id not in tracker._sent_polls
        assert poll_info is not None
        assert poll_info["chat_id"] == chat_id

        # Check consecutive_misses incremented
        chat_state = tracker._chat_state[str(chat_id)]
        assert chat_state["consecutive_misses"] == 1
        assert chat_state["backpressure_active"] is False  # Not yet at threshold

    def test_backpressure_activates_after_threshold(self, tracker):
        """Test backpressure activates after consecutive misses reach threshold."""
        chat_id = 161427550

        # Send and expire 2 polls (threshold is 2)
        for i in range(2):
            poll_id = f"poll_{i}"
            tracker.record_sent(poll_id, chat_id, i, "temp", f"Q{i}")
            tracker.record_expired(poll_id)

        # Check backpressure is active
        chat_state = tracker._chat_state[str(chat_id)]
        assert chat_state["consecutive_misses"] == 2
        assert chat_state["backpressure_active"] is True

    def test_should_send_allows_when_ok(self, tracker):
        """Test should_send returns True when conditions are met."""
        chat_id = 161427550
        allowed, reason = tracker.should_send(chat_id)

        assert allowed is True
        assert reason == "ok"

    def test_should_send_blocks_when_backpressure_active(self, tracker):
        """Test should_send returns False when backpressure is active."""
        chat_id = 161427550

        # Activate backpressure
        tracker._chat_state[str(chat_id)] = {
            "consecutive_misses": 2,
            "backpressure_active": True,
        }

        allowed, reason = tracker.should_send(chat_id)

        assert allowed is False
        assert "backpressure active" in reason
        assert "2 consecutive misses" in reason

    def test_should_send_blocks_when_too_many_unanswered(self, tracker):
        """Test should_send returns False when too many unanswered polls."""
        chat_id = 161427550

        # Send max_unanswered polls (2)
        tracker.record_sent("poll_1", chat_id, 1, "temp", "Q1")
        tracker.record_sent("poll_2", chat_id, 2, "temp", "Q2")

        allowed, reason = tracker.should_send(chat_id)

        assert allowed is False
        assert "too many unanswered polls" in reason
        assert "(2/2)" in reason

    def test_get_unanswered_count(self, tracker):
        """Test getting unanswered count for a chat."""
        chat_id = 161427550
        other_chat_id = 999999

        # Send 2 polls to chat_id, 1 to other_chat_id
        tracker.record_sent("poll_1", chat_id, 1, "temp", "Q1")
        tracker.record_sent("poll_2", chat_id, 2, "temp", "Q2")
        tracker.record_sent("poll_3", other_chat_id, 3, "temp", "Q3")

        # Check counts
        assert tracker.get_unanswered_count(chat_id) == 2
        assert tracker.get_unanswered_count(other_chat_id) == 1

        # Answer one poll from chat_id
        tracker.record_answered("poll_1")

        # Count should decrease
        assert tracker.get_unanswered_count(chat_id) == 1

    def test_get_last_sent_time(self, tracker):
        """Test getting last sent time for a chat."""
        chat_id = 161427550

        # No polls sent yet
        assert tracker.get_last_sent_time(chat_id) is None

        # Send a poll
        tracker.record_sent("poll_1", chat_id, 1, "temp", "Q1")

        # Should return a datetime
        last_sent = tracker.get_last_sent_time(chat_id)
        assert last_sent is not None
        assert isinstance(last_sent, datetime)

        # Should be recent (within last minute)
        now = datetime.utcnow()
        assert (now - last_sent).total_seconds() < 60

    def test_get_expired_polls(self, tracker):
        """Test finding polls that expired during downtime."""
        chat_id = 161427550
        now = datetime.utcnow()

        # Create a poll that already expired
        old_poll_id = "old_poll"
        past_time = now - timedelta(hours=2)
        tracker._sent_polls[old_poll_id] = {
            "chat_id": chat_id,
            "message_id": 1,
            "template_id": "temp",
            "sent_at": past_time.isoformat(),
            "expires_at": (past_time + timedelta(minutes=45)).isoformat(),
            "question": "Old question",
        }

        # Create a poll that hasn't expired yet
        new_poll_id = "new_poll"
        tracker._sent_polls[new_poll_id] = {
            "chat_id": chat_id,
            "message_id": 2,
            "template_id": "temp",
            "sent_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=45)).isoformat(),
            "question": "New question",
        }

        # Get expired polls
        expired = tracker.get_expired_polls()

        # Should find only the old poll
        assert len(expired) == 1
        assert expired[0]["poll_id"] == old_poll_id

    def test_get_chat_state(self, tracker):
        """Test getting chat state."""
        chat_id = 161427550

        # Empty state for new chat
        state = tracker.get_chat_state(chat_id)
        assert state["consecutive_misses"] == 0
        assert state["backpressure_active"] is False

        # Send and expire some polls
        tracker.record_sent("poll_1", chat_id, 1, "temp", "Q1")
        tracker.record_expired("poll_1")

        # State should be updated
        state = tracker.get_chat_state(chat_id)
        assert state["consecutive_misses"] == 1

    def test_state_persistence(self, temp_state_file):
        """Test state is saved and loaded correctly."""
        # Create tracker and record some state
        with patch('src.services.poll_lifecycle._STATE_FILE', temp_state_file):
            tracker1 = PollLifecycleTracker()
            tracker1.record_sent("poll_1", 161427550, 1, "temp", "Q1")
            tracker1.record_sent("poll_2", 161427550, 2, "temp", "Q2")

        # Verify file was created
        assert temp_state_file.exists()
        data = json.loads(temp_state_file.read_text())
        assert "poll_1" in data["sent_polls"]
        assert "poll_2" in data["sent_polls"]

        # Create new tracker instance (should load from disk)
        with patch('src.services.poll_lifecycle._STATE_FILE', temp_state_file):
            tracker2 = PollLifecycleTracker()

        # State should be loaded
        assert "poll_1" in tracker2._sent_polls
        assert "poll_2" in tracker2._sent_polls
        assert tracker2.get_unanswered_count(161427550) == 2

    def test_state_file_missing_graceful_fallback(self, tmp_path):
        """Test tracker handles missing state file gracefully."""
        nonexistent_file = tmp_path / "does_not_exist.json"

        with patch('src.services.poll_lifecycle._STATE_FILE', nonexistent_file):
            tracker = PollLifecycleTracker()

        # Should initialize with empty state
        assert tracker._sent_polls == {}
        assert tracker._chat_state == {}

    def test_expiration_time_calculation(self, tracker):
        """Test that expiration time is calculated correctly."""
        poll_id = "poll_123"
        chat_id = 161427550

        before = datetime.utcnow()
        tracker.record_sent(poll_id, chat_id, 1, "temp", "Q")
        after = datetime.utcnow()

        poll_info = tracker._sent_polls[poll_id]
        sent_at = datetime.fromisoformat(poll_info["sent_at"])
        expires_at = datetime.fromisoformat(poll_info["expires_at"])

        # Check sent_at is between before and after
        assert before <= sent_at <= after

        # Check expires_at is TTL minutes after sent_at
        expected_delta = timedelta(minutes=tracker.ttl_minutes)
        actual_delta = expires_at - sent_at
        assert abs((actual_delta - expected_delta).total_seconds()) < 1

    def test_multiple_chats_independent(self, tracker):
        """Test that different chats have independent state."""
        chat_1 = 111111
        chat_2 = 222222

        # Send polls to different chats
        tracker.record_sent("poll_1", chat_1, 1, "temp", "Q1")
        tracker.record_sent("poll_2", chat_2, 2, "temp", "Q2")

        # Expire poll in chat_1
        tracker.record_expired("poll_1")

        # Chat_1 should have miss, chat_2 should not
        assert tracker.get_chat_state(chat_1)["consecutive_misses"] == 1
        assert tracker.get_chat_state(chat_2)["consecutive_misses"] == 0

    def test_answering_nonexistent_poll_graceful(self, tracker):
        """Test answering a poll that doesn't exist is handled gracefully."""
        # Should not crash
        tracker.record_answered("nonexistent_poll")

        # No state should be affected
        assert len(tracker._sent_polls) == 0

    def test_expiring_nonexistent_poll_returns_none(self, tracker):
        """Test expiring a poll that doesn't exist returns None."""
        result = tracker.record_expired("nonexistent_poll")
        assert result is None

    def test_backpressure_resets_on_any_answer(self, tracker):
        """Test that answering ANY poll resets backpressure, not just the latest."""
        chat_id = 161427550

        # Send 3 polls
        tracker.record_sent("poll_1", chat_id, 1, "temp", "Q1")
        tracker.record_sent("poll_2", chat_id, 2, "temp", "Q2")
        tracker.record_sent("poll_3", chat_id, 3, "temp", "Q3")

        # Activate backpressure manually
        tracker._chat_state[str(chat_id)]["consecutive_misses"] = 2
        tracker._chat_state[str(chat_id)]["backpressure_active"] = True

        # Answer the FIRST poll
        tracker.record_answered("poll_1")

        # Backpressure should be reset
        assert tracker._chat_state[str(chat_id)]["consecutive_misses"] == 0
        assert tracker._chat_state[str(chat_id)]["backpressure_active"] is False

    def test_custom_thresholds(self, temp_state_file):
        """Test tracker respects custom threshold values."""
        with patch('src.services.poll_lifecycle._STATE_FILE', temp_state_file):
            tracker = PollLifecycleTracker(
                ttl_minutes=60,
                max_unanswered=3,
                backpressure_threshold=5,
            )

        assert tracker.ttl_minutes == 60
        assert tracker.max_unanswered == 3
        assert tracker.backpressure_threshold == 5

        chat_id = 161427550

        # Send 3 polls (at custom max_unanswered)
        for i in range(3):
            tracker.record_sent(f"poll_{i}", chat_id, i, "temp", f"Q{i}")

        # Should still allow sending (not over limit yet)
        allowed, reason = tracker.should_send(chat_id)
        assert allowed is False  # 3/3 is at the limit
        assert "too many unanswered" in reason

        # Expire 4 polls (below backpressure_threshold of 5)
        for i in range(4):
            poll_id = f"poll_expire_{i}"
            tracker.record_sent(poll_id, chat_id, 100 + i, "temp", f"Q{i}")
            tracker.record_expired(poll_id)

        # Backpressure should NOT be active yet
        assert tracker._chat_state[str(chat_id)]["backpressure_active"] is False

        # Expire one more (5th miss, reaches threshold)
        tracker.record_sent("poll_5", chat_id, 200, "temp", "Q5")
        tracker.record_expired("poll_5")

        # Now backpressure should be active
        assert tracker._chat_state[str(chat_id)]["consecutive_misses"] == 5
        assert tracker._chat_state[str(chat_id)]["backpressure_active"] is True


class TestSingletonBehavior:
    """Test the singleton pattern for get_poll_lifecycle_tracker."""

    def test_singleton_returns_same_instance(self):
        """Test that get_poll_lifecycle_tracker returns the same instance."""
        from src.services.poll_lifecycle import get_poll_lifecycle_tracker, _tracker

        # Reset singleton
        import src.services.poll_lifecycle
        src.services.poll_lifecycle._tracker = None

        tracker1 = get_poll_lifecycle_tracker()
        tracker2 = get_poll_lifecycle_tracker()

        assert tracker1 is tracker2

    def test_singleton_loads_defaults_when_no_config(self):
        """Test that singleton loads defaults when config file is missing."""
        from src.services.poll_lifecycle import get_poll_lifecycle_tracker

        # Reset singleton
        import src.services.poll_lifecycle
        src.services.poll_lifecycle._tracker = None

        # Get tracker (will load from actual config or use defaults)
        tracker = get_poll_lifecycle_tracker()

        # Should have some config (either from file or defaults)
        assert tracker.ttl_minutes > 0
        assert tracker.max_unanswered > 0
        assert tracker.backpressure_threshold > 0
