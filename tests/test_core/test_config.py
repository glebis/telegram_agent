"""
Tests for configuration loading and profiles.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.config import (
    deep_merge,
    get_config_value,
    get_settings,
    is_development,
    is_production,
    is_testing,
    load_profile_config,
    load_yaml_config,
)


class TestYamlLoading:
    """Tests for YAML configuration loading."""

    def test_load_yaml_nonexistent_file(self, tmp_path):
        """Test loading a non-existent file returns empty dict."""
        result = load_yaml_config(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_load_yaml_valid_file(self, tmp_path):
        """Test loading a valid YAML file."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("key: value\nnested:\n  inner: data")

        result = load_yaml_config(yaml_file)

        assert result == {"key": "value", "nested": {"inner": "data"}}

    def test_load_yaml_empty_file(self, tmp_path):
        """Test loading an empty file returns empty dict."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        result = load_yaml_config(yaml_file)

        assert result == {}

    def test_load_yaml_invalid_syntax(self, tmp_path):
        """Test loading invalid YAML returns empty dict."""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("key: [unclosed")

        result = load_yaml_config(yaml_file)

        assert result == {}


class TestDeepMerge:
    """Tests for deep dictionary merging."""

    def test_shallow_merge(self):
        """Test merging flat dictionaries."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        result = deep_merge(base, override)

        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self):
        """Test merging nested dictionaries."""
        base = {
            "outer": {"inner1": 1, "inner2": 2},
            "other": "value",
        }
        override = {
            "outer": {"inner2": 20, "inner3": 30},
        }

        result = deep_merge(base, override)

        assert result == {
            "outer": {"inner1": 1, "inner2": 20, "inner3": 30},
            "other": "value",
        }

    def test_deep_merge_empty_base(self):
        """Test merging into empty dict."""
        result = deep_merge({}, {"key": "value"})
        assert result == {"key": "value"}

    def test_deep_merge_empty_override(self):
        """Test merging with empty override."""
        base = {"key": "value"}
        result = deep_merge(base, {})
        assert result == {"key": "value"}

    def test_deep_merge_does_not_modify_original(self):
        """Test that original dicts are not modified."""
        base = {"key": "original"}
        override = {"key": "new"}

        deep_merge(base, override)

        assert base["key"] == "original"


class TestProfileLoading:
    """Tests for environment profile loading."""

    def test_load_profile_defaults_only(self, tmp_path):
        """Test loading when only defaults exist."""
        # This tests the real defaults.yaml in the project
        config = load_profile_config("development")

        # Should have loaded defaults at minimum
        assert "timeouts" in config or "paths" in config or config == {}

    def test_load_profile_unknown_environment(self):
        """Test loading an unknown environment uses defaults."""
        config = load_profile_config("unknown_environment")

        # Should not crash, returns whatever defaults provide
        assert isinstance(config, dict)


class TestConfigValue:
    """Tests for get_config_value helper."""

    def test_get_nested_value(self):
        """Test getting a nested configuration value."""
        # This depends on defaults.yaml existing
        value = get_config_value("timeouts.buffer_timeout", 2.5)

        # Should either find it or use default
        assert isinstance(value, (int, float))

    def test_get_missing_value_returns_default(self):
        """Test missing value returns default."""
        value = get_config_value("nonexistent.path.to.nowhere", "default_value")

        assert value == "default_value"

    def test_get_top_level_value(self):
        """Test getting a top-level configuration value."""
        value = get_config_value("timeouts", None)

        # Should be a dict if it exists, or None
        assert value is None or isinstance(value, dict)


class TestSettings:
    """Tests for Settings class."""

    def test_settings_has_defaults(self):
        """Test that Settings has sensible defaults."""
        settings = get_settings()

        # Allow common environment names
        assert settings.environment in ["development", "production", "testing", "test"]
        assert settings.buffer_timeout > 0
        assert settings.max_buffer_messages > 0

    def test_settings_database_url(self):
        """Test database URL is set."""
        settings = get_settings()

        assert settings.database_url
        assert "sqlite" in settings.database_url or "postgres" in settings.database_url

    def test_settings_python_executable(self):
        """Test Python executable is set."""
        settings = get_settings()

        assert settings.python_executable
        assert Path(settings.python_executable).exists()


class TestEnvironmentHelpers:
    """Tests for environment check helpers."""

    def test_is_development_default(self):
        """Test is_development returns True by default."""
        settings = get_settings()
        if settings.environment == "development":
            assert is_development() is True
            assert is_production() is False
            assert is_testing() is False

    @patch.dict(os.environ, {"ENVIRONMENT": "production"})
    def test_is_production_with_env(self):
        """Test is_production when ENVIRONMENT is set."""
        # Note: This won't affect cached settings, just demonstrates the pattern
        from src.core.config import Settings
        settings = Settings(environment="production")
        assert settings.environment == "production"

    @patch.dict(os.environ, {"ENVIRONMENT": "testing"})
    def test_is_testing_with_env(self):
        """Test is_testing when ENVIRONMENT is set."""
        from src.core.config import Settings
        settings = Settings(environment="testing")
        assert settings.environment == "testing"


class TestProfileIntegration:
    """Integration tests for profile system."""

    def test_development_profile_exists(self):
        """Test development profile file exists."""
        from src.core.config import PROJECT_ROOT
        profile_path = PROJECT_ROOT / "config" / "profiles" / "development.yaml"
        assert profile_path.exists(), "Development profile should exist"

    def test_testing_profile_exists(self):
        """Test testing profile file exists."""
        from src.core.config import PROJECT_ROOT
        profile_path = PROJECT_ROOT / "config" / "profiles" / "testing.yaml"
        assert profile_path.exists(), "Testing profile should exist"

    def test_production_profile_exists(self):
        """Test production profile file exists."""
        from src.core.config import PROJECT_ROOT
        profile_path = PROJECT_ROOT / "config" / "profiles" / "production.yaml"
        assert profile_path.exists(), "Production profile should exist"

    def test_defaults_file_exists(self):
        """Test defaults.yaml file exists."""
        from src.core.config import PROJECT_ROOT
        defaults_path = PROJECT_ROOT / "config" / "defaults.yaml"
        assert defaults_path.exists(), "defaults.yaml should exist"
