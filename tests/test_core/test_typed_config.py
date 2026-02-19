"""Tests for typed configuration domain objects."""

import pytest
from datetime import time
from pydantic import ValidationError


class TestPersonalityProfile:
    """Tests for PersonalityProfile typed config."""

    def test_valid_personality_profile(self):
        from src.core.typed_config import PersonalityProfile

        p = PersonalityProfile(
            voice="diana",
            emotion="cheerful",
            struggle_threshold=3,
            celebration_style="moderate",
        )
        assert p.voice == "diana"
        assert p.emotion == "cheerful"
        assert p.struggle_threshold == 3
        assert p.celebration_style == "moderate"

    def test_personality_profile_rejects_negative_threshold(self):
        from src.core.typed_config import PersonalityProfile

        with pytest.raises(ValidationError):
            PersonalityProfile(
                voice="diana",
                emotion="cheerful",
                struggle_threshold=-1,
                celebration_style="moderate",
            )

    def test_personality_profile_rejects_invalid_celebration_style(self):
        from src.core.typed_config import PersonalityProfile

        with pytest.raises(ValidationError):
            PersonalityProfile(
                voice="diana",
                emotion="cheerful",
                struggle_threshold=3,
                celebration_style="invalid_style",
            )

    def test_personality_profile_immutable(self):
        from src.core.typed_config import PersonalityProfile

        p = PersonalityProfile(
            voice="diana",
            emotion="cheerful",
            struggle_threshold=3,
            celebration_style="moderate",
        )
        with pytest.raises(ValidationError):
            p.voice = "troy"


class TestModePreset:
    """Tests for ModePreset typed config."""

    def test_valid_preset(self):
        from src.core.typed_config import ModePreset

        preset = ModePreset(
            name="Structured",
            description="Detailed structured output",
            prompt="Analyze this image",
        )
        assert preset.name == "Structured"
        assert preset.prompt == "Analyze this image"

    def test_preset_requires_name(self):
        from src.core.typed_config import ModePreset

        with pytest.raises(ValidationError):
            ModePreset(
                description="desc",
                prompt="prompt",
            )


class TestModeConfig:
    """Tests for ModeConfig typed config."""

    def test_valid_mode_no_presets(self):
        from src.core.typed_config import ModeConfig

        mode = ModeConfig(
            name="Default",
            prompt="Describe the image.",
            embed=False,
        )
        assert mode.name == "Default"
        assert mode.presets == []
        assert mode.embed is False

    def test_valid_mode_with_presets(self):
        from src.core.typed_config import ModeConfig, ModePreset

        mode = ModeConfig(
            name="Formal",
            prompt="Analyze this image.",
            embed=True,
            max_tokens=500,
            temperature=0.2,
            presets=[
                ModePreset(
                    name="Structured",
                    description="Detailed output",
                    prompt="Structured analysis",
                ),
            ],
        )
        assert len(mode.presets) == 1
        assert mode.presets[0].name == "Structured"
        assert mode.max_tokens == 500

    def test_mode_defaults(self):
        from src.core.typed_config import ModeConfig

        mode = ModeConfig(name="Test", prompt="Test prompt")
        assert mode.embed is False
        assert mode.presets == []
        assert mode.max_tokens is None
        assert mode.temperature is None


class TestModeCatalog:
    """Tests for ModeCatalog (collection of modes + settings + aliases)."""

    def test_catalog_from_modes_dict(self):
        from src.core.typed_config import ModeCatalog, ModeConfig

        catalog = ModeCatalog(
            modes={
                "default": ModeConfig(
                    name="Default",
                    prompt="Describe the image.",
                ),
            },
            aliases={},
        )
        assert "default" in catalog.modes
        assert catalog.modes["default"].name == "Default"

    def test_catalog_get_mode(self):
        from src.core.typed_config import ModeCatalog, ModeConfig

        catalog = ModeCatalog(
            modes={
                "default": ModeConfig(name="Default", prompt="Describe."),
            },
            aliases={},
        )
        mode = catalog.get_mode("default")
        assert mode is not None
        assert mode.name == "Default"

    def test_catalog_get_mode_missing(self):
        from src.core.typed_config import ModeCatalog

        catalog = ModeCatalog(modes={}, aliases={})
        assert catalog.get_mode("nonexistent") is None

    def test_catalog_available_modes(self):
        from src.core.typed_config import ModeCatalog, ModeConfig

        catalog = ModeCatalog(
            modes={
                "default": ModeConfig(name="Default", prompt="D."),
                "formal": ModeConfig(name="Formal", prompt="F."),
            },
            aliases={},
        )
        assert set(catalog.available_modes()) == {"default", "formal"}

    def test_catalog_resolve_alias(self):
        from src.core.typed_config import ModeCatalog, ModeConfig

        catalog = ModeCatalog(
            modes={
                "artistic": ModeConfig(name="Artistic", prompt="A."),
            },
            aliases={"/analyze": "artistic.Critic"},
        )
        assert catalog.resolve_alias("/analyze") == "artistic.Critic"
        assert catalog.resolve_alias("/unknown") is None

    def test_catalog_settings(self):
        from src.core.typed_config import ModeCatalog, ModeConfig, ModeSettings

        catalog = ModeCatalog(
            modes={
                "default": ModeConfig(name="Default", prompt="D."),
            },
            aliases={},
            settings=ModeSettings(
                similarity_threshold=0.8,
                max_similar_images=10,
            ),
        )
        assert catalog.settings.similarity_threshold == 0.8
        assert catalog.settings.max_similar_images == 10


