from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chats.id"), nullable=False
    )

    # Telegram message info
    message_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    from_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Message content
    message_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # text, photo, document, etc.
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Bot response info
    is_bot_message: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reply_to_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Associated image (if any)
    image_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("images.id"), nullable=True
    )

    # Admin tracking
    admin_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # Sent manually by admin
    admin_user: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # Admin who sent the message

    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")  # noqa: F821
    image: Mapped[Optional["Image"]] = relationship("Image")  # noqa: F821

    # Media message types (photo, voice, video, document carry file data)
    _MEDIA_TYPES = frozenset({"photo", "voice", "video", "document", "video_note"})

    # --- Domain behavior ---

    def get_content(self) -> str:
        """Return the effective text content (text preferred over caption)."""
        return self.text or self.caption or ""

    def is_from_bot(self) -> bool:
        """Check whether this message was sent by the bot."""
        return bool(self.is_bot_message)

    def is_admin_sent(self) -> bool:
        """Check whether this message was sent manually by an admin."""
        return bool(self.admin_sent)

    def is_media_type(self) -> bool:
        """Check whether this message carries media (photo/voice/video/document)."""
        return self.message_type in self._MEDIA_TYPES

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, message_id={self.message_id}, type={self.message_type})>"
