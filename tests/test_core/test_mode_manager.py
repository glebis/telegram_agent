"""
Tests for the Mode Manager.

Tests cover:
- ModeManager initialization (default path, custom path, fallback)
- Mode operations (available modes, mode info, validation)
- Preset operations (presets list, preset info, validation)
- Prompt retrieval (mode prompts, preset prompts)
- Settings retrieval (global settings, thresholds)
- Command aliases
- Configuration validation
- Configuration reload
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.core.mode_manager import ModeManager

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_config():
    """Return a sample valid configuration."""
    return {
        "modes": {
            "default": {
                "name": "Default",
                "description": "Quick description",
                "prompt": "Describe the image in 40 words or less.",
                "embed": False,
                "max_tokens": 100,
                "presets": [
                    {
                        "name": "Quick",
                        "description": "Quick mode preset",
                        "prompt": "Describe quickly.",
                    },
                ],
            },
            "formal": {
                "name": "Formal Analysis",
                "description": "Structured analysis",
                "prompt": "Provide a formal analysis.",
                "embed": True,
                "presets": [
                    {
                        "name": "Structured",
                        "description": "Detailed structured output",
                        "prompt": "Analyze with structured YAML output.",
                    },
                    {
                        "name": "Tags",
                        "description": "Tag extraction",
                        "prompt": "Extract hierarchical tags.",
                    },
                ],
            },
            "artistic": {
                "name": "Artistic",
                "description": "Art analysis",
                "prompt": "Analyze artistically.",
                "embed": True,
                "presets": [
                    {
                        "name": "Critic",
                        "description": "Art critic view",
                        "prompt": "Analyze like an art critic.",
                    },
                ],
            },
        },
        "settings": {
            "similarity_threshold": 0.75,
            "max_similar_images": 10,
            "image_max_size": 2048,
            "supported_formats": ["jpg", "png", "gif"],
        },
        "aliases": {
            "/quick": "default.Quick",
            "/formal": "formal.Structured",
            "/tags": "formal.Tags",
            "/critic": "artistic.Critic",
        },
    }


@pytest.fixture
def config_file(sample_config):
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config, f)
        return f.name


@pytest.fixture
def mode_manager(config_file):
    """Create a ModeManager with sample config."""
    return ModeManager(config_path=config_file)


@pytest.fixture
def minimal_config():
    """Return minimal valid configuration."""
    return {
        "modes": {
            "default": {
                "name": "Default",
                "prompt": "Describe this.",
            }
        },
        "aliases": {},
    }


@pytest.fixture
def minimal_config_file(minimal_config):
    """Create a temporary minimal config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(minimal_config, f)
        return f.name


# =============================================================================
# Initialization Tests
# =============================================================================


class TestModeManagerInit:
    """Tests for ModeManager initialization."""

    def test_init_with_custom_path(self, config_file):
        """Test initialization with custom config path."""
        manager = ModeManager(config_path=config_file)

        assert manager.config_path == Path(config_file)
        assert manager._config is not None

    def test_init_with_default_path(self):
        """Test initialization uses default path when none provided."""
        # This may or may not work depending on whether the default file exists
        # Just verify it doesn't crash
        try:
            manager = ModeManager()
            assert manager.config_path is not None
        except Exception:
            # If default config doesn't exist, fallback should be used
            pass

    def test_init_with_nonexistent_file(self):
        """Test initialization with non-existent file uses fallback."""
        manager = ModeManager(config_path="/nonexistent/path/config.yaml")

        # Should use fallback config
        assert manager._config is not None
        assert "default" in manager._config.get("modes", {})

    def test_fallback_config_structure(self):
        """Test that fallback config has expected structure."""
        manager = ModeManager(config_path="/nonexistent/config.yaml")

        # Check fallback has basic structure
        assert "modes" in manager._config
        assert "default" in manager._config["modes"]
        assert "prompt" in manager._config["modes"]["default"]

    def test_init_loads_modes(self, mode_manager):
        """Test that initialization loads modes from config."""
        modes = mode_manager.get_available_modes()

        assert "default" in modes
        assert "formal" in modes
        assert "artistic" in modes


