"""
Collect Mode Service - Accumulates messages until triggered.

Allows users to send multiple files, voice messages, and text
without immediate response. Processing happens when:
- User sends /collect:go [prompt]
- User sends keyword trigger ("now respond", "process this", "go ahead")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Trigger keywords that will process collected items
TRIGGER_KEYWORDS = [
    "now respond",
    "process this",
    "go ahead",
    "обработай",  # Russian: process
    "ответь",     # Russian: respond
]


class CollectItemType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    DOCUMENT = "document"
    VIDEO_NOTE = "video_note"


@dataclass
class CollectItem:
    """A single collected item."""
    type: CollectItemType
    message_id: int
    timestamp: datetime
    # Content varies by type:
    # - TEXT: the text string
    # - IMAGE/VOICE/VIDEO/DOCUMENT: file_id or local path
    content: str
    # Optional metadata
    caption: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    duration: Optional[int] = None  # For voice/video


@dataclass
class CollectSession:
    """Active collect session for a chat."""
    chat_id: int
    user_id: int
    started_at: datetime = field(default_factory=datetime.now)
    items: list[CollectItem] = field(default_factory=list)
    # Optional prompt to use when processing
    pending_prompt: Optional[str] = None

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()

    def summary(self) -> dict[str, int]:
        """Return count by item type."""
        counts: dict[str, int] = {}
        for item in self.items:
            key = item.type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def summary_text(self) -> str:
        """Human-readable summary."""
        counts = self.summary()
        if not counts:
            return "empty"
        parts = []
        type_labels = {
            "text": "text",
            "image": "image",
            "voice": "voice",
            "video": "video",
            "document": "doc",
            "video_note": "video note",
        }
        for item_type, count in counts.items():
            label = type_labels.get(item_type, item_type)
            if count > 1:
                label += "s"
            parts.append(f"{count} {label}")
        return ", ".join(parts)


class CollectService:
    """Manages collect sessions across chats."""

    # Session timeout in seconds (1 hour)
    SESSION_TIMEOUT = 3600
    # Maximum items per session
    MAX_ITEMS = 50

    def __init__(self):
        self._sessions: dict[int, CollectSession] = {}  # chat_id -> session
        self._lock = asyncio.Lock()
        logger.info("CollectService initialized")

    async def start_session(self, chat_id: int, user_id: int) -> CollectSession:
        """Start a new collect session for a chat."""
        async with self._lock:
            # End existing session if any
            if chat_id in self._sessions:
                logger.info(f"Ending existing collect session for chat {chat_id}")

            session = CollectSession(chat_id=chat_id, user_id=user_id)
            self._sessions[chat_id] = session
            logger.info(f"Started collect session for chat {chat_id}")
            return session

    async def end_session(self, chat_id: int) -> Optional[CollectSession]:
        """End and return the collect session for a chat."""
        async with self._lock:
            session = self._sessions.pop(chat_id, None)
            if session:
                logger.info(
                    f"Ended collect session for chat {chat_id}: "
                    f"{session.item_count} items collected"
                )
            return session

    async def get_session(self, chat_id: int) -> Optional[CollectSession]:
        """Get the active collect session for a chat, if any."""
        async with self._lock:
            session = self._sessions.get(chat_id)
            if session:
                # Check for timeout
                if session.age_seconds > self.SESSION_TIMEOUT:
                    logger.info(f"Collect session for chat {chat_id} timed out")
                    del self._sessions[chat_id]
                    return None
            return session

    async def is_collecting(self, chat_id: int) -> bool:
        """Check if a chat is in collect mode."""
        session = await self.get_session(chat_id)
        return session is not None

    async def add_item(
        self,
        chat_id: int,
        item_type: CollectItemType,
        message_id: int,
        content: str,
        caption: Optional[str] = None,
        file_name: Optional[str] = None,
        mime_type: Optional[str] = None,
        duration: Optional[int] = None,
    ) -> Optional[CollectItem]:
        """Add an item to the collect session."""
        async with self._lock:
            session = self._sessions.get(chat_id)
            if not session:
                return None

            # Check max items
            if len(session.items) >= self.MAX_ITEMS:
                logger.warning(
                    f"Collect session for chat {chat_id} at max capacity "
                    f"({self.MAX_ITEMS} items)"
                )
                return None

            item = CollectItem(
                type=item_type,
                message_id=message_id,
                timestamp=datetime.now(),
                content=content,
                caption=caption,
                file_name=file_name,
                mime_type=mime_type,
                duration=duration,
            )
            session.items.append(item)
            logger.info(
                f"Added {item_type.value} to collect session for chat {chat_id} "
                f"(now {len(session.items)} items)"
            )
            return item

    async def get_status(self, chat_id: int) -> Optional[dict[str, Any]]:
        """Get status of collect session."""
        session = await self.get_session(chat_id)
        if not session:
            return None

        return {
            "active": True,
            "item_count": session.item_count,
            "summary": session.summary(),
            "summary_text": session.summary_text(),
            "started_at": session.started_at.isoformat(),
            "age_seconds": session.age_seconds,
        }

    def check_trigger_keywords(self, text: str) -> bool:
        """Check if text contains trigger keywords."""
        text_lower = text.lower().strip()
        for keyword in TRIGGER_KEYWORDS:
            if keyword in text_lower:
                return True
        return False


# Singleton instance
_collect_service: Optional[CollectService] = None


def get_collect_service() -> CollectService:
    """Get or create the collect service singleton."""
    global _collect_service
    if _collect_service is None:
        _collect_service = CollectService()
    return _collect_service
