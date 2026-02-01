"""
Voice settings and accountability partner configuration handlers.

Provides inline keyboard interfaces for:
- Voice synthesis settings (voice model, emotion, response mode)
- Tracker management (add, edit, remove trackers)
- Accountability partner configuration
- Notification preferences
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...services.voice_synthesis import get_available_voices, get_available_emotions

logger = logging.getLogger(__name__)

# Callback data prefixes for routing
CB_VOICE_MENU = "voice_menu"
CB_VOICE_SELECT = "voice_select"
CB_EMOTION_SELECT = "emotion_select"
CB_RESPONSE_MODE = "response_mode"
CB_TRACKER_MENU = "tracker_menu"
CB_PARTNER_MENU = "partner_menu"
CB_BACK = "settings_back"


async def voice_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Main /voice_settings command - shows voice configuration menu.
    """
    chat = update.effective_chat
    if not chat:
        return

    # Get current settings from database
    # For now, use defaults
    current_voice = "diana"
    current_emotion = "cheerful"
    current_mode = "smart"

    text = (
        "🎤 <b>Voice Settings</b>\n\n"
        f"Current voice: <b>{current_voice}</b>\n"
        f"Emotion style: <b>{current_emotion}</b>\n"
        f"Response mode: <b>{current_mode}</b>\n\n"
        "What would you like to configure?"
    )

    keyboard = [
        [
            InlineKeyboardButton("🎭 Change Voice", callback_data=f"{CB_VOICE_SELECT}"),
            InlineKeyboardButton(
                "🎨 Change Emotion", callback_data=f"{CB_EMOTION_SELECT}"
            ),
        ],
        [
            InlineKeyboardButton(
                "📢 Response Mode", callback_data=f"{CB_RESPONSE_MODE}"
            ),
        ],
        [
            InlineKeyboardButton("🎙️ Test Voice", callback_data="voice_test"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to Settings", callback_data=f"{CB_BACK}"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def handle_voice_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show voice selection menu."""
    voices = get_available_voices()

    text = "🎭 <b>Select Voice</b>\n\n" "Choose a voice for responses:\n\n"

    keyboard = []

    # Female voices
    keyboard.append(
        [
            InlineKeyboardButton("👩 Diana (Warm)", callback_data="voice_set:diana"),
            InlineKeyboardButton(
                "👩 Hannah (Professional)", callback_data="voice_set:hannah"
            ),
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "👩 Autumn (Friendly)", callback_data="voice_set:autumn"
            ),
        ]
    )

    # Male voices
    keyboard.append(
        [
            InlineKeyboardButton(
                "👨 Austin (Supportive)", callback_data="voice_set:austin"
            ),
            InlineKeyboardButton("👨 Daniel (Calm)", callback_data="voice_set:daniel"),
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "👨 Troy (Energetic)", callback_data="voice_set:troy"
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton("⬅️ Back", callback_data=f"{CB_VOICE_MENU}"),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


async def handle_emotion_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show emotion style selection menu."""
    emotions = get_available_emotions()

    text = "🎨 <b>Select Emotion Style</b>\n\n" "Choose default emotion for responses:\n\n"

    keyboard = [
        [
            InlineKeyboardButton(
                "😊 Cheerful (Upbeat)", callback_data="emotion_set:cheerful"
            ),
        ],
        [
            InlineKeyboardButton(
                "😐 Neutral (Standard)", callback_data="emotion_set:neutral"
            ),
        ],
        [
            InlineKeyboardButton(
                "🤫 Whisper (Soft)", callback_data="emotion_set:whisper"
            ),
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data=f"{CB_VOICE_MENU}"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


async def handle_response_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show response mode selection menu."""
    text = (
        "📢 <b>Response Mode</b>\n\n"
        "Choose when to use voice responses:\n\n"
        "• <b>Always Voice</b> - All responses synthesized\n"
        "• <b>Smart Mode</b> - Voice for check-ins, text for complex info\n"
        "• <b>Voice on Request</b> - Only when you ask\n"
        "• <b>Text Only</b> - Disable voice responses"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔊 Always Voice", callback_data="mode_set:always_voice"
            ),
        ],
        [
            InlineKeyboardButton("🧠 Smart Mode", callback_data="mode_set:smart"),
        ],
        [
            InlineKeyboardButton(
                "🎯 Voice on Request", callback_data="mode_set:voice_on_request"
            ),
        ],
        [
            InlineKeyboardButton("📝 Text Only", callback_data="mode_set:text_only"),
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data=f"{CB_VOICE_MENU}"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


async def handle_voice_test(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate and send a test voice message."""
    from ...services.voice_synthesis import synthesize_voice_mp3

    chat = update.effective_chat
    if not chat:
        return

    await update.callback_query.answer("Generating test voice...")

    try:
        # Get user settings (for now use defaults)
        voice = "diana"

        # Generate test message
        test_text = (
            "Hey! This is a test of the voice synthesis. "
            "How does it sound? Let me know if you'd like to try a different voice!"
        )

        # Generate MP3 (high quality, fast encoding)
        audio_bytes = await synthesize_voice_mp3(
            test_text, voice=voice, emotion="cheerful", quality=2
        )

        # Send as voice message (no caption)
        await context.bot.send_voice(
            chat_id=chat.id,
            voice=audio_bytes,
        )

    except Exception as e:
        logger.error(f"Error generating test voice: {e}")
        await update.callback_query.answer("Error generating voice. Try again later.")


async def tracker_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Main /trackers command - shows tracker management menu."""
    text = (
        "📊 <b>Tracker Settings</b>\n\n"
        "Manage your habits, medications, values, and commitments.\n\n"
        "What would you like to do?"
    )

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Tracker", callback_data="tracker_add"),
        ],
        [
            InlineKeyboardButton("📋 View Trackers", callback_data="tracker_list"),
        ],
        [
            InlineKeyboardButton("⏰ Set Check-in Times", callback_data="tracker_times"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to Settings", callback_data=f"{CB_BACK}"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def partner_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Main /partners command - shows accountability partner menu."""
    text = (
        "👥 <b>Accountability Partners</b>\n\n"
        "Share your progress with trusted contacts.\n\n"
        "Partners can receive:\n"
        "• Daily progress updates\n"
        "• Weekly summaries\n"
        "• Milestone celebrations\n"
        "• Struggle alerts (optional)\n\n"
        "What would you like to do?"
    )

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Partner", callback_data="partner_add"),
        ],
        [
            InlineKeyboardButton("👥 Manage Partners", callback_data="partner_list"),
        ],
        [
            InlineKeyboardButton(
                "🔔 Notification Settings", callback_data="partner_notifications"
            ),
        ],
        [
            InlineKeyboardButton("🔒 Privacy Settings", callback_data="partner_privacy"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to Settings", callback_data=f"{CB_BACK}"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def main_settings_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Main settings menu with all configuration options."""
    text = (
        "⚙️ <b>Settings</b>\n\n"
        "Configure your personal accountability assistant:\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("🎤 Voice Settings", callback_data=f"{CB_VOICE_MENU}"),
        ],
        [
            InlineKeyboardButton(
                "📊 Tracker Settings", callback_data=f"{CB_TRACKER_MENU}"
            ),
        ],
        [
            InlineKeyboardButton(
                "👥 Accountability Partners", callback_data=f"{CB_PARTNER_MENU}"
            ),
        ],
        [
            InlineKeyboardButton("🔔 Notifications", callback_data="notifications_menu"),
        ],
        [
            InlineKeyboardButton("🔒 Privacy", callback_data="privacy_menu"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


# Callback query router for voice settings
async def handle_voice_settings_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Route voice settings callback queries to appropriate handlers."""

    if data == CB_VOICE_MENU:
        await voice_settings_command(update, context)

    elif data == CB_VOICE_SELECT:
        await handle_voice_select(update, context)

    elif data == CB_EMOTION_SELECT:
        await handle_emotion_select(update, context)

    elif data == CB_RESPONSE_MODE:
        await handle_response_mode(update, context)

    elif data == "voice_test":
        await handle_voice_test(update, context)

    elif data.startswith("voice_set:"):
        voice = data.split(":")[1]
        # TODO: Save to database
        await update.callback_query.answer(f"Voice set to {voice}!")
        await voice_settings_command(update, context)

    elif data.startswith("emotion_set:"):
        emotion = data.split(":")[1]
        # TODO: Save to database
        await update.callback_query.answer(f"Emotion set to {emotion}!")
        await voice_settings_command(update, context)

    elif data.startswith("mode_set:"):
        mode = data.split(":")[1]
        # TODO: Save to database
        await update.callback_query.answer(f"Response mode set to {mode}!")
        await voice_settings_command(update, context)

    elif data == CB_TRACKER_MENU:
        await tracker_settings_command(update, context)

    elif data == CB_PARTNER_MENU:
        await partner_settings_command(update, context)

    elif data == CB_BACK:
        await main_settings_menu(update, context)

    else:
        logger.warning(f"Unknown voice settings callback: {data}")
