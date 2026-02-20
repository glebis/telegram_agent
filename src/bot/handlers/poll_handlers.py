"""
Poll Handlers - Handle poll responses and commands.

Manages:
- Poll answer callbacks
- /polls commands for manual control
- Poll statistics and insights
"""

import logging
from typing import Any, Dict, Optional

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, PollAnswerHandler

from ...core.error_messages import sanitize_error
from ...core.i18n import get_user_locale_from_update, t
from ...services.polling_service import get_polling_service
from ...utils.error_reporting import handle_errors

logger = logging.getLogger(__name__)


async def forward_poll_to_claude(
    chat_id: int,
    user_id: int,
    question: str,
    selected_answer: str,
    options: list,
    poll_type: Optional[str] = None,
    poll_category: Optional[str] = None,
    voice_origin: Optional[Dict[str, Any]] = None,
    poll_message_id: Optional[int] = None,
) -> None:
    """
    Forward poll response to Claude Code session.

    Sends poll Q+A with voice origin context to active Claude session.
    If no active session, creates a new one (when Claude mode is active).

    Args:
        chat_id: Telegram chat ID
        user_id: Telegram user ID
        question: Poll question text
        selected_answer: User's selected answer
        options: List of all poll options
        poll_type: Type of poll (emotion, decision, etc)
        poll_category: Category (work, personal, health, etc)
        voice_origin: Voice transcription metadata if poll came from voice
        poll_message_id: Message ID of the poll (for threading)
    """
    from ...services.claude_code_service import get_claude_code_service
    from ..handlers.base import send_message_sync
    from ..handlers.formatting import markdown_to_telegram_html, split_message

    service = get_claude_code_service()

    # Build poll context prompt for Claude
    prompt_parts = [
        "[Poll Response Received]",
        f"Question: {question}",
        f"Options: {', '.join(options)}",
        f"User answered: {selected_answer}",
    ]

    if poll_type:
        prompt_parts.append(f"Poll type: {poll_type}")
    if poll_category:
        prompt_parts.append(f"Category: {poll_category}")

    # Add voice origin context
    if voice_origin:
        prompt_parts.append("")
        prompt_parts.append("[This poll was sent during a voice message interaction]")
        if voice_origin.get("transcription"):
            prompt_parts.append(
                f"Voice transcription that preceded this poll: {voice_origin['transcription']}"
            )

    prompt_parts.append("")
    prompt_parts.append(
        "The user just answered this poll. Please acknowledge their response and "
        "integrate this information into our conversation context."
    )

    poll_prompt = "\n".join(prompt_parts)

    logger.info(
        f"Forwarding poll to Claude: chat={chat_id}, "
        f"Q='{question[:50]}...', A='{selected_answer}', "
        f"voice_origin={bool(voice_origin)}"
    )

    # Send brief status message
    locale = "en"
    status_text = "🤖 " + t("polls.sending_to_claude", locale)
    status_result = send_message_sync(
        chat_id=chat_id,
        text=status_text,
        parse_mode="HTML",
        reply_to=poll_message_id,
    )

    if not status_result:
        logger.error("Failed to send Claude status message for poll forward")
        return

    status_msg_id = status_result.get("message_id")

    try:
        # Get active session
        session_id = service.active_sessions.get(chat_id)

        # Get thinking effort from chat settings
        from sqlalchemy import select

        from ...core.database import get_db_session
        from ...models.chat import Chat as ChatModel

        thinking_effort = "medium"  # Default
        async with get_db_session() as session:
            result = await session.execute(
                select(ChatModel).where(ChatModel.chat_id == chat_id)
            )
            chat_obj = result.scalar_one_or_none()
            if chat_obj and chat_obj.thinking_effort:
                thinking_effort = chat_obj.thinking_effort

        # Execute Claude with the poll context
        result_text = ""
        async for msg_type, content, sid in service.execute_prompt(
            prompt=poll_prompt,
            chat_id=chat_id,
            user_id=user_id,
            session_id=session_id,
            thinking_effort=thinking_effort,
        ):
            if msg_type == "text":
                result_text += content
            elif msg_type == "done":
                break

        # Send Claude's response to the chat
        if result_text.strip():
            formatted = markdown_to_telegram_html(result_text)
            for chunk in split_message(formatted):
                send_message_sync(chat_id, chunk, parse_mode="HTML")

            # Delete status message
            from ..handlers.base import _run_telegram_api_sync

            _run_telegram_api_sync(
                "deleteMessage",
                {
                    "chat_id": chat_id,
                    "message_id": status_msg_id,
                },
            )

            logger.info("Poll forwarded to Claude successfully, response sent")
        else:
            logger.warning("Claude returned empty response for poll")

    except Exception as e:
        logger.error(f"Error forwarding poll to Claude: {e}", exc_info=True)
        # Update status message with error
        from ..handlers.base import edit_message_sync

        edit_message_sync(
            chat_id=chat_id,
            message_id=status_msg_id,
            text="❌ " + t("polls.forward_error", locale, error=sanitize_error(e)),
            parse_mode="HTML",
        )


