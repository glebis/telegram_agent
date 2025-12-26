"""
Completion Reactions Module

Sends stickers, animations, or emojis when tasks complete.
Configurable via environment variables.
"""

import logging
import random
from pathlib import Path
from typing import Optional

from ..core.config import get_settings

logger = logging.getLogger(__name__)


async def send_completion_reaction(
    bot,
    chat_id: int,
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """
    Send a completion reaction (emoji/sticker/animation) to celebrate task completion.

    Args:
        bot: Telegram bot instance
        chat_id: Chat ID to send to
        reply_to_message_id: Optional message ID to reply to

    Returns:
        True if reaction was sent, False otherwise
    """
    settings = get_settings()

    # Check probability
    if random.random() > settings.completion_reaction_probability:
        logger.debug("Skipping completion reaction (probability check)")
        return False

    reaction_type = settings.completion_reaction_type.lower()

    if reaction_type == "none":
        return False

    try:
        if reaction_type == "emoji":
            await _send_emoji_reaction(
                bot,
                chat_id,
                settings.completion_reaction_value,
                reply_to_message_id,
            )
        elif reaction_type == "sticker":
            await _send_sticker(
                bot,
                chat_id,
                settings.completion_reaction_value,
                reply_to_message_id,
            )
        elif reaction_type == "animation":
            await _send_animation(
                bot,
                chat_id,
                settings.completion_reaction_value,
                reply_to_message_id,
            )
        else:
            logger.warning(f"Unknown completion reaction type: {reaction_type}")
            return False

        logger.info(f"Sent completion reaction: {reaction_type}")
        return True

    except Exception as e:
        logger.error(f"Failed to send completion reaction: {e}")
        return False


async def _send_emoji_reaction(
    bot,
    chat_id: int,
    emoji_config: str,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """
    Send emoji as text message or reaction.

    If emoji_config contains commas, pick one randomly.
    """
    emojis = [e.strip() for e in emoji_config.split(",")]
    emoji = random.choice(emojis)

    # Try to use reaction API (Telegram Reactions)
    # Falls back to sending as text message
    try:
        # Try reaction first (more subtle)
        if reply_to_message_id:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=reply_to_message_id,
                reaction=[{"type": "emoji", "emoji": emoji}],
            )
        else:
            # No message to react to, send as standalone
            await bot.send_message(
                chat_id=chat_id,
                text=emoji,
            )
    except Exception as e:
        # Fallback to text message
        logger.debug(f"Reaction API failed, using text: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=emoji,
            reply_to_message_id=reply_to_message_id,
        )


async def _send_sticker(
    bot,
    chat_id: int,
    sticker_config: str,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """
    Send sticker from file_id or file path.

    sticker_config can be:
    - Telegram file_id (starts with CAACAgI...)
    - File path to .webp sticker
    - Comma-separated list (random pick)
    """
    stickers = [s.strip() for s in sticker_config.split(",")]
    sticker = random.choice(stickers)

    # Check if file path
    if Path(sticker).exists():
        with open(sticker, "rb") as f:
            await bot.send_sticker(
                chat_id=chat_id,
                sticker=f,
                reply_to_message_id=reply_to_message_id,
            )
    else:
        # Assume file_id
        await bot.send_sticker(
            chat_id=chat_id,
            sticker=sticker,
            reply_to_message_id=reply_to_message_id,
        )


async def _send_animation(
    bot,
    chat_id: int,
    animation_config: str,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """
    Send animation (GIF) from file_id or file path.

    animation_config can be:
    - Telegram file_id
    - File path to .gif/.mp4
    - Comma-separated list (random pick)
    """
    animations = [a.strip() for a in animation_config.split(",")]
    animation = random.choice(animations)

    # Check if file path
    if Path(animation).exists():
        with open(animation, "rb") as f:
            await bot.send_animation(
                chat_id=chat_id,
                animation=f,
                reply_to_message_id=reply_to_message_id,
            )
    else:
        # Assume file_id
        await bot.send_animation(
            chat_id=chat_id,
            animation=animation,
            reply_to_message_id=reply_to_message_id,
        )
