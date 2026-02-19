"""Tests for typed config loader — parses YAML into typed domain objects."""

import textwrap
from pathlib import Path


class TestLoadModeCatalog:
    """Test loading modes.yaml into a ModeCatalog."""

    def test_load_from_real_modes_yaml(self):
        from src.core.typed_config_loader import load_mode_catalog

        project_root = Path(__file__).resolve().parent.parent.parent
        modes_path = project_root / "config" / "modes.yaml"
        catalog = load_mode_catalog(modes_path)

        assert "default" in catalog.modes
        assert "formal" in catalog.modes
        assert "artistic" in catalog.modes
        assert catalog.modes["default"].name == "Default"
        assert catalog.modes["default"].embed is False
        assert catalog.modes["formal"].embed is True
        assert len(catalog.modes["formal"].presets) == 3
        assert catalog.settings.similarity_threshold == 0.7

    def test_load_from_minimal_yaml(self, tmp_path):
        from src.core.typed_config_loader import load_mode_catalog

        yaml_file = tmp_path / "modes.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            modes:
              simple:
                name: Simple
                prompt: Describe.
            aliases:
              /s: simple
            settings:
              similarity_threshold: 0.9
            """))

        catalog = load_mode_catalog(yaml_file)
        assert "simple" in catalog.modes
        assert catalog.modes["simple"].name == "Simple"
        assert catalog.resolve_alias("/s") == "simple"
        assert catalog.settings.similarity_threshold == 0.9

    def test_load_missing_file_returns_fallback(self, tmp_path):
        from src.core.typed_config_loader import load_mode_catalog

        catalog = load_mode_catalog(tmp_path / "nonexistent.yaml")
        assert "default" in catalog.modes
        assert catalog.modes["default"].name == "Default"

    def test_load_modes_with_presets(self, tmp_path):
        from src.core.typed_config_loader import load_mode_catalog

        yaml_file = tmp_path / "modes.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            modes:
              analysis:
                name: Analysis
                prompt: Default analysis.
                embed: true
                max_tokens: 500
                temperature: 0.2
                presets:
                  - name: Detailed
                    description: Detailed output
                    prompt: Detailed analysis.
                  - name: Quick
                    description: Quick output
                    prompt: Quick analysis.
            """))

        catalog = load_mode_catalog(yaml_file)
        mode = catalog.modes["analysis"]
        assert mode.embed is True
        assert mode.max_tokens == 500
        assert len(mode.presets) == 2
        assert mode.presets[0].name == "Detailed"


class TestLoadAccountabilityConfig:
    """Test loading accountability section from defaults.yaml."""

    def test_load_from_real_defaults_yaml(self):
        from src.core.typed_config_loader import load_accountability_config

        project_root = Path(__file__).resolve().parent.parent.parent
        defaults_path = project_root / "config" / "defaults.yaml"
        config = load_accountability_config(defaults_path)

        assert "gentle" in config.personalities
        assert "supportive" in config.personalities
        assert "direct" in config.personalities
        assert "assertive" in config.personalities
        assert "tough_love" in config.personalities
        assert config.personalities["gentle"].voice == "diana"
        assert config.personalities["assertive"].emotion == "cheerful"
        assert config.default_personality == "supportive"

    def test_load_from_minimal_yaml(self, tmp_path):
        from src.core.typed_config_loader import load_accountability_config

        yaml_file = tmp_path / "defaults.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            accountability:
              personalities:
                calm:
                  voice: diana
                  emotion: whisper
                  struggle_threshold: 5
                  celebration_style: quiet
              default_personality: calm
            """))

        config = load_accountability_config(yaml_file)
        assert "calm" in config.personalities
        assert config.default_personality == "calm"

    def test_load_missing_file_returns_empty(self, tmp_path):
        from src.core.typed_config_loader import load_accountability_config

        config = load_accountability_config(tmp_path / "nonexistent.yaml")
        assert config.personalities == {}

    def test_load_yaml_without_accountability_section(self, tmp_path):
        from src.core.typed_config_loader import load_accountability_config

        yaml_file = tmp_path / "defaults.yaml"
        yaml_file.write_text("timeouts:\n  buffer_timeout: 2.5\n")

        config = load_accountability_config(yaml_file)
        assert config.personalities == {}


class TestLoadTrailSchedule:
    """Test loading trail schedule from environment / YAML."""

    def test_load_from_env(self, monkeypatch):
        from src.core.typed_config_loader import load_trail_schedule

        monkeypatch.setenv("TRAIL_REVIEW_ENABLED", "true")
        monkeypatch.setenv("TRAIL_REVIEW_CHAT_ID", "12345")
        monkeypatch.setenv("TRAIL_REVIEW_TIMES", "08:00,16:00")

        schedule = load_trail_schedule()
        assert schedule.enabled is True
        assert schedule.chat_id == "12345"
        from datetime import time

        assert schedule.poll_times == [time(8, 0), time(16, 0)]

    def test_load_defaults_when_env_missing(self, monkeypatch):
        from src.core.typed_config_loader import load_trail_schedule

        monkeypatch.delenv("TRAIL_REVIEW_ENABLED", raising=False)
        monkeypatch.delenv("TRAIL_REVIEW_CHAT_ID", raising=False)
        monkeypatch.delenv("TRAIL_REVIEW_TIMES", raising=False)

        schedule = load_trail_schedule()
        assert schedule.enabled is True
        assert schedule.chat_id is None
        from datetime import time

        assert schedule.poll_times == [time(9, 0), time(14, 0), time(20, 0)]

    def test_load_disabled(self, monkeypatch):
        from src.core.typed_config_loader import load_trail_schedule

        monkeypatch.setenv("TRAIL_REVIEW_ENABLED", "false")
        monkeypatch.setenv("TRAIL_REVIEW_CHAT_ID", "12345")

        schedule = load_trail_schedule()
        assert schedule.enabled is False
        assert schedule.is_active() is False


class TestCachedLoaders:
    """Test the cached/singleton accessor functions."""

    def test_get_mode_catalog_cached(self):
        from src.core.typed_config_loader import (
            _clear_caches,
            get_mode_catalog,
        )

        _clear_caches()
        c1 = get_mode_catalog()
        c2 = get_mode_catalog()
        assert c1 is c2  # same object (cached)

    def test_get_accountability_config_cached(self):
        from src.core.typed_config_loader import (
            _clear_caches,
            get_accountability_config,
        )

        _clear_caches()
        c1 = get_accountability_config()
        c2 = get_accountability_config()
        assert c1 is c2

    def test_get_trail_schedule_cached(self, monkeypatch):
        from src.core.typed_config_loader import (
            _clear_caches,
            get_trail_schedule,
        )

        monkeypatch.delenv("TRAIL_REVIEW_ENABLED", raising=False)
        monkeypatch.delenv("TRAIL_REVIEW_CHAT_ID", raising=False)
        monkeypatch.delenv("TRAIL_REVIEW_TIMES", raising=False)

        _clear_caches()
        s1 = get_trail_schedule()
        s2 = get_trail_schedule()
        assert s1 is s2

    def test_clear_caches_forces_reload(self):
        from src.core.typed_config_loader import (
            _clear_caches,
            get_mode_catalog,
        )

        _clear_caches()
        c1 = get_mode_catalog()
        _clear_caches()
        c2 = get_mode_catalog()
        # Equal content but different object identity after cache clear
        assert c1 == c2
        assert c1 is not c2
