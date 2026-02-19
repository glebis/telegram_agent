"""
Note viewing commands.

Contains:
- /note - View a note from the Obsidian vault
- Note path validation and security
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Tuple

from telegram import Update
from telegram.ext import ContextTypes

from ...core.config import get_settings
from ...core.error_messages import sanitize_error
from ...core.i18n import get_user_locale_from_update, t
from .formatting import markdown_to_telegram_html, split_message

logger = logging.getLogger(__name__)


def _sanitize_note_name(note_name: str) -> Tuple[bool, str]:
    """
    Validate and sanitize note name to prevent path traversal attacks.

    Returns: (is_valid, sanitized_name_or_error_message)
    """
    # Reject empty names
    if not note_name or not note_name.strip():
        return False, "note.empty_name"

    # Reject path traversal attempts
    if ".." in note_name or note_name.startswith("/") or note_name.startswith("~"):
        logger.warning(f"Path traversal attempt blocked: {note_name[:100]}")
        return False, "note.invalid_name"

    # Block shell metacharacters
    dangerous_chars = re.compile(r'[<>:"|?*\\/\x00-\x1f]')
    if dangerous_chars.search(note_name):
        logger.warning(f"Dangerous characters in note name: {note_name[:100]}")
        return False, "note.invalid_chars"

    # Limit length
    if len(note_name) > 200:
        return False, "note.name_too_long"

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
    locale = get_user_locale_from_update(update)
    vault_path = Path(get_settings().vault_path).expanduser()

    # Validate note name
    is_valid, result = _sanitize_note_name(note_name)
    if not is_valid:
        logger.warning(f"Invalid note name rejected: {note_name[:100]}")
        if update.message:
            await update.message.reply_text("❌ " + t(result, locale))
        return

    note_name = result

    # Try to find the note
    note_file = vault_path / f"{note_name}.md"

    # Validate path stays within vault
    if not _validate_path_in_vault(note_file, vault_path):
        logger.warning(f"Path traversal blocked for: {note_name}")
        if update.message:
            await update.message.reply_text("❌ " + t("note.invalid_path", locale))
        return

    if not note_file.exists():
        # Try searching recursively
        try:
            basename = Path(note_name).name
            proc = await asyncio.create_subprocess_exec(
                "find",
                str(vault_path),
                "-type",
                "f",
                "-name",
                f"{basename}.md",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            matches = stdout.decode().strip().split("\n")
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
                        "❌ " + t("note.not_found", locale, name=note_name)
                    )
                return
        except Exception as e:
            logger.error(f"Error searching for note: {e}")
            if update.message:
                await update.message.reply_text("❌ " + t("note.search_error", locale))
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
                continued = t("note.continued_below", locale)
                await update.message.reply_text(
                    f"📄 <b>{note_name}</b>\n\n{chunks[0]}\n\n<i>{continued}</i>",
                    parse_mode="HTML",
                )

                for i, chunk in enumerate(chunks[1:], 2):
                    is_last = i == len(chunks)
                    if is_last:
                        await update.message.reply_text(chunk, parse_mode="HTML")
                    else:
                        part = t(
                            "note.part_indicator",
                            locale,
                            current=i,
                            total=len(chunks),
                        )
                        await update.message.reply_text(
                            chunk + f"\n\n<i>{part}</i>",
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
            await update.message.reply_text(
                "❌ " + t("note.read_error", locale, error=sanitize_error(e))
            )


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /note command - view a note from the vault."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Note command from user {user.id} in chat {chat.id}")

    if not context.args:
        locale = get_user_locale_from_update(update)
        if update.message:
            await update.message.reply_text(
                t("note.usage", locale).strip(),
                parse_mode="HTML",
            )
        return

    note_name = " ".join(context.args)
    await view_note_command(update, context, note_name)
