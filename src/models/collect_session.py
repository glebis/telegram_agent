"""
Database model for persisting collect sessions.

This allows collect mode to survive bot restarts.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class CollectSession(Base, TimestampMixin):
    """
    Persisted collect session for a chat.

    Stores the active collect session state so it survives bot restarts.
    Items are stored as JSON in the items_json field.
    """

    __tablename__ = "collect_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # JSON array of CollectItem dicts
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Optional pending prompt
    pending_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Whether session is active
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<CollectSession(id={self.id}, chat_id={self.chat_id}, "
            f"is_active={self.is_active})>"
        )
