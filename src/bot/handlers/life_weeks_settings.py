"""
Life Weeks settings command and callback handlers.

Provides configuration UI for:
- Enable/disable life weeks notifications
- Set date of birth
- Configure notification time
- Choose reply destination (daily note, weekly note, custom journal)
"""

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from ...core.database import get_db_session
from ...models.life_weeks_settings import LifeWeeksSettings
from ...services.life_weeks_image import calculate_weeks_lived
from ...utils.error_reporting import handle_errors

logger = logging.getLogger(__name__)

# Conversation states
STATE_AWAITING_DOB = 1
STATE_AWAITING_TIME = 2
STATE_AWAITING_CUSTOM_PATH = 3

# Callback data prefixes
CB_LW_ENABLE = "lw_enable"
CB_LW_DISABLE = "lw_disable"
CB_LW_SET_DOB = "lw_set_dob"
CB_LW_SET_TIME = "lw_set_time"
CB_LW_DEST = "lw_dest"
CB_LW_CUSTOM_PATH = "lw_custom_path"
CB_LW_BACK = "lw_back"


@handle_errors("life_weeks_settings_command")
async def life_weeks_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show life weeks settings menu."""
    user = update.effective_user
    if not user:
        return

    # Get current settings from database
    async with get_db_session() as session:
        result = await session.get(LifeWeeksSettings, user.id)
        if not result:
            # Create settings if they don't exist
            result = LifeWeeksSettings(user_id=user.id, username=user.username)
            session.add(result)
            await session.commit()

        settings = result

    # Calculate day of week if DOB is set
    day_name = ""
    if settings.date_of_birth and settings.life_weeks_day is not None:
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        day_name = days[settings.life_weeks_day]

    # Format destination
    dest_display = {
        "daily_note": "Daily Note",
        "weekly_note": "Weekly Note",
        "custom_journal": "Custom Journal",
    }.get(settings.life_weeks_reply_destination, settings.life_weeks_reply_destination)

    # Build status message
    status = "✅ Enabled" if settings.life_weeks_enabled else "❌ Disabled"

    text = "📅 <b>Life Weeks Notification</b>\n\n" f"Status: <b>{status}</b>\n"

    if settings.date_of_birth:
        try:
            weeks_lived = calculate_weeks_lived(settings.date_of_birth)
            text += (
                f"Birthday: <b>{settings.date_of_birth}</b> (Week {weeks_lived:,})\n"
            )
            if day_name:
                text += f"Day: <b>{day_name}</b>\n"
        except Exception:
            text += f"Birthday: <b>{settings.date_of_birth}</b>\n"
    else:
        text += "Birthday: <i>Not set</i>\n"

    text += (
        f"Time: <b>{settings.life_weeks_time}</b>\n"
        f"Reply Destination: <b>{dest_display}</b>\n"
    )

    if (
        settings.life_weeks_reply_destination == "custom_journal"
        and settings.life_weeks_custom_path
    ):
        text += f"Custom Path: <code>{settings.life_weeks_custom_path}</code>\n"

    text += "\n<i>Configure your weekly life visualization:</i>"

    # Build keyboard
    keyboard = []

    # Enable/Disable button
    if settings.life_weeks_enabled:
        keyboard.append(
            [InlineKeyboardButton("❌ Disable", callback_data=CB_LW_DISABLE)]
        )
    else:
        keyboard.append([InlineKeyboardButton("✅ Enable", callback_data=CB_LW_ENABLE)])

    # Configuration buttons
    keyboard.extend(
        [
            [InlineKeyboardButton("📅 Set Birthday", callback_data=CB_LW_SET_DOB)],
            [InlineKeyboardButton("🕐 Set Time", callback_data=CB_LW_SET_TIME)],
            [
                InlineKeyboardButton(
                    "Daily Note", callback_data=f"{CB_LW_DEST}:daily_note"
                ),
                InlineKeyboardButton(
                    "Weekly Note", callback_data=f"{CB_LW_DEST}:weekly_note"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📓 Custom Journal", callback_data=f"{CB_LW_DEST}:custom_journal"
                )
            ],
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


@handle_errors("handle_life_weeks_callback")
async def handle_life_weeks_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle life weeks settings callbacks."""
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return ConversationHandler.END

    await query.answer()

    data = query.data

    async with get_db_session() as session:
        settings = await session.get(LifeWeeksSettings, user.id)
        if not settings:
            settings = LifeWeeksSettings(user_id=user.id, username=user.username)
            session.add(settings)

        if data == CB_LW_ENABLE:
            settings.life_weeks_enabled = True
            await session.commit()
            await life_weeks_settings_command(update, context)

        elif data == CB_LW_DISABLE:
            settings.life_weeks_enabled = False
            await session.commit()
            await life_weeks_settings_command(update, context)

        elif data == CB_LW_SET_DOB:
            await query.edit_message_text(
                "📅 <b>Set Birthday</b>\n\n"
                "Please send your date of birth in format:\n"
                "<code>YYYY-MM-DD</code>\n\n"
                "Example: <code>1984-04-25</code>",
                parse_mode="HTML",
            )
            return STATE_AWAITING_DOB

        elif data == CB_LW_SET_TIME:
            await query.edit_message_text(
                "🕐 <b>Set Notification Time</b>\n\n"
                "Please send the time you want to receive notifications:\n"
                "<code>HH:MM</code>\n\n"
                "Example: <code>09:00</code>",
                parse_mode="HTML",
            )
            return STATE_AWAITING_TIME

        elif data.startswith(f"{CB_LW_DEST}:"):
            dest = data.split(":", 1)[1]
            settings.life_weeks_reply_destination = dest

            # If custom journal, prompt for path
            if dest == "custom_journal" and not settings.life_weeks_custom_path:
                await session.commit()
                await query.edit_message_text(
                    "📓 <b>Custom Journal Path</b>\n\n"
                    "Please send the full path to your journal file:\n\n"
                    "Example:\n"
                    "<code>~/Research/vault/Journal/life-reflections.md</code>",
                    parse_mode="HTML",
                )
                return STATE_AWAITING_CUSTOM_PATH

            await session.commit()
            await life_weeks_settings_command(update, context)

    return ConversationHandler.END


