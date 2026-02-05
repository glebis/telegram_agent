"""
Accountability partner models for social accountability features.
"""

from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AccountabilityPartner(Base, TimestampMixin):
    """Accountability partnership between two users."""

    __tablename__ = "accountability_partners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_settings.user_id"), nullable=False
    )

    # Partner details
    partner_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    partner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Sharing settings
    overall_level: Mapped[str] = mapped_column(
        String(50), default="progress_only"
    )  # progress_only, summary, full_transparency

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<AccountabilityPartner(id={self.id}, user_id={self.user_id}, partner={self.partner_telegram_id}, level={self.overall_level})>"


class PartnerTrackerOverride(Base, TimestampMixin):
    """Per-tracker sharing overrides for accountability partners."""

    __tablename__ = "partner_tracker_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partnership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accountability_partners.id"), nullable=False
    )
    tracker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trackers.id"), nullable=False
    )

    # Sharing level override
    share_level: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # private, progress_only, summary, full_transparency

    def __repr__(self) -> str:
        return f"<PartnerTrackerOverride(partnership={self.partnership_id}, tracker={self.tracker_id}, level={self.share_level})>"


class PartnerNotificationSchedule(Base, TimestampMixin):
    """Notification schedule for accountability partners."""

    __tablename__ = "partner_notification_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partnership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accountability_partners.id"), nullable=False
    )

    # Notification settings
    notification_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # daily_update, weekly_digest, milestone, struggle
    schedule: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # Time string or cron-like
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<PartnerNotificationSchedule(partnership={self.partnership_id}, type={self.notification_type}, enabled={self.enabled})>"


class PartnerQuietHours(Base, TimestampMixin):
    """Quiet hours configuration for accountability partners."""

    __tablename__ = "partner_quiet_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partnership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accountability_partners.id"), nullable=False
    )

    # Quiet hours
    start_time: Mapped[str] = mapped_column(String(10), nullable=False)  # HH:MM format
    end_time: Mapped[str] = mapped_column(String(10), nullable=False)  # HH:MM format
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    def __repr__(self) -> str:
        return f"<PartnerQuietHours(partnership={self.partnership_id}, {self.start_time}-{self.end_time})>"


class PartnerPermission(Base, TimestampMixin):
    """Granular permissions for accountability partners."""

    __tablename__ = "partner_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partnership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accountability_partners.id"), nullable=False
    )

    # Permission
    permission_key: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # see_progress, see_notes, request_checkin, etc
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<PartnerPermission(partnership={self.partnership_id}, key={self.permission_key}, enabled={self.enabled})>"


class PartnerNotification(Base, TimestampMixin):
    """History of notifications sent to accountability partners."""

    __tablename__ = "partner_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partnership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accountability_partners.id"), nullable=False
    )

    # Notification details
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Delivery status
    delivered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    read: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    def __repr__(self) -> str:
        return f"<PartnerNotification(id={self.id}, partnership={self.partnership_id}, type={self.notification_type})>"