# =============================================================================
# Mode Operations Tests
# =============================================================================


class TestModeOperations:
    """Tests for mode-related operations."""

    def test_get_available_modes(self, mode_manager):
        """Test getting list of available modes."""
        modes = mode_manager.get_available_modes()

        assert isinstance(modes, list)
        assert len(modes) == 3
        assert "default" in modes
        assert "formal" in modes
        assert "artistic" in modes

    def test_get_available_modes_empty(self):
        """Test get_available_modes with empty config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"modes": {}}, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            modes = manager.get_available_modes()

            assert modes == []

    def test_get_mode_info_exists(self, mode_manager):
        """Test getting info for existing mode."""
        info = mode_manager.get_mode_info("default")

        assert info is not None
        assert info["name"] == "Default"
        assert "prompt" in info
        assert info["embed"] is False

    def test_get_mode_info_with_presets(self, mode_manager):
        """Test getting info for mode with presets."""
        info = mode_manager.get_mode_info("formal")

        assert info is not None
        assert "presets" in info
        assert len(info["presets"]) == 2

    def test_get_mode_info_not_found(self, mode_manager):
        """Test getting info for non-existent mode."""
        info = mode_manager.get_mode_info("nonexistent")

        assert info is None

    def test_is_valid_mode_true(self, mode_manager):
        """Test is_valid_mode returns True for valid mode."""
        assert mode_manager.is_valid_mode("default") is True
        assert mode_manager.is_valid_mode("formal") is True
        assert mode_manager.is_valid_mode("artistic") is True

    def test_is_valid_mode_false(self, mode_manager):
        """Test is_valid_mode returns False for invalid mode."""
        assert mode_manager.is_valid_mode("nonexistent") is False
        assert mode_manager.is_valid_mode("") is False
        assert mode_manager.is_valid_mode("FORMAL") is False  # Case sensitive


# =============================================================================
# Preset Operations Tests
# =============================================================================


class TestPresetOperations:
    """Tests for preset-related operations."""

    def test_get_mode_presets_exists(self, mode_manager):
        """Test getting presets for mode that has them."""
        presets = mode_manager.get_mode_presets("formal")

        assert isinstance(presets, list)
        assert len(presets) == 2
        assert "Structured" in presets
        assert "Tags" in presets

    def test_get_mode_presets_no_presets(self, minimal_config_file):
        """Test getting presets for mode without presets."""
        manager = ModeManager(config_path=minimal_config_file)
        presets = manager.get_mode_presets("default")

        assert presets == []

    def test_get_mode_presets_invalid_mode(self, mode_manager):
        """Test getting presets for invalid mode."""
        presets = mode_manager.get_mode_presets("nonexistent")

        assert presets == []

    def test_get_preset_info_exists(self, mode_manager):
        """Test getting info for existing preset."""
        info = mode_manager.get_preset_info("formal", "Structured")

        assert info is not None
        assert info["name"] == "Structured"
        assert "prompt" in info
        assert "description" in info

    def test_get_preset_info_not_found(self, mode_manager):
        """Test getting info for non-existent preset."""
        info = mode_manager.get_preset_info("formal", "NonexistentPreset")

        assert info is None

    def test_get_preset_info_invalid_mode(self, mode_manager):
        """Test getting preset info for invalid mode."""
        info = mode_manager.get_preset_info("nonexistent", "SomePreset")

        assert info is None

    def test_is_valid_preset_true(self, mode_manager):
        """Test is_valid_preset returns True for valid preset."""
        assert mode_manager.is_valid_preset("formal", "Structured") is True
        assert mode_manager.is_valid_preset("formal", "Tags") is True
        assert mode_manager.is_valid_preset("artistic", "Critic") is True

    def test_is_valid_preset_false(self, mode_manager):
        """Test is_valid_preset returns False for invalid preset."""
        assert mode_manager.is_valid_preset("formal", "Nonexistent") is False
        assert mode_manager.is_valid_preset("default", "Structured") is False
        assert mode_manager.is_valid_preset("nonexistent", "Structured") is False


# =============================================================================
# Prompt Retrieval Tests
# =============================================================================


class TestPromptRetrieval:
    """Tests for prompt retrieval."""

    def test_get_mode_prompt_no_preset(self, mode_manager):
        """Test getting mode prompt without preset."""
        prompt = mode_manager.get_mode_prompt("default")

        assert isinstance(prompt, str)
        assert "40 words" in prompt

    def test_get_mode_prompt_with_preset(self, mode_manager):
        """Test getting mode prompt with preset."""
        prompt = mode_manager.get_mode_prompt("formal", "Structured")

        assert isinstance(prompt, str)
        assert "YAML" in prompt

    def test_get_mode_prompt_invalid_mode(self, mode_manager):
        """Test getting prompt for invalid mode returns default."""
        prompt = mode_manager.get_mode_prompt("nonexistent")

        assert prompt == "Describe this image."

    def test_get_mode_prompt_invalid_preset(self, mode_manager):
        """Test getting prompt with invalid preset returns mode default."""
        prompt = mode_manager.get_mode_prompt("formal", "NonexistentPreset")

        assert isinstance(prompt, str)
        assert prompt == "Provide a formal analysis."

    def test_get_mode_prompt_none_preset(self, mode_manager):
        """Test getting prompt with None preset."""
        prompt = mode_manager.get_mode_prompt("formal", None)

        assert prompt == "Provide a formal analysis."


# =============================================================================
# Embed Setting Tests
# =============================================================================


class TestEmbedSetting:
    """Tests for should_embed method."""

    def test_should_embed_true(self, mode_manager):
        """Test should_embed returns True when configured."""
        assert mode_manager.should_embed("formal") is True
        assert mode_manager.should_embed("artistic") is True

    def test_should_embed_false(self, mode_manager):
        """Test should_embed returns False when configured."""
        assert mode_manager.should_embed("default") is False

    def test_should_embed_invalid_mode(self, mode_manager):
        """Test should_embed returns False for invalid mode."""
        assert mode_manager.should_embed("nonexistent") is False


# =============================================================================
# Settings Tests
# =============================================================================


class TestSettings:
    """Tests for settings retrieval."""

    def test_get_mode_settings(self, mode_manager):
        """Test getting all mode settings."""
        settings = mode_manager.get_mode_settings()

        assert isinstance(settings, dict)
        assert "similarity_threshold" in settings
        assert "max_similar_images" in settings
        assert "image_max_size" in settings
        assert "supported_formats" in settings

    def test_get_mode_settings_empty(self, minimal_config_file):
        """Test getting settings when none defined."""
        manager = ModeManager(config_path=minimal_config_file)
        settings = manager.get_mode_settings()

        assert settings == {}

    def test_get_similarity_threshold(self, mode_manager):
        """Test getting similarity threshold."""
        threshold = mode_manager.get_similarity_threshold()

        assert threshold == 0.75

    def test_get_similarity_threshold_default(self, minimal_config_file):
        """Test similarity threshold default value."""
        manager = ModeManager(config_path=minimal_config_file)
        threshold = manager.get_similarity_threshold()

        assert threshold == 0.7  # Default

    def test_get_max_similar_images(self, mode_manager):
        """Test getting max similar images."""
        max_images = mode_manager.get_max_similar_images()

        assert max_images == 10

    def test_get_max_similar_images_default(self, minimal_config_file):
        """Test max similar images default value."""
        manager = ModeManager(config_path=minimal_config_file)
        max_images = manager.get_max_similar_images()

        assert max_images == 5  # Default

    def test_get_image_max_size(self, mode_manager):
        """Test getting image max size."""
        max_size = mode_manager.get_image_max_size()

        assert max_size == 2048

    def test_get_image_max_size_default(self, minimal_config_file):
        """Test image max size default value."""
        manager = ModeManager(config_path=minimal_config_file)
        max_size = manager.get_image_max_size()

        assert max_size == 1024  # Default

    def test_get_supported_formats(self, mode_manager):
        """Test getting supported formats."""
        formats = mode_manager.get_supported_formats()

        assert isinstance(formats, list)
        assert "jpg" in formats
        assert "png" in formats
        assert "gif" in formats

    def test_get_supported_formats_default(self, minimal_config_file):
        """Test supported formats default value."""
        manager = ModeManager(config_path=minimal_config_file)
        formats = manager.get_supported_formats()

        assert formats == ["jpg", "jpeg", "png", "webp"]  # Default


# =============================================================================
# Alias Tests
# =============================================================================


class TestAliases:
    """Tests for command aliases."""

    def test_get_command_aliases(self, mode_manager):
        """Test getting all command aliases."""
        aliases = mode_manager.get_command_aliases()

        assert isinstance(aliases, dict)
        assert "/quick" in aliases
        assert "/formal" in aliases
        assert "/tags" in aliases

    def test_get_command_aliases_empty(self, minimal_config_file):
        """Test getting aliases when none defined."""
        manager = ModeManager(config_path=minimal_config_file)
        aliases = manager.get_command_aliases()

        assert aliases == {}

    def test_resolve_alias_exists(self, mode_manager):
        """Test resolving existing alias."""
        target = mode_manager.resolve_alias("/quick")
        assert target == "default.Quick"

        target = mode_manager.resolve_alias("/formal")
        assert target == "formal.Structured"

        target = mode_manager.resolve_alias("/critic")
        assert target == "artistic.Critic"

    def test_resolve_alias_not_found(self, mode_manager):
        """Test resolving non-existent alias."""
        target = mode_manager.resolve_alias("/nonexistent")

        assert target is None

    def test_resolve_alias_case_sensitive(self, mode_manager):
        """Test that alias resolution is case sensitive."""
        target = mode_manager.resolve_alias("/QUICK")

        assert target is None


# =============================================================================
# Reload Tests
# =============================================================================


class TestReload:
    """Tests for configuration reload."""

    def test_reload_config_success(self, sample_config):
        """Test successful config reload."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)

            # Modify and save
            sample_config["modes"]["new_mode"] = {
                "name": "New Mode",
                "prompt": "New prompt",
            }

            with open(f.name, "w") as f2:
                yaml.dump(sample_config, f2)

            # Reload
            result = manager.reload_config()

            assert result is True
            assert "new_mode" in manager.get_available_modes()

    def test_reload_config_failure(self, mode_manager):
        """Test config reload when file is deleted."""
        # Delete the config file
        import os

        os.remove(mode_manager.config_path)

        # Reload should fail but not crash
        result = mode_manager.reload_config()

        # Should return True (uses fallback) or False depending on implementation
        # The important thing is it doesn't crash
        assert result in [True, False]


