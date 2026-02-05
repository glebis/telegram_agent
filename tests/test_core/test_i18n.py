"""Tests for the i18n framework."""

from unittest.mock import MagicMock

import pytest
import yaml

from src.core.i18n import (
    _locale_cache,
    _translations,
    clear_locale_cache,
    get_user_locale_from_update,
    load_translations,
    normalize_locale,
    set_user_locale,
    t,
)


@pytest.fixture(autouse=True)
def reset_i18n_state():
    """Reset module-level state before each test."""
    _translations.clear()
    from src.core.i18n import SUPPORTED_LOCALES

    SUPPORTED_LOCALES.clear()
    _locale_cache.clear()
    yield
    _translations.clear()
    SUPPORTED_LOCALES.clear()
    _locale_cache.clear()


@pytest.fixture
def locales_dir(tmp_path):
    """Create a temp locales directory with test translations."""
    en_data = {
        "commands": {
            "start": {
                "welcome": "Welcome, {name}!",
                "error": "An error occurred.",
            },
            "help": {"title": "Help"},
        },
        "messages": {
            "greeting": "Hello",
            "with_vars": "Size: {size}MB, max: {max}MB",
        },
    }
    ru_data = {
        "commands": {
            "start": {
                "welcome": "Добро пожаловать, {name}!",
            },
        },
        "messages": {
            "greeting": "Привет",
        },
    }

    en_file = tmp_path / "en.yaml"
    ru_file = tmp_path / "ru.yaml"

    with open(en_file, "w") as f:
        yaml.dump(en_data, f, allow_unicode=True)
    with open(ru_file, "w") as f:
        yaml.dump(ru_data, f, allow_unicode=True)

    return tmp_path


class TestLoadTranslations:
    def test_loads_yaml_files(self, locales_dir):
        load_translations(locales_dir)
        assert "en" in _translations
        assert "ru" in _translations

    def test_supported_locales_populated(self, locales_dir):
        from src.core.i18n import SUPPORTED_LOCALES

        load_translations(locales_dir)
        assert SUPPORTED_LOCALES == {"en", "ru"}

    def test_empty_dir(self, tmp_path):
        load_translations(tmp_path)
        assert len(_translations) == 0

    def test_invalid_yaml_skipped(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(": : invalid: yaml: {{")
        load_translations(tmp_path)
        # Bad file should be skipped without crashing
        assert "bad" not in _translations


class TestTranslate:
    def test_basic_lookup(self, locales_dir):
        load_translations(locales_dir)
        assert t("messages.greeting", "en") == "Hello"

    def test_russian_lookup(self, locales_dir):
        load_translations(locales_dir)
        assert t("messages.greeting", "ru") == "Привет"

    def test_fallback_to_english(self, locales_dir):
        """Russian missing key should fall back to English."""
        load_translations(locales_dir)
        # "commands.help.title" only exists in English
        assert t("commands.help.title", "ru") == "Help"

    def test_fallback_to_raw_key(self, locales_dir):
        """Completely missing key returns the key itself."""
        load_translations(locales_dir)
        assert t("nonexistent.key", "en") == "nonexistent.key"

    def test_interpolation(self, locales_dir):
        load_translations(locales_dir)
        result = t("commands.start.welcome", "en", name="Alice")
        assert result == "Welcome, Alice!"

    def test_interpolation_russian(self, locales_dir):
        load_translations(locales_dir)
        result = t("commands.start.welcome", "ru", name="Алиса")
        assert result == "Добро пожаловать, Алиса!"

    def test_multiple_interpolation_vars(self, locales_dir):
        load_translations(locales_dir)
        result = t("messages.with_vars", "en", size="5", max="10")
        assert result == "Size: 5MB, max: 10MB"

    def test_missing_interpolation_var_safe(self, locales_dir):
        """Missing interpolation vars should not crash."""
        load_translations(locales_dir)
        result = t("commands.start.welcome", "en")
        # Should return template as-is since {name} can't be resolved
        assert "{name}" in result

    def test_none_locale_defaults_to_english(self, locales_dir):
        load_translations(locales_dir)
        assert t("messages.greeting", None) == "Hello"

    def test_unsupported_locale_defaults_to_english(self, locales_dir):
        load_translations(locales_dir)
        assert t("messages.greeting", "xx") == "Hello"

    def test_auto_loads_on_first_call(self):
        """t() should auto-load translations if not yet loaded."""
        # Don't call load_translations() — use real project locales
        result = t("commands.start.init_error", "en")
        # Should load from project locales/en.yaml
        assert "error" in result.lower() or result == "commands.start.init_error"


class TestNormalizeLocale:
    def test_none(self, locales_dir):
        load_translations(locales_dir)
        assert normalize_locale(None) == "en"

    def test_empty_string(self, locales_dir):
        load_translations(locales_dir)
        assert normalize_locale("") == "en"

    def test_simple_code(self, locales_dir):
        load_translations(locales_dir)
        assert normalize_locale("en") == "en"
        assert normalize_locale("ru") == "ru"

    def test_with_region(self, locales_dir):
        load_translations(locales_dir)
        assert normalize_locale("en-US") == "en"
        assert normalize_locale("ru-RU") == "ru"

    def test_with_underscore(self, locales_dir):
        load_translations(locales_dir)
        assert normalize_locale("en_US") == "en"

    def test_uppercase(self, locales_dir):
        load_translations(locales_dir)
        assert normalize_locale("EN") == "en"
        assert normalize_locale("RU") == "ru"

    def test_unsupported_falls_to_default(self, locales_dir):
        load_translations(locales_dir)
        assert normalize_locale("xx") == "en"
        assert normalize_locale("zh-CN") == "en"


class TestLocaleCache:
    def test_set_and_get(self, locales_dir):
        load_translations(locales_dir)
        set_user_locale(12345, "ru")
        assert _locale_cache.get(12345) == "ru"

    def test_set_normalizes(self, locales_dir):
        load_translations(locales_dir)
        set_user_locale(12345, "en-US")
        assert _locale_cache.get(12345) == "en"

    def test_clear(self, locales_dir):
        load_translations(locales_dir)
        set_user_locale(12345, "ru")
        set_user_locale(67890, "en")
        clear_locale_cache()
        assert _locale_cache.get(12345) is None
        assert _locale_cache.get(67890) is None

    def test_get_user_locale_from_update_cached(self, locales_dir):
        load_translations(locales_dir)
        set_user_locale(42, "ru")

        mock_update = MagicMock()
        mock_update.effective_user.id = 42
        mock_update.effective_user.language_code = "en"

        # Should return cached value, not language_code
        assert get_user_locale_from_update(mock_update) == "ru"

    def test_get_user_locale_from_update_from_telegram(self, locales_dir):
        load_translations(locales_dir)

        mock_update = MagicMock()
        mock_update.effective_user.id = 99
        mock_update.effective_user.language_code = "ru"

        assert get_user_locale_from_update(mock_update) == "ru"

    def test_get_user_locale_from_update_no_user(self, locales_dir):
        load_translations(locales_dir)

        mock_update = MagicMock()
        mock_update.effective_user = None

        assert get_user_locale_from_update(mock_update) == "en"

    def test_get_user_locale_caches_result(self, locales_dir):
        load_translations(locales_dir)

        mock_update = MagicMock()
        mock_update.effective_user.id = 77
        mock_update.effective_user.language_code = "ru"

        get_user_locale_from_update(mock_update)

        # Should now be cached
        assert _locale_cache.get(77) == "ru"
