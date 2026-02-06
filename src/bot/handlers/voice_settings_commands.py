"""
Voice settings and accountability partner configuration handlers.

Provides inline keyboard interfaces for:
- Voice synthesis settings (voice model, emotion, response mode)
- Tracker management (add, edit, remove trackers)
- Accountability partner configuration
- Notification preferences
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...core.database import get_chat_by_telegram_id, get_db_session
from ...core.i18n import get_user_locale_from_update, t
from ...models.tracker import CheckIn, Tracker
from ...models.user_settings import UserSettings
from ...services.tts_service import get_tts_service

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
CB_TTS_PROVIDER = "tts_provider_select"


async def voice_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Main /voice_settings command - shows voice configuration menu.
    """
    locale = get_user_locale_from_update(update)
    chat = update.effective_chat
    if not chat:
        return

    # Get current settings from database
    service = get_tts_service()
    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        current_voice = chat_obj.voice_name if chat_obj else "diana"
        current_emotion = chat_obj.voice_emotion if chat_obj else "cheerful"
        current_mode = chat_obj.voice_response_mode if chat_obj else "text_only"
        current_verbosity = chat_obj.voice_verbosity if chat_obj else "full"
        tts_provider = chat_obj.tts_provider if chat_obj else ""

    resolved_provider = service.resolve_provider(tts_provider)

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

    provider_display = {
        "groq": "Groq Orpheus",
        "openai": "OpenAI TTS",
    }.get(resolved_provider, resolved_provider)
    provider_label = (
        provider_display if tts_provider else f"{provider_display} (default)"
    )

    text = (
        "🎤 <b>Voice Settings</b>\n\n"
        f"TTS provider: <b>{provider_label}</b>\n"
        f"Current voice: <b>{current_voice.title()}</b>\n"
        f"Emotion style: <b>{current_emotion.title()}</b>\n"
        f"Response mode: <b>{mode_display}</b>\n"
        f"Voice detail: <b>{verbosity_display}</b>\n\n"
        "What would you like to configure?"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                t("inline.voice.tts_provider", locale),
                callback_data=f"{CB_TTS_PROVIDER}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.change_voice", locale),
                callback_data=f"{CB_VOICE_SELECT}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.change_emotion", locale),
                callback_data=f"{CB_EMOTION_SELECT}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.response_mode", locale),
                callback_data=f"{CB_RESPONSE_MODE}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.voice_detail", locale),
                callback_data=f"{CB_VOICE_VERBOSITY}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.test_voice", locale), callback_data="voice_test"
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.common.back_to_settings", locale),
                callback_data=f"{CB_BACK}",
            ),
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
    """Show voice selection menu (dynamic per provider)."""
    locale = get_user_locale_from_update(update)
    chat = update.effective_chat
    service = get_tts_service()

    # Determine active provider
    tts_provider = ""
    if chat:
        async with get_db_session() as session:
            chat_obj = await get_chat_by_telegram_id(session, chat.id)
            if chat_obj:
                tts_provider = chat_obj.tts_provider

    provider = service.resolve_provider(tts_provider)
    voices = service.get_voices(provider)

    provider_label = {"groq": "Groq Orpheus", "openai": "OpenAI TTS"}.get(
        provider, provider
    )
    text = (
        f"🎭 <b>Select Voice</b> ({provider_label})\n\n"
        "Choose a voice for responses:\n\n"
    )

    keyboard = []
    for name, description in voices.items():
        # Truncate description to keep button short
        short_desc = description.split(",")[0] if "," in description else description
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{name.title()} — {short_desc}", callback_data=f"voice_set:{name}"
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_VOICE_MENU}"
            ),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


async def handle_emotion_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show emotion style selection menu (or info if provider lacks emotions)."""
    locale = get_user_locale_from_update(update)
    chat = update.effective_chat
    service = get_tts_service()

    tts_provider = ""
    if chat:
        async with get_db_session() as session:
            chat_obj = await get_chat_by_telegram_id(session, chat.id)
            if chat_obj:
                tts_provider = chat_obj.tts_provider

    provider = service.resolve_provider(tts_provider)
    emotions = service.get_emotions(provider)

    if not emotions:
        provider_label = {"groq": "Groq Orpheus", "openai": "OpenAI TTS"}.get(
            provider, provider
        )
        text = (
            "🎨 <b>Emotion Styles</b>\n\n"
            f"{provider_label} does not support emotion tags.\n"
            "Switch to Groq Orpheus for emotion support."
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    t("inline.common.back", locale),
                    callback_data=f"{CB_VOICE_MENU}",
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )
        return

    emotion_emojis = {"cheerful": "😊", "neutral": "😐", "whisper": "🤫"}

    text = (
        "🎨 <b>Select Emotion Style</b>\n\n" "Choose default emotion for responses:\n\n"
    )

    keyboard = []
    for name, description in emotions.items():
        emoji = emotion_emojis.get(name, "🎵")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{emoji} {name.title()} ({description})",
                    callback_data=f"emotion_set:{name}",
                )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_VOICE_MENU}"
            )
        ],
    )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


async def handle_response_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show response mode selection menu."""
    locale = get_user_locale_from_update(update)
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
                t("inline.voice.always_voice", locale),
                callback_data="mode_set:always_voice",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.smart_mode", locale),
                callback_data="mode_set:smart",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.voice_on_request", locale),
                callback_data="mode_set:voice_on_request",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.text_only", locale),
                callback_data="mode_set:text_only",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_VOICE_MENU}"
            ),
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
    locale = get_user_locale_from_update(update)
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
                t("inline.voice.full_response", locale),
                callback_data="verbosity_set:full",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.shortened", locale),
                callback_data="verbosity_set:short",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.voice.brief", locale),
                callback_data="verbosity_set:brief",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_VOICE_MENU}"
            ),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