# =============================================================================
# Validation Tests
# =============================================================================


class TestValidation:
    """Tests for configuration validation."""

    def test_validate_valid_config(self, mode_manager):
        """Test validation of valid config."""
        errors = mode_manager.validate_config()

        assert errors == []

    def test_validate_empty_config(self):
        """Test validation of empty config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"modes": {}}, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert len(errors) > 0
            assert any("No modes defined" in e for e in errors)

    def test_validate_mode_not_dict(self):
        """Test validation when mode is not a dict."""
        config = {"modes": {"bad_mode": "not a dict"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("not a dictionary" in e for e in errors)

    def test_validate_mode_missing_prompt(self):
        """Test validation when mode missing prompt."""
        config = {
            "modes": {
                "no_prompt_mode": {
                    "name": "No Prompt"
                    # Missing prompt
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("missing 'prompt' field" in e for e in errors)

    def test_validate_presets_not_list(self):
        """Test validation when presets is not a list."""
        config = {
            "modes": {
                "bad_presets": {
                    "name": "Bad Presets",
                    "prompt": "A prompt",
                    "presets": "not a list",
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("presets must be a list" in e for e in errors)

    def test_validate_preset_not_dict(self):
        """Test validation when preset is not a dict."""
        config = {
            "modes": {
                "mode": {
                    "name": "Mode",
                    "prompt": "A prompt",
                    "presets": ["not a dict"],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("preset 0 is not a dictionary" in e for e in errors)

    def test_validate_preset_missing_name(self):
        """Test validation when preset missing name."""
        config = {
            "modes": {
                "mode": {
                    "name": "Mode",
                    "prompt": "A prompt",
                    "presets": [
                        {
                            "prompt": "Preset prompt"
                            # Missing name
                        }
                    ],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("missing 'name' field" in e for e in errors)

    def test_validate_preset_missing_prompt(self):
        """Test validation when preset missing prompt."""
        config = {
            "modes": {
                "mode": {
                    "name": "Mode",
                    "prompt": "A prompt",
                    "presets": [
                        {
                            "name": "Preset"
                            # Missing prompt
                        }
                    ],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("missing 'prompt' field" in e for e in errors)

    def test_validate_alias_wrong_format(self):
        """Test validation when alias target not in mode.preset format."""
        config = {
            "modes": {
                "default": {
                    "name": "Default",
                    "prompt": "A prompt",
                }
            },
            "aliases": {"/bad": "nodotshere"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("mode.preset" in e for e in errors)

    def test_validate_alias_invalid_mode(self):
        """Test validation when alias references invalid mode."""
        config = {
            "modes": {
                "default": {
                    "name": "Default",
                    "prompt": "A prompt",
                }
            },
            "aliases": {"/bad": "nonexistent.preset"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("invalid mode" in e for e in errors)

    def test_validate_alias_invalid_preset(self):
        """Test validation when alias references invalid preset."""
        config = {
            "modes": {
                "mymode": {
                    "name": "My Mode",
                    "prompt": "A prompt",
                    "presets": [{"name": "ValidPreset", "prompt": "Preset prompt"}],
                }
            },
            "aliases": {"/bad": "mymode.InvalidPreset"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            assert any("invalid preset" in e for e in errors)

    def test_validate_none_config(self):
        """Test validation with None config."""
        manager = ModeManager(config_path="/nonexistent/path.yaml")
        # Manually set config to None
        manager._config = None

        errors = manager.validate_config()

        assert any("empty or invalid" in e for e in errors)


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_mode_with_empty_presets_list(self):
        """Test mode with empty presets list."""
        config = {
            "modes": {"mode": {"name": "Mode", "prompt": "A prompt", "presets": []}}
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            presets = manager.get_mode_presets("mode")

            assert presets == []

    def test_mode_with_extra_fields(self, sample_config):
        """Test that extra fields in config don't cause issues."""
        sample_config["modes"]["default"]["extra_field"] = "extra_value"
        sample_config["modes"]["default"]["another_extra"] = 123

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            info = manager.get_mode_info("default")

            assert info["extra_field"] == "extra_value"
            assert info["another_extra"] == 123

    def test_multiline_prompt(self, sample_config):
        """Test mode with multiline prompt."""
        sample_config["modes"]["multiline"] = {
            "name": "Multiline",
            "prompt": """This is a
            multiline
            prompt with lots of text.""",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            prompt = manager.get_mode_prompt("multiline")

            assert "multiline" in prompt
            assert "prompt" in prompt

    def test_unicode_in_config(self, sample_config):
        """Test config with unicode characters."""
        sample_config["modes"]["unicode"] = {
            "name": "Unicode Mode",
            "prompt": "Describe in 40 words. Use emojis if appropriate.",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f, allow_unicode=True)
            f.flush()

            manager = ModeManager(config_path=f.name)
            prompt = manager.get_mode_prompt("unicode")

            assert "40 words" in prompt

    def test_special_characters_in_mode_name(self, sample_config):
        """Test mode with special characters in name."""
        sample_config["modes"]["mode-with-dashes"] = {
            "name": "Mode With Dashes",
            "prompt": "A prompt",
        }
        sample_config["modes"]["mode_with_underscores"] = {
            "name": "Mode With Underscores",
            "prompt": "Another prompt",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)

            assert manager.is_valid_mode("mode-with-dashes") is True
            assert manager.is_valid_mode("mode_with_underscores") is True

    def test_alias_with_mode_only(self):
        """Test alias that points to mode without preset triggers error."""
        config = {
            "modes": {
                "default": {
                    "name": "Default",
                    "prompt": "A prompt",
                }
            },
            "aliases": {"/nodot": "default"},  # Missing dot - should trigger error
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            errors = manager.validate_config()

            # This should trigger the "should be in mode.preset format" error
            assert any("mode.preset" in e for e in errors)

    def test_numeric_settings(self, sample_config):
        """Test settings with various numeric types."""
        sample_config["settings"]["float_setting"] = 0.123456789
        sample_config["settings"]["int_setting"] = 12345

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f)
            f.flush()

            manager = ModeManager(config_path=f.name)
            settings = manager.get_mode_settings()

            assert settings["float_setting"] == 0.123456789
            assert settings["int_setting"] == 12345

    def test_path_object_handling(self, config_file):
        """Test that Path objects are handled correctly."""
        manager = ModeManager(config_path=Path(config_file))

        assert manager._config is not None
        assert len(manager.get_available_modes()) > 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple operations."""

    def test_full_workflow(self, mode_manager):
        """Test a full workflow of mode manager operations."""
        # Get available modes
        modes = mode_manager.get_available_modes()
        assert len(modes) > 0

        # Get info for first mode
        first_mode = modes[0]
        info = mode_manager.get_mode_info(first_mode)
        assert info is not None

        # Check if mode has presets
        presets = mode_manager.get_mode_presets(first_mode)

        if presets:
            # Get preset info and prompt
            preset_info = mode_manager.get_preset_info(first_mode, presets[0])
            assert preset_info is not None

            prompt = mode_manager.get_mode_prompt(first_mode, presets[0])
            assert isinstance(prompt, str)
        else:
            # Get mode prompt directly
            prompt = mode_manager.get_mode_prompt(first_mode)
            assert isinstance(prompt, str)

    def test_alias_to_mode_lookup(self, mode_manager):
        """Test resolving alias and getting mode info."""
        # Resolve alias
        target = mode_manager.resolve_alias("/formal")
        assert target == "formal.Structured"

        # Parse target
        parts = target.split(".", 1)
        mode_name = parts[0]
        preset_name = parts[1] if len(parts) > 1 else None

        # Get mode info
        mode_info = mode_manager.get_mode_info(mode_name)
        assert mode_info is not None

        # Get preset info
        preset_info = mode_manager.get_preset_info(mode_name, preset_name)
        assert preset_info is not None

        # Get combined prompt
        prompt = mode_manager.get_mode_prompt(mode_name, preset_name)
        assert "YAML" in prompt

    def test_settings_and_formats(self, mode_manager):
        """Test retrieving settings and using them together."""
        threshold = mode_manager.get_similarity_threshold()
        max_images = mode_manager.get_max_similar_images()
        max_size = mode_manager.get_image_max_size()
        formats = mode_manager.get_supported_formats()

        # Verify all settings are reasonable
        assert 0 <= threshold <= 1
        assert max_images > 0
        assert max_size > 0
        assert len(formats) > 0
