"""Life Weeks notification settings — bounded context model.

Owns: date_of_birth, life_weeks_enabled/day/time, reply destination.
Split from UserSettings (issue #222).
"""

from typing import Optional

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class LifeWeeksSettings(Base, TimestampMixin):
    """Per-user life-weeks visualization configuration."""

    __tablename__ = "life_weeks_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    date_of_birth: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # YYYY-MM-DD format

    life_weeks_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    life_weeks_day: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 0=Monday, 6=Sunday

    life_weeks_time: Mapped[str] = mapped_column(
        String(10), default="09:00", nullable=False
    )

    life_weeks_reply_destination: Mapped[str] = mapped_column(
        String(50), default="daily_note", nullable=False
    )

    life_weeks_custom_path: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    def __init__(self, **kwargs):
        defaults = {
            "life_weeks_enabled": False,
            "date_of_birth": None,
            "life_weeks_day": None,
            "life_weeks_time": "09:00",
            "life_weeks_reply_destination": "daily_note",
            "life_weeks_custom_path": None,
        }
        for k, v in defaults.items():
            kwargs.setdefault(k, v)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<LifeWeeksSettings(user_id={self.user_id}, "
            f"enabled={self.life_weeks_enabled})>"
        )
