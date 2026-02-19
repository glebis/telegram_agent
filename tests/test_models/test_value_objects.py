"""Tests for domain value objects — eliminate primitive obsession."""

import pytest

from src.models.value_objects import ResponseMode, VoicePreferences


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


class TestResponseMode:
    """Slice 2: ResponseMode value object."""

    # --- Valid construction ---

    def test_default(self):
        rm = ResponseMode()
        assert rm.value == "text_only"

    def test_all_valid_values(self):
        for val in (
            "voice_only",
            "always_voice",
            "smart",
            "voice_on_request",
            "text_only",
        ):
            rm = ResponseMode(val)
            assert rm.value == val

    # --- Invalid values rejected ---

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError, match="response mode"):
            ResponseMode("auto")

    def test_empty_value_raises(self):
        with pytest.raises(ValueError, match="response mode"):
            ResponseMode("")

    def test_none_coercion_raises(self):
        with pytest.raises((ValueError, TypeError)):
            ResponseMode(None)  # type: ignore[arg-type]

    # --- Equality and hashing ---

    def test_equality(self):
        assert ResponseMode("smart") == ResponseMode("smart")

    def test_inequality(self):
        assert ResponseMode("smart") != ResponseMode("text_only")

    def test_hash_consistent(self):
        assert hash(ResponseMode("smart")) == hash(ResponseMode("smart"))

    def test_usable_as_dict_key(self):
        d = {ResponseMode("smart"): 1}
        assert d[ResponseMode("smart")] == 1

    # --- Immutability ---

    def test_immutable(self):
        rm = ResponseMode("smart")
        with pytest.raises(AttributeError):
            rm.value = "text_only"  # type: ignore[misc]

    # --- String interop ---

    def test_str(self):
        rm = ResponseMode("smart")
        assert str(rm) == "smart"

    def test_repr(self):
        rm = ResponseMode("smart")
        assert "smart" in repr(rm)

    # --- Predicates ---

    def test_is_voice_true(self):
        for val in ("voice_only", "always_voice"):
            assert ResponseMode(val).is_voice is True

    def test_is_voice_false(self):
        assert ResponseMode("text_only").is_voice is False
        assert ResponseMode("voice_on_request").is_voice is False

    def test_is_voice_smart(self):
        # smart is context-dependent, not unconditionally voice
        assert ResponseMode("smart").is_voice is False
