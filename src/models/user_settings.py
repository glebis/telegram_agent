"""
User settings model for voice and accountability preferences.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class UserSettings(Base, TimestampMixin):
    """User preferences for voice responses and assistant behavior."""

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Voice Settings
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    voice_model: Mapped[str] = mapped_column(
        String(50), default="diana"
    )  # diana, hannah, autumn, austin, daniel, troy
    emotion_style: Mapped[str] = mapped_column(
        String(50), default="cheerful"
    )  # cheerful, neutral, whisper
    response_mode: Mapped[str] = mapped_column(
        String(50), default="smart"
    )  # always_voice, voice_on_request, text_only, smart

    # Check-in Settings
    check_in_times: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array: ["09:00", "21:00"]
    reminder_style: Mapped[str] = mapped_column(
        String(50), default="gentle"
    )  # gentle, direct, motivational
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Privacy Settings
    privacy_level: Mapped[str] = mapped_column(
        String(50), default="private"
    )  # private, shared, public
    data_retention: Mapped[str] = mapped_column(
        String(50), default="1_year"
    )  # 1_month, 6_months, 1_year, forever

    # Health Data Consent (GDPR Art. 9 - Special Category Data)
    health_data_consent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    def __repr__(self) -> str:
        return f"<UserSettings(user_id={self.user_id}, voice={self.voice_model}, response_mode={self.response_mode})>"
