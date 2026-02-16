"""
Claude mode cache — in-memory LRU cache for chat.claude_mode.

Moved from bot/handlers/base.py to the core layer so that both
handlers and services can import it without layer violations.
"""

import logging

from sqlalchemy import select

from ..models.chat import Chat
from ..utils.lru_cache import LRUCache
from .database import get_db_session

logger = logging.getLogger(__name__)

_claude_mode_cache: LRUCache[int, bool] = LRUCache(max_size=10000)


async def init_claude_mode_cache() -> None:
    """Initialize Claude mode cache from database on startup."""
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Chat).where(Chat.claude_mode.is_(True))
            )
            chats = result.scalars().all()
            for chat in chats:
                _claude_mode_cache[chat.chat_id] = True
            logger.info(f"Initialized Claude mode cache with {len(chats)} active chats")
    except Exception as e:
        logger.error(f"Error initializing Claude mode cache: {e}")


async def get_claude_mode(chat_id: int) -> bool:
    """Check if a chat is in Claude mode (locked session)."""
    if chat_id in _claude_mode_cache:
        return _claude_mode_cache[chat_id]

    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat_record = result.scalar_one_or_none()
            if chat_record:
                mode = getattr(chat_record, "claude_mode", False)
                _claude_mode_cache[chat_id] = mode
                return mode
            return False
    except Exception as e:
        logger.error(f"Error getting claude_mode: {e}")
        return False


async def set_claude_mode(chat_id: int, enabled: bool) -> bool:
    """Set Claude mode (locked session) for a chat."""
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat_record = result.scalar_one_or_none()
            if chat_record:
                chat_record.claude_mode = enabled
                await session.commit()
                _claude_mode_cache[chat_id] = enabled
                logger.info(f"Set claude_mode={enabled} for chat {chat_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"Error setting claude_mode: {e}")
        return False
