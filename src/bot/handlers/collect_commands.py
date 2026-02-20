"""
Collect mode commands for batch input accumulation.

Contains:
- /collect:start - Start collecting items
- /collect:go - Process collected items with Claude
- /collect:stop - Stop collecting without processing
- /collect:status - Show what's been collected
- /collect:clear - Clear queue but stay in collect mode
- /collect:help - Show collect command help
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ...core.i18n import get_user_locale_from_update, t
from ...utils.error_reporting import handle_errors

logger = logging.getLogger(__name__)

# Text-based MIME types that should be read and included directly in prompts
TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/html",
    "text/css",
    "text/javascript",
    "text/csv",
    "text/xml",
    "text/yaml",
    "text/x-yaml",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
}

# Text-based file extensions (fallback when MIME type is missing)
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".py",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".sql",
    ".r",
    ".swift",
    ".kt",
    ".scala",
    ".conf",
    ".ini",
    ".toml",
    ".env",
    ".gitignore",
    ".dockerfile",
    ".csv",
}

# Maximum file size for inline reading (100KB)
MAX_TEXT_FILE_SIZE = 100 * 1024


def _is_text_document(mime_type: Optional[str], file_name: Optional[str]) -> bool:
    """Check if a document should be read as text and included inline."""
    # Check MIME type first
    if mime_type and mime_type.lower() in TEXT_MIME_TYPES:
        return True

    # Fall back to extension check
    if file_name:
        ext = Path(file_name).suffix.lower()
        if ext in TEXT_EXTENSIONS:
            return True

    return False


def _read_text_document(file_id: str, file_name: Optional[str]) -> Optional[str]:
    """Download and read a text document, returning its content."""
    from ...utils.subprocess_helper import download_telegram_file

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set, cannot read document")
        return None

    try:
        # Create temp file with appropriate extension
        suffix = Path(file_name).suffix if file_name else ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            temp_path = Path(tmp.name)

        # Download the file
        result = download_telegram_file(
            file_id=file_id,
            bot_token=bot_token,
            output_path=temp_path,
            timeout=60,
        )

        if not result.success:
            logger.error(f"Failed to download document: {result.error}")
            return None

        # Check file size
        file_size = temp_path.stat().st_size
        if file_size > MAX_TEXT_FILE_SIZE:
            logger.warning(
                f"Document too large for inline reading: {file_size} bytes "
                f"(max {MAX_TEXT_FILE_SIZE})"
            )
            # Clean up
            temp_path.unlink(missing_ok=True)
            return None

        # Read content
        content = temp_path.read_text(encoding="utf-8", errors="replace")

        # Clean up temp file
        temp_path.unlink(missing_ok=True)

        logger.info(f"Read text document '{file_name}': {len(content)} chars")
        return content

    except Exception as e:
        logger.error(f"Error reading text document: {e}", exc_info=True)
        return None


@handle_errors("collect_command")
async def collect_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect command with :subcommand syntax."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or not update.message:
        return

    # Parse :subcommand from raw message text
    raw_text = update.message.text or ""
    subcommand = None
    remaining_text = ""

    if raw_text.startswith("/collect:"):
        after_collect = raw_text[9:]
        parts = after_collect.split(None, 1)
        if parts:
            subcommand = parts[0].lower()
            remaining_text = parts[1] if len(parts) > 1 else ""
    else:
        remaining_text = " ".join(context.args) if context.args else ""

    logger.info(
        f"Collect command from user {user.id}: subcommand={subcommand}, "
        f"text_len={len(remaining_text)}"
    )

    locale = get_user_locale_from_update(update)

    # Check if user is admin
    from ...services.claude_code_service import is_claude_code_admin

    if not await is_claude_code_admin(chat.id):
        await update.message.reply_text(t("collect.no_permission", locale))
        return

    # Route to subcommand handlers
    if subcommand == "start" or subcommand == "on":
        await _collect_start(update, context)
    elif subcommand == "go":
        await _collect_go(update, context, remaining_text)
    elif subcommand == "stop" or subcommand == "off":
        await _collect_stop(update, context)
    elif subcommand == "exit":
        await _collect_exit(update, context)
    elif subcommand == "status" or subcommand == "?":
        await _collect_status(update, context)
    elif subcommand == "clear" or subcommand == "x":
        await _collect_clear(update, context)
    elif subcommand == "help":
        await _collect_help(update, context)
    elif subcommand is None:
        await _collect_help(update, context)
    else:
        await update.message.reply_text(
            t("collect.unknown_subcommand", locale, sub=subcommand).strip(),
            parse_mode="HTML",
        )


async def _collect_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:start - begin collecting items."""
    from ...services.collect_service import get_collect_service
    from ...services.keyboard_service import get_keyboard_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or not update.message:
        return

    locale = get_user_locale_from_update(update)

    service = get_collect_service()
    await service.start_session(chat.id, user.id)

    from ..adapters.telegram_keyboards import reply_keyboard_from_data

    keyboard_service = get_keyboard_service()
    collect_keyboard = reply_keyboard_from_data(
        keyboard_service.build_collect_keyboard()
    )

    await update.message.reply_text(
        "📥 "
        + t("collect.start_title", locale)
        + "\n\n"
        + t("collect.start_body", locale)
        + "\n\n"
        + t("collect.start_hint", locale),
        parse_mode="HTML",
        reply_markup=collect_keyboard,
    )