@handle_errors("handle_poll_answer")
async def handle_poll_answer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle poll answer from user.

    Stores response in database with embeddings and context.
    """
    if not update.poll_answer:
        return

    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    option_ids = poll_answer.option_ids
    user = poll_answer.user

    if not option_ids:
        logger.warning(f"Poll answer {poll_id} has no option_ids")
        return

    # Get poll context from bot_data
    if "poll_context" not in context.bot_data:
        logger.warning(f"No poll_context in bot_data for poll {poll_id}")
        return

    if poll_id not in context.bot_data["poll_context"]:
        logger.warning(f"Poll {poll_id} not found in poll_context")
        return

    poll_ctx = context.bot_data["poll_context"][poll_id]

    # Extract poll details
    question = poll_ctx.get("question")
    options = poll_ctx.get("options", [])
    poll_type = poll_ctx.get("poll_type")
    poll_category = poll_ctx.get("poll_category")
    template_id = poll_ctx.get("template_id")
    chat_id = poll_ctx.get("chat_id")
    message_id = poll_ctx.get("message_id")

    # Get selected option
    selected_option_id = option_ids[0]
    selected_option_text = (
        options[selected_option_id] if selected_option_id < len(options) else "Unknown"
    )

    logger.info(
        f"Poll answer received: poll_id={poll_id}, user={user.first_name}, "
        f"type={poll_type}, answer='{selected_option_text}'"
    )

    # Get origin info for enriched metadata
    origin = poll_ctx.get("origin", {})
    voice_origin = origin.get("voice_origin")
    source_type = origin.get("source_type", "unknown")

    # Save response
    polling_service = get_polling_service()

    try:
        # Enrich context_metadata with origin info
        context_metadata = {
            "template_id": template_id,
            "user_first_name": user.first_name,
            "user_id": user.id,
            "source_type": source_type,
            "voice_origin": voice_origin,
        }

        response = await polling_service.save_response(
            chat_id=chat_id,
            poll_id=poll_id,
            message_id=message_id,
            question=question,
            options=options,
            selected_option_id=selected_option_id,
            selected_option_text=selected_option_text,
            poll_type=poll_type,
            poll_category=poll_category,
            context_metadata=context_metadata,
        )

        logger.info(f"Saved poll response: {response.id}")

        # Notify lifecycle tracker: resets backpressure counter
        from ...services.poll_lifecycle import get_poll_lifecycle_tracker

        lifecycle_tracker = get_poll_lifecycle_tracker()
        lifecycle_tracker.record_answered(poll_id)

        # Track poll response in reply context
        from ...services.reply_context import get_reply_context_service

        reply_service = get_reply_context_service()
        reply_service.track_poll_response(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user.id,
            question=question,
            selected_answer=selected_option_text,
            options=options,
            source_type=source_type,
        )

        # Forward to Claude if Claude mode is active
        from ..handlers.base import get_claude_mode

        claude_mode_active = await get_claude_mode(chat_id)

        if claude_mode_active:
            logger.info("Claude mode active, forwarding poll to Claude")
            from ...utils.task_tracker import create_tracked_task

            create_tracked_task(
                forward_poll_to_claude(
                    chat_id=chat_id,
                    user_id=user.id,
                    question=question,
                    selected_answer=selected_option_text,
                    options=options,
                    poll_type=poll_type,
                    poll_category=poll_category,
                    voice_origin=voice_origin,
                    poll_message_id=message_id,
                ),
                name="claude_poll_forward",
            )

        # Clean up context
        del context.bot_data["poll_context"][poll_id]

    except Exception as e:
        logger.error(f"Error saving poll response: {e}", exc_info=True)


@handle_errors("polls_command")
async def polls_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /polls commands.

    Subcommands:
    - /polls or /polls:status - Show poll statistics
    - /polls:send - Manually trigger next poll
    - /polls:stats [days] - Show detailed statistics
    - /polls:pause - Pause automatic polls
    - /polls:resume - Resume automatic polls
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    locale = get_user_locale_from_update(update)

    # Parse subcommand
    command_text = update.message.text.split()[0]
    subcommand = None

    if ":" in command_text:
        subcommand = command_text.split(":", 1)[1]

    polling_service = get_polling_service()

    # /polls:send - manually trigger next poll
    if subcommand == "send":
        await _send_poll_now(update, context, polling_service, chat_id)
        return

    # /polls:stats - detailed statistics
    if subcommand == "stats":
        await _show_statistics(update, context, polling_service, chat_id)
        return

    # /polls:pause - pause automatic polls
    if subcommand == "pause":
        # Set flag in chat settings
        if "poll_settings" not in context.chat_data:
            context.chat_data["poll_settings"] = {}
        context.chat_data["poll_settings"]["paused"] = True

        await update.message.reply_text(
            "⏸️ " + t("polls.paused", locale),
            parse_mode="HTML",
        )
        return

    # /polls:resume - resume automatic polls
    if subcommand == "resume":
        if "poll_settings" in context.chat_data:
            context.chat_data["poll_settings"]["paused"] = False

        await update.message.reply_text(
            "▶️ " + t("polls.resumed", locale),
            parse_mode="HTML",
        )
        return

    # /polls or /polls:status - show status
    await _show_status(update, context, polling_service, chat_id)


async def _send_poll_now(
    update: Update, context: ContextTypes.DEFAULT_TYPE, polling_service, chat_id: int
) -> None:
    """Send next poll immediately."""
    locale = get_user_locale_from_update(update)
    try:
        poll_template = await polling_service.get_next_poll(chat_id)

        if not poll_template:
            await update.message.reply_text(
                "⏰ " + t("polls.no_poll_available", locale),
                parse_mode="HTML",
            )
            return

        # Send poll
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=poll_template["question"],
            options=poll_template["options"],
            is_anonymous=False,
            allows_multiple_answers=False,
        )

        # Check for recent voice context to track poll origin
        from ...services.reply_context import MessageType, get_reply_context_service

        reply_service = get_reply_context_service()
        recent_voice = reply_service.get_recent_context_by_type(
            chat_id, MessageType.VOICE_TRANSCRIPTION, max_age_minutes=10
        )

        origin_info = {
            "source_type": "manual",
            "voice_origin": None,
        }

        if recent_voice:
            origin_info["source_type"] = "voice"
            origin_info["voice_origin"] = {
                "transcription": recent_voice.transcription,
                "voice_file_id": recent_voice.voice_file_id,
                "message_id": recent_voice.message_id,
                "created_at": recent_voice.created_at.isoformat(),
            }
            logger.info(
                f"Poll sent in voice context: transcript='{recent_voice.transcription[:60]}...'"
            )

        # Store poll context
        if "poll_context" not in context.bot_data:
            context.bot_data["poll_context"] = {}

        context.bot_data["poll_context"][poll_message.poll.id] = {
            "question": poll_template["question"],
            "options": poll_template["options"],
            "poll_type": poll_template["type"],
            "poll_category": poll_template.get("category"),
            "template_id": poll_template["id"],
            "chat_id": chat_id,
            "message_id": poll_message.message_id,
            "origin": origin_info,
        }

        # Register in lifecycle tracker for TTL and backpressure tracking
        from ...services.poll_lifecycle import get_poll_lifecycle_tracker

        tracker = get_poll_lifecycle_tracker()
        tracker.record_sent(
            poll_id=poll_message.poll.id,
            chat_id=chat_id,
            message_id=poll_message.message_id,
            template_id=poll_template["id"],
            question=poll_template["question"],
        )

        # Schedule expiration job
        from ...services.poll_scheduler import _schedule_poll_expiration

        _schedule_poll_expiration(context, poll_message.poll.id, tracker.ttl_minutes)

        # Update send counter in database
        await polling_service.increment_send_count(poll_template["question"])

        logger.info(f"Sent poll {poll_template['id']} to chat {chat_id}")

    except Exception as e:
        logger.error(f"Error sending poll: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ " + t("polls.send_error", locale, error=sanitize_error(e)),
            parse_mode="HTML",
        )


async def _show_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE, polling_service, chat_id: int
) -> None:
    """Show poll status and basic stats."""
    locale = get_user_locale_from_update(update)
    try:
        # Check if paused
        paused = context.chat_data.get("poll_settings", {}).get("paused", False)

        # Get recent stats
        stats = await polling_service.get_statistics(chat_id, days=7)

        message = "📊 " + t("polls.status_title", locale) + "\n\n"

        if paused:
            message += "⏸️ " + t("polls.status_paused", locale) + "\n\n"
        else:
            message += "▶️ " + t("polls.status_active", locale) + "\n\n"

        # Show lifecycle state
        from ...services.poll_lifecycle import get_poll_lifecycle_tracker

        tracker = get_poll_lifecycle_tracker()
        lifecycle = tracker.get_chat_state(chat_id)
        unanswered = tracker.get_unanswered_count(chat_id)

        if lifecycle.get("backpressure_active"):
            message += (
                t(
                    "polls.backpressure_active",
                    locale,
                    count=lifecycle.get("consecutive_misses", 0),
                )
                + "\n\n"
            )
        else:
            message += t("polls.unanswered_polls", locale, count=unanswered) + "\n"
            message += (
                t(
                    "polls.consecutive_misses",
                    locale,
                    count=lifecycle.get("consecutive_misses", 0),
                )
                + "\n\n"
            )

        message += t("polls.last_7_days", locale) + "\n"
        message += (
            "• "
            + t("polls.total_responses", locale, count=stats.get("total_responses", 0))
            + "\n"
        )
        message += (
            "• "
            + t("polls.avg_per_day", locale, value=f"{stats.get('avg_per_day', 0):.1f}")
            + "\n\n"
        )

        if stats.get("by_type"):
            message += t("polls.by_type", locale) + "\n"
            for poll_type, count in stats["by_type"].items():
                message += f"  {poll_type}: {count}\n"
            message += "\n"

        message += t("polls.commands_title", locale) + "\n"
        message += "/polls:send - Send poll now\n"
        message += "/polls:stats - Detailed statistics\n"
        message += "/polls:pause - Pause polls\n"
        message += "/polls:resume - Resume polls\n"

        await update.message.reply_text(message, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error showing poll status: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ " + t("polls.error", locale, error=sanitize_error(e)),
            parse_mode="HTML",
        )


async def _show_statistics(
    update: Update, context: ContextTypes.DEFAULT_TYPE, polling_service, chat_id: int
) -> None:
    """Show detailed poll statistics."""
    locale = get_user_locale_from_update(update)
    try:
        # Parse days argument
        args = update.message.text.split()
        days = int(args[1]) if len(args) > 1 else 7

        stats = await polling_service.get_statistics(chat_id, days=days)

        message = "📊 " + t("polls.stats_title", locale, days=days) + "\n\n"

        message += (
            t(
                "polls.total_responses_label",
                locale,
                count=stats.get("total_responses", 0),
            )
            + "\n"
        )
        message += (
            t(
                "polls.avg_per_day_label",
                locale,
                value=f"{stats.get('avg_per_day', 0):.1f}",
            )
            + "\n\n"
        )

        if stats.get("by_type"):
            message += t("polls.by_type", locale) + "\n"
            for poll_type, count in sorted(
                stats["by_type"].items(), key=lambda x: x[1], reverse=True
            ):
                message += f"  • {poll_type}: {count}\n"
            message += "\n"

        if stats.get("by_category"):
            message += t("polls.by_category", locale) + "\n"
            for category, count in sorted(
                stats["by_category"].items(), key=lambda x: x[1], reverse=True
            ):
                message += f"  • {category}: {count}\n"
            message += "\n"

        if stats.get("by_day"):
            message += t("polls.by_day", locale) + "\n"
            for day, count in stats["by_day"].items():
                message += f"  • {day}: {count}\n"
            message += "\n"

        if stats.get("by_hour"):
            message += t("polls.peak_hours", locale) + "\n"
            # Show top 5 hours
            top_hours = sorted(stats["by_hour"], key=lambda x: x[1], reverse=True)[:5]
            for hour, count in top_hours:
                message += (
                    f"  • {hour:02d}:00 - "
                    + t("polls.responses_label", locale, count=count)
                    + "\n"
                )

        await update.message.reply_text(message, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error showing statistics: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ " + t("polls.error", locale, error=sanitize_error(e)),
            parse_mode="HTML",
        )


# send_scheduled_poll and helpers moved to services/poll_scheduler.py
# Re-export for backward compatibility
from ...services.poll_scheduler import send_scheduled_poll  # noqa: F401, E402


def register_poll_handlers(application) -> None:
    """Register poll handlers with the application."""
    application.add_handler(CommandHandler("polls", polls_command))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    logger.info("Poll handlers registered")
