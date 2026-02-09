"""
Claude Code commands.

Contains:
- /claude - Execute prompts with Claude Code
- /claude:new - Start new session
- /claude:reset - Reset session and kill stuck processes
- /claude:lock - Lock mode (all messages go to Claude)
- /claude:unlock - Unlock mode
- /claude:sessions - List all sessions
- /claude:help - Show Claude command help
- /meta - Execute prompts in telegram_agent directory
- execute_claude_prompt - Main execution function
"""

import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from telegram import Update
from telegram.ext import ContextTypes

from ...core.authorization import AuthTier, require_tier
from ...core.config import PROJECT_ROOT, get_settings
from ...core.i18n import get_user_locale_from_update, t
from ...utils.session_emoji import format_session_id
from .base import (
    edit_message_sync,
    get_claude_mode,
    get_voice_url,
    initialize_user_chat,
    send_message_sync,
    set_claude_mode,
)
from .formatting import escape_html, markdown_to_telegram_html, split_message

logger = logging.getLogger(__name__)


# =============================================================================
# New Session Trigger Detection (#14)
# =============================================================================

# Trigger phrases that start a new session (case-insensitive)
NEW_SESSION_TRIGGERS = [
    "new session",
    "start new session",
    "fresh session",
    "новая сессия",  # Russian
]


def detect_new_session_trigger(text: str) -> dict:
    """
    Detect if text starts with a 'new session' trigger phrase.

    Args:
        text: The message text to check

    Returns:
        dict with:
            - triggered: bool - True if trigger phrase detected
            - prompt: str - Text after the trigger phrase (or original text if not triggered)
    """
    if not text:
        return {"triggered": False, "prompt": text or ""}

    text_lower = text.lower().strip()

    for trigger in NEW_SESSION_TRIGGERS:
        if text_lower.startswith(trigger):
            # Extract the prompt after the trigger phrase
            remainder = text[len(trigger) :].strip()
            # Handle newlines - take everything after trigger
            remainder = remainder.lstrip("\n").strip()
            return {"triggered": True, "prompt": remainder}

    return {"triggered": False, "prompt": text}


def _format_work_summary(stats: dict) -> str:
    """Format work statistics into human-readable summary."""
    if not stats:
        return ""

    parts = []

    # Duration
    duration = stats.get("duration", "")
    if duration:
        parts.append(f"⏱️ {duration}")

    # Tool usage summary
    tool_counts = stats.get("tool_counts", {})
    if tool_counts:
        # Format key tools
        tool_summary = []
        if tool_counts.get("Read"):
            tool_summary.append(f"📖 {tool_counts['Read']} reads")
        if tool_counts.get("Write") or tool_counts.get("Edit"):
            writes = tool_counts.get("Write", 0) + tool_counts.get("Edit", 0)
            tool_summary.append(f"✍️ {writes} edits")
        if tool_counts.get("Grep") or tool_counts.get("Glob"):
            searches = tool_counts.get("Grep", 0) + tool_counts.get("Glob", 0)
            tool_summary.append(f"🔍 {searches} searches")
        if tool_counts.get("Bash"):
            tool_summary.append(f"⚡ {tool_counts['Bash']} commands")

        if tool_summary:
            parts.append(" · ".join(tool_summary))

    # Web activity
    web_fetches = stats.get("web_fetches", [])
    if web_fetches:
        parts.append(f"🌐 {len(web_fetches)} web fetches")

    # Skills used
    skills = stats.get("skills_used", [])
    if skills:
        skills_str = ", ".join(skills)
        parts.append(f"🎯 Skills: {skills_str}")

    if not parts:
        return ""

    return "\n\n<i>" + " · ".join(parts) + "</i>"