async def _collect_go(
    update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str = ""
) -> None:
    """Handle /collect:go - process collected items with Claude."""
    from ...services.collect_service import CollectItemType, get_collect_service
    from ...services.keyboard_service import get_keyboard_service
    from .claude_commands import execute_claude_prompt

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        logger.warning("_collect_go: Missing chat or user")
        return

    message = update.message or update.effective_message
    if not message:
        logger.warning("_collect_go: Missing message, cannot proceed")
        return

    service = get_collect_service()
    session = await service.end_session(chat.id)

    # Show post-collect keyboard (New Collection / Exit Collect)
    from ..adapters.telegram_keyboards import reply_keyboard_from_data

    keyboard_service = get_keyboard_service()
    post_collect_keyboard = reply_keyboard_from_data(
        keyboard_service.build_post_collect_keyboard()
    )

    locale = get_user_locale_from_update(update)

    if not session or not session.items:
        await message.reply_text(
            "📭 " + t("collect.nothing_collected", locale),
            parse_mode="HTML",
            reply_markup=post_collect_keyboard,
        )
        return

    # Build combined prompt from collected items
    combined_parts = []

    if prompt:
        combined_parts.append(f"User request: {prompt}\n")

    combined_parts.append(f"Collected {session.item_count} items:\n")

    images = []
    voices = []
    documents = []
    texts = []

    # Track documents that were read inline vs binary attachments
    binary_documents = []
    text_documents_read = 0

    for item in session.items:
        if item.type == CollectItemType.TEXT:
            texts.append(item.content)
        elif item.type == CollectItemType.IMAGE:
            images.append(item.content)
            if item.caption:
                texts.append(f"[Image caption: {item.caption}]")
        elif item.type == CollectItemType.VOICE:
            voices.append(item.content)
            if item.transcription:
                texts.append(f"[Voice message transcription]: {item.transcription}")
        elif item.type == CollectItemType.DOCUMENT:
            # Check if this is a text-based document that should be read inline
            if _is_text_document(item.mime_type, item.file_name):
                # Try to read the document content
                doc_content = _read_text_document(item.content, item.file_name)
                if doc_content:
                    # Add document content inline with clear markers
                    file_label = item.file_name or "document"
                    doc_block = f"\n--- Start of file: {file_label} ---\n"
                    doc_block += doc_content
                    doc_block += f"\n--- End of file: {file_label} ---"
                    texts.append(doc_block)
                    text_documents_read += 1
                    if item.caption:
                        texts.append(f"[Document caption: {item.caption}]")
                else:
                    # Failed to read, treat as binary
                    binary_documents.append((item.content, item.file_name))
                    if item.caption:
                        texts.append(
                            f"[Document '{item.file_name}' caption: {item.caption}]"
                        )
            else:
                # Binary document (PDF, images, etc.) - keep as attachment
                binary_documents.append((item.content, item.file_name))
                if item.caption:
                    texts.append(
                        f"[Document '{item.file_name}' caption: {item.caption}]"
                    )
        elif item.type == CollectItemType.VIDEO:
            binary_documents.append((item.content, item.file_name or "video"))
            if item.transcription:
                texts.append(f"[Video transcription]: {item.transcription}")
        elif item.type == CollectItemType.VIDEO_NOTE:
            voices.append(item.content)
            if item.transcription:
                texts.append(f"[Video note transcription]: {item.transcription}")

    # Use binary_documents for the documents list (text docs are already in texts)
    documents = binary_documents

    if texts:
        combined_parts.append("\n--- Text content ---\n")
        combined_parts.extend(texts)

    if images:
        combined_parts.append(f"\n[{len(images)} images attached]")
    if voices:
        combined_parts.append(f"\n[{len(voices)} voice messages to transcribe]")
    if documents:
        combined_parts.append(f"\n[{len(documents)} binary documents attached]")

    if text_documents_read > 0:
        logger.info(
            f"Read {text_documents_read} text documents inline for chat {chat.id}"
        )

    full_prompt = "\n".join(combined_parts)

    if hasattr(context, "user_data") and context.user_data is not None:
        context.user_data["collected_images"] = images
        context.user_data["collected_voices"] = voices
        context.user_data["collected_documents"] = documents

    logger.info(
        f"Processing collected items for chat {chat.id}: "
        f"{len(images)} images, {len(voices)} voices, {len(documents)} docs, "
        f"{len(texts)} texts"
    )

    await message.reply_text(
        "🚀 " + t("collect.processing", locale, summary=session.summary_text(locale)),
        parse_mode="HTML",
    )

    logger.info(f"Calling execute_claude_prompt with prompt length: {len(full_prompt)}")
    await execute_claude_prompt(update, context, full_prompt)
    logger.info("execute_claude_prompt completed for collect_go")


