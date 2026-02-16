"""
Base utilities for bot handlers.

Contains shared functions used across handler modules:
- User/Chat initialization
- Claude mode cache management

Telegram API helpers (send_message_sync, edit_message_sync, etc.) have been
moved to src/utils/telegram_api — re-exported here for backward compatibility.
"""

import logging
import os
import socket
from typing import Optional

from sqlalchemy import select

from ...core.database import get_db_session
from ...core.mode_cache import (  # noqa: F401 — re-exports
    _claude_mode_cache,
    get_claude_mode,
    init_claude_mode_cache,
    set_claude_mode,
)
from ...models.chat import Chat
from ...models.user import User
from ...utils.telegram_api import (  # noqa: F401 — re-exports
    _run_telegram_api_sync,
    edit_message_sync,
    send_message_sync,
    send_photo_sync,
)

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """Get the local network IP address for mobile access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_voice_url(session_id: str, project: str = "vault") -> str:
    """Generate the voice server URL for continuing conversation with voice."""
    base_url = os.environ.get("VOICE_SERVER_URL", "https://vox.realitytouch.org")
    return f"{base_url}?session={session_id}&project={project}"


async def initialize_user_chat(
    user_id: int,
    chat_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    language_code: Optional[str] = None,
) -> bool:
    """Initialize user and chat in database if they don't exist."""
    try:
        async with get_db_session() as session:
            # Check if user exists
            user_result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                user = User(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    language_code=language_code,
                )
                session.add(user)
                await session.flush()
                logger.info(f"Created new user: {user_id} ({username})")
            elif language_code and user.language_code != language_code:
                user.language_code = language_code

            # Warm the locale cache
            if language_code:
                from ...core.i18n import set_user_locale

                set_user_locale(user_id, language_code)

            # Check if chat exists
            chat_result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            chat_record: Optional[Chat] = chat_result.scalar_one_or_none()

            if not chat_record:
                chat_record = Chat(
                    chat_id=chat_id, user_id=user.id, current_mode="default"
                )
                session.add(chat_record)
                logger.info(f"Created new chat: {chat_id}")

            await session.commit()
            return True

    except Exception as e:
        logger.error(f"Error initializing user/chat: {e}")
        return False


# Claude mode cache and helpers are now defined in src/core/mode_cache.py
# and re-exported above for backward compatibility.
