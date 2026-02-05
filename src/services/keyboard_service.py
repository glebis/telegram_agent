"""
Keyboard Service - Manages per-user reply keyboards.

This service handles loading keyboard configurations, building ReplyKeyboardMarkup,
and mapping button text back to commands.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup

from ..core.database import get_db_session
from ..models.chat import Chat
from ..models.keyboard_config import KeyboardConfig
from ..models.user import User

logger = logging.getLogger(__name__)


class KeyboardService:
    """Service for managing user reply keyboards."""

    def __init__(self):
        self._config_cache: Dict[int, Dict] = {}  # user_id -> config
        self._default_config: Optional[Dict] = None
        self._load_default_config()

    def _load_default_config(self) -> None:
        """Load default keyboard config from YAML."""
        config_path = Path(__file__).parent.parent.parent / "config" / "keyboard.yaml"
        try:
            with open(config_path, "r") as f:
                self._default_config = yaml.safe_load(f)
                logger.info(f"Loaded keyboard config from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load keyboard config: {e}")
            self._default_config = self._get_fallback_config()

    def _get_fallback_config(self) -> Dict:
        """Fallback config if YAML fails to load."""
        return {
            "default_keyboard": {
                "enabled": True,
                "resize_keyboard": True,
                "one_time": False,
                "rows": [
                    [
                        {"emoji": "💬", "label": "Claude", "action": "/claude"},
                        {"emoji": "🆕", "label": "New", "action": "/claude:new"},
                    ],
                    [
                        {"emoji": "⚙️", "label": "Settings", "action": "/settings"},
                        {"emoji": "📋", "label": "Menu", "action": "/menu"},
                    ],
                ],
            },
            "available_buttons": {},
            "command_categories": {},
        }

    def get_default_keyboard_config(self) -> Dict:
        """Get the default keyboard configuration."""
        if self._default_config:
            return self._default_config.get("default_keyboard", {})
        return self._get_fallback_config()["default_keyboard"]

    def get_collect_keyboard_config(self) -> Dict:
        """Get the collect mode keyboard configuration."""
        if self._default_config:
            return self._default_config.get("collect_keyboard", {})
        # Fallback collect keyboard
        return {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [
                    {"emoji": "▶️", "label": "Go", "action": "/collect:go"},
                    {"emoji": "⏹️", "label": "Cancel", "action": "/collect:stop"},
                    {"emoji": "🗑️", "label": "Clear", "action": "/collect:clear"},
                ]
            ],
        }

    def get_post_collect_keyboard_config(self) -> Dict:
        """Get the post-collect keyboard configuration (after processing)."""
        if self._default_config:
            return self._default_config.get("post_collect_keyboard", {})
        # Fallback post-collect keyboard
        return {
            "enabled": True,
            "resize_keyboard": True,
            "one_time": False,
            "rows": [
                [
                    {
                        "emoji": "📎",
                        "label": "New Collection",
                        "action": "/collect:start",
                    },
                    {"emoji": "🚪", "label": "Exit Collect", "action": "/collect:exit"},
                ]
            ],
        }

    async def get_user_config(self, user_id: int) -> Dict:
        """
        Get keyboard config for a user, creating default if needed.

        Args:
            user_id: Telegram user ID

        Returns:
            Keyboard configuration dict
        """
        # Check cache first
        if user_id in self._config_cache:
            return self._config_cache[user_id]

        try:
            async with get_db_session() as session:
                # Get user's DB id from telegram user_id
                result = await session.execute(
                    select(User).where(User.user_id == user_id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    # User not in DB yet, return default
                    return self.get_default_keyboard_config()

                # Get keyboard config
                result = await session.execute(
                    select(KeyboardConfig).where(KeyboardConfig.user_id == user.id)
                )
                config = result.scalar_one_or_none()

                if config:
                    parsed = {
                        "enabled": config.enabled,
                        "resize_keyboard": config.resize_keyboard,
                        "one_time": config.one_time,
                        "rows": json.loads(config.buttons_json),
                    }
                    self._config_cache[user_id] = parsed
                    return parsed
        except Exception as e:
            logger.error(f"Error getting keyboard config for user {user_id}: {e}")

        return self.get_default_keyboard_config()

    async def save_user_config(self, user_id: int, config: Dict) -> bool:
        """
        Save keyboard config for a user.

        Args:
            user_id: Telegram user ID
            config: Keyboard configuration dict

        Returns:
            True if saved successfully
        """
        try:
            async with get_db_session() as session:
                # Get user's DB id
                result = await session.execute(
                    select(User).where(User.user_id == user_id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    logger.warning(
                        f"Cannot save keyboard config: user {user_id} not found"
                    )
                    return False

                # Get or create config
                result = await session.execute(
                    select(KeyboardConfig).where(KeyboardConfig.user_id == user.id)
                )
                kb_config = result.scalar_one_or_none()

                if not kb_config:
                    kb_config = KeyboardConfig(user_id=user.id, buttons_json="[]")
                    session.add(kb_config)

                kb_config.buttons_json = json.dumps(config.get("rows", []))
                kb_config.enabled = config.get("enabled", True)
                kb_config.resize_keyboard = config.get("resize_keyboard", True)
                kb_config.one_time = config.get("one_time", False)

                await session.commit()

                # Update cache
                self._config_cache[user_id] = config
                logger.info(f"Saved keyboard config for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error saving keyboard config for user {user_id}: {e}")
            return False

    async def reset_user_config(self, user_id: int) -> bool:
        """
        Reset user's keyboard config to default.

        Args:
            user_id: Telegram user ID

        Returns:
            True if reset successfully
        """
        # Clear from cache
        self._config_cache.pop(user_id, None)

        try:
            async with get_db_session() as session:
                # Get user's DB id
                result = await session.execute(
                    select(User).where(User.user_id == user_id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    return True  # No user = no config to reset

                # Delete existing config
                result = await session.execute(
                    select(KeyboardConfig).where(KeyboardConfig.user_id == user.id)
                )
                kb_config = result.scalar_one_or_none()

                if kb_config:
                    await session.delete(kb_config)
                    await session.commit()
                    logger.info(f"Reset keyboard config for user {user_id}")

                return True
        except Exception as e:
            logger.error(f"Error resetting keyboard config for user {user_id}: {e}")
            return False

    @staticmethod
    def _resolve_button_label(button: Dict, locale: Optional[str] = None) -> str:
        """Resolve button label, preferring i18n key over raw label.

        Args:
            button: Button dict with optional label_key and label fields.
            locale: Locale code for translation.

        Returns:
            Resolved label string.
        """
        label_key = button.get("label_key")
        if label_key:
            from ..core.i18n import t

            resolved = t(label_key, locale)
            # If t() returns the raw key, fall back to label field
            if resolved != label_key:
                return resolved
        return button.get("label", "")

    def _build_keyboard_rows(
        self, rows: List, locale: Optional[str] = None
    ) -> List[List[KeyboardButton]]:
        """Build keyboard button rows with i18n-resolved labels.

        Args:
            rows: List of button row dicts from config.
            locale: Locale code for translation.

        Returns:
            List of KeyboardButton rows.
        """
        keyboard: List[List[KeyboardButton]] = []
        for row in rows:
            keyboard_row: List[KeyboardButton] = []
            for button in row:
                emoji = button.get("emoji", "")
                label = self._resolve_button_label(button, locale)
                text = f"{emoji} {label}".strip()
                keyboard_row.append(KeyboardButton(text=text))
            if keyboard_row:
                keyboard.append(keyboard_row)
        return keyboard

    async def build_reply_keyboard(
        self, user_id: int, locale: Optional[str] = None
    ) -> Optional[ReplyKeyboardMarkup]:
        """
        Build ReplyKeyboardMarkup for a user.

        Args:
            user_id: Telegram user ID
            locale: Locale code for i18n label resolution

        Returns:
            ReplyKeyboardMarkup or None if disabled
        """
        config = await self.get_user_config(user_id)

        if not config.get("enabled", True):
            return None

        rows = config.get("rows", [])
        if not rows:
            return None

        keyboard = self._build_keyboard_rows(rows, locale)

        if not keyboard:
            return None

        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=config.get("resize_keyboard", True),
            one_time_keyboard=config.get("one_time", False),
        )

    def build_collect_keyboard(
        self, locale: Optional[str] = None
    ) -> ReplyKeyboardMarkup:
        """Build the collect mode keyboard."""
        config = self.get_collect_keyboard_config()
        keyboard = self._build_keyboard_rows(config.get("rows", []), locale)

        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=config.get("resize_keyboard", True),
            one_time_keyboard=config.get("one_time", False),
        )

    def build_post_collect_keyboard(
        self, locale: Optional[str] = None
    ) -> ReplyKeyboardMarkup:
        """Build the post-collect keyboard (shown after processing)."""
        config = self.get_post_collect_keyboard_config()
        keyboard = self._build_keyboard_rows(config.get("rows", []), locale)

        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=config.get("resize_keyboard", True),
            one_time_keyboard=config.get("one_time", False),
        )

    def _match_button_text(self, btn: Dict, text: str) -> bool:
        """Check if button text matches, trying all supported locales.

        Args:
            btn: Button config dict.
            text: User's button text to match.

        Returns:
            True if the text matches this button in any locale.
        """
        from ..core.i18n import SUPPORTED_LOCALES

        # Check raw label (backward compat + user-customized configs)
        raw_text = f"{btn.get('emoji', '')} {btn.get('label', '')}".strip()
        if text == raw_text:
            return True

        # Check i18n labels across all locales
        label_key = btn.get("label_key")
        if label_key:
            from ..core.i18n import t

            for locale in SUPPORTED_LOCALES:
                resolved = t(label_key, locale)
                if resolved != label_key:
                    i18n_text = f"{btn.get('emoji', '')} {resolved}".strip()
                    if text == i18n_text:
                        return True

        return False

    def get_action_for_button_text(self, text: str) -> Optional[str]:
        """
        Map button text back to action command.

        Checks all supported locales so translated button labels
        correctly map back to their action commands.

        Args:
            text: Button text (e.g., "💬 Claude")

        Returns:
            Action command (e.g., "/claude") or None
        """
        text = text.strip()

        # Check available buttons from config
        if self._default_config:
            buttons = self._default_config.get("available_buttons", {})
            for key, btn in buttons.items():
                if self._match_button_text(btn, text):
                    return btn.get("action")

        # Check default keyboard rows
        default_kb = self.get_default_keyboard_config()
        for row in default_kb.get("rows", []):
            for btn in row:
                if self._match_button_text(btn, text):
                    return btn.get("action")

        # Check collect keyboard rows
        collect_kb = self.get_collect_keyboard_config()
        for row in collect_kb.get("rows", []):
            for btn in row:
                if self._match_button_text(btn, text):
                    return btn.get("action")

        # Check post-collect keyboard rows
        post_collect_kb = self.get_post_collect_keyboard_config()
        for row in post_collect_kb.get("rows", []):
            for btn in row:
                if self._match_button_text(btn, text):
                    return btn.get("action")

        return None

    def get_available_buttons(self) -> Dict[str, Dict[str, Any]]:
        """Get all available buttons for customization."""
        if self._default_config:
            return self._default_config.get("available_buttons", {})
        return {}

    def get_command_categories(self) -> Dict[str, Dict[str, Any]]:
        """Get command categories for /menu."""
        if self._default_config:
            return self._default_config.get("command_categories", {})
        return {}

    def clear_cache(self, user_id: Optional[int] = None) -> None:
        """
        Clear config cache.

        Args:
            user_id: Specific user to clear, or None for all
        """
        if user_id:
            self._config_cache.pop(user_id, None)
            logger.debug(f"Cleared keyboard cache for user {user_id}")
        else:
            self._config_cache.clear()
            logger.debug("Cleared all keyboard cache")


# Global instance
_keyboard_service: Optional[KeyboardService] = None


def get_keyboard_service() -> KeyboardService:
    """Get the keyboard service singleton."""
    global _keyboard_service
    if _keyboard_service is None:
        _keyboard_service = KeyboardService()
    return _keyboard_service


# =============================================================================
# Auto-forward voice to Claude settings (#13)
# =============================================================================


async def get_auto_forward_voice(chat_id: int) -> bool:
    """
    Get auto_forward_voice setting for a chat.

    Args:
        chat_id: Telegram chat ID

    Returns:
        True if auto-forward is enabled (default), False otherwise
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()

            if not chat:
                # Default is True for new chats
                return True

            return chat.auto_forward_voice
    except Exception as e:
        logger.error(f"Error getting auto_forward_voice for chat {chat_id}: {e}")
        # Default to True on error
        return True


