"""Domain value objects — replace primitive obsession with validated types."""

from __future__ import annotations

import re
from typing import Iterable, Iterator, Tuple


class VoicePreferences:
    """Validated voice synthesis preferences.

    Allowed values:
        mode: voice_only, always_voice, smart, voice_on_request, text_only
        voice_name: diana, hannah, autumn, austin, daniel, troy
        emotion: cheerful, neutral, whisper
    """

    VALID_MODES = frozenset(
        {"voice_only", "always_voice", "smart", "voice_on_request", "text_only"}
    )
    VALID_VOICE_NAMES = frozenset(
        {"diana", "hannah", "autumn", "austin", "daniel", "troy"}
    )
    VALID_EMOTIONS = frozenset({"cheerful", "neutral", "whisper"})

    __slots__ = ("_mode", "_voice_name", "_emotion")

    def __init__(
        self,
        mode: str = "text_only",
        voice_name: str = "diana",
        emotion: str = "cheerful",
    ) -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(
                f"Invalid mode {mode!r}; must be one of {sorted(self.VALID_MODES)}"
            )
        if voice_name not in self.VALID_VOICE_NAMES:
            raise ValueError(
                f"Invalid voice_name {voice_name!r}; "
                f"must be one of {sorted(self.VALID_VOICE_NAMES)}"
            )
        if emotion not in self.VALID_EMOTIONS:
            raise ValueError(
                f"Invalid emotion {emotion!r}; "
                f"must be one of {sorted(self.VALID_EMOTIONS)}"
            )
        object.__setattr__(self, "_mode", mode)
        object.__setattr__(self, "_voice_name", voice_name)
        object.__setattr__(self, "_emotion", emotion)

    # --- Read-only properties ---

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def voice_name(self) -> str:
        return self._voice_name

    @property
    def emotion(self) -> str:
        return self._emotion

    # --- Immutability ---

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable; cannot set {name!r}")

    # --- Equality and hashing ---

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VoicePreferences):
            return NotImplemented
        return (
            self._mode == other._mode
            and self._voice_name == other._voice_name
            and self._emotion == other._emotion
        )

    def __hash__(self) -> int:
        return hash((self._mode, self._voice_name, self._emotion))

    def __repr__(self) -> str:
        return (
            f"VoicePreferences(mode={self._mode!r}, "
            f"voice_name={self._voice_name!r}, emotion={self._emotion!r})"
        )


class ResponseMode:
    """Validated voice response mode.

    Allowed values: voice_only, always_voice, smart, voice_on_request, text_only
    """

    VALID_VALUES = frozenset(
        {"voice_only", "always_voice", "smart", "voice_on_request", "text_only"}
    )
    _UNCONDITIONAL_VOICE = frozenset({"voice_only", "always_voice"})

    __slots__ = ("_value",)

    def __init__(self, value: str = "text_only") -> None:
        if not isinstance(value, str):
            raise TypeError(
                f"response mode must be a string, got {type(value).__name__}"
            )
        if value not in self.VALID_VALUES:
            raise ValueError(
                f"Invalid response mode {value!r}; "
                f"must be one of {sorted(self.VALID_VALUES)}"
            )
        object.__setattr__(self, "_value", value)

    @property
    def value(self) -> str:
        return self._value

    @property
    def is_voice(self) -> bool:
        """True when mode unconditionally produces voice output."""
        return self._value in self._UNCONDITIONAL_VOICE

    # --- Immutability ---

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable; cannot set {name!r}")

    # --- Equality and hashing ---

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResponseMode):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"ResponseMode({self._value!r})"


class CheckInSchedule:
    """Validated collection of HH:MM check-in times.

    Accepts one or more HH:MM strings. Stores them sorted and deduplicated.
    Validates 00:00-23:59 range.
    """

    _HH_MM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

    __slots__ = ("_times",)

    def __init__(self, *times: str) -> None:
        validated = []
        for t in times:
            if not self._HH_MM_RE.match(t):
                raise ValueError(f"Invalid time {t!r}; must match HH:MM (00:00-23:59)")
            validated.append(t)
        object.__setattr__(self, "_times", tuple(sorted(set(validated))))

    @classmethod
    def from_string(cls, value: str) -> CheckInSchedule:
        """Create from a single HH:MM string."""
        return cls(value)

    @classmethod
    def from_strings(cls, values: Iterable[str]) -> CheckInSchedule:
        """Create from a list of HH:MM strings (e.g. JSON-decoded array)."""
        return cls(*values)

    @property
    def times(self) -> Tuple[str, ...]:
        return self._times

    # --- Immutability ---

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable; cannot set {name!r}")

    # --- Equality and hashing ---

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CheckInSchedule):
            return NotImplemented
        return self._times == other._times

    def __hash__(self) -> int:
        return hash(self._times)

    # --- Container protocol ---

    def __len__(self) -> int:
        return len(self._times)

    def __iter__(self) -> Iterator[str]:
        return iter(self._times)

    def __contains__(self, item: object) -> bool:
        return item in self._times

    def __bool__(self) -> bool:
        return len(self._times) > 0

    # --- String interop ---

    def __str__(self) -> str:
        return ",".join(self._times)

    def __repr__(self) -> str:
        times_str = ", ".join(repr(t) for t in self._times)
        return f"CheckInSchedule({times_str})"
