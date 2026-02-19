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

    # --- Domain behavior ---

    def get_locale(self, default: str = "en") -> str:
        """Return the user's language code, or *default* if unset."""
        return self.language_code or default

    def get_display_name(self) -> str:
        """Return a human-readable display name.

        Priority: first+last name > username > 'User {user_id}'.
        """
        parts = [
            p
            for p in (self.first_name, self.last_name)
            if p  # skip None and empty strings
        ]
        if parts:
            return " ".join(parts)
        if self.username:
            return self.username
        return f"User {self.user_id}"

    def has_consent(self) -> bool:
        """Check whether GDPR consent has been given."""
        return bool(self.consent_given)

    def is_banned(self) -> bool:
        """Check whether the user is banned."""
        return bool(self.banned)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, user_id={self.user_id}, username={self.username})>"
