"""Life Weeks ORM models.

LifeWeekConfig — per-user settings (birth date, notification schedule).
LifeWeekEntry — weekly reflection entries (pending/completed/skipped).
"""

from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class LifeWeekConfig(Base, TimestampMixin):
    """Per-user Life Weeks configuration."""

    __tablename__ = "life_week_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, index=True
    )
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    notification_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 0=Monday
    notification_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LifeWeekEntry(Base, TimestampMixin):
    """Individual life week reflection entry."""

    __tablename__ = "life_week_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, completed, skipped
    reflection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
