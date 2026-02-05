"""
Base utilities for bot handlers.

Contains shared functions used across handler modules:
- Telegram API helpers (sync subprocess wrappers)
- User/Chat initialization
- Claude mode cache management
"""

import json
import logging
import os
import socket
from typing import Optional

from sqlalchemy import select

from ...core.database import get_db_session
from ...models.chat import Chat
from ...models.user import User
from ...utils.lru_cache import LRUCache
from ...utils.subprocess_helper import run_python_script

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


def _run_telegram_api_sync(method: str, payload: dict) -> Optional[dict]:
    """Call Telegram Bot API using secure subprocess (bypasses async blocking)."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    try:
        script = """
import sys
import json
import os
import requests

# Read payload from stdin
data = json.load(sys.stdin)
method = data["method"]
payload = data["payload"]

# Get token from environment (not interpolated in script)
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

r = requests.post(
    f"https://api.telegram.org/bot{bot_token}/{method}",
    json=payload,
    timeout=30
)
result = r.json()
if result.get("ok"):
    print(json.dumps({"success": True, "result": result["result"]}))
else:
    print(json.dumps({"success": False, "error": result}))
"""
        result = run_python_script(
            script=script,
            input_data={"method": method, "payload": payload},
            env_vars={"TELEGRAM_BOT_TOKEN": bot_token},
            timeout=60,
        )

        if result.success:
            response = json.loads(result.stdout)
            if response.get("success"):
                return response.get("result")
            else:
                logger.warning(f"Telegram API {method} failed: {response.get('error')}")
                return None
        else:
            logger.warning(f"Telegram API {method} subprocess failed: {result.error}")
            return None
    except Exception as e:
        logger.error(f"Error calling Telegram API {method}: {e}")
        return None


def send_message_sync(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_to: int = None,
    reply_markup: dict = None,
) -> Optional[dict]:
    """
    Send a message using the Telegram HTTP API via subprocess.

    Bypasses async blocking issues.
    """
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _run_telegram_api_sync("sendMessage", payload)


def edit_message_sync(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict = None,
) -> Optional[dict]:
    """
    Edit a message using the Telegram HTTP API via subprocess.

    Bypasses async blocking issues.
    """
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _run_telegram_api_sync("editMessageText", payload)


def send_photo_sync(
    chat_id: int,
    photo_path: str,
    caption: str = None,
    parse_mode: str = "HTML",
) -> Optional[dict]:
    """
    Send a photo using the Telegram HTTP API via subprocess.

    Bypasses async blocking issues.
    """
    import os
    import subprocess

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    # Use curl with multipart/form-data
    cmd = [
        "curl",
        "-s",
        "-X",
        "POST",
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        "-F",
        f"chat_id={chat_id}",
        "-F",
        f"photo=@{photo_path}",
    ]

    if caption:
        cmd.extend(["-F", f"caption={caption}"])
    if parse_mode:
        cmd.extend(["-F", f"parse_mode={parse_mode}"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            import json

            return json.loads(result.stdout)
        else:
            logger.error(f"Telegram API sendPhoto failed: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Error sending photo via Telegram API: {e}")
        return None


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


# In-memory cache for Claude mode to avoid database deadlocks during message processing
_claude_mode_cache: LRUCache[int, bool] = LRUCache(max_size=10000)


async def init_claude_mode_cache() -> None:
    """Initialize Claude mode cache from database on startup."""
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.claude_mode.is_(True)))
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