async def _collect_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:stop - cancel collecting without processing."""
    from ...services.collect_service import get_collect_service
    from ...services.keyboard_service import get_keyboard_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not update.message:
        return

    locale = get_user_locale_from_update(update)

    service = get_collect_service()
    session = await service.end_session(chat.id)

    from ..adapters.telegram_keyboards import reply_keyboard_from_data

    keyboard_service = get_keyboard_service()
    normal_keyboard = reply_keyboard_from_data(
        await keyboard_service.build_reply_keyboard(user.id if user else 0)
    )

    if session:
        await update.message.reply_text(
            "🚫 "
            + t("collect.stop_discarded", locale, summary=session.summary_text(locale)),
            parse_mode="HTML",
            reply_markup=normal_keyboard,
        )
    else:
        await update.message.reply_text(
            t("collect.not_in_mode", locale),
            parse_mode="HTML",
            reply_markup=normal_keyboard,
        )


async def _collect_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:status - show what's been collected."""
    from ...services.collect_service import get_collect_service

    chat = update.effective_chat

    if not chat or not update.message:
        return

    locale = get_user_locale_from_update(update)

    service = get_collect_service()
    status = await service.get_status(chat.id, locale=locale)

    if not status:
        await update.message.reply_text(
            t("collect.status_not_active", locale),
            parse_mode="HTML",
        )
        return

    age_mins = int(status["age_seconds"] / 60)
    await update.message.reply_text(
        "📦 "
        + t("collect.status_title", locale)
        + "\n\n"
        + t("collect.status_items", locale, summary=status["summary_text"] or "empty")
        + "\n"
        + t("collect.status_age", locale, minutes=age_mins)
        + "\n\n"
        + "<code>/collect:go</code> to process\n"
        + "<code>/collect:clear</code> to empty queue",
        parse_mode="HTML",
    )


async def _collect_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:clear - clear queue but stay in collect mode."""
    from ...services.collect_service import get_collect_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or not update.message:
        return

    service = get_collect_service()
    old_session = await service.end_session(chat.id)

    locale = get_user_locale_from_update(update)

    if old_session:
        await service.start_session(chat.id, user.id)
        await update.message.reply_text(
            "🗑 "
            + t("collect.cleared", locale, summary=old_session.summary_text(locale)),
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            t("collect.not_in_mode", locale),
            parse_mode="HTML",
        )


async def _collect_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:exit - exit collect mode and restore normal keyboard."""
    from ...services.collect_service import get_collect_service
    from ...services.keyboard_service import get_keyboard_service

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not update.message:
        return

    locale = get_user_locale_from_update(update)

    # End any active session
    service = get_collect_service()
    await service.end_session(chat.id)

    # Restore normal keyboard
    from ..adapters.telegram_keyboards import reply_keyboard_from_data

    keyboard_service = get_keyboard_service()
    normal_keyboard = reply_keyboard_from_data(
        await keyboard_service.build_reply_keyboard(user.id if user else 0)
    )

    await update.message.reply_text(
        "✅ " + t("collect.exited", locale),
        parse_mode="HTML",
        reply_markup=normal_keyboard,
    )


async def _collect_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:help - show collect command help."""
    if update.message:
        locale = get_user_locale_from_update(update)
        await update.message.reply_text(
            t("collect.help_text", locale).strip(),
            parse_mode="HTML",
        )
