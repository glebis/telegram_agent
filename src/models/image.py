from typing import Optional

from sqlalchemy import BLOB, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Image(Base, TimestampMixin):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chats.id"), nullable=False
    )

    # Telegram file info
    file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_unique_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # File paths
    original_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Path to original image
    compressed_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Path to compressed image

    # Image metadata
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # jpg, png, etc.

    # AI Analysis
    analysis: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON string with LLM analysis
    mode_used: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # Mode used for analysis
    preset_used: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # Preset used for analysis

    # Vector embedding for similarity search (artistic mode only)
    embedding: Mapped[Optional[bytes]] = mapped_column(BLOB, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # Model used for embedding

    # Processing status
    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, processing, completed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="images")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Image(id={self.id}, file_unique_id={self.file_unique_id}, status={self.processing_status})>"
