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

from telegram import Update
from telegram.ext import ContextTypes

from ...core.authorization import AuthTier, require_tier
from ...core.i18n import get_user_locale_from_update, t
from ...utils.error_reporting import handle_errors
from .base import initialize_user_chat
from .note_commands import view_note_command

logger = logging.getLogger(__name__)


@handle_errors("start_command")
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
        language_code=user.language_code,
    )

    locale = get_user_locale_from_update(update)

    if not success:
        if update.message:
            await update.message.reply_text(t("commands.start.init_error", locale))
        return

    welcome_msg = t("commands.start.welcome", locale).strip()

    from ...services.keyboard_service import get_keyboard_service
    from ..adapters.telegram_keyboards import reply_keyboard_from_data

    keyboard_service = get_keyboard_service()
    reply_keyboard = reply_keyboard_from_data(
        await keyboard_service.build_reply_keyboard(user.id, locale)
    )

    if update.message:
        await update.message.reply_text(
            welcome_msg, parse_mode="HTML", reply_markup=reply_keyboard
        )


HELP_CATEGORIES = [
    ("claude", "🤖"),
    ("images", "🖼"),
    ("notes", "📝"),
    ("voice", "🎙"),
    ("tracker", "📊"),
    ("settings", "⚙️"),
    ("system", "🔧"),
]


def _build_help_keyboard(locale: str = "en"):
    """Build inline keyboard with help category buttons."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = []
    row = []
    for cat_key, emoji in HELP_CATEGORIES:
        title = t(f"commands.help.cat_{cat_key}.title", locale)
        row.append(
            InlineKeyboardButton(f"{emoji} {title}", callback_data=f"help:{cat_key}")
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


@handle_errors("help_command")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command — show categories with inline keyboard."""
    user = update.effective_user

    logger.info(f"Help command from user {user.id if user else 'unknown'}")

    locale = get_user_locale_from_update(update)
    overview = t("commands.help.overview", locale)
    keyboard = _build_help_keyboard(locale)

    if update.message:
        await update.message.reply_text(
            f"<b>📖 Help</b>\n\n{overview}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )


@handle_errors("handle_help_callback")
async def handle_help_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Handle help:xxx callback queries."""
    query = update.callback_query
    if not query:
        return

    locale = get_user_locale_from_update(update)
    # data is "help:category" or "help:back"
    _, _, category = data.partition(":")

    if category == "back":
        overview = t("commands.help.overview", locale)
        keyboard = _build_help_keyboard(locale)
        await query.edit_message_text(
            f"<b>📖 Help</b>\n\n{overview}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    # Show category detail with back button
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    text = t(f"commands.help.cat_{category}.text", locale).strip()
    back_label = t("commands.help.back_button", locale)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(back_label, callback_data="help:back")]]
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


@handle_errors("gallery_command")
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
        language_code=user.language_code,
    )

    locale = get_user_locale_from_update(update)

    from ...services.gallery_service import get_gallery_service

    gallery_service = get_gallery_service()

    try:
        images, total_images, total_pages = (
            await gallery_service.get_user_images_paginated(
                user_id=user.id, page=page, locale=locale
            )
        )

        response_text = gallery_service.format_gallery_page(
            images=images,
            page=page,
            total_pages=total_pages,
            total_images=total_images,
            locale=locale,
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
            await update.message.reply_text("❌ " + t("commands.gallery.error", locale))


@handle_errors("menu_command")
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command - show all available commands by category."""
    user = update.effective_user

    if not user:
        return

    logger.info(f"Menu command from user {user.id}")

    locale = get_user_locale_from_update(update)

    from ...services.keyboard_service import get_keyboard_service

    service = get_keyboard_service()
    categories = service.get_command_categories()

    if not categories:
        if update.message:
            await update.message.reply_text(
                t("commands.menu.not_available", locale),
                parse_mode="HTML",
            )
        return

    lines = ["<b>📋 " + t("commands.menu.title", locale) + "</b>"]

    for cat_key, category in categories.items():
        emoji = category.get("emoji", "")
        # Prefer i18n title via title_key, fall back to raw title
        title_key = category.get("title_key")
        if title_key:
            title = t(title_key, locale)
            if title == title_key:
                title = category.get("title", cat_key.title())
        else:
            title = category.get("title", cat_key.title())
        lines.append(f"\n{emoji} <b>{title}</b>")

        for cmd in category.get("commands", []):
            command = cmd.get("command", "")
            # Prefer i18n description via description_key
            desc_key = cmd.get("description_key")
            if desc_key:
                desc = t(desc_key, locale)
                if desc == desc_key:
                    desc = cmd.get("description", "")
            else:
                desc = cmd.get("description", "")
            # Commands as plain text so Telegram auto-links them as clickable
            lines.append(f"  {command} — {desc}")

    from ..adapters.telegram_keyboards import reply_keyboard_from_data

    reply_keyboard = reply_keyboard_from_data(
        await service.build_reply_keyboard(user.id, locale)
    )

    if update.message:
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_keyboard,
        )


@require_tier(AuthTier.ADMIN)
@handle_errors("settings_command")
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - show unified settings hub (admin only)."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info(f"Settings command from user {user.id} in chat {chat.id}")

    # Import and call the unified settings hub
    from .voice_settings_commands import main_settings_menu

    await main_settings_menu(update, context)
