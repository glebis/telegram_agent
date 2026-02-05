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


async def memory_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
    content = get_memory(chat_id)
    if not content or content.strip() == "":
        text = (
            "No memory set for this chat.\n\n"
            "Use <code>/memory edit &lt;text&gt;</code> to set preferences, or "
            "<code>/memory add &lt;text&gt;</code> to append."
        )
    else:
        text = f"<b>Chat Memory:</b>\n\n<pre>{escape_html(content)}</pre>"

    send_message_sync(chat_id, text, parse_mode="HTML")


async def _memory_edit(update: Update, chat_id: int, text: str) -> None:
    """Replace memory with provided text."""
    if not text.strip():
        send_message_sync(
            chat_id,
            "Usage: <code>/memory edit &lt;text&gt;</code>\n\n"
            "This replaces the entire memory content.",
            parse_mode="HTML",
        )
        return

    update_memory(chat_id, text.strip())
    send_message_sync(
        chat_id,
        "Memory updated. Claude will use this in future sessions.",
    )


async def _memory_add(update: Update, chat_id: int, text: str) -> None:
    """Append text to existing memory."""
    if not text.strip():
        send_message_sync(
            chat_id,
            "Usage: <code>/memory add &lt;text&gt;</code>\n\n"
            "This appends to existing memory.",
            parse_mode="HTML",
        )
        return

    append_memory(chat_id, text.strip())
    send_message_sync(
        chat_id,
        "Appended to memory. Claude will use this in future sessions.",
    )


async def _memory_export(update: Update, chat_id: int) -> None:
    """Send CLAUDE.md as a Telegram document."""
    path = export_memory_path(chat_id)
    if not path:
        send_message_sync(chat_id, "No memory file exists for this chat.")
        return

    try:
        import requests

        bot_token = __import__("os").getenv("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            send_message_sync(chat_id, "Bot token not configured.")
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
        send_message_sync(chat_id, "Failed to export memory file.")


async def _memory_reset(update: Update, chat_id: int) -> None:
    """Reset memory to default template."""
    reset_memory(chat_id)
    send_message_sync(
        chat_id,
        "Memory reset to default template.",
    )
