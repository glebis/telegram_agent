"""
Language selection command handler.

Commands:
- /language — Show language selection keyboard
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...core.database import get_db_session
from ...core.i18n import (
    SUPPORTED_LOCALES,
    get_user_locale_from_update,
    load_translations,
    set_user_locale,
    t,
)
from ...models.user import User

logger = logging.getLogger(__name__)

# Language display names and flags
LANGUAGE_INFO = {
    "en": {"name": "English", "flag": "🇬🇧"},
    "ru": {"name": "Русский", "flag": "🇷🇺"},
}


def _get_available_languages() -> list[tuple[str, str, str]]:
    """Get list of available languages as (code, name, flag) tuples."""
    # Ensure translations are loaded
    if not SUPPORTED_LOCALES:
        load_translations()

    languages = []
    for code in sorted(SUPPORTED_LOCALES):
        info = LANGUAGE_INFO.get(code, {"name": code.upper(), "flag": "🌐"})
        languages.append((code, info["name"], info["flag"]))

    return languages


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /language command — show language selection."""
    user = update.effective_user
    if not user:
        return

    locale = get_user_locale_from_update(update)
    languages = _get_available_languages()

    # Build message
    lines = [
        f"🌐 <b>{t('commands.language.title', locale)}</b>\n",
        t(
            "commands.language.current",
            locale,
            lang=LANGUAGE_INFO.get(locale, {}).get("name", locale),
        ),
        "",
        t("commands.language.select", locale),
    ]

    # Build keyboard
    keyboard = []
    for code, name, flag in languages:
        check = " ✓" if code == locale else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{flag} {name}{check}",
                    callback_data=f"lang:{code}",
                )
            ]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


async def handle_language_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Handle language selection callback."""
    query = update.callback_query
    user = update.effective_user

    if not query or not user:
        return

    # Extract language code from callback data
    new_locale = data.split(":", 1)[1] if ":" in data else data

    # Validate locale
    if new_locale not in SUPPORTED_LOCALES:
        await query.answer(t("commands.language.invalid", "en"), show_alert=True)
        return

    # Update cache
    set_user_locale(user.id, new_locale)

    # Persist to database
    try:
        async with get_db_session() as session:
            from sqlalchemy import select

            result = await session.execute(select(User).where(User.user_id == user.id))
            db_user = result.scalar_one_or_none()

            if db_user:
                db_user.language_code = new_locale
                await session.commit()
                logger.info(f"Updated language for user {user.id} to {new_locale}")
    except Exception as e:
        logger.error(f"Failed to persist language preference: {e}")

    # Send confirmation in NEW language
    lang_info = LANGUAGE_INFO.get(new_locale, {"name": new_locale, "flag": "🌐"})
    confirmation = t("commands.language.changed", new_locale, lang=lang_info["name"])

    await query.answer(f"{lang_info['flag']} {confirmation}")

    # Update message with new selection
    languages = _get_available_languages()
    lines = [
        f"🌐 <b>{t('commands.language.title', new_locale)}</b>\n",
        t("commands.language.current", new_locale, lang=lang_info["name"]),
        "",
        t("commands.language.select", new_locale),
    ]

    keyboard = []
    for code, name, flag in languages:
        check = " ✓" if code == new_locale else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{flag} {name}{check}",
                    callback_data=f"lang:{code}",
                )
            ]
        )

    try:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.debug(f"Could not edit message: {e}")
