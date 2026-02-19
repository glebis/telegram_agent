"""Voice synthesis settings — bounded context model.

Owns: voice_enabled, voice_model, emotion_style, response_mode.
Split from UserSettings (issue #222).
"""

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class VoiceSettings(Base, TimestampMixin):
    """Per-user voice synthesis configuration."""

    __tablename__ = "voice_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    voice_model: Mapped[str] = mapped_column(String(50), default="diana")
    emotion_style: Mapped[str] = mapped_column(String(50), default="cheerful")
    response_mode: Mapped[str] = mapped_column(String(50), default="smart")

    def __init__(self, **kwargs):
        defaults = {
            "voice_enabled": True,
            "voice_model": "diana",
            "emotion_style": "cheerful",
            "response_mode": "smart",
        }
        for k, v in defaults.items():
            kwargs.setdefault(k, v)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<VoiceSettings(user_id={self.user_id}, "
            f"voice={self.voice_model}, mode={self.response_mode})>"
        )
