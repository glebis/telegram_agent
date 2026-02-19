"""Domain value objects — replace primitive obsession with validated types."""

from __future__ import annotations


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
        raise AttributeError(
            f"{type(self).__name__} is immutable; cannot set {name!r}"
        )

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