async def handle_voice_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send a test voice message using the user's provider."""
    chat = update.effective_chat
    if not chat:
        return

    await update.callback_query.answer("Generating test voice...")

    try:
        service = get_tts_service()

        # Get user settings from database
        async with get_db_session() as session:
            chat_obj = await get_chat_by_telegram_id(session, chat.id)
            voice = chat_obj.voice_name if chat_obj else "diana"
            emotion = chat_obj.voice_emotion if chat_obj else "cheerful"
            tts_provider = chat_obj.tts_provider if chat_obj else ""

        # Generate test message
        test_text = (
            "Hey! This is a test of the voice synthesis. "
            "How does it sound? Let me know if you'd like to try a different voice!"
        )

        # Generate MP3 using user's provider
        audio_bytes = await service.synthesize_mp3(
            test_text,
            voice=voice,
            emotion=emotion,
            provider=tts_provider,
            quality=2,
        )

        # Send as voice message (no caption)
        await context.bot.send_voice(
            chat_id=chat.id,
            voice=audio_bytes,
        )

    except Exception as e:
        logger.error(f"Error generating test voice: {e}")
        await update.callback_query.answer("Error generating voice. Try again later.")


async def handle_tts_provider_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show TTS provider selection menu."""
    locale = get_user_locale_from_update(update)
    chat = update.effective_chat
    if not chat:
        return

    get_tts_service()

    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        current = chat_obj.tts_provider if chat_obj else ""

    def check(val):
        return " ✓" if current == val else ""

    text = (
        "🔊 <b>Select TTS Provider</b>\n\n"
        "Choose your text-to-speech engine:\n\n"
        "• <b>Groq Orpheus</b> — 6 voices, 3 emotions, expressive\n"
        "• <b>OpenAI TTS</b> — 10 voices, no emotions, natural\n"
        "• <b>System Default</b> — uses the server default\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                f"Groq Orpheus{check('groq')}", callback_data="tts_set:groq"
            ),
        ],
        [
            InlineKeyboardButton(
                f"OpenAI TTS{check('openai')}", callback_data="tts_set:openai"
            ),
        ],
        [
            InlineKeyboardButton(
                f"System Default{check('')}", callback_data="tts_set:"
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_VOICE_MENU}"
            ),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


TRACKER_TYPE_EMOJI = {
    "habit": "🔄",
    "medication": "💊",
    "value": "💎",
    "commitment": "🎯",
}
TRACKER_TYPES = ("habit", "medication", "value", "commitment")


async def _ensure_user_settings_for_tracker(user_id: int) -> None:
    """Ensure UserSettings row exists for user."""
    async with get_db_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        if not result.scalar_one_or_none():
            session.add(UserSettings(user_id=user_id))
            await session.flush()
            await session.commit()


async def tracker_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Main /trackers command - shows tracker management menu with live list."""
    locale = get_user_locale_from_update(update)
    user = update.effective_user
    if not user:
        return

    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker)
            .where(
                Tracker.user_id == user.id,
                Tracker.active == True,  # noqa: E712
            )
            .order_by(Tracker.type, Tracker.name)
        )
        trackers = list(result.scalars().all())

    if trackers:
        lines = [
            "📊 <b>Tracker Settings</b>\n",
            "<b>Active Trackers:</b>",
        ]
        for tr in trackers:
            emoji = TRACKER_TYPE_EMOJI.get(tr.type, "📋")
            time_str = f" ⏰ {tr.check_time}" if tr.check_time else ""
            lines.append(f"  {emoji} {tr.name} ({tr.type}){time_str}")
        lines.append("\nManage your trackers:")
        text = "\n".join(lines)
    else:
        text = (
            "📊 <b>Tracker Settings</b>\n\n"
            "No active trackers yet.\n\n"
            "Add your first tracker to start building streaks!"
        )

    keyboard = [
        [
            InlineKeyboardButton(
                t("inline.tracker.add_tracker", locale),
                callback_data="tracker_add",
            ),
        ],
    ]

    if trackers:
        keyboard.append(
            [
                InlineKeyboardButton(
                    t("inline.tracker.view_trackers", locale),
                    callback_data="tracker_list",
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    t("inline.tracker.set_times", locale),
                    callback_data="tracker_times",
                ),
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back_to_settings", locale),
                callback_data=f"{CB_BACK}",
            ),
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


async def tracker_add_type_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show tracker type selection menu."""
    locale = get_user_locale_from_update(update)

    text = (
        "➕ <b>Add New Tracker</b>\n\n"
        "Choose the type of tracker:\n\n"
        "🔄 <b>Habit</b> — Regular activities (exercise, reading)\n"
        "💊 <b>Medication</b> — Meds, supplements, vitamins\n"
        "💎 <b>Value</b> — Values to uphold (gratitude, patience)\n"
        "🎯 <b>Commitment</b> — Specific goals or promises\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("🔄 Habit", callback_data="tracker_type:habit"),
            InlineKeyboardButton(
                "💊 Medication", callback_data="tracker_type:medication"
            ),
        ],
        [
            InlineKeyboardButton("💎 Value", callback_data="tracker_type:value"),
            InlineKeyboardButton(
                "🎯 Commitment", callback_data="tracker_type:commitment"
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.common.back", locale),
                callback_data=f"{CB_TRACKER_MENU}",
            ),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def tracker_name_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, tracker_type: str
) -> None:
    """Prompt user to type tracker name. Stores type in user_data."""
    emoji = TRACKER_TYPE_EMOJI.get(tracker_type, "📋")

    # Store the pending tracker type so message handler can pick it up
    if context and context.user_data is not None:
        context.user_data["pending_tracker_type"] = tracker_type

    text = (
        f"{emoji} <b>New {tracker_type.title()} Tracker</b>\n\n"
        "Send the name for your tracker as your next message.\n\n"
        "<i>Examples: Exercise, Vitamins, Read 30min, Meditate</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="tracker_cancel_add",
            ),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def handle_tracker_name_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Handle text message when user is in tracker-add flow.

    Returns True if the message was consumed, False otherwise.
    """
    if not context or context.user_data is None:
        return False

    tracker_type = context.user_data.get("pending_tracker_type")
    if not tracker_type:
        return False

    # Clear the pending state
    del context.user_data["pending_tracker_type"]

    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return False

    name = update.message.text.strip()
    if not name:
        await update.message.reply_text(
            "Please provide a name for the tracker.", parse_mode="HTML"
        )
        return True

    # Truncate if too long
    if len(name) > 100:
        name = name[:100]

    await _ensure_user_settings_for_tracker(user.id)

    async with get_db_session() as session:
        # Check for duplicate
        existing = await session.execute(
            select(Tracker).where(
                Tracker.user_id == user.id,
                Tracker.active == True,  # noqa: E712
                func.lower(Tracker.name) == name.lower(),
            )
        )
        if existing.scalar_one_or_none():
            await update.message.reply_text(
                f"⚠️ A tracker named <b>{name}</b> already exists.",
                parse_mode="HTML",
            )
            return True

        tracker = Tracker(
            user_id=user.id,
            type=tracker_type,
            name=name,
            check_frequency="daily",
            active=True,
        )
        session.add(tracker)
        await session.commit()

    emoji = TRACKER_TYPE_EMOJI.get(tracker_type, "📋")
    keyboard = [
        [
            InlineKeyboardButton("📊 View Trackers", callback_data="tracker_list"),
            InlineKeyboardButton("➕ Add Another", callback_data="tracker_add"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ {emoji} <b>{name}</b> created!\n"
        f"Type: {tracker_type}\n"
        f"Frequency: daily\n\n"
        f"Check in with: <code>/track:done {name}</code>",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    return True


async def tracker_list_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all trackers with management buttons."""
    locale = get_user_locale_from_update(update)
    user = update.effective_user
    if not user:
        return

    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker)
            .where(Tracker.user_id == user.id)
            .order_by(Tracker.active.desc(), Tracker.type, Tracker.name)
        )
        trackers = list(result.scalars().all())

    if not trackers:
        text = (
            "📋 <b>Your Trackers</b>\n\n"
            "No trackers found.\n"
            "Tap <b>Add Tracker</b> to create one!"
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Tracker", callback_data="tracker_add"),
            ],
            [
                InlineKeyboardButton(
                    t("inline.common.back", locale),
                    callback_data=f"{CB_TRACKER_MENU}",
                ),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=reply_markup
            )
        return

    active = [tr for tr in trackers if tr.active]
    archived = [tr for tr in trackers if not tr.active]

    lines = ["📋 <b>Your Trackers</b>\n"]

    if active:
        lines.append("<b>Active:</b>")
        for tr in active:
            emoji = TRACKER_TYPE_EMOJI.get(tr.type, "📋")
            time_str = f" ⏰ {tr.check_time}" if tr.check_time else ""
            lines.append(f"  {emoji} <b>{tr.name}</b> ({tr.type}){time_str}")

    if archived:
        lines.append("\n<b>Archived:</b>")
        for tr in archived:
            emoji = TRACKER_TYPE_EMOJI.get(tr.type, "📋")
            lines.append(f"  {emoji} <s>{tr.name}</s> ({tr.type})")

    lines.append("\nTap a tracker to manage it:")
    text = "\n".join(lines)

    # Build per-tracker management buttons
    keyboard = []
    for tr in active:
        emoji = TRACKER_TYPE_EMOJI.get(tr.type, "📋")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{emoji} {tr.name}",
                    callback_data=f"tracker_detail:{tr.id}",
                ),
            ]
        )

    if archived:
        for tr in archived:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"📦 {tr.name} (restore)",
                        callback_data=f"tracker_restore:{tr.id}",
                    ),
                ]
            )

    keyboard.append(
        [
            InlineKeyboardButton("➕ Add Tracker", callback_data="tracker_add"),
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back", locale),
                callback_data=f"{CB_TRACKER_MENU}",
            ),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def tracker_detail_view(
    update: Update, context: ContextTypes.DEFAULT_TYPE, tracker_id: int
) -> None:
    """Show detail view for a single tracker with action buttons."""
    locale = get_user_locale_from_update(update)
    user = update.effective_user
    if not user:
        return

    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker).where(Tracker.id == tracker_id, Tracker.user_id == user.id)
        )
        tracker = result.scalar_one_or_none()

        if not tracker:
            if update.callback_query:
                await update.callback_query.answer("Tracker not found", show_alert=True)
            return

        # Get streak info
        streak = await _get_tracker_streak(session, user.id, tracker_id)
        best = await _get_tracker_best_streak(session, user.id, tracker_id)
        rate_7 = await _get_tracker_rate(session, user.id, tracker_id, 7)

        # Get today's check-in
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ci_result = await session.execute(
            select(CheckIn).where(
                CheckIn.user_id == user.id,
                CheckIn.tracker_id == tracker_id,
                CheckIn.created_at >= today_start,
            )
        )
        today_checkin = ci_result.scalar_one_or_none()

        # Get last 7 days grid
        week_ago = datetime.now() - timedelta(days=7)
        grid_result = await session.execute(
            select(CheckIn).where(
                CheckIn.user_id == user.id,
                CheckIn.tracker_id == tracker_id,
                CheckIn.created_at >= week_ago,
            )
        )
        recent = list(grid_result.scalars().all())

    emoji = TRACKER_TYPE_EMOJI.get(tracker.type, "📋")
    grid = _build_streak_grid(recent, 7)
    today_status = today_checkin.status if today_checkin else "not checked in"
    time_str = tracker.check_time or "not set"

    text = (
        f"{emoji} <b>{tracker.name}</b>\n\n"
        f"Type: {tracker.type}\n"
        f"Frequency: {tracker.check_frequency}\n"
        f"Check-in time: {time_str}\n"
        f"Today: {today_status}\n\n"
        f"<b>Last 7 days:</b> {grid}\n"
        f"🔥 Streak: {streak} days (best: {best})\n"
        f"📊 7-day rate: {rate_7:.0%}"
    )

    keyboard = []

    # Check-in buttons (only if not done today)
    if not today_checkin or today_checkin.status != "completed":
        keyboard.append(
            [
                InlineKeyboardButton(
                    "✅ Done Today",
                    callback_data=f"tracker_done:{tracker_id}",
                ),
                InlineKeyboardButton(
                    "⏭ Skip Today",
                    callback_data=f"tracker_skip:{tracker_id}",
                ),
            ]
        )

    # Management buttons
    keyboard.append(
        [
            InlineKeyboardButton(
                "⏰ Set Time",
                callback_data=f"tracker_settime:{tracker_id}",
            ),
            InlineKeyboardButton(
                "🗑 Archive",
                callback_data=f"tracker_archive:{tracker_id}",
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back", locale),
                callback_data="tracker_list",
            ),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def tracker_time_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, tracker_id: int
) -> None:
    """Show per-tracker check-in time picker."""
    locale = get_user_locale_from_update(update)
    user = update.effective_user
    if not user:
        return

    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker).where(Tracker.id == tracker_id, Tracker.user_id == user.id)
        )
        tracker = result.scalar_one_or_none()

    if not tracker:
        if update.callback_query:
            await update.callback_query.answer("Tracker not found", show_alert=True)
        return

    emoji = TRACKER_TYPE_EMOJI.get(tracker.type, "📋")
    current_time = tracker.check_time or "not set"

    text = (
        f"⏰ <b>Set Check-in Time</b>\n\n"
        f"{emoji} <b>{tracker.name}</b>\n"
        f"Current: <b>{current_time}</b>\n\n"
        "Choose a check-in reminder time:"
    )

    # Build time grid: 07:00 - 22:00, 4 per row
    hours = list(range(7, 23))
    keyboard = []
    row = []
    for h in hours:
        time_str = f"{h:02d}:00"
        check = " ✓" if time_str == tracker.check_time else ""
        row.append(
            InlineKeyboardButton(
                f"{time_str}{check}",
                callback_data=f"tracker_time_set:{tracker_id}:{time_str}",
            )
        )
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Clear time option
    keyboard.append(
        [
            InlineKeyboardButton(
                "🚫 No Reminder",
                callback_data=f"tracker_time_clear:{tracker_id}",
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back", locale),
                callback_data=f"tracker_detail:{tracker_id}",
            ),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


async def tracker_times_overview(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show all trackers with their check-in times for bulk editing."""
    locale = get_user_locale_from_update(update)
    user = update.effective_user
    if not user:
        return

    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker)
            .where(
                Tracker.user_id == user.id,
                Tracker.active == True,  # noqa: E712
            )
            .order_by(Tracker.type, Tracker.name)
        )
        trackers = list(result.scalars().all())

    if not trackers:
        text = "⏰ <b>Check-in Times</b>\n\n" "No active trackers. Add one first!"
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Tracker", callback_data="tracker_add"),
            ],
            [
                InlineKeyboardButton(
                    t("inline.common.back", locale),
                    callback_data=f"{CB_TRACKER_MENU}",
                ),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=reply_markup
            )
        return

    lines = [
        "⏰ <b>Check-in Times</b>\n",
        "Tap a tracker to set its reminder time:\n",
    ]
    for tr in trackers:
        emoji = TRACKER_TYPE_EMOJI.get(tr.type, "📋")
        time_str = tr.check_time or "no reminder"
        lines.append(f"  {emoji} <b>{tr.name}</b> — {time_str}")

    text = "\n".join(lines)

    keyboard = []
    for tr in trackers:
        emoji = TRACKER_TYPE_EMOJI.get(tr.type, "📋")
        time_display = tr.check_time or "—"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{emoji} {tr.name} ({time_display})",
                    callback_data=f"tracker_settime:{tr.id}",
                ),
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back", locale),
                callback_data=f"{CB_TRACKER_MENU}",
            ),
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=reply_markup
        )


