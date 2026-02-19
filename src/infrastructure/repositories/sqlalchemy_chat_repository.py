"""SQLAlchemy implementation of ChatRepository."""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chat import Chat

logger = logging.getLogger(__name__)


class SqlAlchemyChatRepository:
    """Concrete ChatRepository backed by SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_chat_id: int) -> Optional[Chat]:
        """Look up a chat by Telegram chat ID."""
        result = await self._session.execute(
            select(Chat).where(Chat.chat_id == telegram_chat_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> List[Chat]:
        """Get all chats belonging to a user."""
        result = await self._session.execute(
            select(Chat).where(Chat.user_id == user_id)
        )
        return list(result.scalars().all())
