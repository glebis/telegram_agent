from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .keyboard_config import KeyboardConfig


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # GDPR consent fields
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Admin fields
    banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Relationships
    chats: Mapped[List["Chat"]] = relationship(  # noqa: F821
        "Chat", back_populates="user", cascade="all, delete-orphan"
    )
    claude_sessions: Mapped[List["ClaudeSession"]] = relationship(  # noqa: F821
        "ClaudeSession", back_populates="user", cascade="all, delete-orphan"
    )
    keyboard_config: Mapped[Optional["KeyboardConfig"]] = relationship(
        "KeyboardConfig",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, user_id={self.user_id}, username={self.username})>"
