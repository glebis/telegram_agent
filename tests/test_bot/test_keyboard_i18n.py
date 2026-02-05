"""Tests for keyboard i18n -- inline button labels.

Verifies that keyboard utility methods produce correctly localized button
text for English, Russian, and the None/missing locale fallback path.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.i18n import load_translations, t

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_project_translations():
    """Ensure the real project locale files are loaded before each test."""
    load_translations()  # loads from locales/en.yaml + locales/ru.yaml
    yield


@pytest.fixture
def keyboard_utils():
    """Create a KeyboardUtils instance with mocked ModeManager."""
    with (
        patch("src.bot.keyboard_utils.ModeManager") as mock_mm_cls,
        patch("src.bot.keyboard_utils.get_callback_data_manager") as mock_cbm,
    ):
        mock_mm_instance = MagicMock()
        mock_mm_instance.get_mode_presets.side_effect = lambda mode: {
            "artistic": ["Critic", "Photo-coach", "Creative"],
            "formal": ["Structured", "Tags", "COCO"],
            "default": [],
        }.get(mode, [])
        mock_mm_cls.return_value = mock_mm_instance

        mock_cbm_instance = MagicMock()
        mock_cbm_instance.create_callback_data.side_effect = (
            lambda action, file_id, mode, preset=None: (
                f"{action}:{file_id[:8]}:{mode}:{preset or ''}"
            )
        )
        mock_cbm.return_value = mock_cbm_instance

        from src.bot.keyboard_utils import KeyboardUtils

        ku = KeyboardUtils()
        ku.mode_manager = mock_mm_instance
        ku.callback_manager = mock_cbm_instance
        return ku


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_button_texts(keyboard) -> list[str]:
    """Flatten inline keyboard into a list of button `.text` values."""
    return [btn.text for row in keyboard.inline_keyboard for btn in row]


# ===========================================================================
# 1-4. Direct t() calls for inline.claude.unlock
# ===========================================================================


class TestTranslateInlineKeys:
    """Verify t() returns correct labels for inline keyboard keys."""

    def test_unlock_english(self):
        assert t("inline.claude.unlock", "en") == "\U0001f513 Unlock"

    def test_unlock_russian(self):
        assert t("inline.claude.unlock", "ru") == "\U0001f513 Разблокировать"

    def test_unlock_none_locale_falls_back_to_english(self):
        result = t("inline.claude.unlock", None)
        assert result == "\U0001f513 Unlock"

    def test_unlock_no_locale_falls_back_to_english(self):
        result = t("inline.claude.unlock")
        assert result == "\U0001f513 Unlock"


# ===========================================================================
# 5-7. create_claude_action_keyboard locale behaviour
# ===========================================================================


class TestClaudeActionKeyboardI18n:
    """Verify create_claude_action_keyboard produces localized buttons."""

    def test_english_buttons(self, keyboard_utils):
        kb = keyboard_utils.create_claude_action_keyboard(
            has_active_session=False, locale="en"
        )
        texts = _all_button_texts(kb)
        # English labels from en.yaml inline.claude.*
        assert any("New Session" in t for t in texts)
        assert any("Sessions" in t for t in texts)

    def test_russian_buttons(self, keyboard_utils):
        kb = keyboard_utils.create_claude_action_keyboard(
            has_active_session=False, locale="ru"
        )
        texts = _all_button_texts(kb)
        assert any("Новая сессия" in t for t in texts)
        assert any("Сессии" in t for t in texts)

    def test_no_locale_falls_back_to_english(self, keyboard_utils):
        kb = keyboard_utils.create_claude_action_keyboard(has_active_session=False)
        texts = _all_button_texts(kb)
        # Without locale, should default to English
        assert any("New Session" in t for t in texts)
        assert any("Sessions" in t for t in texts)


# ===========================================================================
# 8-9. create_settings_keyboard locale behaviour
# ===========================================================================


class TestSettingsKeyboardI18n:
    """Verify create_settings_keyboard produces localized labels."""

    def test_settings_english(self, keyboard_utils):
        kb = keyboard_utils.create_settings_keyboard(
            keyboard_enabled=True,
            auto_forward_voice=True,
            locale="en",
        )
        texts = _all_button_texts(kb)
        assert any("Disable Keyboard" in t for t in texts)
        assert any("Voice" in t for t in texts)
        assert any("Customize Layout" in t for t in texts)
        assert any("Reset to Default" in t for t in texts)
        assert any("Back to Settings" in t for t in texts)

    def test_settings_russian(self, keyboard_utils):
        kb = keyboard_utils.create_settings_keyboard(
            keyboard_enabled=True,
            auto_forward_voice=True,
            locale="ru",
        )
        texts = _all_button_texts(kb)
        assert any("Выключить клавиатуру" in t for t in texts)
        assert any("Голос" in t for t in texts)
        assert any("Настроить раскладку" in t for t in texts)
        assert any("Сбросить настройки" in t for t in texts)
        assert any("К настройкам" in t for t in texts)


# ===========================================================================
# 10-11. Gallery keyboard with interpolation
# ===========================================================================


class TestGalleryKeyboardI18n:
    """Verify gallery keyboard interpolation for view_image and page_indicator."""

    @pytest.fixture
    def sample_images(self):
        return [
            {"id": 1, "file_path": "/img/1.jpg", "analysis": "a1"},
            {"id": 2, "file_path": "/img/2.jpg", "analysis": "a2"},
        ]

    def test_view_image_contains_number_english(self, keyboard_utils, sample_images):
        kb = keyboard_utils.create_gallery_navigation_keyboard(
            images=sample_images, page=1, total_pages=3, locale="en"
        )
        texts = _all_button_texts(kb)
        # "View Image 1" and "View Image 2" expected
        assert any("View Image 1" in t for t in texts)
        assert any("View Image 2" in t for t in texts)

    def test_view_image_contains_number_russian(self, keyboard_utils, sample_images):
        kb = keyboard_utils.create_gallery_navigation_keyboard(
            images=sample_images, page=1, total_pages=3, locale="ru"
        )
        texts = _all_button_texts(kb)
        # Russian: "Изображение 1" / "Изображение 2"
        assert any("1" in t and "\U0001f50d" in t for t in texts)
        assert any("2" in t and "\U0001f50d" in t for t in texts)

    def test_page_indicator_interpolation(self, keyboard_utils, sample_images):
        kb = keyboard_utils.create_gallery_navigation_keyboard(
            images=sample_images, page=2, total_pages=5, locale="en"
        )
        texts = _all_button_texts(kb)
        assert any("2/5" in t for t in texts)

    def test_page_indicator_interpolation_russian(self, keyboard_utils, sample_images):
        kb = keyboard_utils.create_gallery_navigation_keyboard(
            images=sample_images, page=3, total_pages=7, locale="ru"
        )
        texts = _all_button_texts(kb)
        assert any("3/7" in t for t in texts)


# ===========================================================================
# 12. create_claude_complete_keyboard -- retry/more/new in Russian
# ===========================================================================


class TestClaudeCompleteKeyboardI18n:
    """Verify create_claude_complete_keyboard buttons are localized."""

    def test_retry_more_new_russian(self, keyboard_utils):
        kb = keyboard_utils.create_claude_complete_keyboard(
            has_session=True, locale="ru"
        )
        texts = _all_button_texts(kb)
        assert any("Повторить" in t for t in texts)  # retry
        assert any("Ещё" in t for t in texts)  # more
        assert any("Новая" in t for t in texts)  # new

    def test_retry_more_new_english(self, keyboard_utils):
        kb = keyboard_utils.create_claude_complete_keyboard(
            has_session=True, locale="en"
        )
        texts = _all_button_texts(kb)
        assert any("Retry" in t for t in texts)
        assert any("More" in t for t in texts)
        assert any("New" in t for t in texts)


# ===========================================================================
# 13. Lock / unlock labels are localized
# ===========================================================================


class TestLockUnlockI18n:
    """Verify lock and unlock button labels are localized."""

    def test_lock_mode_english(self, keyboard_utils):
        kb = keyboard_utils.create_claude_complete_keyboard(
            is_locked=False, locale="en"
        )
        texts = _all_button_texts(kb)
        assert any("Lock Mode" in t for t in texts)

    def test_unlock_mode_english(self, keyboard_utils):
        kb = keyboard_utils.create_claude_complete_keyboard(is_locked=True, locale="en")
        texts = _all_button_texts(kb)
        assert any("Unlock Mode" in t for t in texts)

    def test_lock_mode_russian(self, keyboard_utils):
        kb = keyboard_utils.create_claude_complete_keyboard(
            is_locked=False, locale="ru"
        )
        texts = _all_button_texts(kb)
        assert any("Заблокировать" in t for t in texts)

    def test_unlock_mode_russian(self, keyboard_utils):
        kb = keyboard_utils.create_claude_complete_keyboard(is_locked=True, locale="ru")
        texts = _all_button_texts(kb)
        assert any("Разблокировать" in t for t in texts)

    def test_locked_keyboard_unlock_english(self, keyboard_utils):
        kb = keyboard_utils.create_claude_locked_keyboard(locale="en")
        texts = _all_button_texts(kb)
        assert any("Unlock" in t for t in texts)

    def test_locked_keyboard_unlock_russian(self, keyboard_utils):
        kb = keyboard_utils.create_claude_locked_keyboard(locale="ru")
        texts = _all_button_texts(kb)
        assert any("Разблокировать" in t for t in texts)