# --- Helper functions for tracker stats ---


async def _get_tracker_streak(session, user_id: int, tracker_id: int) -> int:
    """Calculate current streak for a tracker."""
    result = await session.execute(
        select(CheckIn)
        .where(
            CheckIn.user_id == user_id,
            CheckIn.tracker_id == tracker_id,
            CheckIn.status.in_(["completed", "partial"]),
        )
        .order_by(CheckIn.created_at.desc())
    )
    check_ins = list(result.scalars().all())
    if not check_ins:
        return 0

    streak = 0
    current_date = datetime.now().date()
    for ci in check_ins:
        ci_date = ci.created_at.date()
        if ci_date == current_date:
            streak += 1
            current_date -= timedelta(days=1)
        elif ci_date < current_date:
            break
    return streak


async def _get_tracker_best_streak(session, user_id: int, tracker_id: int) -> int:
    """Calculate best streak ever for a tracker."""
    result = await session.execute(
        select(CheckIn)
        .where(
            CheckIn.user_id == user_id,
            CheckIn.tracker_id == tracker_id,
            CheckIn.status.in_(["completed", "partial"]),
        )
        .order_by(CheckIn.created_at.asc())
    )
    check_ins = list(result.scalars().all())
    if not check_ins:
        return 0

    best = 1
    current = 1
    for i in range(1, len(check_ins)):
        prev_date = check_ins[i - 1].created_at.date()
        curr_date = check_ins[i].created_at.date()
        if curr_date == prev_date:
            continue
        elif curr_date == prev_date + timedelta(days=1):
            current += 1
        else:
            best = max(best, current)
            current = 1
    return max(best, current)


