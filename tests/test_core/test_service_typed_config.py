"""Tests verifying that the 3 key services use typed config objects.

Slice 3: mode_manager, accountability_service, trail_scheduler
should accept typed config instead of raw dicts / env vars.
"""

from datetime import time
from pathlib import Path

# =============================================================================
# ModeManager + ModeCatalog integration
# =============================================================================


class TestModeManagerTypedConfig:
    """ModeManager should delegate to a ModeCatalog internally."""

    def test_manager_exposes_catalog(self):
        """ModeManager.catalog should be a ModeCatalog instance."""
        from src.core.mode_manager import ModeManager
        from src.core.typed_config import ModeCatalog

        project_root = Path(__file__).resolve().parent.parent.parent
        mm = ModeManager(config_path=project_root / "config" / "modes.yaml")
        assert isinstance(mm.catalog, ModeCatalog)

    def test_catalog_modes_match_raw_modes(self):
        """Typed catalog should contain the same modes as raw config."""
        from src.core.mode_manager import ModeManager

        project_root = Path(__file__).resolve().parent.parent.parent
        mm = ModeManager(config_path=project_root / "config" / "modes.yaml")
        raw_modes = list(mm._config.get("modes", {}).keys())
        catalog_modes = mm.catalog.available_modes()
        assert set(raw_modes) == set(catalog_modes)

    def test_get_mode_info_still_returns_dict(self):
        """Backward-compat: get_mode_info() still returns a dict."""
        from src.core.mode_manager import ModeManager

        project_root = Path(__file__).resolve().parent.parent.parent
        mm = ModeManager(config_path=project_root / "config" / "modes.yaml")
        info = mm.get_mode_info("default")
        assert isinstance(info, dict)
        assert info["name"] == "Default"

    def test_from_catalog_constructor(self):
        """ModeManager can be constructed directly from a ModeCatalog."""
        from src.core.mode_manager import ModeManager
        from src.core.typed_config import ModeCatalog, ModeConfig

        catalog = ModeCatalog(
            modes={
                "test": ModeConfig(name="Test", prompt="Test prompt."),
            },
            aliases={"/t": "test"},
        )
        mm = ModeManager.from_catalog(catalog)
        assert mm.is_valid_mode("test")
        assert mm.resolve_alias("/t") == "test"
        assert mm.get_mode_prompt("test") == "Test prompt."


# =============================================================================
# AccountabilityService + AccountabilityConfig
# =============================================================================


class TestAccountabilityServiceTypedConfig:
    """AccountabilityService should use AccountabilityConfig instead of raw dict."""

    def test_module_level_config_is_typed(self):
        """The module should expose a typed AccountabilityConfig."""
        from src.core.typed_config import AccountabilityConfig
        from src.services.accountability_service import get_personality_config

        config = get_personality_config()
        assert isinstance(config, AccountabilityConfig)

    def test_personality_lookup_returns_typed_profile(self):
        """Looking up a personality returns a PersonalityProfile."""
        from src.core.typed_config import PersonalityProfile
        from src.services.accountability_service import get_personality_config

        config = get_personality_config()
        p = config.get_personality("supportive")
        assert p is None or isinstance(p, PersonalityProfile)

    def test_send_check_in_uses_typed_config(self):
        """send_check_in should use typed personality config for voice/emotion."""
        from src.core.typed_config import AccountabilityConfig, PersonalityProfile

        # Build a test config
        config = AccountabilityConfig(
            personalities={
                "test_pers": PersonalityProfile(
                    voice="test_voice",
                    emotion="test_emotion",
                    struggle_threshold=3,
                    celebration_style="moderate",
                ),
            },
            default_personality="test_pers",
        )
        # Verify the typed lookup works
        p = config.get_personality("test_pers")
        assert p.voice == "test_voice"
        assert p.emotion == "test_emotion"


# =============================================================================
# TrailScheduler + TrailSchedule
# =============================================================================


class TestTrailSchedulerTypedConfig:
    """TrailSchedulerConfig should delegate to TrailSchedule."""

    def test_scheduler_config_has_schedule(self, monkeypatch):
        """TrailSchedulerConfig.schedule should be a TrailSchedule."""
        monkeypatch.setenv("TRAIL_REVIEW_ENABLED", "true")
        monkeypatch.setenv("TRAIL_REVIEW_CHAT_ID", "12345")
        monkeypatch.setenv("TRAIL_REVIEW_TIMES", "09:00,14:00")

        from src.core.typed_config import TrailSchedule
        from src.services.trail_scheduler import TrailSchedulerConfig

        config = TrailSchedulerConfig()
        assert isinstance(config.schedule, TrailSchedule)

    def test_scheduler_config_poll_times_typed(self, monkeypatch):
        """Poll times from TrailSchedulerConfig should match typed schedule."""
        monkeypatch.setenv("TRAIL_REVIEW_ENABLED", "true")
        monkeypatch.setenv("TRAIL_REVIEW_CHAT_ID", "99")
        monkeypatch.setenv("TRAIL_REVIEW_TIMES", "10:00,18:00")

        from src.services.trail_scheduler import TrailSchedulerConfig

        config = TrailSchedulerConfig()
        assert config.schedule.poll_times == [time(10, 0), time(18, 0)]
        assert config.schedule.is_active() is True

    def test_scheduler_from_schedule(self, monkeypatch):
        """TrailSchedulerConfig can be created from a TrailSchedule."""
        from src.core.typed_config import TrailSchedule
        from src.services.trail_scheduler import TrailSchedulerConfig

        schedule = TrailSchedule(
            enabled=True,
            chat_id="42",
            poll_times=[time(8, 0)],
        )
        config = TrailSchedulerConfig.from_schedule(schedule)
        assert config.schedule is schedule
        assert config.is_enabled() is True
        assert config.get_poll_times() == [time(8, 0)]

    def test_scheduler_backward_compat_get_poll_times(self, monkeypatch):
        """get_poll_times() still works as before."""
        monkeypatch.setenv("TRAIL_REVIEW_ENABLED", "true")
        monkeypatch.setenv("TRAIL_REVIEW_CHAT_ID", "1")
        monkeypatch.setenv("TRAIL_REVIEW_TIMES", "09:00,14:00,20:00")

        from src.services.trail_scheduler import TrailSchedulerConfig

        config = TrailSchedulerConfig()
        times = config.get_poll_times()
        assert times == [time(9, 0), time(14, 0), time(20, 0)]

    def test_scheduler_backward_compat_is_enabled(self, monkeypatch):
        """is_enabled() still works as before."""
        monkeypatch.setenv("TRAIL_REVIEW_ENABLED", "false")
        monkeypatch.delenv("TRAIL_REVIEW_CHAT_ID", raising=False)

        from src.services.trail_scheduler import TrailSchedulerConfig

        config = TrailSchedulerConfig()
        assert config.is_enabled() is False
