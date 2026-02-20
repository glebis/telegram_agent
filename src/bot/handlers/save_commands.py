"""
Save command — /save <url> [destination]

Explicitly save a URL to the Obsidian vault.
Delegates to the existing handle_link_message flow.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ...core.i18n import get_user_locale_from_update
from ...utils.error_reporting import handle_errors

logger = logging.getLogger(__name__)

VALID_DESTINATIONS = {"inbox", "research", "daily", "media"}


@handle_errors("save_command")
async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /save command — save a URL to the Obsidian vault."""
    message = update.message
    if not message:
        return

    args = context.args or []

    if not args:
        await message.reply_text(
            "<b>Save a link to your vault</b>\n\n"
            "Usage:\n"
            "  /save &lt;url&gt; — save to inbox\n"
            "  /save &lt;url&gt; research — save to Research/\n"
            "  /save &lt;url&gt; daily — save to Daily/\n"
            "  /save &lt;url&gt; media — save to media/\n\n"
            "Or just paste a URL directly in chat.",
            parse_mode="HTML",
        )
        return

    url = args[0]
    destination = args[1].lower() if len(args) > 1 else "inbox"

    if destination not in VALID_DESTINATIONS:
        await message.reply_text(
            f"Unknown destination: <code>{destination}</code>\n"
            f"Valid options: {', '.join(sorted(VALID_DESTINATIONS))}",
            parse_mode="HTML",
        )
        return

    locale = get_user_locale_from_update(update)

    from ..message_handlers import handle_link_message

    logger.info(f"Save command: url={url[:80]}, destination={destination}")
    await handle_link_message(message, [url], destination, locale=locale)
