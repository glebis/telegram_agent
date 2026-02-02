"""
Core bot commands.

Contains:
- /start - Welcome message and deep link handling
- /help - Help information
- /menu - Command menu
- /settings - User settings
- /gallery - Image gallery
"""

import logging
import urllib.parse
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from .base import initialize_user_chat
from .note_commands import view_note_command

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(
        f"Start command from user {user.id} in chat {chat.id}, args={context.args}"
    )

    # Check for deep link parameters FIRST
    if context.args and len(context.args) > 0:
        param = context.args[0]
        logger.info(f"Deep link param received: {param[:100]}")

        if param.startswith("note_"):
            encoded_name = param[5:]
            note_name = urllib.parse.unquote(encoded_name)
            logger.info(f"Deep link request for note: {note_name}")
            await view_note_command(update, context, note_name)
            return
        else:
            logger.info(f"Unknown deep link type: {param[:50]}")

    # Initialize user and chat in database
    success = await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    if not success:
        if update.message:
            await update.message.reply_text(
                "Sorry, there was an error initializing your session. Please try again."
            )
        return

    welcome_msg = """<b>Personal Knowledge Capture</b>

A bridge between fleeting thoughts and your knowledge system.

<b>What I process:</b>

<b>Links</b> — Send any URL. I fetch the full content, extract the essence, and save it to your Obsidian vault. Smart routing learns your preferences.

<b>Images</b> — Photos are analyzed and classified (screenshot, receipt, document, diagram, photo). Each routes to the appropriate folder. Receipts go to expenses, diagrams to research.

<b>Voice</b> — Speak your thoughts. I transcribe via Whisper, detect intent (task, note, quick thought), and append to your daily notes or inbox.

<b>Text</b> — Prefix with <code>inbox:</code>, <code>research:</code>, or <code>task:</code> to route directly.

Everything flows to your Obsidian vault. The system learns from your corrections.

<i>Send something to begin.</i>"""

    from ...services.keyboard_service import get_keyboard_service

    keyboard_service = get_keyboard_service()
    reply_keyboard = await keyboard_service.build_reply_keyboard(user.id)

    if update.message:
        await update.message.reply_text(
            welcome_msg, parse_mode="HTML", reply_markup=reply_keyboard
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    user = update.effective_user

    logger.info(f"Help command from user {user.id if user else 'unknown'}")

    help_msg = """<b>📖 Commands</b>

<b>Core:</b>
<code>/start</code> — Welcome message
<code>/help</code> — This help
<code>/menu</code> — Command menu by category
<code>/settings</code> — Preferences &amp; voice config
<code>/note name</code> — View vault note
<code>/gallery</code> — Browse uploaded images

<b>Claude Code:</b>
<code>/claude prompt</code> — Execute prompt
<code>/claude:new</code> — New session
<code>/claude:sessions</code> — List sessions
<code>/claude:lock</code> — Lock mode (all → Claude)
<code>/claude:unlock</code> — Unlock mode
<code>/claude:reset</code> — Reset session
<code>/claude:help</code> — Claude help
<code>/session</code> — Active session info
<code>/session rename</code> — Rename session
<code>/meta prompt</code> — Work on bot itself

<b>Research &amp; Collect:</b>
<code>/research topic</code> — Deep web research → vault
<code>/research:help</code> — Research options
<code>/collect:start</code> — Begin collecting items
<code>/collect:go</code> — Process collected items
<code>/collect:status</code> — Show queue
<code>/collect:stop</code> — Cancel collection

<b>Learning &amp; Review:</b>
<code>/review</code> — SRS cards due for review
<code>/srs_stats</code> — Spaced repetition stats
<code>/trail</code> — Next trail for review
<code>/trail:list</code> — All trails due

<b>Polls &amp; Tracking:</b>
<code>/polls</code> — Poll statistics
<code>/polls:send</code> — Trigger next poll
<code>/polls:pause</code> / <code>resume</code> — Toggle auto-polls

<b>Voice &amp; Media:</b>
<code>/voice_settings</code> — Voice model &amp; emotion

<b>Privacy:</b>
<code>/privacy</code> — Privacy info &amp; consent
<code>/mydata</code> — Export your data
<code>/deletedata</code> — Delete your data

<b>Mode Shortcuts:</b>
<code>/analyze</code> <code>/coach</code> <code>/creative</code> <code>/quick</code>
<code>/formal</code> <code>/tags</code> <code>/coco</code> <code>/mode</code>

<b>Tips:</b>
• Send images for AI analysis
• Voice notes → transcribed → Claude
• Links are captured to vault
• Prefix text with <code>inbox:</code> or <code>task:</code>
• Reply to any message to continue context"""

    if update.message:
        await update.message.reply_text(help_msg, parse_mode="HTML")


async def gallery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gallery command"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Gallery command from user {user.id} in chat {chat.id}")

    # Parse page number
    page = 1
    if context.args:
        try:
            page = max(1, int(context.args[0]))
        except (ValueError, IndexError):
            page = 1

    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    from ...services.gallery_service import get_gallery_service

    gallery_service = get_gallery_service()

    try:
        images, total_images, total_pages = (
            await gallery_service.get_user_images_paginated(user_id=user.id, page=page)
        )

        response_text = gallery_service.format_gallery_page(
            images=images,
            page=page,
            total_pages=total_pages,
            total_images=total_images,
        )

        from ..keyboard_utils import get_keyboard_utils

        keyboard_utils = get_keyboard_utils()
        reply_markup = keyboard_utils.create_gallery_navigation_keyboard(
            images=images, page=page, total_pages=total_pages
        )

        if update.message:
            await update.message.reply_text(
                response_text, parse_mode="HTML", reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Error in gallery command: {e}")
        if update.message:
            await update.message.reply_text(
                "❌ Sorry, there was an error loading your gallery. Please try again later."
            )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command - show all available commands by category."""
    user = update.effective_user

    if not user:
        return

    logger.info(f"Menu command from user {user.id}")

    from ...services.keyboard_service import get_keyboard_service

    service = get_keyboard_service()
    categories = service.get_command_categories()

    if not categories:
        if update.message:
            await update.message.reply_text(
                "Menu not available. Try /help instead.",
                parse_mode="HTML",
            )
        return

    lines = ["<b>📋 Command Menu</b>"]

    for cat_key, category in categories.items():
        emoji = category.get("emoji", "")
        title = category.get("title", cat_key.title())
        lines.append(f"\n{emoji} <b>{title}</b>")

        for cmd in category.get("commands", []):
            command = cmd.get("command", "")
            desc = cmd.get("description", "")
            # Commands as plain text so Telegram auto-links them as clickable
            lines.append(f"  {command} — {desc}")

    reply_keyboard = await service.build_reply_keyboard(user.id)

    if update.message:
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_keyboard,
        )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - show keyboard customization menu."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Settings command from user {user.id} in chat {chat.id}")

    from ...services.keyboard_service import (
        get_keyboard_service,
        get_auto_forward_voice,
        get_transcript_correction_level,
        get_show_transcript,
    )
    from ..keyboard_utils import get_keyboard_utils
    from ...core.database import get_db_session
    from sqlalchemy import select
    from ...models.chat import Chat

    service = get_keyboard_service()
    keyboard_utils = get_keyboard_utils()

    config = await service.get_user_config(user.id)
    enabled = config.get("enabled", True)

    # Get auto_forward_voice setting
    auto_forward_voice = await get_auto_forward_voice(chat.id)

    # Get transcript correction level
    correction_level = await get_transcript_correction_level(chat.id)

    # Get show_transcript setting
    show_transcript = await get_show_transcript(chat.id)

    # Get model settings from chat
    show_model_buttons = False
    default_model = "sonnet"
    async with get_db_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat.id)
        )
        chat_obj = result.scalar_one_or_none()
        if chat_obj:
            show_model_buttons = chat_obj.show_model_buttons
            default_model = chat_obj.claude_model or "sonnet"

    reply_markup = keyboard_utils.create_settings_keyboard(
        enabled, auto_forward_voice, correction_level, show_model_buttons, default_model,
        show_transcript,
    )

    correction_display = {"none": "OFF", "vocabulary": "Terms", "full": "Full"}
    model_emojis = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}
    model_emoji = model_emojis.get(default_model, "🎵")

    if update.message:
        await update.message.reply_text(
            "<b>⚙️ Settings</b>\n\n"
            f"Reply Keyboard: {'✅ Enabled' if enabled else '❌ Disabled'}\n"
            f"Voice → Claude: {'🔊 ON' if auto_forward_voice else '🔇 OFF'}\n"
            f"Corrections: {correction_display.get(correction_level, 'Terms')}\n"
            f"Transcripts: {'📝 ON' if show_transcript else '🔇 OFF'}\n"
            f"Model Buttons: {'✅ ON' if show_model_buttons else '🔲 OFF'}\n"
            f"Default Model: {model_emoji} {default_model.title()}\n\n"
            "Customize your settings:",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
