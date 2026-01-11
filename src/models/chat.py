from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    chat_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="private"
    )  # private, group, supergroup, channel
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Mode system
    current_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default="default"
    )
    current_preset: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Claude Code mode - when True, all messages route to Claude
    claude_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Claude Code model preference (haiku, sonnet, opus)
    claude_model: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="sonnet")

    # Auto-forward voice messages to Claude Code (default: True)
    auto_forward_voice: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Settings
    settings: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON string for chat-specific settings

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="chats")
    images: Mapped[List["Image"]] = relationship(
        "Image", back_populates="chat", cascade="all, delete-orphan"
    )
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, chat_id={self.chat_id}, mode={self.current_mode})>"