async def _get_tracker_rate(session, user_id: int, tracker_id: int, days: int) -> float:
    """Calculate completion rate over last N days."""
    start_date = datetime.now() - timedelta(days=days)
    result = await session.execute(
        select(func.count(CheckIn.id)).where(
            CheckIn.user_id == user_id,
            CheckIn.tracker_id == tracker_id,
            CheckIn.status == "completed",
            CheckIn.created_at >= start_date,
        )
    )
    completed = result.scalar() or 0
    if days == 0:
        return 0.0
    return min(completed / days, 1.0)


def _build_streak_grid(check_ins, days: int = 7) -> str:
    """Generate visual streak grid for last N days."""
    today = datetime.now().date()
    status_by_date = {}
    for ci in check_ins:
        d = ci.created_at.date()
        if d not in status_by_date or ci.status == "completed":
            status_by_date[d] = ci.status

    grid = ""
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        status = status_by_date.get(d)
        if status == "completed":
            grid += "🟩"
        elif status == "skipped":
            grid += "🟨"
        elif status == "partial":
            grid += "🟧"
        else:
            grid += "⬜"
    return grid


async def partner_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Main /partners command - shows virtual accountability partner menu."""
    locale = get_user_locale_from_update(update)
    chat = update.effective_chat
    if not chat:
        return

    # Get current settings
    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        enabled = chat_obj.accountability_enabled if chat_obj else False
        current_personality = chat_obj.partner_personality if chat_obj else "supportive"
        current_voice = chat_obj.partner_voice_override if chat_obj else None
        check_in_time = chat_obj.check_in_time if chat_obj else "19:00"
        celebration_style = chat_obj.celebration_style if chat_obj else "moderate"
        struggle_threshold = chat_obj.struggle_threshold if chat_obj else 3

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
    status_icon = "ON" if enabled else "OFF"

    text = (
        "🤖 <b>Virtual Accountability Partner</b>\n\n"
        f"Status: <b>{status_icon}</b>\n\n"
    )

    if enabled:
        text += (
            f"<b>Current Settings:</b>\n"
            f"• Personality: {current_emoji} {current_name}{voice_info}\n"
            f"• Check-in time: {check_in_time}\n"
            f"• Celebrations: {celebration_style.title()}\n"
            f"• Struggle alert after: {struggle_threshold} missed days\n\n"
            "What would you like to configure?"
        )
    else:
        text += (
            "Enable the partner to get scheduled voice reminders, "
            "milestone celebrations, and struggle support."
        )

    toggle_key = "inline.partner.disable" if enabled else "inline.partner.enable"
    toggle_cb = "partner_toggle_disable" if enabled else "partner_toggle_enable"

    keyboard = [
        [InlineKeyboardButton(t(toggle_key, locale), callback_data=toggle_cb)],
    ]

    if enabled:
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(
                        t("inline.partner.change_personality", locale),
                        callback_data=f"{CB_PARTNER_PERSONALITY}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        t("inline.partner.set_checkin_time", locale),
                        callback_data="partner_check_in_time",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        t("inline.partner.notifications", locale),
                        callback_data="partner_notifications",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        t("inline.partner.test_voice", locale),
                        callback_data="partner_test_voice",
                    ),
                ],
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back_to_settings", locale),
                callback_data=f"{CB_BACK}",
            )
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


async def partner_personality_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show personality selection menu."""
    locale = get_user_locale_from_update(update)
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
                t("inline.partner.gentle", locale)
                + (" ✓" if current_personality == "gentle" else ""),
                callback_data="personality_gentle",
            )
        ],
        [
            InlineKeyboardButton(
                t("inline.partner.supportive", locale)
                + (" ✓" if current_personality == "supportive" else ""),
                callback_data="personality_supportive",
            )
        ],
        [
            InlineKeyboardButton(
                t("inline.partner.direct", locale)
                + (" ✓" if current_personality == "direct" else ""),
                callback_data="personality_direct",
            )
        ],
        [
            InlineKeyboardButton(
                t("inline.partner.assertive", locale)
                + (" ✓" if current_personality == "assertive" else ""),
                callback_data="personality_assertive",
            )
        ],
        [
            InlineKeyboardButton(
                t("inline.partner.tough_love", locale)
                + (" ✓" if current_personality == "tough_love" else ""),
                callback_data="personality_tough_love",
            )
        ],
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_PARTNER_MENU}"
            )
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


