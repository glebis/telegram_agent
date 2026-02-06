"""
Memory commands.

Contains:
- /memory — Display current CLAUDE.md content
- /memory edit <text> — Replace CLAUDE.md content
- /memory add <text> — Append text to CLAUDE.md
- /memory export — Send CLAUDE.md as Telegram document
- /memory reset — Restore default template
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ...core.authorization import AuthTier, get_user_tier
from ...core.i18n import get_user_locale_from_update, t
from ...services.workspace_service import (
    append_memory,
    export_memory_path,
    get_memory,
    reset_memory,
    update_memory,
)
from .base import initialize_user_chat, send_message_sync
from .formatting import escape_html

logger = logging.getLogger(__name__)

# Subcommands that require ADMIN tier
_ADMIN_SUBCOMMANDS = {"edit", "reset"}


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /memory command with subcommand routing.

    Subcommands:
        (none)  — show current memory
        edit    — replace memory content
        add     — append to memory
        export  — send CLAUDE.md as file
        reset   — restore default template
    """
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.message:
        return

    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )

    # Parse subcommand from message text (e.g. "/memory edit ..." or "/memory:edit ...")
    raw_text = update.message.text or ""
    # Strip the /memory command itself
    # Handle both "/memory edit text" and "/memory:edit text"
    if raw_text.startswith("/memory:"):
        remainder = raw_text[len("/memory:") :]
    elif raw_text.startswith("/memory"):
        remainder = raw_text[len("/memory") :].lstrip()
    else:
        remainder = ""

    # Split into subcommand and arguments
    parts = remainder.split(None, 1)
    subcommand = parts[0].lower() if parts else ""
    args_text = parts[1] if len(parts) > 1 else ""

    # Check authorization for sensitive subcommands
    locale = get_user_locale_from_update(update)
    if subcommand in _ADMIN_SUBCOMMANDS:
        tier = get_user_tier(user.id, chat.id)
        if tier < AuthTier.ADMIN:
            send_message_sync(chat.id, t("memory.not_authorized", locale))
            return

    if subcommand == "edit":
        await _memory_edit(update, chat.id, args_text)
    elif subcommand == "add":
        await _memory_add(update, chat.id, args_text)
    elif subcommand == "export":
        await _memory_export(update, chat.id)
    elif subcommand == "reset":
        await _memory_reset(update, chat.id)
    elif subcommand == "":
        await _memory_show(update, chat.id)
    else:
        # Unknown subcommand — treat as show
        await _memory_show(update, chat.id)


async def _memory_show(update: Update, chat_id: int) -> None:
    """Display current memory content."""
    locale = get_user_locale_from_update(update)
    content = get_memory(chat_id)
    if not content or content.strip() == "":
        text = t("memory.show_empty", locale).strip()
    else:
        title = t("memory.show_title", locale)
        text = f"{title}\n\n<pre>{escape_html(content)}</pre>"

    send_message_sync(chat_id, text, parse_mode="HTML")


async def _memory_edit(update: Update, chat_id: int, text: str) -> None:
    """Replace memory with provided text."""
    locale = get_user_locale_from_update(update)
    if not text.strip():
        send_message_sync(
            chat_id,
            t("memory.edit_usage", locale).strip(),
            parse_mode="HTML",
        )
        return

    update_memory(chat_id, text.strip())
    send_message_sync(chat_id, t("memory.edit_success", locale))


async def _memory_add(update: Update, chat_id: int, text: str) -> None:
    """Append text to existing memory."""
    locale = get_user_locale_from_update(update)
    if not text.strip():
        send_message_sync(
            chat_id,
            t("memory.add_usage", locale).strip(),
            parse_mode="HTML",
        )
        return

    append_memory(chat_id, text.strip())
    send_message_sync(chat_id, t("memory.add_success", locale))


async def _memory_export(update: Update, chat_id: int) -> None:
    """Send CLAUDE.md as a Telegram document."""
    locale = get_user_locale_from_update(update)
    path = export_memory_path(chat_id)
    if not path:
        send_message_sync(chat_id, t("memory.export_empty", locale))
        return

    try:
        import requests

        bot_token = __import__("os").getenv("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            send_message_sync(chat_id, t("memory.bot_token_error", locale))
            return

        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendDocument",
                data={"chat_id": chat_id},
                files={"document": ("CLAUDE.md", f, "text/markdown")},
                timeout=30,
            )
    except Exception as e:
        logger.error("Failed to export memory for chat %s: %s", chat_id, e)
        send_message_sync(chat_id, t("memory.export_error", locale))


async def _memory_reset(update: Update, chat_id: int) -> None:
    """Reset memory to default template."""
    locale = get_user_locale_from_update(update)
    reset_memory(chat_id)
    send_message_sync(chat_id, t("memory.reset_success", locale))