class TestModeSettings:
    """Tests for ModeSettings defaults."""

    def test_defaults(self):
        from src.core.typed_config import ModeSettings

        s = ModeSettings()
        assert s.similarity_threshold == 0.7
        assert s.max_similar_images == 5
        assert s.image_max_size == 1024
        assert s.supported_formats == ["jpg", "jpeg", "png", "webp"]


class TestTrailSchedule:
    """Tests for TrailSchedule typed config."""

    def test_valid_schedule(self):
        from src.core.typed_config import TrailSchedule

        schedule = TrailSchedule(
            enabled=True,
            chat_id="12345",
            poll_times=[time(9, 0), time(14, 0), time(20, 0)],
        )
        assert schedule.enabled is True
        assert schedule.chat_id == "12345"
        assert len(schedule.poll_times) == 3

    def test_schedule_defaults(self):
        from src.core.typed_config import TrailSchedule

        schedule = TrailSchedule()
        assert schedule.enabled is True
        assert schedule.chat_id is None
        assert schedule.poll_times == [time(9, 0), time(14, 0), time(20, 0)]

    def test_schedule_is_enabled_requires_chat_id(self):
        from src.core.typed_config import TrailSchedule

        # enabled=True but no chat_id => is_active() returns False
        schedule = TrailSchedule(enabled=True, chat_id=None)
        assert schedule.is_active() is False

        # enabled=True and chat_id present => is_active() returns True
        schedule2 = TrailSchedule(enabled=True, chat_id="12345")
        assert schedule2.is_active() is True

        # enabled=False => is_active() returns False regardless
        schedule3 = TrailSchedule(enabled=False, chat_id="12345")
        assert schedule3.is_active() is False

    def test_schedule_from_time_strings(self):
        from src.core.typed_config import TrailSchedule

        schedule = TrailSchedule.from_time_strings(
            enabled=True,
            chat_id="123",
            time_strings=["09:00", "14:00", "20:00"],
        )
        assert schedule.poll_times == [time(9, 0), time(14, 0), time(20, 0)]

    def test_schedule_from_time_strings_invalid_skipped(self):
        from src.core.typed_config import TrailSchedule

        schedule = TrailSchedule.from_time_strings(
            enabled=True,
            chat_id="123",
            time_strings=["09:00", "bad", "20:00"],
        )
        assert schedule.poll_times == [time(9, 0), time(20, 0)]

    def test_schedule_immutable(self):
        from src.core.typed_config import TrailSchedule

        schedule = TrailSchedule()
        with pytest.raises(ValidationError):
            schedule.enabled = False


class TestAccountabilityConfig:
    """Tests for AccountabilityConfig (collection of personality profiles)."""

    def test_valid_config(self):
        from src.core.typed_config import AccountabilityConfig, PersonalityProfile

        config = AccountabilityConfig(
            personalities={
                "gentle": PersonalityProfile(
                    voice="diana",
                    emotion="whisper",
                    struggle_threshold=5,
                    celebration_style="quiet",
                ),
                "supportive": PersonalityProfile(
                    voice="diana",
                    emotion="cheerful",
                    struggle_threshold=3,
                    celebration_style="moderate",
                ),
            },
            default_personality="supportive",
        )
        assert "gentle" in config.personalities
        assert config.default_personality == "supportive"

    def test_get_personality(self):
        from src.core.typed_config import AccountabilityConfig, PersonalityProfile

        config = AccountabilityConfig(
            personalities={
                "supportive": PersonalityProfile(
                    voice="diana",
                    emotion="cheerful",
                    struggle_threshold=3,
                    celebration_style="moderate",
                ),
            },
            default_personality="supportive",
        )
        p = config.get_personality("supportive")
        assert p is not None
        assert p.voice == "diana"

    def test_get_personality_fallback_to_default(self):
        from src.core.typed_config import AccountabilityConfig, PersonalityProfile

        config = AccountabilityConfig(
            personalities={
                "supportive": PersonalityProfile(
                    voice="diana",
                    emotion="cheerful",
                    struggle_threshold=3,
                    celebration_style="moderate",
                ),
            },
            default_personality="supportive",
        )
        p = config.get_personality("nonexistent")
        assert p is not None
        assert p.voice == "diana"  # fell back to default

    def test_get_personality_returns_none_when_no_default(self):
        from src.core.typed_config import AccountabilityConfig

        config = AccountabilityConfig(
            personalities={},
            default_personality="nonexistent",
        )
        assert config.get_personality("anything") is None
