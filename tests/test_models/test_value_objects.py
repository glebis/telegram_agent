"""Tests for domain value objects — eliminate primitive obsession."""

import pytest

from src.models.value_objects import VoicePreferences


class TestVoicePreferences:
    """Slice 1: VoicePreferences value object."""

    # --- Valid construction ---

    def test_valid_defaults(self):
        vp = VoicePreferences()
        assert vp.mode == "text_only"
        assert vp.voice_name == "diana"
        assert vp.emotion == "cheerful"

    def test_valid_explicit(self):
        vp = VoicePreferences(
            mode="smart", voice_name="autumn", emotion="neutral"
        )
        assert vp.mode == "smart"
        assert vp.voice_name == "autumn"
        assert vp.emotion == "neutral"

    def test_all_valid_modes(self):
        for mode in (
            "voice_only",
            "always_voice",
            "smart",
            "voice_on_request",
            "text_only",
        ):
            vp = VoicePreferences(mode=mode)
            assert vp.mode == mode

    def test_all_valid_voice_names(self):
        for name in ("diana", "hannah", "autumn", "austin", "daniel", "troy"):
            vp = VoicePreferences(voice_name=name)
            assert vp.voice_name == name

    def test_all_valid_emotions(self):
        for emotion in ("cheerful", "neutral", "whisper"):
            vp = VoicePreferences(emotion=emotion)
            assert vp.emotion == emotion

    # --- Invalid values rejected ---

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            VoicePreferences(mode="loud")

    def test_invalid_voice_name_raises(self):
        with pytest.raises(ValueError, match="voice_name"):
            VoicePreferences(voice_name="siri")

    def test_invalid_emotion_raises(self):
        with pytest.raises(ValueError, match="emotion"):
            VoicePreferences(emotion="angry")

    def test_empty_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            VoicePreferences(mode="")

    # --- Equality and hashing ---

    def test_equality_same_values(self):
        a = VoicePreferences(mode="smart", voice_name="diana", emotion="neutral")
        b = VoicePreferences(mode="smart", voice_name="diana", emotion="neutral")
        assert a == b

    def test_inequality_different_values(self):
        a = VoicePreferences(mode="smart")
        b = VoicePreferences(mode="text_only")
        assert a != b

    def test_hashable(self):
        vp = VoicePreferences(mode="smart", voice_name="diana", emotion="neutral")
        assert hash(vp) == hash(
            VoicePreferences(mode="smart", voice_name="diana", emotion="neutral")
        )

    def test_usable_in_set(self):
        a = VoicePreferences(mode="smart")
        b = VoicePreferences(mode="smart")
        assert len({a, b}) == 1

    # --- Immutability ---

    def test_immutable(self):
        vp = VoicePreferences()
        with pytest.raises(AttributeError):
            vp.mode = "smart"  # type: ignore[misc]

    # --- Repr ---

    def test_repr(self):
        vp = VoicePreferences(mode="smart", voice_name="diana", emotion="cheerful")
        r = repr(vp)
        assert "smart" in r
        assert "diana" in r
        assert "cheerful" in r
