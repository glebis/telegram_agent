"""Tests for Life Weeks feature — domain logic and models.

TDD: RED → GREEN → REFACTOR for week calculation, models, and service.
"""

from datetime import date, datetime

import pytest


class TestLifeWeekCalculator:
    """Slice 1: Pure function — calculate life week number from birth date."""

    def test_born_today_is_week_zero(self):
        from src.services.life_weeks_domain import calculate_life_week

        today = date(2026, 2, 20)
        assert calculate_life_week(today, reference_date=today) == 0

    def test_born_6_days_ago_is_week_zero(self):
        from src.services.life_weeks_domain import calculate_life_week

        birth = date(2026, 2, 14)
        ref = date(2026, 2, 20)
        assert calculate_life_week(birth, reference_date=ref) == 0

    def test_born_7_days_ago_is_week_one(self):
        from src.services.life_weeks_domain import calculate_life_week

        birth = date(2026, 2, 13)
        ref = date(2026, 2, 20)
        assert calculate_life_week(birth, reference_date=ref) == 1

    def test_born_one_year_ago_is_about_52(self):
        from src.services.life_weeks_domain import calculate_life_week

        birth = date(2025, 2, 20)
        ref = date(2026, 2, 20)
        week = calculate_life_week(birth, reference_date=ref)
        assert 52 <= week <= 53

    def test_born_30_years_ago(self):
        from src.services.life_weeks_domain import calculate_life_week

        birth = date(1996, 2, 20)
        ref = date(2026, 2, 20)
        week = calculate_life_week(birth, reference_date=ref)
        assert 1560 <= week <= 1570  # ~30 * 52

    def test_none_birth_date_raises(self):
        from src.services.life_weeks_domain import calculate_life_week

        with pytest.raises((ValueError, TypeError)):
            calculate_life_week(None)

    def test_future_birth_date_raises(self):
        from src.services.life_weeks_domain import calculate_life_week

        with pytest.raises(ValueError):
            calculate_life_week(date(2030, 1, 1), reference_date=date(2026, 2, 20))

    def test_default_reference_is_today(self):
        from src.services.life_weeks_domain import calculate_life_week

        birth = date(2000, 1, 1)
        week = calculate_life_week(birth)
        assert week > 1300  # Born in 2000, currently 2026


class TestLifeWeekFormatting:
    """Slice 2: Format life week info for display."""

    def test_format_week_number(self):
        from src.services.life_weeks_domain import format_life_week

        result = format_life_week(1565, date(1996, 2, 20))
        assert "1565" in result or "1,565" in result

    def test_format_includes_age_context(self):
        from src.services.life_weeks_domain import format_life_week

        result = format_life_week(1565, date(1996, 2, 20))
        assert "30" in result or "year" in result.lower()

    def test_format_includes_percentage(self):
        from src.services.life_weeks_domain import format_life_week

        result = format_life_week(1565, date(1996, 2, 20))
        # Assuming ~80 year lifespan (4160 weeks)
        assert "%" in result


class TestLifeWeekConfig:
    """Slice 3: Configuration model for per-user Life Weeks settings."""

    def test_config_model_can_be_instantiated(self):
        from src.models.life_weeks import LifeWeekConfig

        config = LifeWeekConfig(
            user_id=123,
            birth_date=date(1990, 5, 15),
            notification_day=0,  # Monday
            notification_hour=9,
            enabled=True,
        )
        assert config.user_id == 123
        assert config.birth_date == date(1990, 5, 15)
        assert config.enabled is True

    def test_config_with_explicit_defaults(self):
        from src.models.life_weeks import LifeWeekConfig

        # ORM defaults only apply on flush; test explicit construction
        config = LifeWeekConfig(
            user_id=1,
            birth_date=date(1990, 1, 1),
            notification_day=0,
            notification_hour=9,
            enabled=True,
        )
        assert config.notification_day == 0
        assert config.notification_hour == 9
        assert config.enabled is True


class TestLifeWeekEntry:
    """Slice 4: Entry model for tracking weekly reflections."""

    def test_entry_model_can_be_instantiated(self):
        from src.models.life_weeks import LifeWeekEntry

        entry = LifeWeekEntry(
            user_id=123,
            week_number=1565,
            status="pending",
        )
        assert entry.user_id == 123
        assert entry.week_number == 1565
        assert entry.status == "pending"

    def test_entry_status_values(self):
        from src.models.life_weeks import LifeWeekEntry

        for status in ("pending", "completed", "skipped"):
            entry = LifeWeekEntry(user_id=1, week_number=1, status=status)
            assert entry.status == status

    def test_entry_can_have_reflection_text(self):
        from src.models.life_weeks import LifeWeekEntry

        entry = LifeWeekEntry(
            user_id=1,
            week_number=1565,
            status="completed",
            reflection="This week I learned...",
        )
        assert entry.reflection == "This week I learned..."


class TestShouldNotify:
    """Slice 5: Scheduler decision logic — should we notify today?"""

    def test_should_notify_on_correct_day_and_hour(self):
        from src.services.life_weeks_domain import should_notify

        # Monday at 9am, config says Monday at 9
        now = datetime(2026, 2, 16, 9, 0)  # Monday
        assert should_notify(notification_day=0, notification_hour=9, now=now) is True

    def test_should_not_notify_wrong_day(self):
        from src.services.life_weeks_domain import should_notify

        # Tuesday at 9am, config says Monday at 9
        now = datetime(2026, 2, 17, 9, 0)  # Tuesday
        assert should_notify(notification_day=0, notification_hour=9, now=now) is False

    def test_should_not_notify_wrong_hour(self):
        from src.services.life_weeks_domain import should_notify

        # Monday at 3pm, config says Monday at 9am
        now = datetime(2026, 2, 16, 15, 0)  # Monday 3pm
        assert should_notify(notification_day=0, notification_hour=9, now=now) is False

    def test_should_notify_within_hour_window(self):
        from src.services.life_weeks_domain import should_notify

        # Monday at 9:30, config says Monday at 9 — should still notify (same hour)
        now = datetime(2026, 2, 16, 9, 30)
        assert should_notify(notification_day=0, notification_hour=9, now=now) is True