async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude command with :subcommand syntax."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    # Parse :subcommand from raw message text
    raw_text = update.message.text if update.message else ""
    subcommand = None
    remaining_text = ""

    if raw_text.startswith("/claude:"):
        after_claude = raw_text[8:]
        parts = after_claude.split(None, 1)
        if parts:
            subcommand = parts[0].lower()
            remaining_text = parts[1] if len(parts) > 1 else ""
    else:
        remaining_text = " ".join(context.args) if context.args else ""

    logger.info(
        f"Claude command from user {user.id}: subcommand={subcommand}, "
        f"text_len={len(remaining_text)}"
    )

    # Check if user is admin
    from ...services.claude_code_service import (
        get_claude_code_service,
        is_claude_code_admin,
    )

    if not await is_claude_code_admin(chat.id):
        if update.message:
            locale = get_user_locale_from_update(update)
            await update.message.reply_text(t("claude.no_permission", locale))
        return

    # Route to subcommand handlers
    if subcommand == "new":
        await _claude_new(update, context, remaining_text)
        return
    elif subcommand == "reset":
        await _claude_reset(update, context)
        return
    elif subcommand == "lock":
        await _claude_lock(update, context)
        return
    elif subcommand == "unlock":
        await _claude_unlock(update, context)
        return
    elif subcommand == "sessions":
        await _claude_sessions(update, context)
        return
    elif subcommand == "help":
        await _claude_help(update, context)
        return
    elif subcommand:
        if update.message:
            locale = get_user_locale_from_update(update)
            await update.message.reply_text(
                t("claude.unknown_subcommand", locale, sub=subcommand),
                parse_mode="HTML",
            )
        return

    # Initialize user and chat
    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )

    prompt = remaining_text.strip() if remaining_text else None

    if not prompt:
        # Show help and session options
        service = get_claude_code_service()
        active_session_id = await service.get_active_session(chat.id)

        last_prompt = None
        if active_session_id:
            sessions = await service.get_user_sessions(chat.id, limit=1)
            if sessions:
                last_prompt = sessions[0].last_prompt

        is_locked = await get_claude_mode(chat.id)

        from ..keyboard_utils import get_keyboard_utils

        keyboard_utils = get_keyboard_utils()
        locale = get_user_locale_from_update(update)
        reply_markup = keyboard_utils.create_claude_action_keyboard(
            has_active_session=bool(active_session_id),
            is_locked=is_locked,
            locale=locale,
        )

        if active_session_id:
            session_display = format_session_id(active_session_id)
            prompt_preview = (last_prompt or "No prompt")[:40]
            lock_label = (
                f"🔒 {t('claude.status_mode_locked', locale)}"
                if is_locked
                else f"🔓 {t('claude.status_mode_unlocked', locale)}"
            )
            send_hint = (
                t("claude.status_send_locked", locale)
                if is_locked
                else t("claude.status_send_unlocked", locale)
            )
            status_text = (
                f"<b>🤖 {t('claude.status_title', locale)}</b>\n\n"
                f"▶️ {t('claude.status_session', locale, session=session_display)}\n"
                f"{t('claude.status_last', locale, prompt=prompt_preview)}\n"
                f"Mode: {lock_label}\n\n"
                f"{send_hint}"
            )
        else:
            status_text = (
                f"<b>🤖 {t('claude.status_title', locale)}</b>\n\n"
                f"{t('claude.status_no_session', locale)}\n"
                f"{t('claude.status_work_dir', locale)}\n\n"
                f"{t('claude.status_send_hint', locale)}"
            )

        if update.message:
            await update.message.reply_text(
                status_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        return

    # Buffer the prompt for potential follow-up messages
    from ...services.message_buffer import get_message_buffer

    buffer = get_message_buffer()
    await buffer.add_claude_command(update, context, prompt)

    logger.info(
        f"Buffered /claude prompt for chat {chat.id}, "
        f"waiting for potential follow-up messages"
    )


async def _claude_new(
    update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str = ""
) -> None:
    """Handle /claude:new - start a new Claude Code session."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude new session for chat {chat.id}")

    from sqlalchemy import update as sql_update

    from ...core.database import get_db_session
    from ...models.chat import Chat
    from ...services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()
    await service.end_session(chat.id)
    await set_claude_mode(chat.id, True)  # Lock mode ON - next message goes to Claude

    # Set pending_auto_forward_claude flag - next message will start a fresh session
    async with get_db_session() as session:
        await session.execute(
            sql_update(Chat)
            .where(Chat.chat_id == chat.id)
            .values(pending_auto_forward_claude=True)
        )
        await session.commit()

    if prompt.strip():
        await execute_claude_prompt(update, context, prompt.strip(), force_new=True)
    else:
        if update.message:
            locale = get_user_locale_from_update(update)
            await update.message.reply_text(
                f"🆕 🔒 <b>{t('claude.new_session_ready', locale)}</b>\n\n"
                f"{t('claude.new_send_hint', locale)}\n\n"
                f"{t('claude.new_unlock_hint', locale)}",
                parse_mode="HTML",
            )
    logger.info(f"New session requested, lock mode ON for chat {chat.id}")


async def _claude_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:sessions - list and manage sessions."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude sessions for chat {chat.id}")

    from ...services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()
    sessions = await service.get_user_sessions(chat.id)
    active_session = await service.get_active_session(chat.id)

    if not sessions:
        if update.message:
            locale = get_user_locale_from_update(update)
            await update.message.reply_text(
                t("claude.no_sessions", locale),
                parse_mode="HTML",
            )
        return

    from ..keyboard_utils import get_keyboard_utils

    keyboard_utils = get_keyboard_utils()
    locale = get_user_locale_from_update(update)
    reply_markup = keyboard_utils.create_claude_sessions_keyboard(
        sessions, active_session, locale=locale
    )

    if update.message:
        await update.message.reply_text(
            f"<b>{t('claude.sessions_title', locale)}</b> ({len(sessions)})\n\n"
            f"{t('claude.sessions_select', locale)}",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


async def _claude_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:reset - reset session and kill stuck processes."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude reset for chat {chat.id}")

    from ...services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()

    session_ended = await service.end_session(chat.id)
    await set_claude_mode(chat.id, False)

    # Kill stuck Claude processes
    killed_processes = 0
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*--resume"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                pid = pid.strip()
                if not pid.isdigit():
                    logger.warning(f"Invalid PID skipped: {pid[:20]}")
                    continue
                try:
                    subprocess.run(["kill", "-15", pid], capture_output=True, timeout=5)
                    killed_processes += 1
                    logger.info(f"Killed stuck Claude process: {pid}")
                except Exception as e:
                    logger.warning(f"Failed to kill process {pid}: {e}")
    except Exception as e:
        logger.warning(f"Error checking for stuck processes: {e}")

    locale = get_user_locale_from_update(update)
    status_parts = []
    if session_ended:
        status_parts.append(t("claude.reset_session_cleared", locale))
    else:
        status_parts.append(t("claude.reset_no_session", locale))

    if killed_processes > 0:
        status_parts.append(
            t("claude.reset_processes_killed", locale, n=killed_processes)
        )

    if update.message:
        await update.message.reply_text(
            f"🔄 <b>{t('claude.reset_title', locale)}</b>\n\n• "
            + "\n• ".join(status_parts),
            parse_mode="HTML",
        )


async def _claude_lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:lock - enable locked mode."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude lock for chat {chat.id}")

    from ...services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()
    latest = await service.get_latest_session(chat.id)

    if not latest:
        if update.message:
            locale = get_user_locale_from_update(update)
            await update.message.reply_text(
                t("claude.no_session_found", locale),
                parse_mode="HTML",
            )
        return

    session_id, last_used, is_active = latest

    if not is_active:
        await service.reactivate_session(chat.id, session_id)
        logger.info(f"Reactivated session {session_id[:8]}... for lock")

    await set_claude_mode(chat.id, True)

    from ..keyboard_utils import get_keyboard_utils

    keyboard_utils = get_keyboard_utils()
    locale = get_user_locale_from_update(update)

    if update.message:
        session_display = format_session_id(session_id)

        idle_time = datetime.utcnow() - last_used if last_used else timedelta(0)
        idle_minutes = int(idle_time.total_seconds() // 60)

        if last_used:
            if idle_minutes < 60:
                time_info = t("claude.time_minutes_ago", locale, n=idle_minutes)
            else:
                hours = idle_minutes // 60
                time_info = (
                    t("claude.time_hours_ago", locale, n=hours)
                    if hours < 24
                    else t("claude.time_days_ago", locale, n=hours // 24)
                )
        else:
            time_info = t("claude.time_unknown", locale)

        warning = ""
        if idle_minutes > 30:
            warning = f"\n⚠️ <i>{t('claude.locked_idle_warning', locale, time=time_info)}</i>\n"

        await update.message.reply_text(
            f"🔒 <b>{t('claude.locked_title', locale)}</b>\n\n"
            f"{t('claude.locked_session', locale, session=session_display)}\n"
            f"{t('claude.locked_last_used', locale, time=time_info)}{warning}\n"
            f"{t('claude.locked_all_messages', locale)}\n\n"
            f"{t('claude.new_unlock_hint', locale)}",
            parse_mode="HTML",
            reply_markup=keyboard_utils.create_claude_locked_keyboard(locale=locale),
        )
    logger.info(f"Claude mode locked for chat {chat.id}")


async def _claude_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:unlock - disable locked mode."""
    chat = update.effective_chat

    if not chat:
        return

    logger.info(f"Claude unlock for chat {chat.id}")

    await set_claude_mode(chat.id, False)

    if update.message:
        locale = get_user_locale_from_update(update)
        await update.message.reply_text(
            f"🔓 <b>{t('claude.unlocked_title', locale)}</b>\n\n"
            f"{t('claude.unlocked_normal', locale)}",
            parse_mode="HTML",
        )
    logger.info(f"Claude mode unlocked for chat {chat.id}")


async def _claude_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:help - show Claude command help."""
    if update.message:
        locale = get_user_locale_from_update(update)
        await update.message.reply_text(
            t("claude.help_text", locale),
            parse_mode="HTML",
        )


@require_tier(AuthTier.OWNER)
async def meta_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /meta command - execute prompts in telegram_agent directory (owner only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    from ...services.claude_code_service import get_claude_code_service

    # Initialize user and chat
    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )

    # Get the prompt from command args
    prompt = " ".join(context.args) if context.args else ""

    if not prompt:
        if update.message:
            locale = get_user_locale_from_update(update)
            await update.message.reply_text(
                t("claude.meta_help", locale),
                parse_mode="HTML",
            )
        return

    logger.info(f"Meta command from user {user.id}: prompt_len={len(prompt)}")

    # Use telegram_agent directory
    telegram_agent_dir = str(PROJECT_ROOT)

    # Check if this is a reply to a previous bot message
    # If so, try to continue that session instead of forcing new
    is_reply = update.message and update.message.reply_to_message is not None

    if is_reply and update.message.reply_to_message:
        # Extract reply context to get session_id
        from ...services.reply_context import get_reply_context_service

        reply_service = get_reply_context_service()
        reply_msg_id = update.message.reply_to_message.message_id
        reply_ctx = reply_service.get_context(chat.id, reply_msg_id)

        if reply_ctx and reply_ctx.session_id:
            # Continue the session from the reply
            context.user_data["force_session_id"] = reply_ctx.session_id
            force_new = False
            logger.info(
                f"Meta command replying to session {reply_ctx.session_id[:8]}..."
            )
        elif update.message.reply_to_message.from_user.is_bot:
            # Reply to bot message but no session in cache - try to restore from DB
            service = get_claude_code_service()
            active_session = await service.get_active_session(chat.id)
            if active_session:
                context.user_data["force_session_id"] = active_session
                force_new = False
                logger.info(
                    f"Meta command restored session {active_session[:8]}... from DB"
                )
            else:
                force_new = True
        else:
            force_new = True
    else:
        force_new = True

    logger.info(f"Meta command force_new={force_new}")

    await execute_claude_prompt(
        update=update,
        context=context,
        prompt=prompt,
        force_new=force_new,
        custom_cwd=telegram_agent_dir,
    )


def _is_path_in_safe_directory(file_path: str) -> bool:
    """Check if a file path is within a safe directory."""
    try:
        resolved = Path(file_path).resolve()
        settings = get_settings()

        safe_directories = [
            Path(settings.vault_path).expanduser(),
            Path(settings.vault_temp_images_dir).expanduser(),
            PROJECT_ROOT / "data",
            PROJECT_ROOT / "outputs",
            Path.home() / "Desktop",
            Path.home() / "Downloads",
            Path("/tmp"),
            Path("/private/tmp"),
        ]

        for safe_dir in safe_directories:
            try:
                safe_resolved = safe_dir.resolve()
                if resolved.is_relative_to(safe_resolved):
                    return True
            except (ValueError, RuntimeError):
                continue

        logger.warning(f"File path outside safe directories blocked: {file_path}")
        return False
    except Exception as e:
        logger.error(f"Error validating file path {file_path}: {e}")
        return False


def _get_vault_relative_path(file_path: str) -> Optional[str]:
    """
    Get the relative path from vault root if the file is in the vault.

    Returns:
        Relative path like "Claude-Drafts/note.md" or None if not in vault.
    """
    try:
        settings = get_settings()
        vault_path = Path(settings.vault_path).expanduser().resolve()
        resolved = Path(file_path).resolve()

        if resolved.is_relative_to(vault_path):
            return str(resolved.relative_to(vault_path))
        return None
    except (ValueError, RuntimeError):
        return None


def _transform_vault_paths_in_text(text: str) -> str:
    """
    Transform full vault paths in text to clickable wikilinks.

    Replaces paths like /Users/server/Research/vault/Claude-Drafts/note.md
    with [[Claude-Drafts/note]] which gets converted to clickable deep links
    by markdown_to_telegram_html().
    """
    import re

    settings = get_settings()
    vault_path = Path(settings.vault_path).expanduser().resolve()
    vault_str = str(vault_path)

    # Pattern to match vault paths (handles both /Users/... and ~/Research/...)
    # Also handle the expanded home path
    home_path = str(Path.home())
    vault_patterns = [
        vault_str,  # /Users/server/Research/vault
        vault_str.replace(home_path, "~"),  # ~/Research/vault
    ]

    result = text
    for vault_prefix in vault_patterns:
        # Match vault path followed by a file path ending in .md
        # Allow spaces in path/filenames — use .md as the boundary
        # Exclude only chars that break HTML or markdown: < > " ` \n
        pattern = re.escape(vault_prefix) + r'/([^<>"\`\n]+?\.md)\b'

        def replace_with_wikilink(match):
            relative = match.group(1)
            # Remove .md extension for wikilink format
            if relative.endswith(".md"):
                relative = relative[:-3]
            # Return as wikilink - will be converted to clickable deep link
            return f"[[{relative}]]"

        result = re.sub(pattern, replace_with_wikilink, result)

    return result


def _extract_file_paths(text: str) -> tuple[List[str], List[str]]:
    """Extract file paths from Claude output.

    Returns:
        Tuple of (sendable_files, vault_notes) where:
        - sendable_files: non-markdown files that can be sent to user
        - vault_notes: vault markdown files (as relative paths) for view buttons
    """
    import re

    sendable_extensions = {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".mp3",
        ".mp4",
        ".wav",
        ".doc",
        ".docx",
        ".xlsx",
        ".csv",
        ".zip",
        ".tar",
        ".gz",
    }

    clean_text = re.sub(r"`([^`]+)`", r"\1", text)
    path_pattern = r"(?:/[^\s<>\"|*?`]+|~/[^\s<>\"|*?`]+)"

    sendable_files = []
    vault_notes = []
    seen = set()

    for match in re.finditer(path_pattern, clean_text):
        path = match.group(0)
        path = path.rstrip(".,;:!?)")
        expanded_path = os.path.expanduser(path)

        if expanded_path in seen:
            continue
        seen.add(expanded_path)

        if not os.path.isfile(expanded_path):
            continue

        if not _is_path_in_safe_directory(expanded_path):
            continue

        ext = os.path.splitext(expanded_path)[1].lower()

        # Check if it's a vault markdown file
        if ext == ".md":
            relative_path = _get_vault_relative_path(expanded_path)
            if relative_path:
                vault_notes.append(relative_path)
        elif ext in sendable_extensions:
            sendable_files.append(expanded_path)

    return sendable_files, vault_notes


async def _send_files(message, file_paths: List[str]) -> None:
    """Send non-markdown files to the user via Telegram."""
    for file_path in file_paths:
        try:
            filename = os.path.basename(file_path)
            ext = os.path.splitext(file_path)[1].lower()

            with open(file_path, "rb") as f:
                if ext in {".png", ".jpg", ".jpeg", ".gif"}:
                    await message.reply_photo(photo=f, caption=f"📎 {filename}")
                elif ext in {".mp3", ".wav", ".ogg"}:
                    await message.reply_audio(audio=f, caption=f"🎵 {filename}")
                elif ext in {".mp4", ".mov", ".avi"}:
                    await message.reply_video(video=f, caption=f"🎬 {filename}")
                else:
                    await message.reply_document(document=f, caption=f"📄 {filename}")
            logger.info(f"Sent file to user: {filename}")

        except Exception as e:
            logger.error(f"Failed to send file {file_path}: {e}")
            await message.reply_text(
                f"❌ {t('claude.send_file_error', filename=os.path.basename(file_path))}"
            )


async def execute_claude_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    force_new: bool = False,
    custom_cwd: Optional[str] = None,
    system_prompt_prefix: Optional[str] = None,
) -> None:
    """Execute a Claude Code prompt with streaming output."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    from ...services.claude_code_service import get_claude_code_service
    from ...services.reply_context import get_reply_context_service
    from ..keyboard_utils import get_keyboard_utils

    service = get_claude_code_service()
    reply_context_service = get_reply_context_service()
    keyboard_utils = get_keyboard_utils()

    # Check for forced session ID from reply context
    forced_session = context.user_data.pop("force_session_id", None)

    if forced_session:
        session_id = forced_session
        logger.info(f"Using forced session from reply: {format_session_id(session_id)}")
    elif force_new:
        session_id = None
        # Mark that we're creating a new session so subsequent messages wait
        service.start_pending_session(chat.id)
    else:
        # Check if there's a pending session being created - wait for it
        if service.has_pending_session(chat.id):
            logger.info(f"Waiting for pending session for chat {chat.id}...")
            pending_session_id = await service.wait_for_pending_session(chat.id)
            if pending_session_id:
                session_id = pending_session_id
                logger.info(f"Using pending session: {format_session_id(session_id)}")
            else:
                session_id = service.active_sessions.get(chat.id)
        else:
            session_id = service.active_sessions.get(chat.id)

    context.user_data["last_claude_prompt"] = prompt

    # Get the message to reply to - handles both regular messages and callback queries
    reply_message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    reply_to_msg_id = reply_message.message_id if reply_message else None

    # Get default model from chat settings
    from sqlalchemy import select

    from ...core.database import get_db_session
    from ...models.chat import Chat as ChatModel

    default_model = "opus"
    thinking_effort = "medium"
    async with get_db_session() as session:
        result = await session.execute(
            select(ChatModel).where(ChatModel.chat_id == chat.id)
        )
        chat_obj = result.scalar_one_or_none()
        if chat_obj:
            if chat_obj.claude_model:
                default_model = chat_obj.claude_model
            if chat_obj.thinking_effort:
                thinking_effort = chat_obj.thinking_effort

    # Use Opus for /meta mode, otherwise use user's default model setting
    selected_model = (
        "opus" if custom_cwd and "telegram_agent" in custom_cwd else default_model
    )
    user_db_id = user.id

    logger.info(f"Using Claude model: {selected_model} for chat {chat.id}")

    locale = get_user_locale_from_update(update)

    model_emoji = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}.get(
        selected_model, "🤖"
    )

    prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
    session_status = (
        t("claude.resuming_session", locale, session=format_session_id(session_id))
        if session_id
        else t("claude.new_session", locale)
    )

    # Determine working directory for display
    work_dir_display = custom_cwd if custom_cwd else "~/Research/vault"
    # Show relative path if it's in home directory
    if custom_cwd and custom_cwd.startswith(str(Path.home())):
        work_dir_display = custom_cwd.replace(str(Path.home()), "~")

    logger.info("Sending status message via sync subprocess...")
    status_text = (
        f"<b>🤖 Claude Code</b> {model_emoji} <i>{selected_model.title()}</i>\n\n"
        f"<i>{escape_html(prompt_preview)}</i>\n\n"
        f"⏳ {session_status}\n"
        f"📂 {work_dir_display}"
    )

    from ..keyboard_utils import KeyboardUtils

    kb = KeyboardUtils()
    processing_keyboard = kb.create_claude_processing_keyboard(locale=locale)

    result = send_message_sync(
        chat_id=chat.id,
        text=status_text,
        parse_mode="HTML",
        reply_to=reply_to_msg_id,
        reply_markup=processing_keyboard.to_dict(),
    )

    if not result:
        logger.error("Failed to send Claude status message via sync")
        return

    status_msg_id = result.get("message_id")
    logger.info(f"Status message sent via sync: message_id={status_msg_id}")

    context.user_data["claude_status_msg_id"] = status_msg_id
    context.user_data["claude_stop_requested"] = False

    accumulated_text = ""
    current_tool = ""
    last_update_time = 0
    update_interval = 1.0
    new_session_id = None
    session_announced = False
    work_stats = None

    try:
        logger.info("Starting Claude execution loop...")
        message_count = 0

        def check_stop():
            return context.user_data.get("claude_stop_requested", False)

        async for msg_type, content, sid in service.execute_prompt(
            prompt=prompt,
            chat_id=chat.id,
            user_id=user_db_id,
            session_id=session_id,
            model=selected_model,
            stop_check=check_stop,
            cwd=custom_cwd,
            system_prompt_prefix=system_prompt_prefix,
            thinking_effort=thinking_effort,
        ):
            if context.user_data.get("claude_stop_requested", False):
                logger.info("Stop requested by user, breaking execution loop")
                accumulated_text += (
                    f"\n\n⏹️ **{t('messages.claude_stopped_by_user', locale)}**"
                )
                break

            message_count += 1
            logger.info(
                f"Received message {message_count}: type={msg_type}, "
                f"content_len={len(content) if content else 0}"
            )

            if sid:
                new_session_id = sid
                # Signal that session is ready for any waiting messages
                if force_new and service.has_pending_session(chat.id):
                    service.complete_pending_session(chat.id, new_session_id)
                if not session_announced and not session_id:
                    session_announced = True
                    session_start_text = (
                        f"<b>🤖 {t('claude.status_title', locale)}</b> {model_emoji}\n\n"
                        f"{t('claude.session_started', locale, session=format_session_id(new_session_id))}\n\n"
                        f"<i>{escape_html(prompt_preview)}</i>"
                    )
                    try:
                        edit_message_sync(
                            chat_id=chat.id,
                            message_id=status_msg_id,
                            text=session_start_text,
                            parse_mode="HTML",
                        )
                        logger.info(
                            f"Announced new session: {format_session_id(new_session_id)}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to announce session start: {e}")

            if msg_type == "text":
                if accumulated_text and not accumulated_text.endswith("\n"):
                    accumulated_text += "\n"
                accumulated_text += content
                current_tool = ""
            elif msg_type == "tool":
                current_tool = content
            elif msg_type in ("done", "error"):
                if msg_type == "error":
                    accumulated_text += content
                elif msg_type == "done" and content:
                    # Parse stats from done message
                    try:
                        import json

                        work_stats = json.loads(content)
                        logger.info(f"Received work stats: {work_stats}")
                    except Exception as e:
                        logger.warning(f"Failed to parse work stats: {e}")
                continue

            # Throttle message updates
            current_time = time.time()
            if current_time - last_update_time >= update_interval:
                display_text = (
                    accumulated_text[-3200:]
                    if len(accumulated_text) > 3200
                    else accumulated_text
                )
                if len(accumulated_text) > 3200:
                    display_text = "...\n" + display_text

                # Transform vault paths for display
                display_text = _transform_vault_paths_in_text(display_text)

                prompt_header = f"<b>→</b> <i>{escape_html(prompt[:80])}{'...' if len(prompt) > 80 else ''}</i>\n\n"
                tool_status = (
                    f"\n\n<code>{escape_html(current_tool)}</code>"
                    if current_tool
                    else ""
                )

                try:
                    edit_message_sync(
                        chat_id=chat.id,
                        message_id=status_msg_id,
                        text=prompt_header
                        + markdown_to_telegram_html(display_text)
                        + tool_status,
                        parse_mode="HTML",
                        reply_markup=processing_keyboard.to_dict(),
                    )
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Failed to update message: {e}")

        # Final update - delete status message and send response in new message
        session_info = (
            f"\n\n<i>Session: {format_session_id(new_session_id)}</i>"
            if new_session_id
            else ""
        )
        prompt_header = f"<b>→</b> <i>{escape_html(prompt[:100])}{'...' if len(prompt) > 100 else ''}</i>\n\n"

        is_locked = await get_claude_mode(chat.id)

        voice_url = None
        if new_session_id:
            voice_url = get_voice_url(new_session_id, project="vault")

        # Extract file paths from output - vault notes go to keyboard, others may be sent
        logger.info(
            f"Checking for files in output ({len(accumulated_text)} chars): "
            f"{repr(accumulated_text[:200])}"
        )
        sendable_files, vault_notes = _extract_file_paths(accumulated_text)

        # Also check work_stats for files that were written/created but not mentioned in text
        if work_stats:
            import re as _re

            sendable_extensions = {
                ".pdf",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".mp3",
                ".mp4",
                ".wav",
                ".doc",
                ".docx",
                ".xlsx",
                ".csv",
                ".zip",
                ".tar",
                ".gz",
            }
            existing_paths = set(sendable_files)

            # Collect candidate paths from files_written and bash commands
            candidate_paths = list(work_stats.get("files_written", []))

            # Extract file paths from bash commands (e.g. pandoc -o output.pdf)
            for cmd in work_stats.get("bash_commands", []):
                # Match -o "path" or -o path patterns
                for m in _re.finditer(r'-o\s+["\']?(/[^\s"\']+\.\w+)["\']?', cmd):
                    candidate_paths.append(m.group(1))
                # Match quoted absolute paths with sendable extensions
                for m in _re.finditer(
                    r'["\']?(/[^\s"\']*\.(?:pdf|png|jpg|jpeg|gif|mp3|mp4|wav|doc|docx|xlsx|csv|zip))["\']?',
                    cmd,
                ):
                    candidate_paths.append(m.group(1))

            for fpath in candidate_paths:
                ext = os.path.splitext(fpath)[1].lower()
                expanded = os.path.expanduser(fpath)
                if expanded in existing_paths:
                    continue
                if not os.path.isfile(expanded):
                    continue
                if not _is_path_in_safe_directory(expanded):
                    continue

                if ext in sendable_extensions:
                    sendable_files.append(expanded)
                    existing_paths.add(expanded)
                    logger.info(f"Added sendable file from work_stats: {expanded}")
                elif ext == ".md":
                    relative_path = _get_vault_relative_path(expanded)
                    if relative_path and relative_path not in vault_notes:
                        vault_notes.append(relative_path)
                        logger.info(
                            f"Added vault note from work_stats: {relative_path}"
                        )

        logger.info(
            f"Found {len(sendable_files)} sendable files, {len(vault_notes)} vault notes"
        )
        if vault_notes:
            logger.info(f"Vault notes for view buttons: {vault_notes}")

        # Get show_model_buttons and clean_responses settings from chat
        show_model_buttons = False
        send_clean_response = False
        from sqlalchemy import select

        from ...core.database import get_db_session
        from ...models.chat import Chat as ChatModel

        async with get_db_session() as session:
            result = await session.execute(
                select(ChatModel).where(ChatModel.chat_id == chat.id)
            )
            chat_obj = result.scalar_one_or_none()
            if chat_obj:
                show_model_buttons = chat_obj.show_model_buttons
                send_clean_response = chat_obj.clean_responses

        complete_keyboard = keyboard_utils.create_claude_complete_keyboard(
            is_locked=is_locked,
            current_model=selected_model,
            voice_url=voice_url,
            note_paths=vault_notes,
            show_model_buttons=show_model_buttons,
            locale=locale,
        )

        keyboard_dict = complete_keyboard.to_dict() if complete_keyboard else None

        max_chunk_size = 3600

        # Transform vault paths to relative paths before display
        transformed_text = _transform_vault_paths_in_text(accumulated_text)
        full_html = markdown_to_telegram_html(transformed_text)

        # Add work summary if available
        work_summary = _format_work_summary(work_stats) if work_stats else ""

        # Delete the status message to start fresh response
        try:
            from ..bot import get_bot

            bot_instance = get_bot()
            if bot_instance and bot_instance.application:
                await bot_instance.application.bot.delete_message(
                    chat_id=chat.id, message_id=status_msg_id
                )
                logger.info(f"Deleted status message {status_msg_id}")
        except Exception as e:
            logger.warning(f"Could not delete status message: {e}")

        # Send response in new message(s)
        # If clean_responses is enabled, send meta info first, then clean response
        if send_clean_response:
            # Send meta-info message (prompt header + work summary + session info)
            meta_text = prompt_header.rstrip() + work_summary + session_info
            send_message_sync(
                chat_id=chat.id,
                text=meta_text,
                parse_mode="HTML",
                reply_to=reply_to_msg_id,
            )

            # Send clean response (just the content, no meta info)
            if len(full_html) <= max_chunk_size:
                result = send_message_sync(
                    chat_id=chat.id,
                    text=full_html,
                    parse_mode="HTML",
                    reply_markup=keyboard_dict,
                )
                if result:
                    status_msg_id = result.get("message_id")
            else:
                chunks = split_message(full_html, max_chunk_size)
                for i, chunk in enumerate(chunks, 1):
                    is_last = i == len(chunks)
                    if is_last:
                        result = send_message_sync(
                            chat_id=chat.id,
                            text=chunk,
                            parse_mode="HTML",
                            reply_markup=keyboard_dict,
                        )
                        if result:
                            status_msg_id = result.get("message_id")
                    else:
                        send_message_sync(
                            chat_id=chat.id,
                            text=chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                            parse_mode="HTML",
                        )
        else:
            # Original behavior: single message with all info
            if (
                len(full_html) + len(prompt_header) + len(work_summary)
                <= max_chunk_size
            ):
                result = send_message_sync(
                    chat_id=chat.id,
                    text=prompt_header + full_html + work_summary + session_info,
                    parse_mode="HTML",
                    reply_markup=keyboard_dict,
                    reply_to=reply_to_msg_id,
                )
                if result:
                    status_msg_id = result.get("message_id")
            else:
                chunks = split_message(full_html, max_chunk_size)

                result = send_message_sync(
                    chat_id=chat.id,
                    text=prompt_header
                    + chunks[0]
                    + "\n\n<i>... continued below ...</i>",
                    parse_mode="HTML",
                    reply_to=reply_to_msg_id,
                )
                if result:
                    status_msg_id = result.get("message_id")

                for i, chunk in enumerate(chunks[1:], 2):
                    is_last = i == len(chunks)
                    if is_last:
                        result = send_message_sync(
                            chat_id=chat.id,
                            text=chunk + work_summary + session_info,
                            parse_mode="HTML",
                            reply_markup=keyboard_dict,
                        )
                        if result:
                            status_msg_id = result.get("message_id")
                    else:
                        send_message_sync(
                            chat_id=chat.id,
                            text=chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                            parse_mode="HTML",
                        )

        # Send non-markdown files (PDFs, images, etc.) if any
        if sendable_files and reply_message:
            logger.info(f"Sending {len(sendable_files)} files: {sendable_files}")
            await _send_files(reply_message, sendable_files)

        # Send voice response if configured (skip if stopped by user)
        from ...services.voice_response_service import get_voice_response_service

        voice_service = get_voice_response_service()
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        was_stopped = context.user_data.get("claude_stop_requested", False)
        if bot_token and accumulated_text and not was_stopped:
            try:
                await voice_service.synthesize_and_send(
                    chat_id=chat.id,
                    text=accumulated_text,
                    bot_token=bot_token,
                    context="claude_response",
                    reply_to_message_id=reply_to_msg_id,
                )
            except Exception as e:
                logger.warning(f"Voice synthesis failed (non-critical): {e}")

        # React with 👍 to indicate completion
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if bot_token:
            url = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
            if reply_to_msg_id:
                try:
                    payload = {
                        "chat_id": chat.id,
                        "message_id": reply_to_msg_id,
                        "reaction": [{"type": "emoji", "emoji": "👍"}],
                    }
                    requests.post(url, json=payload, timeout=5)
                except Exception:
                    pass
            if status_msg_id:
                try:
                    payload = {
                        "chat_id": chat.id,
                        "message_id": status_msg_id,
                        "reaction": [{"type": "emoji", "emoji": "👍"}],
                    }
                    response = requests.post(url, json=payload, timeout=5)
                    if response.json().get("ok"):
                        logger.info("Added 👍 completion reactions")
                except Exception as e:
                    logger.debug(f"Could not add completion reaction: {e}")

        # Track response for reply context
        if new_session_id:
            reply_context_service.track_claude_response(
                message_id=status_msg_id,
                chat_id=chat.id,
                user_id=user.id,
                session_id=new_session_id,
                prompt=prompt,
                response_text=accumulated_text[:1000],
            )
            logger.debug(
                f"Tracked Claude response for reply context: msg={status_msg_id}"
            )

    except Exception as e:
        logger.error(f"Error executing Claude prompt: {e}")
        # Cancel pending session on error so waiting messages don't hang
        if force_new:
            service.cancel_pending_session(chat.id)
        edit_message_sync(
            chat_id=chat.id,
            message_id=status_msg_id,
            text=f"❌ {t('claude.error_prefix', locale, error=str(e))}",
            parse_mode="HTML",
        )


