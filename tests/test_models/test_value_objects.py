"""Tests for domain value objects — eliminate primitive obsession."""

import pytest

from src.models.value_objects import CheckInSchedule, ResponseMode, VoicePreferences


class TestVoicePreferences:
    """Slice 1: VoicePreferences value object."""

    # --- Valid construction ---

    def test_valid_defaults(self):
        vp = VoicePreferences()
        assert vp.mode == "text_only"
        assert vp.voice_name == "diana"
        assert vp.emotion == "cheerful"

    def test_valid_explicit(self):
        vp = VoicePreferences(mode="smart", voice_name="autumn", emotion="neutral")
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


class TestCheckInSchedule:
    """Slice 3: CheckInSchedule value object (validates HH:MM, time ranges)."""

    # --- Valid construction ---

    def test_single_time(self):
        cs = CheckInSchedule("19:00")
        assert cs.times == ("19:00",)

    def test_multiple_times(self):
        cs = CheckInSchedule("09:00", "21:00")
        assert cs.times == ("09:00", "21:00")

    def test_midnight(self):
        cs = CheckInSchedule("00:00")
        assert cs.times == ("00:00",)

    def test_end_of_day(self):
        cs = CheckInSchedule("23:59")
        assert cs.times == ("23:59",)

    def test_from_string_single(self):
        cs = CheckInSchedule.from_string("19:00")
        assert cs.times == ("19:00",)

    def test_from_strings_list(self):
        cs = CheckInSchedule.from_strings(["09:00", "21:00"])
        assert cs.times == ("09:00", "21:00")

    def test_from_strings_empty_yields_no_times(self):
        cs = CheckInSchedule.from_strings([])
        assert cs.times == ()

    # --- Sorted and deduplicated ---

    def test_times_sorted(self):
        cs = CheckInSchedule("21:00", "09:00")
        assert cs.times == ("09:00", "21:00")

    def test_duplicates_removed(self):
        cs = CheckInSchedule("09:00", "09:00", "21:00")
        assert cs.times == ("09:00", "21:00")

    # --- Invalid values rejected ---

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="HH:MM"):
            CheckInSchedule("9:00")

    def test_invalid_hour_raises(self):
        with pytest.raises(ValueError, match="HH:MM"):
            CheckInSchedule("25:00")

    def test_invalid_minute_raises(self):
        with pytest.raises(ValueError, match="HH:MM"):
            CheckInSchedule("12:60")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="HH:MM"):
            CheckInSchedule("noon")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="HH:MM"):
            CheckInSchedule("")

    def test_24_hour_raises(self):
        with pytest.raises(ValueError, match="HH:MM"):
            CheckInSchedule("24:00")

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="HH:MM"):
            CheckInSchedule("-1:00")

    # --- Equality and hashing ---

    def test_equality(self):
        a = CheckInSchedule("09:00", "21:00")
        b = CheckInSchedule("09:00", "21:00")
        assert a == b

    def test_equality_ignores_input_order(self):
        a = CheckInSchedule("21:00", "09:00")
        b = CheckInSchedule("09:00", "21:00")
        assert a == b

    def test_inequality(self):
        a = CheckInSchedule("09:00")
        b = CheckInSchedule("21:00")
        assert a != b

    def test_hashable(self):
        a = CheckInSchedule("09:00", "21:00")
        b = CheckInSchedule("21:00", "09:00")
        assert hash(a) == hash(b)

    # --- Immutability ---

    def test_immutable(self):
        cs = CheckInSchedule("19:00")
        with pytest.raises(AttributeError):
            cs.times = ("20:00",)  # type: ignore[misc]

    # --- String interop ---

    def test_str_single(self):
        cs = CheckInSchedule("19:00")
        assert str(cs) == "19:00"

    def test_str_multiple(self):
        cs = CheckInSchedule("09:00", "21:00")
        assert str(cs) == "09:00,21:00"

    def test_repr(self):
        cs = CheckInSchedule("09:00", "21:00")
        r = repr(cs)
        assert "09:00" in r
        assert "21:00" in r

    # --- Convenience ---

    def test_len(self):
        assert len(CheckInSchedule("09:00", "21:00")) == 2

    def test_iter(self):
        cs = CheckInSchedule("09:00", "21:00")
        assert list(cs) == ["09:00", "21:00"]

    def test_contains(self):
        cs = CheckInSchedule("09:00", "21:00")
        assert "09:00" in cs
        assert "15:00" not in cs

    def test_bool_true(self):
        assert bool(CheckInSchedule("09:00")) is True

    def test_bool_false(self):
        assert bool(CheckInSchedule.from_strings([])) is False
