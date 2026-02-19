"""
Tests for AccountabilityDomainService — pure domain logic with no DB or TTS.

Covers:
- Streak calculation from check-in date lists
- Consecutive miss counting
- Struggle detection against threshold
- Message generation (check-in, celebration, struggle)
- Voice tag stripping
- Time-based greeting periods
- Enthusiasm-based celebration adjustments
"""

from datetime import datetime, timedelta

import pytest


class TestStreakCalculation:
    """Streak counting from a list of check-in dates."""

    def test_no_checkins_returns_zero(self):
        from src.services.accountability_domain import AccountabilityDomainService

        assert AccountabilityDomainService.calculate_streak([], datetime.now()) == 0

    def test_single_today_checkin(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        dates = [now.replace(hour=9)]
        assert AccountabilityDomainService.calculate_streak(dates, now) == 1

    def test_consecutive_days_streak(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        dates = [
            now - timedelta(days=2),
            now - timedelta(days=1),
            now,
        ]
        assert AccountabilityDomainService.calculate_streak(dates, now) == 3

    def test_gap_breaks_streak(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        # Checked in today and 3 days ago, but not yesterday
        dates = [
            now - timedelta(days=3),
            now,
        ]
        assert AccountabilityDomainService.calculate_streak(dates, now) == 1

    def test_no_checkin_today_zero_streak(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        # Last check-in was yesterday
        dates = [now - timedelta(days=1)]
        assert AccountabilityDomainService.calculate_streak(dates, now) == 0

    def test_multiple_checkins_same_day_count_once(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        dates = [
            now - timedelta(days=1, hours=2),
            now - timedelta(days=1, hours=5),
            now.replace(hour=8),
            now.replace(hour=12),
        ]
        assert AccountabilityDomainService.calculate_streak(dates, now) == 2

    def test_unsorted_dates_handled(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        # Dates not in order
        dates = [
            now,
            now - timedelta(days=2),
            now - timedelta(days=1),
        ]
        assert AccountabilityDomainService.calculate_streak(dates, now) == 3


class TestConsecutiveMisses:
    """Count consecutive days without check-ins."""

    def test_no_checkins_returns_zero(self):
        from src.services.accountability_domain import AccountabilityDomainService

        assert (
            AccountabilityDomainService.count_consecutive_misses(None, datetime.now())
            == 0
        )

    def test_checkin_today_zero_misses(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        last_checkin = now.replace(hour=9)
        assert (
            AccountabilityDomainService.count_consecutive_misses(last_checkin, now) == 0
        )

    def test_checkin_yesterday_one_miss(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        last_checkin = now - timedelta(days=1)
        assert (
            AccountabilityDomainService.count_consecutive_misses(last_checkin, now) == 1
        )

    def test_checkin_five_days_ago(self):
        from src.services.accountability_domain import AccountabilityDomainService

        now = datetime(2026, 2, 19, 14, 0)
        last_checkin = now - timedelta(days=5)
        assert (
            AccountabilityDomainService.count_consecutive_misses(last_checkin, now) == 5
        )


class TestStruggleDetection:
    """Detect struggles from miss counts vs threshold."""

    def test_no_struggles_under_threshold(self):
        from src.services.accountability_domain import AccountabilityDomainService

        # tracker_id -> miss_count, threshold = 3
        miss_counts = {1: 1, 2: 2, 3: 0}
        result = AccountabilityDomainService.detect_struggles(miss_counts, threshold=3)
        assert result == {}

    def test_struggles_at_threshold(self):
        from src.services.accountability_domain import AccountabilityDomainService

        miss_counts = {1: 3, 2: 5}
        result = AccountabilityDomainService.detect_struggles(miss_counts, threshold=3)
        assert result == {1: 3, 2: 5}

    def test_mixed_above_and_below(self):
        from src.services.accountability_domain import AccountabilityDomainService

        miss_counts = {1: 2, 2: 4, 3: 1, 4: 3}
        result = AccountabilityDomainService.detect_struggles(miss_counts, threshold=3)
        assert result == {2: 4, 4: 3}


class TestStripVoiceTags:
    """Test removal of voice/emotion markup."""

    def test_strip_bracket_tags(self):
        from src.services.accountability_domain import strip_voice_tags

        assert strip_voice_tags("[whisper]Hello[/whisper]") == "Hello"

    def test_strip_angle_tags(self):
        from src.services.accountability_domain import strip_voice_tags

        assert strip_voice_tags("<sigh>Oh well") == "Oh well"

    def test_strip_mixed_tags(self):
        from src.services.accountability_domain import strip_voice_tags

        result = strip_voice_tags("[cheerful]Great job!<chuckle>")
        assert result == "Great job!"

    def test_no_tags_unchanged(self):
        from src.services.accountability_domain import strip_voice_tags

        assert strip_voice_tags("Plain text here") == "Plain text here"


class TestTimeGreeting:
    """Test time-of-day greeting selection."""

    def test_morning_greeting(self):
        from src.services.accountability_domain import get_time_period

        assert get_time_period(datetime(2026, 2, 19, 8, 0)) == "morning"

    def test_afternoon_greeting(self):
        from src.services.accountability_domain import get_time_period

        assert get_time_period(datetime(2026, 2, 19, 14, 0)) == "afternoon"

    def test_evening_greeting(self):
        from src.services.accountability_domain import get_time_period

        assert get_time_period(datetime(2026, 2, 19, 19, 0)) == "evening"

    def test_night_greeting(self):
        from src.services.accountability_domain import get_time_period

        assert get_time_period(datetime(2026, 2, 19, 23, 0)) == "night"

    def test_boundary_5am_is_morning(self):
        from src.services.accountability_domain import get_time_period

        assert get_time_period(datetime(2026, 2, 19, 5, 0)) == "morning"

    def test_boundary_4am_is_night(self):
        from src.services.accountability_domain import get_time_period

        assert get_time_period(datetime(2026, 2, 19, 4, 0)) == "night"


class TestCelebrationEnthusiasm:
    """Test enthusiasm adjustment on celebration messages."""

    def test_quiet_removes_emoji_and_exclamation(self):
        from src.services.accountability_domain import AccountabilityDomainService

        msg = "🎉 7-day streak! Amazing!"
        result = AccountabilityDomainService.adjust_celebration_enthusiasm(msg, 0.5)
        assert "🎉" not in result
        assert "!" not in result

    def test_enthusiastic_adds_fire(self):
        from src.services.accountability_domain import AccountabilityDomainService

        msg = "7-day streak! Amazing!"
        result = AccountabilityDomainService.adjust_celebration_enthusiasm(msg, 1.5)
        assert result.endswith("🔥")

    def test_moderate_unchanged(self):
        from src.services.accountability_domain import AccountabilityDomainService

        msg = "7-day streak! Amazing!"
        result = AccountabilityDomainService.adjust_celebration_enthusiasm(msg, 1.0)
        assert result == msg

    def test_enthusiasm_mapping(self):
        from src.services.accountability_domain import AccountabilityDomainService

        assert AccountabilityDomainService.get_enthusiasm_value("quiet") == 0.5
        assert AccountabilityDomainService.get_enthusiasm_value("moderate") == 1.0
        assert AccountabilityDomainService.get_enthusiasm_value("enthusiastic") == 2.0
        assert AccountabilityDomainService.get_enthusiasm_value("unknown") == 1.0
