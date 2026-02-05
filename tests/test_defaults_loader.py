"""
Tests for the defaults loader configuration system.

Tests cover:
- YAML file loading
- Deep merge functionality
- Path expansion
- Nested value access
- Convenience functions
- Caching behavior
"""

import os

import yaml

from src.core.defaults_loader import (
    clear_cache,
    deep_merge,
    expand_path,
    get_api_url,
    get_config_value,
    get_limit,
    get_message,
    get_model,
    get_nested,
    get_path,
    get_reaction,
    get_timeout,
    load_defaults,
    load_yaml_file,
)


class TestLoadYamlFile:
    """Tests for load_yaml_file function."""

    def test_load_valid_yaml(self, tmp_path):
        """Test loading a valid YAML file."""
        yaml_content = {"key": "value", "nested": {"inner": 123}}
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        result = load_yaml_file(yaml_file)

        assert result == yaml_content

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading a file that doesn't exist."""
        result = load_yaml_file(tmp_path / "nonexistent.yaml")

        assert result == {}

    def test_load_empty_file(self, tmp_path):
        """Test loading an empty YAML file."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        result = load_yaml_file(yaml_file)

        assert result == {}

    def test_load_yaml_with_lists(self, tmp_path):
        """Test loading YAML with list values."""
        yaml_content = {"items": ["a", "b", "c"], "count": 3}
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        result = load_yaml_file(yaml_file)

        assert result["items"] == ["a", "b", "c"]
        assert result["count"] == 3


class TestDeepMerge:
    """Tests for deep_merge function."""

    def test_simple_merge(self):
        """Test merging flat dictionaries."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}

        result = deep_merge(base, override)

        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Test merging nested dictionaries."""
        base = {"outer": {"a": 1, "b": 2}}
        override = {"outer": {"b": 3, "c": 4}}

        result = deep_merge(base, override)

        assert result == {"outer": {"a": 1, "b": 3, "c": 4}}

    def test_deep_nested_merge(self):
        """Test merging deeply nested dictionaries."""
        base = {"l1": {"l2": {"l3": {"a": 1}}}}
        override = {"l1": {"l2": {"l3": {"b": 2}}}}

        result = deep_merge(base, override)

        assert result == {"l1": {"l2": {"l3": {"a": 1, "b": 2}}}}

    def test_override_replaces_non_dict(self):
        """Test that non-dict values are replaced entirely."""
        base = {"key": [1, 2, 3]}
        override = {"key": [4, 5]}

        result = deep_merge(base, override)

        assert result == {"key": [4, 5]}

    def test_base_unchanged(self):
        """Test that original base dict is not modified."""
        base = {"a": 1}
        override = {"b": 2}

        deep_merge(base, override)

        assert base == {"a": 1}


class TestExpandPath:
    """Tests for expand_path function."""

    def test_expand_tilde(self):
        """Test expanding ~ to home directory."""
        result = expand_path("~/test/path")

        assert result.startswith(os.path.expanduser("~"))
        assert result.endswith("/test/path")

    def test_expand_env_var(self):
        """Test expanding environment variables."""
        os.environ["TEST_VAR"] = "/test/value"

        result = expand_path("$TEST_VAR/subpath")

        assert result == "/test/value/subpath"

        del os.environ["TEST_VAR"]

    def test_empty_path(self):
        """Test that empty path returns empty."""
        assert expand_path("") == ""

    def test_none_path(self):
        """Test that None returns None."""
        assert expand_path(None) is None

    def test_no_expansion_needed(self):
        """Test path without special chars."""
        result = expand_path("/absolute/path")

        assert result == "/absolute/path"


class TestGetNested:
    """Tests for get_nested function."""

    def test_simple_key(self):
        """Test getting a top-level key."""
        config = {"key": "value"}

        result = get_nested(config, "key")

        assert result == "value"

    def test_nested_key(self):
        """Test getting a nested key with dot notation."""
        config = {"outer": {"inner": "value"}}

        result = get_nested(config, "outer.inner")

        assert result == "value"

    def test_deeply_nested_key(self):
        """Test getting a deeply nested key."""
        config = {"a": {"b": {"c": {"d": "deep"}}}}

        result = get_nested(config, "a.b.c.d")

        assert result == "deep"

    def test_missing_key_returns_default(self):
        """Test that missing key returns default."""
        config = {"key": "value"}

        result = get_nested(config, "missing", "default")

        assert result == "default"

    def test_missing_nested_returns_default(self):
        """Test that missing nested path returns default."""
        config = {"outer": {"inner": "value"}}

        result = get_nested(config, "outer.missing.deep", "default")

        assert result == "default"

    def test_default_is_none(self):
        """Test that default is None when not specified."""
        config = {}

        result = get_nested(config, "missing")

        assert result is None


class TestLoadDefaults:
    """Tests for load_defaults function."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_load_from_project_defaults(self):
        """Test loading from the actual project defaults.yaml."""
        config = load_defaults()

        # Check some known sections exist
        assert "paths" in config
        assert "timeouts" in config
        assert "limits" in config
        assert "models" in config

    def test_defaults_contains_expected_values(self):
        """Test that defaults has expected configuration values."""
        config = load_defaults()

        # Check specific known defaults
        assert config["timeouts"]["claude_query_timeout"] == 300
        assert config["limits"]["max_buffer_messages"] == 10
        assert config["models"]["claude_default_model"] == "sonnet"

    def test_load_with_custom_paths(self, tmp_path):
        """Test loading from custom file paths."""
        defaults_content = {"custom": {"setting": "value"}}
        defaults_file = tmp_path / "defaults.yaml"
        defaults_file.write_text(yaml.dump(defaults_content))

        config = load_defaults(defaults_path=defaults_file)

        assert config["custom"]["setting"] == "value"

    def test_settings_override_defaults(self, tmp_path):
        """Test that settings.yaml overrides defaults.yaml."""
        defaults_content = {"key": "default", "other": "keep"}
        settings_content = {"key": "override"}

        defaults_file = tmp_path / "defaults.yaml"
        settings_file = tmp_path / "settings.yaml"
        defaults_file.write_text(yaml.dump(defaults_content))
        settings_file.write_text(yaml.dump(settings_content))

        config = load_defaults(defaults_path=defaults_file, settings_path=settings_file)

        assert config["key"] == "override"
        assert config["other"] == "keep"

    def test_caching_works(self):
        """Test that config is cached."""
        config1 = load_defaults()
        config2 = load_defaults()

        # Should be the same object (cached)
        assert config1 is config2

    def test_reload_bypasses_cache(self):
        """Test that reload=True bypasses cache."""
        config1 = load_defaults()
        config2 = load_defaults(reload=True)

        # Should be different objects
        assert config1 is not config2