@handle_errors("handle_dob_input")
async def handle_dob_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle date of birth input."""
    user = update.effective_user
    if not user or not update.message:
        return ConversationHandler.END

    dob_text = update.message.text.strip()

    # Validate format
    try:
        dob_date = datetime.strptime(dob_text, "%Y-%m-%d")
        weekday = dob_date.weekday()  # 0=Monday, 6=Sunday

        # Update settings
        async with get_db_session() as session:
            settings = await session.get(LifeWeeksSettings, user.id)
            if settings:
                settings.date_of_birth = dob_text
                settings.life_weeks_day = weekday
                await session.commit()

        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        await update.message.reply_text(
            f"✅ Birthday set to {dob_text} ({days[weekday]})\n\n"
            f"Your weekly notification will be sent on {days[weekday]}s.",
            parse_mode="HTML",
        )

        # Return to settings menu
        await life_weeks_settings_command(update, context)

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid date format. Please use YYYY-MM-DD (e.g., 1984-04-25)",
            parse_mode="HTML",
        )
        return STATE_AWAITING_DOB

    return ConversationHandler.END


@handle_errors("handle_time_input")
async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle notification time input."""
    user = update.effective_user
    if not user or not update.message:
        return ConversationHandler.END

    time_text = update.message.text.strip()

    # Validate format
    try:
        hour, minute = map(int, time_text.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time range")

        # Update settings
        async with get_db_session() as session:
            settings = await session.get(LifeWeeksSettings, user.id)
            if settings:
                settings.life_weeks_time = f"{hour:02d}:{minute:02d}"
                await session.commit()

        await update.message.reply_text(
            f"✅ Notification time set to {hour:02d}:{minute:02d}",
            parse_mode="HTML",
        )

        # Return to settings menu
        await life_weeks_settings_command(update, context)

    except Exception:
        await update.message.reply_text(
            "❌ Invalid time format. Please use HH:MM (e.g., 09:00)",
            parse_mode="HTML",
        )
        return STATE_AWAITING_TIME

    return ConversationHandler.END


@handle_errors("handle_custom_path_input")
async def handle_custom_path_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle custom journal path input."""
    user = update.effective_user
    if not user or not update.message:
        return ConversationHandler.END

    path_text = update.message.text.strip()

    # Update settings
    async with get_db_session() as session:
        settings = await session.get(LifeWeeksSettings, user.id)
        if settings:
            settings.life_weeks_custom_path = path_text
            await session.commit()

    await update.message.reply_text(
        f"✅ Custom journal path set to:\n<code>{path_text}</code>",
        parse_mode="HTML",
    )

    # Return to settings menu
    await life_weeks_settings_command(update, context)

    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Cancel conversation and return to settings menu."""
    await life_weeks_settings_command(update, context)
    return ConversationHandler.END
