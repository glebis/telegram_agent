from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class KeyboardConfig(Base, TimestampMixin):
    """Per-user keyboard configuration for reply keyboards."""

    __tablename__ = "keyboard_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    # JSON array of button rows: [[{emoji, label, action}, ...], ...]
    buttons_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Whether reply keyboard is enabled
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Resize keyboard (smaller buttons)
    resize_keyboard: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # One-time keyboard (hides after use)
    one_time: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="keyboard_config")

    def __repr__(self) -> str:
        return f"<KeyboardConfig(id={self.id}, user_id={self.user_id}, enabled={self.enabled})>"