class TestGetConfigValue:
    """Tests for get_config_value function."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_get_simple_value(self):
        """Test getting a simple nested value."""
        result = get_config_value("models.claude_default_model")

        assert result == "sonnet"

    def test_get_with_default(self):
        """Test getting missing value returns default."""
        result = get_config_value("nonexistent.path", "my_default")

        assert result == "my_default"

    def test_get_timeout_value(self):
        """Test getting a timeout value."""
        result = get_config_value("timeouts.claude_query_timeout")

        assert result == 300

    def test_expand_paths_true(self):
        """Test path expansion when enabled."""
        result = get_config_value("paths.vault_path", expand_paths=True)

        # Should expand ~ to actual home
        assert not result.startswith("~")
        assert "Research/vault" in result


class TestConvenienceFunctions:
    """Tests for convenience getter functions."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_get_timeout(self):
        """Test get_timeout returns float."""
        result = get_timeout("claude_query_timeout")

        assert isinstance(result, float)
        assert result == 300.0

    def test_get_timeout_default(self):
        """Test get_timeout with default."""
        result = get_timeout("nonexistent", 42.0)

        assert result == 42.0

    def test_get_limit(self):
        """Test get_limit returns int."""
        result = get_limit("max_buffer_messages")

        assert isinstance(result, int)
        assert result == 10

    def test_get_limit_default(self):
        """Test get_limit with default."""
        result = get_limit("nonexistent", 99)

        assert result == 99

    def test_get_path(self):
        """Test get_path expands path."""
        result = get_path("vault_path")

        assert not result.startswith("~")

    def test_get_model(self):
        """Test get_model returns model name."""
        result = get_model("claude_default_model")

        assert result == "sonnet"

    def test_get_message(self):
        """Test get_message returns message template."""
        result = get_message("error_prefix")

        assert result == "❌"

    def test_get_reaction(self):
        """Test get_reaction returns emoji."""
        result = get_reaction("processing_start")

        assert result == "👀"

    def test_get_api_url(self):
        """Test get_api_url returns URL."""
        result = get_api_url("telegram_api_base")

        assert result == "https://api.telegram.org"