async def set_auto_forward_voice(chat_id: int, enabled: bool) -> bool:
    """
    Set auto_forward_voice setting for a chat.

    Args:
        chat_id: Telegram chat ID
        enabled: True to enable auto-forward, False to disable

    Returns:
        True if setting was saved successfully
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()

            if not chat:
                logger.warning(
                    f"Cannot set auto_forward_voice: chat {chat_id} not found"
                )
                return False

            chat.auto_forward_voice = enabled
            await session.commit()

            logger.info(f"Set auto_forward_voice={enabled} for chat {chat_id}")
            return True
    except Exception as e:
        logger.error(f"Error setting auto_forward_voice for chat {chat_id}: {e}")
        return False


# =============================================================================
# Voice verbosity level settings
# =============================================================================

VALID_VOICE_VERBOSITY_LEVELS = ("full", "short", "brief")


async def get_voice_verbosity(chat_id: int) -> str:
    """
    Get voice_verbosity setting for a chat.

    Args:
        chat_id: Telegram chat ID

    Returns:
        Verbosity level: "full", "short", or "brief" (default: "full")
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()
            if not chat:
                return "full"
            return chat.voice_verbosity or "full"
    except Exception as e:
        logger.error(f"Error getting voice_verbosity for chat {chat_id}: {e}")
        return "full"


