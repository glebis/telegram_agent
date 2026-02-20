"""
Tests for TrackerAggregate — domain aggregate root enforcing check-in invariants.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.models.tracker import CheckIn, Tracker
from src.models.tracker_aggregate import TrackerAggregate


def _make_tracker(user_id: int = 100, tracker_id: int = 1, **kwargs) -> Tracker:
    """Create a detached Tracker instance for unit tests (no DB)."""
    t = Tracker(
        user_id=user_id,
        type=kwargs.get("type", "habit"),
        name=kwargs.get("name", "Exercise"),
        description=kwargs.get("description", None),
        check_frequency=kwargs.get("check_frequency", "daily"),
        check_time=kwargs.get("check_time", None),
        active=kwargs.get("active", True),
    )
    # Set id directly via SA internals (not auto-incremented outside DB)
    t.id = tracker_id
    return t


def _make_checkin(
    tracker_id: int = 1,
    user_id: int = 100,
    status: str = "completed",
    created_at: datetime | None = None,
) -> CheckIn:
    """Create a detached CheckIn instance for unit tests (no DB)."""
    ci = CheckIn(
        tracker_id=tracker_id,
        user_id=user_id,
        status=status,
        notes=None,
    )
    ci.id = None
    ci.created_at = created_at or datetime.now(timezone.utc)
    return ci


class TestTrackerAggregateCreation:
    """Test aggregate construction and basic properties."""

    def test_create_aggregate_from_tracker(self):
        tracker = _make_tracker(user_id=42, tracker_id=7)
        agg = TrackerAggregate(tracker=tracker, check_ins=[])

        assert agg.tracker_id == 7
        assert agg.user_id == 42
        assert agg.name == "Exercise"

    def test_aggregate_exposes_check_ins(self):
        tracker = _make_tracker()
        ci = _make_checkin()
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        assert len(agg.check_ins) == 1

    def test_aggregate_rejects_mismatched_checkin_tracker_id(self):
        tracker = _make_tracker(tracker_id=1)
        bad_ci = _make_checkin(tracker_id=999)

        with pytest.raises(ValueError, match="tracker"):
            TrackerAggregate(tracker=tracker, check_ins=[bad_ci])


class TestMarkCompleted:
    """Test mark_completed — records a 'completed' check-in for a date."""

    def test_mark_completed_creates_checkin(self):
        tracker = _make_tracker(user_id=100, tracker_id=1)
        agg = TrackerAggregate(tracker=tracker, check_ins=[])
        today = datetime.now(timezone.utc).date()

        new_ci = agg.mark_completed(today)

        assert new_ci.status == "completed"
        assert new_ci.tracker_id == 1
        assert new_ci.user_id == 100
        assert len(agg.pending_check_ins) == 1

    def test_mark_completed_for_past_date(self):
        tracker = _make_tracker()
        agg = TrackerAggregate(tracker=tracker, check_ins=[])
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)

        new_ci = agg.mark_completed(yesterday)

        assert new_ci.created_at.date() == yesterday


class TestSkip:
    """Test skip — records a 'skipped' check-in for a date."""

    def test_skip_creates_skipped_checkin(self):
        tracker = _make_tracker(user_id=100, tracker_id=1)
        agg = TrackerAggregate(tracker=tracker, check_ins=[])
        today = datetime.now(timezone.utc).date()

        new_ci = agg.skip(today)

        assert new_ci.status == "skipped"
        assert new_ci.tracker_id == 1
        assert new_ci.user_id == 100
        assert len(agg.pending_check_ins) == 1


class TestComputeStreak:
    """Test compute_streak — counts consecutive completed days backwards from today."""

    def test_streak_zero_when_no_checkins(self):
        tracker = _make_tracker()
        agg = TrackerAggregate(tracker=tracker, check_ins=[])

        assert agg.compute_streak() == 0

    def test_streak_one_for_today_only(self):
        tracker = _make_tracker()
        ci = _make_checkin(
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        assert agg.compute_streak() == 1

    def test_streak_counts_consecutive_days(self):
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        check_ins = []
        for days_ago in range(5):
            d = today - timedelta(days=days_ago)
            ci = _make_checkin(
                status="completed",
                created_at=datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc),
            )
            check_ins.append(ci)

        agg = TrackerAggregate(tracker=tracker, check_ins=check_ins)
        assert agg.compute_streak() == 5

    def test_streak_breaks_on_gap(self):
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        # Today and yesterday, but NOT day-before-yesterday
        check_ins = [
            _make_checkin(
                status="completed",
                created_at=datetime(
                    today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc
                ),
            ),
            _make_checkin(
                status="completed",
                created_at=datetime(
                    (today - timedelta(days=1)).year,
                    (today - timedelta(days=1)).month,
                    (today - timedelta(days=1)).day,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
            # Gap: day -2 missing
            _make_checkin(
                status="completed",
                created_at=datetime(
                    (today - timedelta(days=3)).year,
                    (today - timedelta(days=3)).month,
                    (today - timedelta(days=3)).day,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
        ]
        agg = TrackerAggregate(tracker=tracker, check_ins=check_ins)
        assert agg.compute_streak() == 2

    def test_streak_ignores_skipped(self):
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        ci = _make_checkin(
            status="skipped",
            created_at=datetime(
                today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        assert agg.compute_streak() == 0

    def test_streak_zero_if_no_checkin_today(self):
        """If the most recent check-in is yesterday, streak should still count
        backwards from today — so a gap today means 0."""
        tracker = _make_tracker()
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        ci = _make_checkin(
            status="completed",
            created_at=datetime(
                yesterday.year,
                yesterday.month,
                yesterday.day,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        # No check-in today means streak is broken
        assert agg.compute_streak() == 0


class TestDuplicateCheckInGuard:
    """Enforce: at most one check-in per calendar day per tracker."""

    def test_mark_completed_twice_same_day_raises(self):
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        existing = _make_checkin(
            status="completed",
            created_at=datetime(
                today.year, today.month, today.day, 8, 0, tzinfo=timezone.utc
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[existing])

        with pytest.raises(ValueError, match="already.*check.?in"):
            agg.mark_completed(today)

    def test_skip_twice_same_day_raises(self):
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        existing = _make_checkin(
            status="skipped",
            created_at=datetime(
                today.year, today.month, today.day, 8, 0, tzinfo=timezone.utc
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[existing])

        with pytest.raises(ValueError, match="already.*check.?in"):
            agg.skip(today)

    def test_mark_completed_after_skip_same_day_raises(self):
        """Can't complete on a day already skipped."""
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        existing = _make_checkin(
            status="skipped",
            created_at=datetime(
                today.year, today.month, today.day, 8, 0, tzinfo=timezone.utc
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[existing])

        with pytest.raises(ValueError, match="already.*check.?in"):
            agg.mark_completed(today)

    def test_different_days_allowed(self):
        """Two check-ins on different days should be fine."""
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        existing = _make_checkin(
            status="completed",
            created_at=datetime(
                yesterday.year,
                yesterday.month,
                yesterday.day,
                8,
                0,
                tzinfo=timezone.utc,
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[existing])

        ci = agg.mark_completed(today)
        assert ci.status == "completed"

    def test_pending_checkin_also_blocks_duplicate(self):
        """After mark_completed via aggregate, a second call same day should raise."""
        tracker = _make_tracker()
        agg = TrackerAggregate(tracker=tracker, check_ins=[])
        today = datetime.now(timezone.utc).date()

        agg.mark_completed(today)

        with pytest.raises(ValueError, match="already.*check.?in"):
            agg.mark_completed(today)


class TestOwnershipGuard:
    """Enforce: check-in user_id must match tracker.user_id at construction."""

    def test_rejects_checkin_with_wrong_user_id(self):
        tracker = _make_tracker(user_id=100)
        bad_ci = _make_checkin(user_id=999, tracker_id=1)

        with pytest.raises(ValueError, match="user"):
            TrackerAggregate(tracker=tracker, check_ins=[bad_ci])

    def test_accepts_checkin_with_matching_user_id(self):
        tracker = _make_tracker(user_id=100)
        ci = _make_checkin(user_id=100, tracker_id=1)

        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])
        assert len(agg.check_ins) == 1


