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

from ...core.database import get_db_session, get_chat_by_telegram_id
from ...services.voice_synthesis import get_available_voices, get_available_emotions

logger = logging.getLogger(__name__)

# Callback data prefixes for routing
CB_VOICE_MENU = "voice_menu"
CB_VOICE_SELECT = "voice_select"
CB_EMOTION_SELECT = "emotion_select"
CB_RESPONSE_MODE = "response_mode"
CB_VOICE_VERBOSITY = "voice_verbosity"
CB_TRACKER_MENU = "tracker_menu"
CB_PARTNER_MENU = "partner_menu"
CB_PARTNER_PERSONALITY = "partner_personality"
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
    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        current_voice = chat_obj.voice_name if chat_obj else "diana"
        current_emotion = chat_obj.voice_emotion if chat_obj else "cheerful"
        current_mode = chat_obj.voice_response_mode if chat_obj else "text_only"
        current_verbosity = chat_obj.voice_verbosity if chat_obj else "full"

    # Format mode for display
    mode_display = {
        "always_voice": "Always Voice",
        "smart": "Smart Mode",
        "voice_on_request": "Voice on Request",
        "text_only": "Text Only",
    }.get(current_mode, current_mode)

    # Format verbosity for display
    verbosity_display = {
        "full": "Full Response",
        "short": "Shortened",
        "brief": "Brief (~15s)",
    }.get(current_verbosity, current_verbosity)

    text = (
        "🎤 <b>Voice Settings</b>\n\n"
        f"Current voice: <b>{current_voice.title()}</b>\n"
        f"Emotion style: <b>{current_emotion.title()}</b>\n"
        f"Response mode: <b>{mode_display}</b>\n"
        f"Voice detail: <b>{verbosity_display}</b>\n\n"
        "What would you like to configure?"
    )

    keyboard = [
        [
            InlineKeyboardButton("🎭 Change Voice", callback_data=f"{CB_VOICE_SELECT}"),
        ],
        [
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
            InlineKeyboardButton(
                "📏 Voice Detail", callback_data=f"{CB_VOICE_VERBOSITY}"
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
        [InlineKeyboardButton("👩 Diana (Warm)", callback_data="voice_set:diana")]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "👩 Hannah (Professional)", callback_data="voice_set:hannah"
            )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "👩 Autumn (Friendly)", callback_data="voice_set:autumn"
            )
        ]
    )

    # Male voices
    keyboard.append(
        [
            InlineKeyboardButton(
                "👨 Austin (Supportive)", callback_data="voice_set:austin"
            )
        ]
    )
    keyboard.append(
        [InlineKeyboardButton("👨 Daniel (Calm)", callback_data="voice_set:daniel")]
    )
    keyboard.append(
        [InlineKeyboardButton("👨 Troy (Energetic)", callback_data="voice_set:troy")]
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

    text = (
        "🎨 <b>Select Emotion Style</b>\n\n" "Choose default emotion for responses:\n\n"
    )

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


async def handle_voice_verbosity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show voice verbosity/detail level selection menu."""
    text = (
        "📏 <b>Voice Detail Level</b>\n\n"
        "Choose how much detail in voice responses:\n\n"
        "• <b>Full Response</b> - Read the complete text\n"
        "• <b>Shortened</b> - Key points, 2-4 sentences\n"
        "• <b>Brief (~15s)</b> - One sentence summary"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📄 Full Response", callback_data="verbosity_set:full"
            ),
        ],
        [
            InlineKeyboardButton("📝 Shortened", callback_data="verbosity_set:short"),
        ],
        [
            InlineKeyboardButton(
                "⚡ Brief (~15s)", callback_data="verbosity_set:brief"
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


async def handle_voice_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send a test voice message."""
    from ...services.voice_synthesis import synthesize_voice_mp3

    chat = update.effective_chat
    if not chat:
        return

    await update.callback_query.answer("Generating test voice...")

    try:
        # Get user settings from database
        async with get_db_session() as session:
            chat_obj = await get_chat_by_telegram_id(session, chat.id)
            voice = chat_obj.voice_name if chat_obj else "diana"
            emotion = chat_obj.voice_emotion if chat_obj else "cheerful"

        # Generate test message
        test_text = (
            "Hey! This is a test of the voice synthesis. "
            "How does it sound? Let me know if you'd like to try a different voice!"
        )

        # Generate MP3 (high quality, fast encoding)
        audio_bytes = await synthesize_voice_mp3(
            test_text, voice=voice, emotion=emotion, quality=2
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
            InlineKeyboardButton(
                "⏰ Set Check-in Times", callback_data="tracker_times"
            ),
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
    """Main /partners command - shows virtual accountability partner menu."""
    chat = update.effective_chat
    if not chat:
        return

    # Get current settings
    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        current_personality = chat_obj.partner_personality if chat_obj else "supportive"
        current_voice = chat_obj.partner_voice_override if chat_obj else None
        check_in_time = chat_obj.check_in_time if chat_obj else "19:00"

    personality_emoji = {
        "gentle": "😊",
        "supportive": "💪",
        "direct": "📊",
        "assertive": "🔥",
        "tough_love": "💀",
    }

    personality_display = {
        "gentle": "Gentle",
        "supportive": "Supportive",
        "direct": "Direct",
        "assertive": "Assertive",
        "tough_love": "Tough Love",
    }

    current_emoji = personality_emoji.get(current_personality, "💪")
    current_name = personality_display.get(current_personality, "Supportive")

    voice_info = f" (Voice: {current_voice})" if current_voice else ""

    text = (
        "🤖 <b>Virtual Accountability Partner</b>\n\n"
        f"Your AI accountability assistant helps you stay on track with personalized check-ins.\n\n"
        f"<b>Current Settings:</b>\n"
        f"• Personality: {current_emoji} {current_name}{voice_info}\n"
        f"• Check-in time: {check_in_time}\n\n"
        "What would you like to configure?"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🎭 Change Personality", callback_data=f"{CB_PARTNER_PERSONALITY}"
            ),
        ],
        [
            InlineKeyboardButton(
                "⏰ Set Check-in Time", callback_data="partner_check_in_time"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔔 Notification Settings", callback_data="partner_notifications"
            ),
        ],
        [
            InlineKeyboardButton("🎙️ Test Voice", callback_data="partner_test_voice"),
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


async def partner_personality_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show personality selection menu."""
    chat = update.effective_chat
    if not chat:
        return

    # Get current settings
    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        current_personality = chat_obj.partner_personality if chat_obj else "supportive"

    text = (
        "🎭 <b>Choose Your Partner's Personality</b>\n\n"
        "Select how you want your accountability partner to communicate:\n\n"
        "😊 <b>Gentle</b> — Kind, understanding, never harsh\n"
        '   <i>"It\'s okay if you missed today. Tomorrow is a fresh start."</i>\n\n'
        "💪 <b>Supportive</b> — Encouraging, celebrates wins, gentle on failures\n"
        "   <i>\"I noticed you missed yesterday. That's alright! Let's get back on track.\"</i>\n\n"
        "📊 <b>Direct</b> — Clear, factual, no sugar-coating but respectful\n"
        "   <i>\"You've missed 3 days this week. What's the plan to course-correct?\"</i>\n\n"
        "🔥 <b>Assertive</b> — Firm, holds you accountable, expects commitment\n"
        '   <i>"Third day in a row. You committed to this. Time to step up."</i>\n\n'
        "💀 <b>Tough Love</b> — Brutally honest, no excuses, drill sergeant mode\n"
        '   <i>"Stop making excuses. You said this mattered. Prove it."</i>\n'
    )

    keyboard = [
        [
            InlineKeyboardButton(
                f"😊 Gentle{' ✓' if current_personality == 'gentle' else ''}",
                callback_data="personality_gentle",
            )
        ],
        [
            InlineKeyboardButton(
                f"💪 Supportive{' ✓' if current_personality == 'supportive' else ''}",
                callback_data="personality_supportive",
            )
        ],
        [
            InlineKeyboardButton(
                f"📊 Direct{' ✓' if current_personality == 'direct' else ''}",
                callback_data="personality_direct",
            )
        ],
        [
            InlineKeyboardButton(
                f"🔥 Assertive{' ✓' if current_personality == 'assertive' else ''}",
                callback_data="personality_assertive",
            )
        ],
        [
            InlineKeyboardButton(
                f"💀 Tough Love{' ✓' if current_personality == 'tough_love' else ''}",
                callback_data="personality_tough_love",
            )
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"{CB_PARTNER_MENU}")],
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


async def keyboard_display_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Keyboard and display settings submenu."""
    from ...services.keyboard_service import (
        get_keyboard_service,
        get_auto_forward_voice,
        get_transcript_correction_level,
        get_show_transcript,
    )
    from ...core.database import get_db_session
    from sqlalchemy import select
    from ...models.chat import Chat
    from ..keyboard_utils import get_keyboard_utils

    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

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
        result = await session.execute(select(Chat).where(Chat.chat_id == chat.id))
        chat_obj = result.scalar_one_or_none()
        if chat_obj:
            show_model_buttons = chat_obj.show_model_buttons
            default_model = chat_obj.claude_model or "sonnet"

    reply_markup = keyboard_utils.create_settings_keyboard(
        enabled,
        auto_forward_voice,
        correction_level,
        show_model_buttons,
        default_model,
        show_transcript,
    )

    correction_display = {"none": "OFF", "vocabulary": "Terms", "full": "Full"}
    model_emojis = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}
    model_emoji = model_emojis.get(default_model, "🎵")

    text = (
        "⌨️ <b>Keyboard & Display Settings</b>\n\n"
        f"Reply Keyboard: {'✅ Enabled' if enabled else '❌ Disabled'}\n"
        f"Voice → Claude: {'🔊 ON' if auto_forward_voice else '🔇 OFF'}\n"
        f"Corrections: {correction_display.get(correction_level, 'Terms')}\n"
        f"Transcripts: {'📝 ON' if show_transcript else '🔇 OFF'}\n"
        f"Model Buttons: {'✅ ON' if show_model_buttons else '🔲 OFF'}\n"
        f"Default Model: {model_emoji} {default_model.title()}\n\n"
        "Customize your settings:"
    )

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
        "⚙️ <b>Settings</b>\n\n" "Configure your personal accountability assistant:\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("🎤 Voice Settings", callback_data=f"{CB_VOICE_MENU}"),
        ],
        [
            InlineKeyboardButton(
                "⌨️ Keyboard & Display", callback_data="keyboard_display_menu"
            ),
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
            InlineKeyboardButton(
                "🔔 Notifications", callback_data="notifications_menu"
            ),
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
    """Route voice settings callback queries to appropriate handlers.

    IMPORTANT: This handler manages its own query.answer() calls.
    The parent callback_handlers.py must NOT pre-answer the query,
    otherwise Telegram rejects the second answer and alerts/toasts
    never show to the user.
    """
    query = update.callback_query

    if data == CB_VOICE_MENU:
        await query.answer()
        await voice_settings_command(update, context)

    elif data == CB_VOICE_SELECT:
        await query.answer()
        await handle_voice_select(update, context)

    elif data == CB_EMOTION_SELECT:
        await query.answer()
        await handle_emotion_select(update, context)

    elif data == CB_RESPONSE_MODE:
        await query.answer()
        await handle_response_mode(update, context)

    elif data == CB_VOICE_VERBOSITY:
        await query.answer()
        await handle_voice_verbosity(update, context)

    elif data == "voice_test":
        # handle_voice_test calls its own answer()
        await handle_voice_test(update, context)

    elif data.startswith("voice_set:"):
        voice = data.split(":")[1]
        chat = update.effective_chat
        if chat:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.voice_name = voice
                    await session.commit()
                    logger.info(f"Voice set to {voice} for chat {chat.id}")
        await query.answer(f"✅ Voice set to {voice.title()}!")
        await voice_settings_command(update, context)

    elif data.startswith("emotion_set:"):
        emotion = data.split(":")[1]
        chat = update.effective_chat
        if chat:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.voice_emotion = emotion
                    await session.commit()
                    logger.info(f"Emotion set to {emotion} for chat {chat.id}")
        await query.answer(f"✅ Emotion set to {emotion.title()}!")
        await voice_settings_command(update, context)

    elif data.startswith("mode_set:"):
        mode = data.split(":")[1]
        chat = update.effective_chat
        if chat:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.voice_response_mode = mode
                    await session.commit()
                    logger.info(f"Response mode set to {mode} for chat {chat.id}")

        # Format mode for display
        mode_display = {
            "always_voice": "Always Voice",
            "smart": "Smart Mode",
            "voice_on_request": "Voice on Request",
            "text_only": "Text Only",
        }.get(mode, mode)

        await query.answer(f"✅ Response mode: {mode_display}")
        await voice_settings_command(update, context)

    elif data.startswith("verbosity_set:"):
        verbosity = data.split(":")[1]
        chat = update.effective_chat
        if chat:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.voice_verbosity = verbosity
                    await session.commit()
                    logger.info(
                        f"Voice verbosity set to {verbosity} for chat {chat.id}"
                    )

        # Format verbosity for display
        verbosity_labels = {
            "full": "Full Response",
            "short": "Shortened",
            "brief": "Brief (~15s)",
        }
        await query.answer(
            f"✅ Voice detail: {verbosity_labels.get(verbosity, verbosity)}"
        )
        await voice_settings_command(update, context)

    elif data == CB_TRACKER_MENU:
        await query.answer()
        await tracker_settings_command(update, context)

    elif data == CB_PARTNER_MENU:
        await query.answer()
        await partner_settings_command(update, context)

    elif data == CB_PARTNER_PERSONALITY:
        await query.answer()
        await partner_personality_menu(update, context)

    elif data.startswith("personality_"):
        # Handle personality selection
        personality = data.replace("personality_", "")
        chat = update.effective_chat
        if chat:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.partner_personality = personality
                    await session.commit()

            personality_names = {
                "gentle": "Gentle 😊",
                "supportive": "Supportive 💪",
                "direct": "Direct 📊",
                "assertive": "Assertive 🔥",
                "tough_love": "Tough Love 💀",
            }
            await query.answer(
                f"✅ Personality set to {personality_names.get(personality, personality)}"
            )
            await partner_settings_command(update, context)

    elif data == CB_BACK:
        await query.answer()
        await main_settings_menu(update, context)

    elif data == "keyboard_display_menu":
        await query.answer()
        await keyboard_display_menu(update, context)

    # Tracker sub-actions (placeholder) — show_alert=True displays a modal popup
    elif data in ("tracker_add", "tracker_list", "tracker_times"):
        await query.answer("🚧 Coming soon!", show_alert=True)

    # Partner sub-actions (placeholder)
    elif data in (
        "partner_check_in_time",
        "partner_notifications",
        "partner_test_voice",
    ):
        await query.answer("🚧 Coming soon!", show_alert=True)

    # Top-level settings sub-menus (placeholder)
    elif data in ("notifications_menu", "privacy_menu"):
        await query.answer("🚧 Coming soon!", show_alert=True)

    else:
        await query.answer()
        logger.warning(f"Unknown voice settings callback: {data}")
