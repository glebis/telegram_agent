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

from ...core.config import get_settings
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
    from ...services.claude_code_service import get_claude_code_service, is_claude_code_admin

    if not await is_claude_code_admin(chat.id):
        if update.message:
            await update.message.reply_text(
                "You don't have permission to use Claude Code."
            )
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
            await update.message.reply_text(
                f"Unknown subcommand: <code>:{subcommand}</code>\n\n"
                "Use <code>/claude:help</code> for available commands.",
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
        reply_markup = keyboard_utils.create_claude_action_keyboard(
            has_active_session=bool(active_session_id),
            is_locked=is_locked,
        )

        if active_session_id:
            session_display = format_session_id(active_session_id)
            prompt_preview = (last_prompt or "No prompt")[:40]
            lock_status = "🔒 Locked" if is_locked else "🔓 Unlocked"
            status_text = (
                f"<b>🤖 Claude Code</b>\n\n"
                f"▶️ Session: <code>{session_display}</code>\n"
                f"Last: <i>{prompt_preview}...</i>\n"
                f"Mode: {lock_status}\n\n"
                f"{'Send any message to continue' if is_locked else 'Send prompt to continue, or:'}"
            )
        else:
            status_text = (
                f"<b>🤖 Claude Code</b>\n\n"
                f"No active session\n"
                f"Work dir: <code>~/Research/vault</code>\n\n"
                f"Send a prompt or tap below:"
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

    from ...services.claude_code_service import get_claude_code_service

    service = get_claude_code_service()
    await service.end_session(chat.id)

    if prompt.strip():
        await execute_claude_prompt(update, context, prompt.strip(), force_new=True)
    else:
        if update.message:
            await update.message.reply_text(
                "🆕 Ready to start new session\n\n"
                "Send: <code>/claude your prompt</code>",
                parse_mode="HTML",
            )


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
            await update.message.reply_text(
                "No sessions found.\n\n"
                "Start with: <code>/claude your prompt</code>",
                parse_mode="HTML",
            )
        return

    from ..keyboard_utils import get_keyboard_utils

    keyboard_utils = get_keyboard_utils()
    reply_markup = keyboard_utils.create_claude_sessions_keyboard(
        sessions, active_session
    )

    if update.message:
        await update.message.reply_text(
            f"<b>Sessions</b> ({len(sessions)})\n\n" f"Select to resume:",
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
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                pid = pid.strip()
                if not pid.isdigit():
                    logger.warning(f"Invalid PID skipped: {pid[:20]}")
                    continue
                try:
                    subprocess.run(["kill", "-15", pid], capture_output=True)
                    killed_processes += 1
                    logger.info(f"Killed stuck Claude process: {pid}")
                except Exception as e:
                    logger.warning(f"Failed to kill process {pid}: {e}")
    except Exception as e:
        logger.warning(f"Error checking for stuck processes: {e}")

    status_parts = []
    if session_ended:
        status_parts.append("Session cleared")
    else:
        status_parts.append("No active session")

    if killed_processes > 0:
        status_parts.append(f"{killed_processes} process(es) killed")

    if update.message:
        await update.message.reply_text(
            f"🔄 <b>Reset</b>\n\n• " + "\n• ".join(status_parts),
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
            await update.message.reply_text(
                "No session found.\n\n"
                "Start with: <code>/claude your prompt</code>",
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

    if update.message:
        session_display = format_session_id(session_id)

        idle_time = datetime.utcnow() - last_used if last_used else timedelta(0)
        idle_minutes = int(idle_time.total_seconds() // 60)

        if last_used:
            if idle_minutes < 60:
                time_info = f"{idle_minutes}m ago"
            else:
                hours = idle_minutes // 60
                time_info = f"{hours}h ago" if hours < 24 else f"{hours // 24}d ago"
        else:
            time_info = "unknown"

        warning = ""
        if idle_minutes > 30:
            warning = f"\n⚠️ <i>Session idle {time_info}</i>\n"

        await update.message.reply_text(
            f"🔒 <b>Locked</b>\n\n"
            f"Session: <code>{session_display}</code>\n"
            f"Last used: {time_info}{warning}\n"
            "All messages → Claude\n\n"
            "<code>/claude:unlock</code> to exit",
            parse_mode="HTML",
            reply_markup=keyboard_utils.create_claude_locked_keyboard(),
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
        await update.message.reply_text(
            "🔓 <b>Unlocked</b>\n\n" "Normal mode restored.",
            parse_mode="HTML",
        )
    logger.info(f"Claude mode unlocked for chat {chat.id}")


async def _claude_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /claude:help - show Claude command help."""
    if update.message:
        await update.message.reply_text(
            "<b>Claude Commands</b>\n\n"
            "<code>/claude prompt</code> — Execute prompt\n"
            "<code>/claude:new prompt</code> — New session\n"
            "<code>/claude:sessions</code> — List sessions\n"
            "<code>/claude:lock</code> — Lock mode (all → Claude)\n"
            "<code>/claude:unlock</code> — Unlock mode\n"
            "<code>/claude:reset</code> — Reset & kill stuck\n"
            "<code>/claude:help</code> — This help\n\n"
            "<i>Work dir: ~/Research/vault</i>",
            parse_mode="HTML",
        )


def _is_path_in_safe_directory(file_path: str) -> bool:
    """Check if a file path is within a safe directory."""
    try:
        resolved = Path(file_path).resolve()
        settings = get_settings()

        safe_directories = [
            Path(settings.vault_path).expanduser(),
            Path(settings.vault_temp_images_dir).expanduser(),
            Path.home() / "ai_projects" / "telegram_agent" / "data",
            Path.home() / "ai_projects" / "telegram_agent" / "outputs",
            Path.home() / "Desktop",
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
    Transform full vault paths in text to relative paths.

    Replaces paths like /Users/server/Research/vault/Claude-Drafts/note.md
    with Claude-Drafts/note.md
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
        # Match vault path followed by a file path
        pattern = re.escape(vault_prefix) + r'/([^\s<>"\'\`\)]+\.md)'

        def replace_with_relative(match):
            relative = match.group(1)
            return relative

        result = re.sub(pattern, replace_with_relative, result)

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
                f"❌ Failed to send file: {os.path.basename(file_path)}"
            )


async def execute_claude_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    force_new: bool = False,
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
    else:
        session_id = service.active_sessions.get(chat.id)

    context.user_data["last_claude_prompt"] = prompt

    if not update.message:
        return

    selected_model = "sonnet"
    user_db_id = user.id

    logger.info(f"Using Claude model: {selected_model} for chat {chat.id}")

    model_emoji = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}.get(selected_model, "🤖")

    prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
    session_status = (
        f"Resuming {format_session_id(session_id)}" if session_id else "New session"
    )

    logger.info(f"Sending status message via sync subprocess...")
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
        chat_id=chat.id,
        text=status_text,
        parse_mode="HTML",
        reply_to=update.message.message_id if update.message else None,
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

    try:
        logger.info(f"Starting Claude execution loop...")
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
        ):
            if context.user_data.get("claude_stop_requested", False):
                logger.info("Stop requested by user, breaking execution loop")
                accumulated_text += "\n\n⏹️ **Stopped by user**"
                break

            message_count += 1
            logger.info(
                f"Received message {message_count}: type={msg_type}, "
                f"content_len={len(content) if content else 0}"
            )

            if sid:
                new_session_id = sid
                if not session_announced and not session_id:
                    session_announced = True
                    session_start_text = (
                        f"<b>🤖 Claude Code</b> {model_emoji}\n\n"
                        f"Session: <code>{format_session_id(new_session_id)}</code> started\n\n"
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
                    )
                    last_update_time = current_time
                except Exception as e:
                    logger.warning(f"Failed to update message: {e}")

        # Final update
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
        logger.info(
            f"Found {len(sendable_files)} sendable files, {len(vault_notes)} vault notes"
        )
        if vault_notes:
            logger.info(f"Vault notes for view buttons: {vault_notes}")

        complete_keyboard = keyboard_utils.create_claude_complete_keyboard(
            is_locked=is_locked,
            current_model=selected_model,
            voice_url=voice_url,
            note_paths=vault_notes,
        )

        keyboard_dict = complete_keyboard.to_dict() if complete_keyboard else None

        max_chunk_size = 3600

        # Transform vault paths to relative paths before display
        transformed_text = _transform_vault_paths_in_text(accumulated_text)
        full_html = markdown_to_telegram_html(transformed_text)

        if len(full_html) + len(prompt_header) <= max_chunk_size:
            edit_message_sync(
                chat_id=chat.id,
                message_id=status_msg_id,
                text=prompt_header + full_html + session_info,
                parse_mode="HTML",
                reply_markup=keyboard_dict,
            )
        else:
            chunks = split_message(full_html, max_chunk_size)

            edit_message_sync(
                chat_id=chat.id,
                message_id=status_msg_id,
                text=prompt_header + chunks[0] + "\n\n<i>... continued below ...</i>",
                parse_mode="HTML",
            )

            for i, chunk in enumerate(chunks[1:], 2):
                is_last = i == len(chunks)
                if is_last:
                    send_message_sync(
                        chat_id=chat.id,
                        text=chunk + session_info,
                        parse_mode="HTML",
                        reply_markup=keyboard_dict,
                    )
                else:
                    send_message_sync(
                        chat_id=chat.id,
                        text=chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                        parse_mode="HTML",
                    )

        # Send non-markdown files (PDFs, images, etc.) if any
        if sendable_files:
            logger.info(f"Sending {len(sendable_files)} files: {sendable_files}")
            await _send_files(update.message, sendable_files)

        # React with 👍 to indicate completion
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if bot_token:
            url = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
            if update.message:
                try:
                    payload = {
                        "chat_id": chat.id,
                        "message_id": update.message.message_id,
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
                        logger.info(f"Added 👍 completion reactions")
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
            logger.debug(f"Tracked Claude response for reply context: msg={status_msg_id}")

    except Exception as e:
        logger.error(f"Error executing Claude prompt: {e}")
        edit_message_sync(
            chat_id=chat.id,
            message_id=status_msg_id,
            text=f"❌ Error: {str(e)}",
            parse_mode="HTML",
        )
