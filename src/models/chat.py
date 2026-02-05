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
    claude_model: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="sonnet"
    )

    # Auto-forward voice messages to Claude Code (default: True)
    auto_forward_voice: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Transcript correction level: "none", "vocabulary", "full" (default: vocabulary)
    transcript_correction_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="vocabulary"
    )

    # Show model selection buttons in Claude completion keyboard (default: False)
    show_model_buttons: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Show transcript messages after voice/video transcription (default: True)
    show_transcript: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Pending auto-forward to Claude - when True, next text/voice message auto-forwards to Claude
    pending_auto_forward_claude: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Voice synthesis preferences
    voice_response_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="text_only"
    )  # always_voice, smart, voice_on_request, text_only
    voice_name: Mapped[str] = mapped_column(
        String(20), nullable=False, default="diana"
    )  # diana, hannah, autumn, austin, daniel, troy
    voice_emotion: Mapped[str] = mapped_column(
        String(20), nullable=False, default="cheerful"
    )  # cheerful, neutral, whisper
    voice_verbosity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="full"
    )  # full, short, brief
    tts_provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", server_default=""
    )  # "", "groq", "openai" — empty = system default

    # Virtual Accountability Partner Settings
    accountability_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # Master toggle for virtual accountability partner
    partner_personality: Mapped[str] = mapped_column(
        String(50), nullable=False, default="supportive"
    )  # gentle, supportive, direct, assertive, tough_love
    partner_voice_override: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # User can override auto-selected voice
    check_in_time: Mapped[str] = mapped_column(
        String(10), nullable=False, default="19:00"
    )  # HH:MM format for daily check-in
    struggle_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )  # Consecutive misses before struggle alert
    celebration_style: Mapped[str] = mapped_column(
        String(50), nullable=False, default="moderate"
    )  # quiet, moderate, enthusiastic
    auto_adjust_personality: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # AI suggests personality changes based on behavior

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
