"""
Note viewing commands.

Contains:
- /note - View a note from the Obsidian vault
- Note path validation and security
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Tuple

from telegram import Update
from telegram.ext import ContextTypes

from ...core.config import get_settings
from .formatting import markdown_to_telegram_html, split_message

logger = logging.getLogger(__name__)


def _sanitize_note_name(note_name: str) -> Tuple[bool, str]:
    """
    Validate and sanitize note name to prevent path traversal attacks.

    Returns: (is_valid, sanitized_name_or_error_message)
    """
    # Reject empty names
    if not note_name or not note_name.strip():
        return False, "Note name cannot be empty"

    # Reject path traversal attempts
    if ".." in note_name or note_name.startswith("/") or note_name.startswith("~"):
        logger.warning(f"Path traversal attempt blocked: {note_name[:100]}")
        return False, "Invalid note name"

    # Block shell metacharacters
    dangerous_chars = re.compile(r'[<>:"|?*\\/\x00-\x1f]')
    if dangerous_chars.search(note_name):
        logger.warning(f"Dangerous characters in note name: {note_name[:100]}")
        return False, "Note name contains invalid characters"

    # Limit length
    if len(note_name) > 200:
        return False, "Note name too long"

    return True, note_name.strip()


def _validate_path_in_vault(file_path: Path, vault_path: Path) -> bool:
    """Ensure resolved path is within the vault directory."""
    try:
        resolved = file_path.resolve()
        vault_resolved = vault_path.resolve()
        return resolved.is_relative_to(vault_resolved)
    except (ValueError, RuntimeError):
        return False


async def view_note_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, note_name: str
) -> None:
    """View a note from the Obsidian vault by name."""
    vault_path = Path(get_settings().vault_path).expanduser()

    # Validate note name
    is_valid, result = _sanitize_note_name(note_name)
    if not is_valid:
        logger.warning(f"Invalid note name rejected: {note_name[:100]}")
        if update.message:
            await update.message.reply_text(f"❌ {result}")
        return

    note_name = result

    # Try to find the note
    note_file = vault_path / f"{note_name}.md"

    # Validate path stays within vault
    if not _validate_path_in_vault(note_file, vault_path):
        logger.warning(f"Path traversal blocked for: {note_name}")
        if update.message:
            await update.message.reply_text("❌ Invalid note path")
        return

    if not note_file.exists():
        # Try searching recursively
        try:
            basename = Path(note_name).name
            search_result = subprocess.run(
                ["find", str(vault_path), "-type", "f", "-name", f"{basename}.md"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            matches = search_result.stdout.strip().split("\n")
            matches = [m for m in matches if m]

            # Validate all matches are within vault
            valid_matches = []
            for match in matches:
                match_path = Path(match)
                try:
                    resolved_match = match_path.resolve()
                    if _validate_path_in_vault(resolved_match, vault_path):
                        valid_matches.append(resolved_match)
                except (OSError, ValueError):
                    continue

            if valid_matches:
                note_file = valid_matches[0]
                logger.info(f"Found note via search: {note_file}")
            else:
                logger.info(f"Note not found: {note_name}")
                if update.message:
                    await update.message.reply_text(
                        f"❌ Note not found: {note_name}\n\n"
                        f"The note might not exist in your vault."
                    )
                return
        except Exception as e:
            logger.error(f"Error searching for note: {e}")
            if update.message:
                await update.message.reply_text("❌ Error searching for note")
            return

    # Read the note content
    try:
        with open(note_file, "r", encoding="utf-8") as f:
            content = f.read()

        formatted_content = markdown_to_telegram_html(content)

        max_length = 4000
        if len(formatted_content) > max_length:
            chunks = split_message(formatted_content, max_length)

            if update.message:
                await update.message.reply_text(
                    f"📄 <b>{note_name}</b>\n\n{chunks[0]}\n\n<i>... continued below ...</i>",
                    parse_mode="HTML",
                )

                for i, chunk in enumerate(chunks[1:], 2):
                    is_last = i == len(chunks)
                    if is_last:
                        await update.message.reply_text(chunk, parse_mode="HTML")
                    else:
                        await update.message.reply_text(
                            chunk + f"\n\n<i>... part {i}/{len(chunks)} ...</i>",
                            parse_mode="HTML",
                        )
        else:
            if update.message:
                await update.message.reply_text(
                    f"📄 <b>{note_name}</b>\n\n{formatted_content}",
                    parse_mode="HTML",
                )

    except Exception as e:
        logger.error(f"Error reading note {note_file}: {e}")
        if update.message:
            await update.message.reply_text(f"❌ Error reading note: {str(e)}")


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /note command - view a note from the vault."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Note command from user {user.id} in chat {chat.id}")

    if not context.args:
        if update.message:
            await update.message.reply_text(
                "Usage: <code>/note note name</code>\n\n"
                "Example: <code>/note Claude Code</code>",
                parse_mode="HTML",
            )
        return

    note_name = " ".join(context.args)
    await view_note_command(update, context, note_name)
