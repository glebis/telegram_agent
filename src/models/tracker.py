"""
Tracker models for habit tracking, medication, values, and commitments.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Tracker(Base, TimestampMixin):
    """
    A tracker for habits, medications, values, or commitments.
    """

    __tablename__ = "trackers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_settings.user_id"), nullable=False
    )

    # Tracker details
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # medication, habit, value, commitment
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Scheduling
    check_frequency: Mapped[str] = mapped_column(
        String(50), default="daily"
    )  # daily, weekly, custom
    check_time: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # HH:MM format

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Tracker(id={self.id}, user_id={self.user_id}, type={self.type}, name={self.name})>"


class CheckIn(Base, TimestampMixin):
    """Record of a check-in for a tracker."""

    __tablename__ = "check_ins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_settings.user_id"), nullable=False
    )
    tracker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trackers.id"), nullable=False
    )

    # Check-in data
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # completed, skipped, partial
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamp is from TimestampMixin.created_at

    def __repr__(self) -> str:
        return f"<CheckIn(id={self.id}, tracker_id={self.tracker_id}, status={self.status})>"