class TestDefaultsYamlContent:
    """Tests validating the actual defaults.yaml content."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_all_timeout_values_are_positive(self):
        """Test that all timeout values are positive numbers."""
        config = load_defaults()
        timeouts = config.get("timeouts", {})

        for key, value in timeouts.items():
            assert isinstance(value, (int, float)), f"{key} should be numeric"
            assert value > 0, f"{key} should be positive"

    def test_all_limit_values_are_positive_integers(self):
        """Test that all limit values are positive."""
        config = load_defaults()
        limits = config.get("limits", {})

        for key, value in limits.items():
            assert isinstance(value, (int, float)), f"{key} should be numeric"
            assert value > 0, f"{key} should be positive"

    def test_api_urls_are_valid(self):
        """Test that API URLs are valid HTTPS URLs."""
        config = load_defaults()
        api = config.get("api", {})

        for key, value in api.items():
            if isinstance(value, str) and key.endswith("_base"):
                assert value.startswith("https://"), f"{key} should be HTTPS"

    def test_paths_use_expandable_format(self):
        """Test that paths use ~ or env vars (expandable)."""
        config = load_defaults()
        paths = config.get("paths", {})

        # At least some paths should use ~
        has_tilde = any("~" in str(v) for v in paths.values())
        assert has_tilde, "Paths should use ~ for portability"

    def test_models_section_has_required_models(self):
        """Test that required model configs exist."""
        config = load_defaults()
        models = config.get("models", {})

        assert "claude_default_model" in models
        assert "llm_default_model" in models
        assert "whisper_model" in models

    def test_reactions_are_emojis(self):
        """Test that reaction values are emojis (non-ASCII)."""
        config = load_defaults()
        reactions = config.get("reactions", {})

        # Skip nested dicts like model_emoji
        emoji_keys = [
            "completion_reaction_value",
            "processing_start",
            "processing_complete",
            "processing_failed",
        ]

        for key in emoji_keys:
            value = reactions.get(key, "")
            assert value, f"{key} should have a value"
            # Emoji chars are outside ASCII range
            assert any(ord(c) > 127 for c in value), f"{key} should be emoji"

    def test_bypass_commands_start_with_slash(self):
        """Test that bypass commands are valid bot commands."""
        config = load_defaults()
        commands = config.get("bot", {}).get("bypass_commands", [])

        for cmd in commands:
            assert cmd.startswith("/"), f"Command {cmd} should start with /"


class TestClearCache:
    """Tests for clear_cache function."""

    def test_clear_cache_enables_reload(self):
        """Test that clear_cache allows fresh load."""
        config1 = load_defaults()
        clear_cache()
        config2 = load_defaults()

        # After clearing, should be new object
        assert config1 is not config2
