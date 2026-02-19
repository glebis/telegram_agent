"""
Message Persistence Service

Lightweight fire-and-forget persistence of incoming messages to the messages table.
All errors are caught and logged -- persistence failures must never crash message handling.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from ..core.database import get_db_session
from ..models.chat import Chat
from ..models.message import Message

logger = logging.getLogger(__name__)


async def persist_message(
    telegram_chat_id: int,
    from_user_id: Optional[int],
    message_id: int,
    text: Optional[str],
    message_type: str,
    timestamp: Optional[datetime] = None,
    chat_repo: Optional[object] = None,
    message_repo: Optional[object] = None,
) -> None:
    """Persist an incoming message to the database.

    This is designed to be called fire-and-forget after message processing.
    All exceptions are caught and logged so that persistence failures
    never crash the message handling pipeline.

    Args:
        telegram_chat_id: The Telegram chat ID (will be resolved to internal FK).
        from_user_id: The Telegram user ID of the sender.
        message_id: The Telegram message ID.
        text: The message text (or transcription for voice messages).
        message_type: Message type string (text, voice, photo, video, document, etc.).
        timestamp: Message timestamp. Defaults to now if not provided.
        chat_repo: Optional ChatRepository instance (falls back to direct DB access).
        message_repo: Optional MessageRepository instance (falls back to direct DB access).
    """
    try:
        if chat_repo is not None and message_repo is not None:
            # Use injected repositories
            chat = await chat_repo.get_by_telegram_id(telegram_chat_id)

            if chat is None:
                logger.debug(
                    f"Chat {telegram_chat_id} not found in DB, skipping message persistence"
                )
                return

            msg = Message(
                chat_id=chat.id,
                message_id=message_id,
                from_user_id=from_user_id,
                message_type=message_type,
                text=text,
                is_bot_message=False,
            )

            await message_repo.add(msg)

            logger.debug(
                f"Persisted message {message_id} (type={message_type}) "
                f"for chat {telegram_chat_id}"
            )
        else:
            # Legacy path: direct SQLAlchemy session access
            async with get_db_session() as session:
                # Resolve Telegram chat_id to internal Chat.id (FK target)
                result = await session.execute(
                    select(Chat).where(Chat.chat_id == telegram_chat_id)
                )
                chat = result.scalar_one_or_none()

                if chat is None:
                    logger.debug(
                        f"Chat {telegram_chat_id} not found in DB, skipping message persistence"
                    )
                    return

                msg = Message(
                    chat_id=chat.id,
                    message_id=message_id,
                    from_user_id=from_user_id,
                    message_type=message_type,
                    text=text,
                    is_bot_message=False,
                )

                session.add(msg)
                await session.commit()

                logger.debug(
                    f"Persisted message {message_id} (type={message_type}) "
                    f"for chat {telegram_chat_id}"
                )

    except Exception as e:
        # Fire-and-forget: log and swallow all errors
        logger.warning(
            f"Failed to persist message {message_id} for chat {telegram_chat_id}: {e}"
        )
