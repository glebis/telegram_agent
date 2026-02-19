"""
Pure domain logic for accountability partner.

No database, no TTS, no network I/O — only data transformations.
Extracted from AccountabilityService to separate concerns (issue #226).
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def strip_voice_tags(text: str) -> str:
    """Remove voice/emotion markup tags for clean text display."""
    text = re.sub(r"\[.*?\]", "", text)  # [whisper], [cheerful], etc.
    text = re.sub(r"<\w+>", "", text)  # <sigh>, <chuckle>, etc.
    return text.strip()


def get_time_period(now: datetime) -> str:
    """Return the time-of-day period for a given datetime."""
    hour = now.hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 22:
        return "evening"
    else:
        return "night"


class AccountabilityDomainService:
    """Pure domain logic for accountability tracking.

    All methods are static and accept plain data — no ORM objects required.
    """

    @staticmethod
    def calculate_streak(
        checkin_dates: List[datetime], now: datetime
    ) -> int:
        """Calculate current streak from a list of check-in timestamps.

        Args:
            checkin_dates: Datetimes of completed/partial check-ins (any order).
            now: Current datetime to measure from.

        Returns:
            Number of consecutive days with check-ins ending at today.
        """
        if not checkin_dates:
            return 0

        # Deduplicate to unique dates, sorted descending
        unique_dates = sorted(
            {d.date() for d in checkin_dates}, reverse=True
        )

        today = now.date()
        if unique_dates[0] != today:
            return 0

        streak = 0
        expected = today
        for d in unique_dates:
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif d < expected:
                break

        return streak

    @staticmethod
    def count_consecutive_misses(
        last_checkin: Optional[datetime], now: datetime
    ) -> int:
        """Count consecutive days without check-ins.

        Args:
            last_checkin: Datetime of most recent check-in, or None if never.
            now: Current datetime.

        Returns:
            Number of days since last check-in. 0 if never checked in or today.
        """
        if last_checkin is None:
            return 0

        days_since = (now - last_checkin).days
        return max(0, days_since)

    @staticmethod
    def detect_struggles(
        miss_counts: Dict[int, int], threshold: int
    ) -> Dict[int, int]:
        """Filter trackers that meet or exceed the struggle threshold.

        Args:
            miss_counts: Mapping of tracker_id -> consecutive miss count.
            threshold: Minimum misses to qualify as struggling.

        Returns:
            Subset of miss_counts where count >= threshold.
        """
        return {
            tracker_id: count
            for tracker_id, count in miss_counts.items()
            if count >= threshold
        }

    @staticmethod
    def adjust_celebration_enthusiasm(message: str, enthusiasm: float) -> str:
        """Adjust celebration message based on enthusiasm level.

        Args:
            message: Raw celebration message.
            enthusiasm: Float level (< 0.7 = quiet, > 1.3 = enthusiastic).

        Returns:
            Adjusted message.
        """
        if enthusiasm < 0.7:
            message = (
                message.replace("\U0001f389 ", "")
                .replace("!", ".")
                .replace("<laugh>", "")
                .replace("<chuckle>", "")
            )
        elif enthusiasm > 1.3:
            message = message + " \U0001f525"

        return message

    @staticmethod
    def get_enthusiasm_value(celebration_style: str) -> float:
        """Map celebration style name to enthusiasm float.

        Args:
            celebration_style: One of 'quiet', 'moderate', 'enthusiastic'.

        Returns:
            Float enthusiasm value.
        """
        mapping = {
            "quiet": 0.5,
            "moderate": 1.0,
            "enthusiastic": 2.0,
        }
        return mapping.get(celebration_style, 1.0)
