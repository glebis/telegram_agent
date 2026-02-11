"""
Collect Mode Service - Accumulates messages until triggered.

Allows users to send multiple files, voice messages, and text
without immediate response. Processing happens when:
- User sends /collect:go [prompt]
- User sends keyword trigger ("now respond", "process this", "go ahead")

Sessions are persisted to database to survive bot restarts.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import select

from src.utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)

# Trigger keywords that will process collected items
TRIGGER_KEYWORDS = [
    "now respond",
    "process this",
    "go ahead",
    "обработай",  # Russian: process
    "ответь",  # Russian: respond
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
    transcription: Optional[str] = None  # For voice/video transcriptions

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "type": self.type.value,
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "caption": self.caption,
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "duration": self.duration,
            "transcription": self.transcription,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CollectItem":
        """Create from dict."""
        return cls(
            type=CollectItemType(data["type"]),
            message_id=data["message_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            content=data["content"],
            caption=data.get("caption"),
            file_name=data.get("file_name"),
            mime_type=data.get("mime_type"),
            duration=data.get("duration"),
            transcription=data.get("transcription"),
        )


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

    def summary_text(self, locale: str = "en") -> str:
        """Human-readable summary."""
        from ..core.i18n import t

        counts = self.summary()
        if not counts:
            return t("collect.item_empty", locale)
        parts = []
        for item_type, count in counts.items():
            parts.append(t(f"collect.item_{item_type}", locale, count=count))
        return ", ".join(parts)

    def to_items_json(self) -> str:
        """Convert items to JSON string."""
        return json.dumps([item.to_dict() for item in self.items])

    @classmethod
    def from_db(cls, db_session) -> "CollectSession":
        """Create from database model."""
        items = []
        if db_session.items_json:
            try:
                items_data = json.loads(db_session.items_json)
                items = [CollectItem.from_dict(d) for d in items_data]
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error parsing items_json: {e}")

        return cls(
            chat_id=db_session.chat_id,
            user_id=db_session.user_id,
            started_at=(
                db_session.started_at.replace(tzinfo=None)
                if db_session.started_at
                else datetime.now()
            ),
            items=items,
            pending_prompt=db_session.pending_prompt,
        )


class CollectService:
    """Manages collect sessions across chats with database persistence."""

    # Session timeout in seconds (1 hour)
    SESSION_TIMEOUT = 3600
    # Maximum items per session
    MAX_ITEMS = 50

    def __init__(self):
        self._sessions: dict[int, CollectSession] = {}  # chat_id -> session (cache)
        self._lock = asyncio.Lock()
        self._db_loaded = False
        self._db_loading = False  # Prevent concurrent loads
        logger.info("CollectService initialized")

    async def initialize(self) -> None:
        """Initialize the service by loading sessions from database.

        Call this at startup to pre-load sessions before any message processing.
        This avoids SQLite deadlocks when loading from buffer context.
        """
        await self._load_from_db()

    async def _load_from_db(self) -> None:
        """Load active sessions from database on first access."""
        if self._db_loaded or self._db_loading:
            return

        self._db_loading = True
        logger.info("Loading collect sessions from database...")

        try:
            from ..core.database import get_db_session
            from ..models.collect_session import CollectSession as DBCollectSession

            async with get_db_session() as session:
                result = await session.execute(
                    select(DBCollectSession).where(DBCollectSession.is_active == True)
                )
                db_sessions = result.scalars().all()

                for db_sess in db_sessions:
                    # Check if session is expired
                    if db_sess.started_at:
                        age = (
                            datetime.now() - db_sess.started_at.replace(tzinfo=None)
                        ).total_seconds()
                        if age > self.SESSION_TIMEOUT:
                            # Mark as inactive
                            db_sess.is_active = False
                            await session.commit()
                            logger.info(
                                f"Expired collect session for chat {db_sess.chat_id}"
                            )
                            continue

                    collect_session = CollectSession.from_db(db_sess)
                    self._sessions[db_sess.chat_id] = collect_session
                    logger.info(
                        f"Loaded collect session from DB: chat={db_sess.chat_id}, "
                        f"items={len(collect_session.items)}"
                    )

            self._db_loaded = True
            self._db_loading = False
            logger.info(
                f"Loaded {len(self._sessions)} active collect sessions from database"
            )

        except Exception as e:
            logger.error(f"Error loading collect sessions from DB: {e}", exc_info=True)
            self._db_loaded = True  # Don't retry on error
            self._db_loading = False

    async def _save_to_db(self, chat_id: int) -> None:
        """Save session to database."""
        try:
            from ..core.database import get_db_session
            from ..models.collect_session import CollectSession as DBCollectSession

            session = self._sessions.get(chat_id)
            if not session:
                return

            async with get_db_session() as db:
                # Check if exists
                result = await db.execute(
                    select(DBCollectSession).where(DBCollectSession.chat_id == chat_id)
                )
                db_sess = result.scalar_one_or_none()

                if db_sess:
                    # Update existing
                    db_sess.items_json = session.to_items_json()
                    db_sess.pending_prompt = session.pending_prompt
                    db_sess.is_active = True
                else:
                    # Create new
                    db_sess = DBCollectSession(
                        chat_id=chat_id,
                        user_id=session.user_id,
                        started_at=session.started_at,
                        items_json=session.to_items_json(),
                        pending_prompt=session.pending_prompt,
                        is_active=True,
                    )
                    db.add(db_sess)

                await db.commit()
                logger.info(
                    f"Saved collect session to DB: chat={chat_id}, items={len(session.items)}"
                )

        except Exception as e:
            logger.error(f"Error saving collect session to DB: {e}", exc_info=True)

    async def _delete_from_db(self, chat_id: int) -> None:
        """Mark session as inactive in database."""
        try:
            from ..core.database import get_db_session
            from ..models.collect_session import CollectSession as DBCollectSession

            async with get_db_session() as db:
                result = await db.execute(
                    select(DBCollectSession).where(DBCollectSession.chat_id == chat_id)
                )
                db_sess = result.scalar_one_or_none()

                if db_sess:
                    db_sess.is_active = False
                    await db.commit()
                    logger.info(
                        f"Marked collect session inactive in DB: chat={chat_id}"
                    )

        except Exception as e:
            logger.error(f"Error deleting collect session from DB: {e}", exc_info=True)

    async def start_session(self, chat_id: int, user_id: int) -> CollectSession:
        """Start a new collect session for a chat."""
        await self._load_from_db()

        async with self._lock:
            # End existing session if any
            if chat_id in self._sessions:
                logger.info(f"Ending existing collect session for chat {chat_id}")

            session = CollectSession(chat_id=chat_id, user_id=user_id)
            self._sessions[chat_id] = session
            logger.info(f"Started collect session for chat {chat_id}")

        # Save to DB in background task to avoid SQLite deadlock
        # when called from message buffer's timer callback context
        create_tracked_task(self._save_to_db(chat_id), name=f"collect_save_{chat_id}")
        return session

    async def end_session(self, chat_id: int) -> Optional[CollectSession]:
        """End and return the collect session for a chat."""
        await self._load_from_db()

        async with self._lock:
            session = self._sessions.pop(chat_id, None)
            if session:
                logger.info(
                    f"Ended collect session for chat {chat_id}: "
                    f"{session.item_count} items collected"
                )

        # Mark as inactive in DB in background task to avoid SQLite deadlock
        # when called from message buffer's timer callback context
        if session:
            create_tracked_task(
                self._delete_from_db(chat_id), name=f"collect_delete_{chat_id}"
            )

        return session

    async def get_session(self, chat_id: int) -> Optional[CollectSession]:
        """Get the active collect session for a chat, if any."""
        await self._load_from_db()

        async with self._lock:
            session = self._sessions.get(chat_id)
            if session:
                # Check for timeout
                if session.age_seconds > self.SESSION_TIMEOUT:
                    logger.info(f"Collect session for chat {chat_id} timed out")
                    del self._sessions[chat_id]
                    # Mark as inactive in DB (don't await inside lock)
                    create_tracked_task(
                        self._delete_from_db(chat_id), name=f"collect_delete_{chat_id}"
                    )
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
        transcription: Optional[str] = None,
    ) -> Optional[CollectItem]:
        """Add an item to the collect session."""
        await self._load_from_db()

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
                transcription=transcription,
            )
            session.items.append(item)
            logger.info(
                f"Added {item_type.value} to collect session for chat {chat_id} "
                f"(now {len(session.items)} items)"
            )

        # Save to DB in background task to avoid SQLite deadlock
        # when called from message buffer's timer callback context
        create_tracked_task(self._save_to_db(chat_id), name=f"collect_save_{chat_id}")
        return item

    async def get_status(
        self, chat_id: int, locale: str = "en"
    ) -> Optional[dict[str, Any]]:
        """Get status of collect session."""
        session = await self.get_session(chat_id)
        if not session:
            return None

        return {
            "active": True,
            "item_count": session.item_count,
            "summary": session.summary(),
            "summary_text": session.summary_text(locale),
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