async def set_voice_verbosity(chat_id: int, level: str) -> bool:
    """
    Set voice_verbosity setting for a chat.

    Args:
        chat_id: Telegram chat ID
        level: "full", "short", or "brief"

    Returns:
        True if setting was saved successfully
    """
    if level not in VALID_VOICE_VERBOSITY_LEVELS:
        logger.warning(f"Invalid voice verbosity level: {level}")
        return False

    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()
            if not chat:
                logger.warning(f"Cannot set voice_verbosity: chat {chat_id} not found")
                return False

            chat.voice_verbosity = level
            await session.commit()
            logger.info(f"Set voice_verbosity={level} for chat {chat_id}")
            return True
    except Exception as e:
        logger.error(f"Error setting voice_verbosity for chat {chat_id}: {e}")
        return False


# =============================================================================
# Transcript correction level settings (#12)
# =============================================================================

VALID_CORRECTION_LEVELS = ("none", "vocabulary", "full")


async def get_transcript_correction_level(chat_id: int) -> str:
    """
    Get transcript_correction_level setting for a chat.

    Args:
        chat_id: Telegram chat ID

    Returns:
        Correction level: "none", "vocabulary", or "full" (default: "vocabulary")
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()

            if not chat:
                return "vocabulary"  # Default

            return chat.transcript_correction_level or "vocabulary"
    except Exception as e:
        logger.error(
            f"Error getting transcript_correction_level for chat {chat_id}: {e}"
        )
        return "vocabulary"


async def set_transcript_correction_level(chat_id: int, level: str) -> bool:
    """
    Set transcript_correction_level setting for a chat.

    Args:
        chat_id: Telegram chat ID
        level: "none", "vocabulary", or "full"

    Returns:
        True if setting was saved successfully
    """
    if level not in VALID_CORRECTION_LEVELS:
        logger.warning(f"Invalid correction level: {level}")
        return False

    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()

            if not chat:
                logger.warning(
                    f"Cannot set transcript_correction_level: chat {chat_id} not found"
                )
                return False

            chat.transcript_correction_level = level
            await session.commit()

            logger.info(f"Set transcript_correction_level={level} for chat {chat_id}")
            return True
    except Exception as e:
        logger.error(
            f"Error setting transcript_correction_level for chat {chat_id}: {e}"
        )
        return False


# =============================================================================
# Show transcript setting
# =============================================================================

# In-memory cache to avoid database deadlocks during buffer processing.
# The message buffer flushes from an async timer callback where SQLite
# queries can deadlock.  This mirrors the _admin_cache pattern used by
# claude_code_service.is_claude_code_admin().
_show_transcript_cache: Dict[int, bool] = {}


async def init_show_transcript_cache() -> None:
    """Pre-populate the show_transcript cache from DB at startup.

    Must be called during bot initialization (outside the message-buffer
    timer callback context) so that get_show_transcript never needs to
    hit the async DB from the buffer context.
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat))
            chats = result.scalars().all()
            for chat in chats:
                _show_transcript_cache[chat.chat_id] = chat.show_transcript
            logger.info(f"Initialized show_transcript cache with {len(chats)} chats")
    except Exception as e:
        logger.error(f"Error initializing show_transcript cache: {e}")


