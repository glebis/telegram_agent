"""SQLAlchemy implementation of MessageRepository."""

import logging
from datetime import datetime
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.message import Message

logger = logging.getLogger(__name__)


class SqlAlchemyMessageRepository:
    """Concrete MessageRepository backed by SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: Message) -> Message:
        """Persist a new message and return it with ID populated."""
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def get_latest_by_chat(self, chat_id: int, limit: int = 10) -> List[Message]:
        """Get the most recent messages for a chat, newest first."""
        result = await self._session.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_older_than(self, chat_id: int, cutoff: datetime) -> int:
        """Delete messages older than cutoff for a given chat. Returns count."""
        result = await self._session.execute(
            delete(Message).where(
                Message.chat_id == chat_id,
                Message.created_at < cutoff,
            )
        )
        return result.rowcount  # type: ignore[attr-defined]