async def forward_voice_to_claude(
    chat_id: int,
    user_id: int,
    transcription: str,
    transcription_msg_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    force_new: bool = False,
) -> None:
    """
    Forward voice transcription to Claude Code session.

    Creates new session if none exists, or uses existing active session.
    Response will reply to the transcription message.

    Args:
        chat_id: Telegram chat ID
        user_id: Telegram user ID
        transcription: The voice transcription text
        transcription_msg_id: Message ID of the transcription message (for reply)
        context: Telegram context
        force_new: If True, force creation of a new session (for pending auto-forward)
    """
    from ...services.claude_code_service import get_claude_code_service
    from ...services.reply_context import get_reply_context_service
    from ..keyboard_utils import get_keyboard_utils

    service = get_claude_code_service()
    reply_context_service = get_reply_context_service()
    get_keyboard_utils()

    # Check for "new session" trigger (#14) or force_new parameter
    trigger_result = detect_new_session_trigger(transcription)
    force_new_session = trigger_result["triggered"] or force_new
    prompt = trigger_result["prompt"] if trigger_result["triggered"] else transcription

    # Handle empty prompt after trigger
    if force_new_session and not prompt:
        prompt = "Hello! I'm ready for a new conversation."

    # Get or create session (force new if trigger detected or force_new=True)
    if force_new_session:
        # End any existing session and start fresh
        await service.end_session(chat_id)
        session_id = None
        reason = "pending auto-forward" if force_new else "phrase trigger"
        logger.info(f"New session triggered by {reason} for chat {chat_id}")
    else:
        session_id = service.active_sessions.get(chat_id)

    logger.info(
        f"Forwarding voice to Claude: chat={chat_id}, "
        f"session={'forced new' if force_new_session else ('existing' if session_id else 'new')}, "
        f"text_len={len(prompt)}"
    )

    # Get model preference from chat settings
    from sqlalchemy import select

    from ...core.database import get_db_session
    from ...models.chat import Chat as ChatModel

    selected_model = "opus"  # Default
    thinking_effort = "medium"  # Default
    send_clean_response = False  # Default
    async with get_db_session() as session:
        result = await session.execute(
            select(ChatModel).where(ChatModel.chat_id == chat_id)
        )
        chat_obj = result.scalar_one_or_none()
        if chat_obj:
            if chat_obj.claude_model:
                selected_model = chat_obj.claude_model
            if chat_obj.thinking_effort:
                thinking_effort = chat_obj.thinking_effort
            send_clean_response = chat_obj.clean_responses

    model_emoji = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}.get(
        selected_model, "🤖"
    )

    prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
    session_status = (
        f"🆕 {t('claude.new_session_triggered')}"
        if force_new_session
        else (
            t("claude.resuming_session", session=format_session_id(session_id))
            if session_id
            else t("claude.new_session")
        )
    )

    # Send status message
    status_text = (
        f"<b>🤖 Claude Code</b> {model_emoji} <i>{selected_model.title()}</i>\n\n"
        f"<i>{escape_html(prompt_preview)}</i>\n\n"
        f"⏳ {session_status}\n"
        f"📂 ~/Research/vault"
    )

    from ..keyboard_utils import KeyboardUtils

    kb = KeyboardUtils()
    processing_keyboard = kb.create_claude_processing_keyboard()

    result = send_message_sync(
        chat_id=chat_id,
        text=status_text,
        parse_mode="HTML",
        reply_to=transcription_msg_id,
        reply_markup=processing_keyboard.to_dict(),
    )

    if not result:
        logger.error("Failed to send Claude status message for voice forward")
        return

    status_msg_id = result.get("message_id")
    logger.info(f"Voice forward status message: message_id={status_msg_id}")

    context.user_data["claude_status_msg_id"] = status_msg_id
    context.user_data["claude_stop_requested"] = False
    context.user_data["last_claude_prompt"] = prompt

    accumulated_text = ""
    current_tool = ""
    last_update_time = 0
    update_interval = 1.0
    new_session_id = None
    work_stats = None

    try:
        logger.info("Starting Claude execution for voice forward...")

        def check_stop():
            return context.user_data.get("claude_stop_requested", False)

        async for msg_type, content, sid in service.execute_prompt(
            prompt=prompt,
            chat_id=chat_id,
            user_id=user_id,
            session_id=session_id,
            stop_check=check_stop,
            thinking_effort=thinking_effort,
        ):
            if new_session_id is None and sid:
                new_session_id = sid

            if msg_type == "tool":
                current_tool = content
                now = time.time()
                if now - last_update_time >= update_interval:
                    edit_message_sync(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=f"{status_text}\n\n<i>Using: {current_tool}</i>",
                        parse_mode="HTML",
                        reply_markup=processing_keyboard.to_dict(),
                    )
                    last_update_time = now

            elif msg_type == "text":
                accumulated_text += content

            elif msg_type == "stats":
                work_stats = content

            elif msg_type == "done":
                accumulated_text = content
                break

        # Format and send final response
        from ..keyboard_utils import KeyboardUtils

        kb = KeyboardUtils()
        keyboard = kb.create_claude_response_keyboard(new_session_id)
        keyboard_dict = keyboard.to_dict() if keyboard else None

        session_info = (
            f"\n\n<code>{format_session_id(new_session_id)}</code>"
            if new_session_id
            else ""
        )

        max_chunk_size = 3500
        prompt_header = f"<b>🎤 {t('claude.voice_header')}</b>\n\n"

        transformed_text = _transform_vault_paths_in_text(accumulated_text)
        full_html = markdown_to_telegram_html(transformed_text)

        work_summary = _format_work_summary(work_stats) if work_stats else ""

        # Delete status message
        try:
            from ..bot import get_bot

            bot_instance = get_bot()
            if bot_instance and bot_instance.application:
                await bot_instance.application.bot.delete_message(
                    chat_id=chat_id, message_id=status_msg_id
                )
                logger.info(f"Deleted voice forward status message {status_msg_id}")
        except Exception as e:
            logger.warning(f"Could not delete status message: {e}")

        # Send response replying to transcription
        # If clean_responses is enabled, send meta info first, then clean response
        if send_clean_response:
            # Send meta-info message (prompt header + work summary + session info)
            meta_text = prompt_header.rstrip() + work_summary + session_info
            send_message_sync(
                chat_id=chat_id,
                text=meta_text,
                parse_mode="HTML",
                reply_to=transcription_msg_id,
            )

            # Send clean response (just the content, no meta info)
            if len(full_html) <= max_chunk_size:
                result = send_message_sync(
                    chat_id=chat_id,
                    text=full_html,
                    parse_mode="HTML",
                    reply_markup=keyboard_dict,
                )
                if result:
                    status_msg_id = result.get("message_id")
            else:
                chunks = split_message(full_html, max_chunk_size)
                for i, chunk in enumerate(chunks, 1):
                    is_last = i == len(chunks)
                    if is_last:
                        result = send_message_sync(
                            chat_id=chat_id,
                            text=chunk,
                            parse_mode="HTML",
                            reply_markup=keyboard_dict,
                        )
                        if result:
                            status_msg_id = result.get("message_id")
                    else:
                        send_message_sync(
                            chat_id=chat_id,
                            text=chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                            parse_mode="HTML",
                        )
        else:
            # Original behavior: single message with all info
            if (
                len(full_html) + len(prompt_header) + len(work_summary)
                <= max_chunk_size
            ):
                result = send_message_sync(
                    chat_id=chat_id,
                    text=prompt_header + full_html + work_summary + session_info,
                    parse_mode="HTML",
                    reply_markup=keyboard_dict,
                    reply_to=transcription_msg_id,
                )
                if result:
                    status_msg_id = result.get("message_id")
            else:
                chunks = split_message(full_html, max_chunk_size)

                result = send_message_sync(
                    chat_id=chat_id,
                    text=prompt_header
                    + chunks[0]
                    + "\n\n<i>... continued below ...</i>",
                    parse_mode="HTML",
                    reply_to=transcription_msg_id,
                )
                if result:
                    status_msg_id = result.get("message_id")

                for i, chunk in enumerate(chunks[1:], 2):
                    is_last = i == len(chunks)
                    if is_last:
                        result = send_message_sync(
                            chat_id=chat_id,
                            text=chunk + work_summary + session_info,
                            parse_mode="HTML",
                            reply_markup=keyboard_dict,
                        )
                        if result:
                            status_msg_id = result.get("message_id")
                    else:
                        send_message_sync(
                            chat_id=chat_id,
                            text=chunk + "\n\n<i>... continued below ...</i>",
                            parse_mode="HTML",
                        )

        logger.info(
            f"Voice forward completed: session={format_session_id(new_session_id)}"
        )

        # Track response for reply context
        if new_session_id:
            reply_context_service.track_claude_response(
                message_id=status_msg_id,
                chat_id=chat_id,
                user_id=user_id,
                session_id=new_session_id,
                prompt=prompt,
                response_text=accumulated_text[:1000],
            )
            logger.debug(f"Tracked voice forward response: msg={status_msg_id}")

    except Exception as e:
        logger.error(f"Error forwarding voice to Claude: {e}")
        edit_message_sync(
            chat_id=chat_id,
            message_id=status_msg_id,
            text=f"❌ {t('claude.voice_forward_error', error=str(e))}",
            parse_mode="HTML",
        )


