"""Accountability partner profile — bounded context model.

Owns: partner personality, check-in scheduling, struggle thresholds.
Split from UserSettings (issue #222).
"""

from typing import Optional

from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AccountabilityProfile(Base, TimestampMixin):
    """Per-user accountability partner configuration."""

    __tablename__ = "accountability_profiles"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    partner_personality: Mapped[str] = mapped_column(
        String(50), default="supportive"
    )
    partner_voice_override: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    check_in_time: Mapped[str] = mapped_column(String(10), default="19:00")
    struggle_threshold: Mapped[int] = mapped_column(Integer, default=3)
    celebration_style: Mapped[str] = mapped_column(String(50), default="moderate")
    auto_adjust_personality: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    # Schedule preferences (moved from UserSettings check-in group)
    check_in_times: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array: ["09:00", "21:00"]
    reminder_style: Mapped[str] = mapped_column(String(50), default="gentle")
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    def __init__(self, **kwargs):
        defaults = {
            "partner_personality": "supportive",
            "partner_voice_override": None,
            "check_in_time": "19:00",
            "struggle_threshold": 3,
            "celebration_style": "moderate",
            "auto_adjust_personality": False,
            "check_in_times": None,
            "reminder_style": "gentle",
            "timezone": "UTC",
        }
        for k, v in defaults.items():
            kwargs.setdefault(k, v)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<AccountabilityProfile(user_id={self.user_id}, "
            f"personality={self.partner_personality})>"
        )
