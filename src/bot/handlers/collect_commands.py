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

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


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

    # Check if user is admin
    from ...services.claude_code_service import is_claude_code_admin

    if not await is_claude_code_admin(chat.id):
        await update.message.reply_text(
            "You don't have permission to use collect mode."
        )
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
            f"Unknown collect subcommand: <code>{subcommand}</code>\n"
            "Use <code>/collect:help</code> for available commands.",
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

    service = get_collect_service()
    await service.start_session(chat.id, user.id)

    keyboard_service = get_keyboard_service()
    collect_keyboard = keyboard_service.build_collect_keyboard()

    await update.message.reply_text(
        "📥 <b>Collect mode ON</b>\n\n"
        "Send files, voice, images, text — I'll collect them silently.\n\n"
        "When ready, tap <b>▶️ Go</b> or say <i>\"now respond\"</i>",
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
    keyboard_service = get_keyboard_service()
    post_collect_keyboard = keyboard_service.build_post_collect_keyboard()

    if not session or not session.items:
        await message.reply_text(
            "📭 Nothing collected. Use <code>/collect:start</code> first.",
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
            documents.append((item.content, item.file_name))
            if item.caption:
                texts.append(f"[Document '{item.file_name}' caption: {item.caption}]")
        elif item.type == CollectItemType.VIDEO:
            documents.append((item.content, item.file_name or "video"))
            if item.transcription:
                texts.append(f"[Video transcription]: {item.transcription}")
        elif item.type == CollectItemType.VIDEO_NOTE:
            voices.append(item.content)
            if item.transcription:
                texts.append(f"[Video note transcription]: {item.transcription}")

    if texts:
        combined_parts.append("\n--- Text content ---\n")
        combined_parts.extend(texts)

    if images:
        combined_parts.append(f"\n[{len(images)} images attached]")
    if voices:
        combined_parts.append(f"\n[{len(voices)} voice messages to transcribe]")
    if documents:
        combined_parts.append(f"\n[{len(documents)} documents attached]")

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
        f"🚀 Processing {session.summary_text()}...",
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

    service = get_collect_service()
    session = await service.end_session(chat.id)

    keyboard_service = get_keyboard_service()
    normal_keyboard = await keyboard_service.build_reply_keyboard(
        user.id if user else 0
    )

    if session:
        await update.message.reply_text(
            f"🚫 Collect mode OFF. Discarded {session.summary_text()}.",
            parse_mode="HTML",
            reply_markup=normal_keyboard,
        )
    else:
        await update.message.reply_text(
            "Not in collect mode.",
            parse_mode="HTML",
            reply_markup=normal_keyboard,
        )


async def _collect_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:status - show what's been collected."""
    from ...services.collect_service import get_collect_service

    chat = update.effective_chat

    if not chat or not update.message:
        return

    service = get_collect_service()
    status = await service.get_status(chat.id)

    if not status:
        await update.message.reply_text(
            "Not in collect mode. Use <code>/collect:start</code>",
            parse_mode="HTML",
        )
        return

    age_mins = int(status["age_seconds"] / 60)
    await update.message.reply_text(
        f"📦 <b>Collect Queue</b>\n\n"
        f"Items: {status['summary_text'] or 'empty'}\n"
        f"Age: {age_mins} min\n\n"
        f"<code>/collect:go</code> to process\n"
        f"<code>/collect:clear</code> to empty queue",
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

    if old_session:
        await service.start_session(chat.id, user.id)
        await update.message.reply_text(
            f"🗑 Cleared {old_session.summary_text()}. Still collecting.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "Not in collect mode.",
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

    # End any active session
    service = get_collect_service()
    await service.end_session(chat.id)

    # Restore normal keyboard
    keyboard_service = get_keyboard_service()
    normal_keyboard = await keyboard_service.build_reply_keyboard(
        user.id if user else 0
    )

    await update.message.reply_text(
        "✅ Exited collect mode.",
        parse_mode="HTML",
        reply_markup=normal_keyboard,
    )


async def _collect_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /collect:help - show collect command help."""
    if update.message:
        await update.message.reply_text(
            "<b>Collect Mode</b>\n\n"
            "Batch input — send multiple items, process together.\n\n"
            "<code>/collect:start</code> — Begin collecting\n"
            "<code>/collect:go</code> — Process all with Claude\n"
            "<code>/collect:go prompt</code> — Process with prompt\n"
            "<code>/collect:status</code> — Show queue\n"
            "<code>/collect:clear</code> — Empty queue\n"
            "<code>/collect:stop</code> — Cancel\n"
            "<code>/collect:exit</code> — Exit collect mode\n\n"
            "<i>Trigger words: \"now respond\", \"process this\"</i>",
            parse_mode="HTML",
        )
