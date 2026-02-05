"""
OpenCode commands.

Contains:
- /opencode - Execute prompts with OpenCode
- /opencode:new - Start new session
- /opencode:reset - Clear session
- /opencode:sessions - List all sessions
- /opencode:help - Show OpenCode command help
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ...core.authorization import AuthTier, require_tier
from ...services.opencode_service import get_opencode_service
from .base import send_message_sync
from .formatting import escape_html

logger = logging.getLogger(__name__)


@require_tier(AuthTier.USER)
async def opencode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /opencode command with :subcommand syntax."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    raw_text = update.message.text if update.message else ""
    subcommand = None
    remaining_text = ""

    if raw_text.startswith("/opencode:"):
        after = raw_text[10:]
        parts = after.split(None, 1)
        if parts:
            subcommand = parts[0].lower()
            remaining_text = parts[1] if len(parts) > 1 else ""
    else:
        remaining_text = " ".join(context.args) if context.args else ""

    logger.info(
        "OpenCode command from user %s: subcommand=%s, text_len=%d",
        user.id,
        subcommand,
        len(remaining_text),
    )

    service = get_opencode_service()

    if not service.is_available():
        send_message_sync(
            chat.id,
            "OpenCode is not installed. Install it with:\n"
            "<code>npm i -g opencode-ai</code>",
            parse_mode="HTML",
        )
        return

    if subcommand == "new":
        await _opencode_new(update, context, remaining_text)
        return
    elif subcommand == "reset":
        await _opencode_reset(update, context)
        return
    elif subcommand == "sessions":
        await _opencode_sessions(update, context)
        return
    elif subcommand == "help":
        await _opencode_help(update, context)
        return
    elif subcommand:
        send_message_sync(
            chat.id,
            f"Unknown subcommand: <code>:{subcommand}</code>\n\n"
            "Use <code>/opencode:help</code> for available commands.",
            parse_mode="HTML",
        )
        return

    if not remaining_text.strip():
        await _opencode_help(update, context)
        return

    await _execute_opencode(update, context, remaining_text.strip())


async def _execute_opencode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    force_new: bool = False,
) -> None:
    """Execute an OpenCode prompt and send the response."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    service = get_opencode_service()

    if force_new:
        service.clear_session(chat.id)

    prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
    session_id = service.get_session(chat.id)
    session_status = f"Resuming session" if session_id else "New session"

    send_message_sync(
        chat.id,
        f"<b>🔧 OpenCode</b>\n\n"
        f"<i>{escape_html(prompt_preview)}</i>\n\n"
        f"⏳ {session_status}",
        parse_mode="HTML",
    )

    response = await service.run_opencode_query(chat.id, prompt)

    if response:
        # Split long responses
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                chunk = response[i : i + 4000]
                send_message_sync(chat.id, chunk)
        else:
            send_message_sync(chat.id, response)
    else:
        send_message_sync(chat.id, "No response from OpenCode.")


async def _opencode_new(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
) -> None:
    """Start a new OpenCode session."""
    chat = update.effective_chat
    if not chat:
        return

    service = get_opencode_service()
    service.clear_session(chat.id)

    if prompt.strip():
        await _execute_opencode(update, context, prompt.strip(), force_new=True)
    else:
        send_message_sync(
            chat.id,
            "Session cleared. Send a prompt with <code>/opencode your question</code>",
            parse_mode="HTML",
        )


async def _opencode_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset OpenCode session."""
    chat = update.effective_chat
    if not chat:
        return

    service = get_opencode_service()
    service.clear_session(chat.id)
    send_message_sync(chat.id, "OpenCode session cleared.")


async def _opencode_sessions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """List OpenCode sessions."""
    chat = update.effective_chat
    if not chat:
        return

    service = get_opencode_service()
    sessions = service.list_sessions(chat.id)

    if not sessions:
        send_message_sync(chat.id, "No OpenCode sessions found.")
        return

    lines = ["<b>OpenCode Sessions</b>\n"]
    active_session = service.get_session(chat.id)

    for s in sessions[-10:]:
        sid = s.get("session_id", "unknown")
        prompt = s.get("first_prompt", "")[:50]
        marker = " ← active" if sid == active_session else ""
        lines.append(f"• <code>{sid[:12]}</code> {escape_html(prompt)}{marker}")

    send_message_sync(chat.id, "\n".join(lines), parse_mode="HTML")


async def _opencode_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show OpenCode help."""
    chat = update.effective_chat
    if not chat:
        return

    service = get_opencode_service()
    status = "✅ installed" if service.is_available() else "❌ not installed"

    send_message_sync(
        chat.id,
        f"<b>🔧 OpenCode Commands</b> ({status})\n\n"
        "<code>/opencode prompt</code> — Run a prompt\n"
        "<code>/opencode:new prompt</code> — New session + prompt\n"
        "<code>/opencode:reset</code> — Clear current session\n"
        "<code>/opencode:sessions</code> — List sessions\n"
        "<code>/opencode:help</code> — This help\n\n"
        "<i>Supports 75+ LLM providers including local models via Ollama.</i>",
        parse_mode="HTML",
    )
