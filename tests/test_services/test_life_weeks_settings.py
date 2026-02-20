"""Tests for Life Weeks settings UI logic.

TDD: RED → GREEN → REFACTOR for settings keyboard, callback routing,
and configuration management.
"""

from datetime import date


class TestSettingsKeyboard:
    """Slice 1: Build inline keyboard for Life Weeks settings."""

    def test_build_keyboard_has_birth_date_button(self):
        from src.services.life_weeks_settings import build_settings_keyboard

        keyboard = build_settings_keyboard(
            birth_date=date(1996, 2, 20),
            notification_day=0,
            notification_hour=9,
            enabled=True,
        )
        # Should return list of button rows
        assert isinstance(keyboard, list)
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        assert any(
            "birth" in label.lower() or "дата" in label.lower() for label in flat_labels
        )

    def test_build_keyboard_has_notification_day_button(self):
        from src.services.life_weeks_settings import build_settings_keyboard

        keyboard = build_settings_keyboard(
            birth_date=date(1996, 2, 20),
            notification_day=0,
            notification_hour=9,
            enabled=True,
        )
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        assert any(
            "day" in label.lower() or "день" in label.lower() for label in flat_labels
        )

    def test_build_keyboard_has_enable_toggle(self):
        from src.services.life_weeks_settings import build_settings_keyboard

        keyboard = build_settings_keyboard(
            birth_date=date(1996, 2, 20),
            notification_day=0,
            notification_hour=9,
            enabled=True,
        )
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        assert any(
            "enable" in label.lower()
            or "disable" in label.lower()
            or "✅" in label
            or "❌" in label
            for label in flat_labels
        )

    def test_build_keyboard_shows_disabled_state(self):
        from src.services.life_weeks_settings import build_settings_keyboard

        keyboard = build_settings_keyboard(
            birth_date=None,
            notification_day=0,
            notification_hour=9,
            enabled=False,
        )
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        # When disabled, toggle should show "Enable" option
        assert any("enable" in label.lower() or "❌" in label for label in flat_labels)


class TestDaySelector:
    """Slice 2: Day-of-week selection for notifications."""

    def test_build_day_keyboard(self):
        from src.services.life_weeks_settings import build_day_keyboard

        keyboard = build_day_keyboard(current_day=0)
        assert isinstance(keyboard, list)
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        # Should have all 7 days
        assert len([l for l in flat_labels if l != "← Back"]) == 7

    def test_current_day_is_marked(self):
        from src.services.life_weeks_settings import build_day_keyboard

        keyboard = build_day_keyboard(current_day=0)  # Monday
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        # Monday should be marked
        monday_labels = [
            l for l in flat_labels if "mon" in l.lower() or "пн" in l.lower()
        ]
        assert any("✓" in l or "✅" in l for l in monday_labels)


class TestHourSelector:
    """Slice 3: Hour selection for notifications."""

    def test_build_hour_keyboard(self):
        from src.services.life_weeks_settings import build_hour_keyboard

        keyboard = build_hour_keyboard(current_hour=9)
        assert isinstance(keyboard, list)
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        # Should have reasonable hour options (not all 24)
        non_back = [l for l in flat_labels if l != "← Back"]
        assert len(non_back) >= 6  # At least morning through evening

    def test_current_hour_is_marked(self):
        from src.services.life_weeks_settings import build_hour_keyboard

        keyboard = build_hour_keyboard(current_hour=9)
        flat_labels = [btn["text"] for row in keyboard for btn in row]
        marked = [l for l in flat_labels if "✓" in l or "✅" in l]
        assert len(marked) >= 1  # Current hour should be marked


class TestSettingsMessage:
    """Slice 4: Format the settings status message."""

    def test_format_settings_configured(self):
        from src.services.life_weeks_settings import format_settings_message

        msg = format_settings_message(
            birth_date=date(1996, 2, 20),
            notification_day=0,
            notification_hour=9,
            enabled=True,
            current_week=1565,
        )
        assert "1565" in msg or "1,565" in msg
        assert "Monday" in msg or "Mon" in msg
        assert "9" in msg

    def test_format_settings_not_configured(self):
        from src.services.life_weeks_settings import format_settings_message

        msg = format_settings_message(
            birth_date=None,
            notification_day=0,
            notification_hour=9,
            enabled=False,
            current_week=None,
        )
        assert "not configured" in msg.lower() or "set" in msg.lower()
