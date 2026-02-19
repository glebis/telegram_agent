"""
TrackerAggregate — aggregate root enforcing check-in invariants.

All mutations to a Tracker's check-in history should go through this aggregate
so that domain rules (one check-in per day, ownership, streak consistency) are
enforced in a single place.
"""

from datetime import date, datetime, timedelta, timezone
from typing import List

from .tracker import CheckIn, Tracker


class TrackerAggregate:
    """Aggregate root wrapping a Tracker and its CheckIns.

    Invariants enforced:
    - Every CheckIn must belong to the same tracker.
    - At most one check-in per calendar day.
    - Check-ins can only be created for the tracker's owner.
    """

    def __init__(self, tracker: Tracker, check_ins: List[CheckIn]) -> None:
        for ci in check_ins:
            if ci.tracker_id != tracker.id:
                raise ValueError(
                    f"CheckIn tracker_id={ci.tracker_id} does not match "
                    f"tracker id={tracker.id}"
                )
            if ci.user_id != tracker.user_id:
                raise ValueError(
                    f"CheckIn user_id={ci.user_id} does not match "
                    f"tracker user_id={tracker.user_id}"
                )
        self._tracker = tracker
        self._check_ins = list(check_ins)
        self._pending: List[CheckIn] = []

    # --- Read-only properties ---

    @property
    def tracker_id(self) -> int:
        return self._tracker.id

    @property
    def user_id(self) -> int:
        return self._tracker.user_id

    @property
    def name(self) -> str:
        return self._tracker.name

    @property
    def check_ins(self) -> List[CheckIn]:
        return list(self._check_ins)

    @property
    def pending_check_ins(self) -> List[CheckIn]:
        """Check-ins created via aggregate methods, not yet persisted."""
        return list(self._pending)

    # --- Commands ---

    def mark_completed(self, for_date: date) -> CheckIn:
        """Record a 'completed' check-in for the given date."""
        return self._add_checkin(for_date, status="completed")

    def skip(self, for_date: date) -> CheckIn:
        """Record a 'skipped' check-in for the given date."""
        return self._add_checkin(for_date, status="skipped")

    # --- Queries ---

    def compute_streak(self) -> int:
        """Count consecutive completed days backwards from today."""
        completed = [
            ci
            for ci in self._check_ins + self._pending
            if ci.status in ("completed", "partial")
        ]
        if not completed:
            return 0

        # Collect unique dates with completions
        completed_dates = {ci.created_at.date() for ci in completed}

        streak = 0
        current = datetime.now(timezone.utc).date()
        while current in completed_dates:
            streak += 1
            current -= timedelta(days=1)

        return streak

    def count_consecutive_misses(self) -> int:
        """Count days since last check-in. Only meaningful for daily trackers."""
        if self._tracker.check_frequency != "daily":
            return 0

        all_cis = self._check_ins + self._pending
        if not all_cis:
            return 0

        last_date = max(ci.created_at.date() for ci in all_cis)
        return max(0, (datetime.now(timezone.utc).date() - last_date).days)

    # --- Private helpers ---

    def _has_checkin_on(self, for_date: date) -> bool:
        """Return True if any check-in already exists for the given date."""
        return any(ci.created_at.date() == for_date for ci in self._check_ins)

    def _add_checkin(self, for_date: date, status: str) -> CheckIn:
        """Create a new CheckIn, enforce invariants, append to pending."""
        if self._has_checkin_on(for_date):
            raise ValueError(
                f"already have a check-in for {for_date} on tracker "
                f"{self._tracker.id}"
            )
        ci = CheckIn(
            tracker_id=self._tracker.id,
            user_id=self._tracker.user_id,
            status=status,
            notes=None,
        )
        ci.created_at = datetime(
            for_date.year, for_date.month, for_date.day, 12, 0, tzinfo=timezone.utc
        )
        self._check_ins.append(ci)
        self._pending.append(ci)
        return ci