async def partner_check_in_time_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show check-in time picker grid."""
    locale = get_user_locale_from_update(update)
    chat = update.effective_chat
    if not chat:
        return

    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        current_time = chat_obj.check_in_time if chat_obj else "19:00"

    text = (
        "⏰ <b>Set Check-in Time</b>\n\n"
        f"Current: <b>{current_time}</b>\n\n"
        "Choose when you'd like your daily check-in reminder:"
    )

    # Build time grid: 07:00 - 22:00, 4 per row
    hours = list(range(7, 23))
    keyboard = []
    row = []
    for h in hours:
        time_str = f"{h:02d}:00"
        check = " ✓" if time_str == current_time else ""
        row.append(
            InlineKeyboardButton(
                f"{time_str}{check}", callback_data=f"partner_time_{time_str}"
            )
        )
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_PARTNER_MENU}"
            )
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


async def partner_notifications_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show notification settings (celebration style, struggle threshold)."""
    locale = get_user_locale_from_update(update)
    chat = update.effective_chat
    if not chat:
        return

    async with get_db_session() as session:
        chat_obj = await get_chat_by_telegram_id(session, chat.id)
        celebration_style = chat_obj.celebration_style if chat_obj else "moderate"
        struggle_threshold = chat_obj.struggle_threshold if chat_obj else 3

    text = (
        "🔔 <b>Notification Settings</b>\n\n"
        "<b>Celebration Style</b>\n"
        "How enthusiastic should milestone celebrations be?\n\n"
        "<b>Struggle Alert Threshold</b>\n"
        "After how many consecutive missed days should I check in?"
    )

    def celeb_check(style):
        return " ✓" if style == celebration_style else ""

    def thresh_check(val):
        return " ✓" if val == struggle_threshold else ""

    keyboard = [
        [
            InlineKeyboardButton(
                t("inline.partner.quiet", locale) + celeb_check("quiet"),
                callback_data="partner_celeb_quiet",
            ),
            InlineKeyboardButton(
                t("inline.partner.moderate", locale) + celeb_check("moderate"),
                callback_data="partner_celeb_moderate",
            ),
            InlineKeyboardButton(
                t("inline.partner.enthusiastic", locale) + celeb_check("enthusiastic"),
                callback_data="partner_celeb_enthusiastic",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.partner.n_days", locale, n=2) + thresh_check(2),
                callback_data="partner_thresh_2",
            ),
            InlineKeyboardButton(
                t("inline.partner.n_days", locale, n=3) + thresh_check(3),
                callback_data="partner_thresh_3",
            ),
            InlineKeyboardButton(
                t("inline.partner.n_days", locale, n=5) + thresh_check(5),
                callback_data="partner_thresh_5",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.common.back", locale), callback_data=f"{CB_PARTNER_MENU}"
            )
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


async def partner_test_voice_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate and send a test partner voice message."""
    from ...services.accountability_service import AccountabilityService
    from ...services.voice_synthesis import synthesize_voice_mp3

    chat = update.effective_chat
    if not chat:
        return

    await update.callback_query.answer("Generating partner voice...")

    try:
        async with get_db_session() as session:
            chat_obj = await get_chat_by_telegram_id(session, chat.id)
            personality = chat_obj.partner_personality if chat_obj else "supportive"
            voice_override = chat_obj.partner_voice_override if chat_obj else None

        # Generate sample check-in message
        message = AccountabilityService.generate_check_in_message(
            personality=personality,
            tracker_name="your habit",
            current_streak=5,
        )

        # Get voice config from personality
        from ...core.defaults_loader import get_config_value

        personalities = get_config_value("accountability.personalities", {})
        personality_config = personalities.get(personality, personalities["supportive"])
        voice = voice_override or personality_config["voice"]
        emotion = personality_config["emotion"]

        audio_bytes = await synthesize_voice_mp3(message, voice=voice, emotion=emotion)

        await context.bot.send_voice(
            chat_id=chat.id,
            voice=audio_bytes,
        )

    except Exception as e:
        logger.error(f"Error generating partner test voice: {e}")
        try:
            await update.callback_query.answer(
                "Error generating voice. Try again later.", show_alert=True
            )
        except Exception:
            pass


async def keyboard_display_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Keyboard and display settings submenu."""
    from sqlalchemy import select

    from ...core.database import get_db_session
    from ...models.chat import Chat
    from ...services.keyboard_service import (
        get_auto_forward_voice,
        get_keyboard_service,
        get_show_transcript,
        get_transcript_correction_level,
        get_whisper_use_locale,
    )
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

    # Get whisper locale setting
    whisper_locale = await get_whisper_use_locale(chat.id)

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
        whisper_use_locale=whisper_locale,
    )

    correction_display = {"none": "OFF", "vocabulary": "Terms", "full": "Full"}
    model_emojis = {"haiku": "⚡", "sonnet": "🎵", "opus": "🎭"}
    model_emoji = model_emojis.get(default_model, "🎵")
    whisper_lang = "Auto (user locale)" if whisper_locale else "English"

    text = (
        "⌨️ <b>Keyboard & Display Settings</b>\n\n"
        f"Reply Keyboard: {'✅ Enabled' if enabled else '❌ Disabled'}\n"
        f"Voice → Claude: {'🔊 ON' if auto_forward_voice else '🔇 OFF'}\n"
        f"Corrections: {correction_display.get(correction_level, 'Terms')}\n"
        f"Transcripts: {'📝 ON' if show_transcript else '🔇 OFF'}\n"
        f"Whisper Language: 🌐 {whisper_lang}\n"
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
    locale = get_user_locale_from_update(update)
    text = (
        "⚙️ <b>Settings</b>\n\n" "Configure your personal accountability assistant:\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                t("inline.main_settings.voice", locale),
                callback_data=f"{CB_VOICE_MENU}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.main_settings.keyboard_display", locale),
                callback_data="keyboard_display_menu",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.main_settings.trackers", locale),
                callback_data=f"{CB_TRACKER_MENU}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.main_settings.accountability", locale),
                callback_data=f"{CB_PARTNER_MENU}",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.main_settings.notifications", locale),
                callback_data="notifications_menu",
            ),
        ],
        [
            InlineKeyboardButton(
                t("inline.main_settings.privacy", locale),
                callback_data="privacy_menu",
            ),
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

    elif data == CB_TTS_PROVIDER:
        await query.answer()
        await handle_tts_provider_select(update, context)

    elif data.startswith("tts_set:"):
        new_provider = data.split(":")[1]  # "" | "groq" | "openai"
        chat = update.effective_chat
        if chat:
            service = get_tts_service()
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    old_provider = service.resolve_provider(chat_obj.tts_provider)
                    chat_obj.tts_provider = new_provider
                    new_resolved = service.resolve_provider(new_provider)

                    # Auto-map voice when switching providers
                    if old_provider != new_resolved:
                        mapped_voice = service.map_voice(
                            chat_obj.voice_name, new_resolved
                        )
                        chat_obj.voice_name = mapped_voice
                        # Reset emotion if target provider has none
                        if not service.get_emotions(new_resolved):
                            chat_obj.voice_emotion = "neutral"

                    await session.commit()
                    logger.info(
                        f"TTS provider set to '{new_provider}' for chat {chat.id}"
                    )

        provider_label = {"groq": "Groq Orpheus", "openai": "OpenAI TTS"}.get(
            new_provider, "System Default"
        )
        await query.answer(f"TTS: {provider_label}")
        await voice_settings_command(update, context)

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

    # Tracker sub-actions — fully implemented
    elif data == "tracker_add":
        await query.answer()
        await tracker_add_type_menu(update, context)

    elif data.startswith("tracker_type:"):
        tracker_type = data.split(":")[1]
        await query.answer()
        await tracker_name_prompt(update, context, tracker_type)

    elif data == "tracker_cancel_add":
        # Clear pending state and go back to tracker menu
        if context and context.user_data is not None:
            context.user_data.pop("pending_tracker_type", None)
        await query.answer("Cancelled")
        await tracker_settings_command(update, context)

    elif data == "tracker_list":
        await query.answer()
        await tracker_list_view(update, context)

    elif data.startswith("tracker_detail:"):
        tracker_id = int(data.split(":")[1])
        await query.answer()
        await tracker_detail_view(update, context, tracker_id)

    elif data.startswith("tracker_done:"):
        tracker_id = int(data.split(":")[1])
        user = update.effective_user
        if user:
            async with get_db_session() as session:
                # Check if already done
                today_start = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                existing = await session.execute(
                    select(CheckIn).where(
                        CheckIn.user_id == user.id,
                        CheckIn.tracker_id == tracker_id,
                        CheckIn.created_at >= today_start,
                    )
                )
                checkin = existing.scalar_one_or_none()

                if checkin and checkin.status == "completed":
                    await query.answer("Already done today!", show_alert=True)
                elif checkin:
                    checkin.status = "completed"
                    await session.commit()
                    await query.answer("✅ Marked as done!")
                    await tracker_detail_view(update, context, tracker_id)
                else:
                    new_checkin = CheckIn(
                        user_id=user.id,
                        tracker_id=tracker_id,
                        status="completed",
                    )
                    session.add(new_checkin)
                    await session.commit()
                    await query.answer("✅ Marked as done!")
                    await tracker_detail_view(update, context, tracker_id)

    elif data.startswith("tracker_skip:"):
        tracker_id = int(data.split(":")[1])
        user = update.effective_user
        if user:
            async with get_db_session() as session:
                today_start = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                existing = await session.execute(
                    select(CheckIn).where(
                        CheckIn.user_id == user.id,
                        CheckIn.tracker_id == tracker_id,
                        CheckIn.created_at >= today_start,
                    )
                )
                checkin = existing.scalar_one_or_none()

                if checkin:
                    checkin.status = "skipped"
                else:
                    new_checkin = CheckIn(
                        user_id=user.id,
                        tracker_id=tracker_id,
                        status="skipped",
                    )
                    session.add(new_checkin)
                await session.commit()
                await query.answer("⏭ Skipped for today")
                await tracker_detail_view(update, context, tracker_id)

    elif data.startswith("tracker_archive:"):
        tracker_id = int(data.split(":")[1])
        user = update.effective_user
        if user:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Tracker).where(
                        Tracker.id == tracker_id,
                        Tracker.user_id == user.id,
                    )
                )
                tracker = result.scalar_one_or_none()
                if tracker:
                    tracker.active = False
                    await session.commit()
                    await query.answer(f"🗑 {tracker.name} archived", show_alert=True)
                    await tracker_list_view(update, context)
                else:
                    await query.answer("Tracker not found", show_alert=True)

    elif data.startswith("tracker_restore:"):
        tracker_id = int(data.split(":")[1])
        user = update.effective_user
        if user:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Tracker).where(
                        Tracker.id == tracker_id,
                        Tracker.user_id == user.id,
                    )
                )
                tracker = result.scalar_one_or_none()
                if tracker:
                    tracker.active = True
                    await session.commit()
                    await query.answer(f"✅ {tracker.name} restored!", show_alert=True)
                    await tracker_list_view(update, context)
                else:
                    await query.answer("Tracker not found", show_alert=True)

    elif data == "tracker_times":
        await query.answer()
        await tracker_times_overview(update, context)

    elif data.startswith("tracker_settime:"):
        tracker_id = int(data.split(":")[1])
        await query.answer()
        await tracker_time_menu(update, context, tracker_id)

    elif data.startswith("tracker_time_set:"):
        parts = data.split(":")
        tracker_id = int(parts[1])
        time_val = parts[2]
        user = update.effective_user
        if user:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Tracker).where(
                        Tracker.id == tracker_id,
                        Tracker.user_id == user.id,
                    )
                )
                tracker = result.scalar_one_or_none()
                if tracker:
                    tracker.check_time = time_val
                    await session.commit()
                    await query.answer(f"⏰ {tracker.name} → {time_val}")
                    await tracker_detail_view(update, context, tracker_id)
                else:
                    await query.answer("Tracker not found", show_alert=True)

    elif data.startswith("tracker_time_clear:"):
        tracker_id = int(data.split(":")[1])
        user = update.effective_user
        if user:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Tracker).where(
                        Tracker.id == tracker_id,
                        Tracker.user_id == user.id,
                    )
                )
                tracker = result.scalar_one_or_none()
                if tracker:
                    tracker.check_time = None
                    await session.commit()
                    await query.answer(f"🚫 {tracker.name} reminder cleared")
                    await tracker_detail_view(update, context, tracker_id)
                else:
                    await query.answer("Tracker not found", show_alert=True)

    # Partner toggle enable/disable
    elif data == "partner_toggle_enable":
        chat = update.effective_chat
        user = update.effective_user
        if chat and user:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.accountability_enabled = True
                    await session.commit()
            # Schedule jobs
            try:
                from ...services.accountability_scheduler import (
                    schedule_user_checkins,
                )

                await schedule_user_checkins(context.application, user.id, chat.id)
            except Exception as e:
                logger.error(f"Error scheduling checkins on enable: {e}")
            await query.answer("Accountability partner enabled!")
            await partner_settings_command(update, context)

    elif data == "partner_toggle_disable":
        chat = update.effective_chat
        user = update.effective_user
        if chat and user:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.accountability_enabled = False
                    await session.commit()
            # Cancel jobs
            try:
                from ...services.accountability_scheduler import (
                    cancel_user_checkins,
                )

                await cancel_user_checkins(context.application, user.id)
            except Exception as e:
                logger.error(f"Error cancelling checkins on disable: {e}")
            await query.answer("Accountability partner disabled.")
            await partner_settings_command(update, context)

    # Check-in time picker
    elif data == "partner_check_in_time":
        await query.answer()
        await partner_check_in_time_menu(update, context)

    elif data.startswith("partner_time_"):
        time_val = data.replace("partner_time_", "")
        chat = update.effective_chat
        user = update.effective_user
        if chat and user:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.check_in_time = time_val
                    await session.commit()
            # Reschedule if enabled
            try:
                async with get_db_session() as session:
                    chat_obj = await get_chat_by_telegram_id(session, chat.id)
                    if chat_obj and chat_obj.accountability_enabled:
                        from ...services.accountability_scheduler import (
                            schedule_user_checkins,
                        )

                        await schedule_user_checkins(
                            context.application, user.id, chat.id
                        )
            except Exception as e:
                logger.error(f"Error rescheduling after time change: {e}")
            await query.answer(f"Check-in time set to {time_val}")
            await partner_settings_command(update, context)

    # Notification settings
    elif data == "partner_notifications":
        await query.answer()
        await partner_notifications_menu(update, context)

    elif data.startswith("partner_celeb_"):
        style = data.replace("partner_celeb_", "")
        chat = update.effective_chat
        if chat:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.celebration_style = style
                    await session.commit()
            style_display = {
                "quiet": "Quiet",
                "moderate": "Moderate",
                "enthusiastic": "Enthusiastic",
            }
            await query.answer(f"Celebration style: {style_display.get(style, style)}")
            await partner_notifications_menu(update, context)

    elif data.startswith("partner_thresh_"):
        threshold = int(data.replace("partner_thresh_", ""))
        chat = update.effective_chat
        if chat:
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat.id)
                if chat_obj:
                    chat_obj.struggle_threshold = threshold
                    await session.commit()
            await query.answer(f"Struggle alert after {threshold} missed days")
            await partner_notifications_menu(update, context)

    # Test partner voice
    elif data == "partner_test_voice":
        await partner_test_voice_handler(update, context)

    # Top-level settings sub-menus (placeholder)
    elif data in ("notifications_menu", "privacy_menu"):
        await query.answer("🚧 Coming soon!", show_alert=True)

    else:
        await query.answer()
        logger.warning(f"Unknown voice settings callback: {data}")