class TestCountConsecutiveMisses:
    """Test count_consecutive_misses — days since last check-in."""

    def test_zero_when_no_checkins(self):
        tracker = _make_tracker()
        agg = TrackerAggregate(tracker=tracker, check_ins=[])

        assert agg.count_consecutive_misses() == 0

    def test_zero_when_checked_in_today(self):
        tracker = _make_tracker()
        today = datetime.now(timezone.utc).date()
        ci = _make_checkin(
            status="completed",
            created_at=datetime(
                today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        assert agg.count_consecutive_misses() == 0

    def test_one_when_last_checkin_yesterday(self):
        tracker = _make_tracker()
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        ci = _make_checkin(
            status="completed",
            created_at=datetime(
                yesterday.year,
                yesterday.month,
                yesterday.day,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        assert agg.count_consecutive_misses() == 1

    def test_three_when_last_checkin_three_days_ago(self):
        tracker = _make_tracker()
        three_ago = datetime.now(timezone.utc).date() - timedelta(days=3)
        ci = _make_checkin(
            status="completed",
            created_at=datetime(
                three_ago.year,
                three_ago.month,
                three_ago.day,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        assert agg.count_consecutive_misses() == 3

    def test_only_counts_daily_frequency(self):
        """Non-daily trackers always return 0 misses."""
        tracker = _make_tracker(check_frequency="weekly")
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        ci = _make_checkin(
            status="completed",
            created_at=datetime(
                yesterday.year,
                yesterday.month,
                yesterday.day,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )
        agg = TrackerAggregate(tracker=tracker, check_ins=[ci])

        assert agg.count_consecutive_misses() == 0