async def session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /session command for session management.

    Usage:
        /session - Show active session info
        /session rename <new-name> - Rename active session
        /session list - List all sessions
    """
    chat = update.effective_chat
    if not chat or not update.message:
        return

    from ...services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()

    # Parse command arguments
    args = context.args or []
    " ".join(args) if args else ""

    locale = get_user_locale_from_update(update)

    if not args:
        # Show active session info
        session_id = await service.get_active_session(chat.id)
        if session_id:
            sessions = await service.get_user_sessions(chat.id, limit=1)
            if sessions:
                session = sessions[0]
                session_name = session.name or "(unnamed)"
                last_prompt = (session.last_prompt or "None")[:100]
                await update.message.reply_text(
                    f"<b>{t('claude.session_active_title', locale)}</b>\n\n"
                    f"{t('claude.session_id_label', locale, session=format_session_id(session_id))}\n"
                    f"{t('claude.session_name_label', locale, name=session_name)}\n"
                    f"{t('claude.session_last_label', locale, prompt=last_prompt)}\n\n"
                    f"{t('claude.session_commands', locale)}",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(t("claude.session_no_active", locale))
        else:
            await update.message.reply_text(
                t("claude.session_no_active_hint", locale),
                parse_mode="HTML",
            )

    elif args[0] == "rename":
        # Rename active session
        if len(args) < 2:
            await update.message.reply_text(
                t("claude.session_rename_usage", locale),
                parse_mode="HTML",
            )
            return

        new_name = " ".join(args[1:])
        session_id = await service.get_active_session(chat.id)

        if not session_id:
            await update.message.reply_text(
                t("claude.session_no_active_rename", locale),
                parse_mode="HTML",
            )
            return

        success = await service.rename_session(session_id, new_name)
        if success:
            await update.message.reply_text(
                f"✅ {t('claude.session_renamed', locale, name=new_name, session=format_session_id(session_id))}",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(t("claude.session_rename_failed", locale))

    elif args[0] == "list":
        # List all sessions (delegate to /claude:sessions)
        await _claude_sessions(update, context)

    else:
        await update.message.reply_text(
            t("claude.session_help", locale),
            parse_mode="HTML",
        )


async def clean_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /clean command - extract clean response from a Claude message.

    Usage: Reply to any Claude message with /clean to get a clean version
    (no prompt header, work summary, or session info).
    """
    locale = get_user_locale_from_update(update)

    if not update.message or not update.message.reply_to_message:
        await update.message.reply_text(
            t("claude.clean_usage", locale),
            parse_mode="HTML",
        )
        return

    original_msg = update.message.reply_to_message
    original_text = original_msg.text or original_msg.caption

    if not original_text:
        await update.message.reply_text(
            t("claude.clean_no_text", locale),
            parse_mode="HTML",
        )
        return

    # Extract clean response by removing:
    # 1. Prompt header: "→ prompt here..."
    # 2. Work summary: "⏱️ 37s · 📖 1 reads..."
    # 3. Session info: "Session: ⚫🟫 6c1b4813"

    lines = original_text.split("\n")
    clean_lines = []
    skip_next = False

    for i, line in enumerate(lines):
        # Skip prompt header (starts with "→" or "🎤")
        if line.strip().startswith(("→", "🎤")):
            skip_next = True
            continue

        # Skip empty line after prompt header
        if skip_next and not line.strip():
            skip_next = False
            continue

        skip_next = False

        # Skip work summary line (contains ⏱️ or starts with specific emojis)
        if "⏱️" in line or line.strip().startswith(
            ("📖", "✍️", "🔍", "⚡", "🌐", "🎯")
        ):
            continue

        # Skip session info line (starts with "Session:")
        if line.strip().startswith("Session:"):
            continue

        # Skip the session emoji line (common pattern: "⚫🟫 xxxxxx")
        if (
            i == len(lines) - 1
            and len(line.strip()) < 20
            and any(
                c in line
                for c in ["⚫", "🟫", "🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "⚪", "🟤"]
            )
        ):
            continue

        clean_lines.append(line)

    clean_text = "\n".join(clean_lines).strip()

    if not clean_text:
        await update.message.reply_text(
            t("claude.clean_empty", locale),
            parse_mode="HTML",
        )
        return

    # Send clean response
    try:
        await update.message.reply_text(
            clean_text,
            parse_mode="HTML",
        )
    except Exception as e:
        # If HTML parsing fails, try plain text
        logger.warning(f"Failed to send clean response as HTML: {e}")
        await update.message.reply_text(clean_text)