async def get_show_transcript(chat_id: int) -> bool:
    """
    Get show_transcript setting for a chat.

    Returns cached value or default (True). Never hits the async DB
    from the message-buffer timer callback context to avoid deadlocks.

    Args:
        chat_id: Telegram chat ID

    Returns:
        True if transcripts should be shown (default), False otherwise
    """
    # Return cached value, or default True for unknown chats
    return _show_transcript_cache.get(chat_id, True)


async def set_show_transcript(chat_id: int, enabled: bool) -> bool:
    """
    Set show_transcript setting for a chat.

    Args:
        chat_id: Telegram chat ID
        enabled: True to show transcripts, False to hide

    Returns:
        True if setting was saved successfully
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()

            if not chat:
                logger.warning(f"Cannot set show_transcript: chat {chat_id} not found")
                return False

            chat.show_transcript = enabled
            await session.commit()

            _show_transcript_cache[chat_id] = enabled
            logger.info(f"Set show_transcript={enabled} for chat {chat_id}")
            return True
    except Exception as e:
        logger.error(f"Error setting show_transcript for chat {chat_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Whisper use user locale setting (opt-in, default: False = always "en")
# ---------------------------------------------------------------------------

_whisper_use_locale_cache: dict[int, bool] = {}


async def init_whisper_use_locale_cache() -> None:
    """Initialize whisper_use_locale cache from database at startup."""
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat))
            chats = result.scalars().all()
            for chat in chats:
                _whisper_use_locale_cache[chat.chat_id] = getattr(
                    chat, "whisper_use_locale", False
                )
            logger.info(f"Initialized whisper_use_locale cache with {len(chats)} chats")
    except Exception as e:
        logger.error(f"Error initializing whisper_use_locale cache: {e}")


async def get_whisper_use_locale(chat_id: int) -> bool:
    """
    Get whisper_use_locale setting for a chat.

    Returns cached value or default (False). When True, Whisper STT uses
    the user's locale for transcription; when False, always uses "en".

    Args:
        chat_id: Telegram chat ID

    Returns:
        True if user locale should be used, False for English (default)
    """
    return _whisper_use_locale_cache.get(chat_id, False)


async def set_whisper_use_locale(chat_id: int, enabled: bool) -> bool:
    """
    Set whisper_use_locale setting for a chat.

    Args:
        chat_id: Telegram chat ID
        enabled: True to use user locale, False for English

    Returns:
        True if setting was saved successfully
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Chat).where(Chat.chat_id == chat_id))
            chat = result.scalar_one_or_none()

            if not chat:
                logger.warning(
                    f"Cannot set whisper_use_locale: chat {chat_id} not found"
                )
                return False

            chat.whisper_use_locale = enabled
            await session.commit()

            _whisper_use_locale_cache[chat_id] = enabled
            logger.info(f"Set whisper_use_locale={enabled} for chat {chat_id}")
            return True
    except Exception as e:
        logger.error(f"Error setting whisper_use_locale for chat {chat_id}: {e}")
        return False
