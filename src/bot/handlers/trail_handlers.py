"""
Trail Review Handlers - Telegram bot handlers for trail review system.

Provides /trail commands and poll handlers for reviewing vault trails.
After completing a poll sequence, the user can reply with text or voice
to add a comment. Claude then updates the trail file with full context.
"""

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, PollAnswerHandler

from ...core.i18n import get_user_locale_from_update, t
from ...services.trail_review_service import get_trail_review_service
from ...utils.error_reporting import handle_errors

logger = logging.getLogger(__name__)

# MessageType for trail review context tracking
TRAIL_REVIEW_TYPE = "trail_review"


@handle_errors("trail_command")
async def trail_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /trail commands.

    Subcommands:
    - /trail or /trail:status - Show next trail for review
    - /trail:list - List all trails due for review
    - /trail:review <name> - Review specific trail
    """
    if not update.message or not update.effective_chat:
        return

    # Parse subcommand
    command_text = update.message.text.split()[0]
    subcommand = None

    if ":" in command_text:
        subcommand = command_text.split(":", 1)[1]

    trail_service = get_trail_review_service()

    # /trail:list - show all trails due
    if subcommand == "list":
        await _trail_list(update, context, trail_service)
        return

    # /trail:review <name> - review specific trail
    if subcommand == "review":
        await _trail_review_specific(update, context, trail_service)
        return

    # /trail or /trail:status - start review for next due trail
    await _trail_status(update, context, trail_service)


async def _trail_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE, trail_service
) -> None:
    """List all trails due for review."""
    locale = get_user_locale_from_update(update)
    trails = trail_service.get_trails_for_review()

    if not trails:
        await update.message.reply_text(
            "✅ " + t("trails.no_trails_due", locale), parse_mode="HTML"
        )
        return

    # Format list
    message = "📋 " + t("trails.list_title", locale) + "\n\n"

    for trail in trails[:10]:  # Limit to 10
        urgency_emoji = (
            "🔴" if trail["urgency"] > 7 else "🟡" if trail["urgency"] > 0 else "🟢"
        )
        velocity_emoji = {"high": "🔥", "medium": "⚡", "low": "🐢"}.get(
            trail["velocity"], "❓"
        )

        if trail["next_review"]:
            message += f"{urgency_emoji} <b>{trail['name']}</b>\n"
            message += f"   {velocity_emoji} {trail['velocity']} · {trail['status']}\n"
            message += f"   Due: {trail['next_review']}"
            if trail["urgency"] > 0:
                message += (
                    " (" + t("trails.days_overdue", locale, days=trail["urgency"]) + ")"
                )
            message += "\n\n"
        else:
            message += f"{urgency_emoji} <b>{trail['name']}</b>\n"
            message += f"   {velocity_emoji} {trail['velocity']} · {trail['status']}\n"
            message += "   " + t("trails.no_review_scheduled", locale) + "\n\n"

    message += "\n" + t("trails.use_trail_hint", locale)

    await update.message.reply_text(message, parse_mode="HTML")


async def _trail_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE, trail_service
) -> None:
    """Start review for most urgent trail."""
    locale = get_user_locale_from_update(update)
    trails = trail_service.get_trails_for_review()

    if not trails:
        await update.message.reply_text(
            "✅ " + t("trails.no_trails_due", locale), parse_mode="HTML"
        )
        return

    # Get most urgent trail
    trail = trails[0]

    # Start poll sequence
    await _start_trail_review(update, context, trail_service, trail)


async def _trail_review_specific(
    update: Update, context: ContextTypes.DEFAULT_TYPE, trail_service
) -> None:
    """Review a specific trail by name."""
    if not update.message:
        return

    locale = get_user_locale_from_update(update)

    # Parse trail name from command arguments
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.message.reply_text(
            "❌ " + t("trails.specify_name", locale), parse_mode="HTML"
        )
        return

    trail_name = args[1].strip()

    # Find trail
    trails = trail_service.get_trails_for_review()
    matching = [tr for tr in trails if trail_name.lower() in tr["name"].lower()]

    if not matching:
        await update.message.reply_text(
            "❌ " + t("trails.not_found", locale, name=trail_name), parse_mode="HTML"
        )
        return

    if len(matching) > 1:
        # Multiple matches, show options
        message = t("trails.multiple_matches_title", locale, name=trail_name) + "\n\n"
        for tr in matching:
            message += f"• {tr['name']}\n"
        message += "\n" + t("trails.multiple_matches_hint", locale)

        await update.message.reply_text(message, parse_mode="HTML")
        return

    # Start review
    await _start_trail_review(update, context, trail_service, matching[0])


async def _start_trail_review(
    update: Update, context: ContextTypes.DEFAULT_TYPE, trail_service, trail: dict
) -> None:
    """Start poll sequence for trail review."""
    if not update.effective_chat:
        return

    locale = get_user_locale_from_update(update)
    chat_id = update.effective_chat.id

    # Get first poll
    first_poll = trail_service.start_poll_sequence(chat_id, trail)

    if not first_poll:
        await update.message.reply_text(
            "❌ " + t("trails.review_error", locale, name=trail["name"]),
            parse_mode="HTML",
        )
        return

    # Send intro message
    intro = "🔍 <b>" + t("trails.review_title", locale, name=trail["name"]) + "</b>\n\n"
    intro += t("trails.review_intro_status", locale, status=trail["status"]) + "\n"
    intro += (
        t("trails.review_intro_velocity", locale, velocity=trail["velocity"]) + "\n"
    )
    if trail.get("next_review"):
        intro += t("trails.review_intro_due", locale, date=trail["next_review"]) + "\n"
    intro += "\n<i>" + t("trails.review_intro_hint", locale) + "</i>"

    await update.message.reply_text(intro, parse_mode="HTML")

    # Send first poll
    await _send_trail_poll(context, chat_id, trail, first_poll)


async def _send_trail_poll(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    trail: dict,
    poll_data: dict,
) -> None:
    """Send a trail review poll and register it in the service."""
    trail_service = get_trail_review_service()

    poll_message = await context.bot.send_poll(
        chat_id=chat_id,
        question=poll_data["question"],
        options=poll_data["options"],
        is_anonymous=False,
        allows_multiple_answers=False,
    )

    # Register in persistent service (NOT in bot_data which is lost on restart)
    trail_service.register_poll(
        poll_id=poll_message.poll.id,
        trail_path=trail["path"],
        field=poll_data["field"],
        chat_id=chat_id,
        options=poll_data["options"],
    )

    # Also keep in bot_data for backward compatibility
    if "trail_polls" not in context.bot_data:
        context.bot_data["trail_polls"] = {}
    context.bot_data["trail_polls"][poll_message.poll.id] = {
        "trail_path": trail["path"],
        "field": poll_data["field"],
        "chat_id": chat_id,
    }

    logger.info(
        f"Sent trail poll: field={poll_data['field']}, "
        f"poll_id={poll_message.poll.id}, trail={trail['name']}"
    )


@handle_errors("handle_trail_poll_answer")
async def handle_trail_poll_answer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle poll answer from user - supports both trail and general polls."""
    if not update.poll_answer:
        return

    poll_id = update.poll_answer.poll_id
    option_ids = update.poll_answer.option_ids

    if not option_ids:
        return

    trail_service = get_trail_review_service()

    # Check persistent trail poll registry first
    poll_info = trail_service.get_poll_info(poll_id)

    # Fall back to bot_data for backward compatibility
    if not poll_info:
        bot_trail_polls = context.bot_data.get("trail_polls", {})
        if poll_id in bot_trail_polls:
            poll_info = bot_trail_polls[poll_id]

    if not poll_info:
        # Not a trail poll - delegate to general poll handler
        if (
            "poll_context" in context.bot_data
            and poll_id in context.bot_data["poll_context"]
        ):
            from ...services.polling_service import get_polling_service

            poll_ctx = context.bot_data["poll_context"][poll_id]
            user = update.poll_answer.user
            selected_option_id = option_ids[0]
            poll_options = poll_ctx.get("options", [])
            selected_option_text = (
                poll_options[selected_option_id]
                if selected_option_id < len(poll_options)
                else "Unknown"
            )

            try:
                polling_service = get_polling_service()
                response = await polling_service.save_response(
                    chat_id=poll_ctx.get("chat_id"),
                    poll_id=poll_id,
                    message_id=poll_ctx.get("message_id"),
                    question=poll_ctx.get("question"),
                    options=poll_options,
                    selected_option_id=selected_option_id,
                    selected_option_text=selected_option_text,
                    poll_type=poll_ctx.get("poll_type"),
                    poll_category=poll_ctx.get("poll_category"),
                    context_metadata={
                        "template_id": poll_ctx.get("template_id"),
                        "user_first_name": user.first_name,
                        "user_id": user.id,
                    },
                )
                logger.info(
                    f"Saved general poll response via trail handler: {response.id}"
                )
                del context.bot_data["poll_context"][poll_id]
            except Exception as e:
                logger.error(f"Error saving general poll response: {e}", exc_info=True)
        else:
            logger.warning(f"Poll {poll_id} not found in trail service or poll_context")
        return

    # This IS a trail poll
    trail_path = poll_info["trail_path"]
    chat_id = poll_info["chat_id"]

    # Get selected answer text
    if chat_id not in trail_service._poll_states:
        logger.warning(f"No poll state for chat {chat_id} (may have expired)")
        trail_service.unregister_poll(poll_id)
        return

    if trail_path not in trail_service._poll_states[chat_id]:
        logger.warning(f"No poll state for trail {trail_path}")
        trail_service.unregister_poll(poll_id)
        return

    state = trail_service._poll_states[chat_id][trail_path]
    current_poll = state["sequence"][state["current_index"]]

    # Map option_id to text using stored options
    stored_options = poll_info.get("options", current_poll.get("options", []))
    if option_ids[0] < len(stored_options):
        selected_option = stored_options[option_ids[0]]
    else:
        selected_option = current_poll["options"][option_ids[0]]

    logger.info(
        f"Trail poll answer: field={current_poll['field']}, "
        f"answer='{selected_option}', trail={state['trail']['name']}"
    )

    # Record answer and get next poll
    next_poll, is_complete = trail_service.get_next_poll(
        chat_id, trail_path, selected_option
    )

    # Clean up this poll from registry
    trail_service.unregister_poll(poll_id)
    context.bot_data.get("trail_polls", {}).pop(poll_id, None)

    if is_complete:
        # Finalize review - update frontmatter
        result = trail_service.finalize_review(chat_id, trail_path)

        locale = "en"  # Poll answers don't carry user locale

        if result["success"]:
            # Build rich summary with next review date
            title = t("trails.complete_title", locale, name=result["trail_name"])
            summary = "✅ <b>" + title + "</b>\n\n"

            summary += t("trails.complete_updates", locale) + "\n"
            for change in result["changes"]:
                summary += f"• {change}\n"

            if result.get("next_review"):
                next_rev = t(
                    "trails.complete_next_review",
                    locale,
                    date=result["next_review"],
                )
                summary += "\n📅 <b>" + next_rev + "</b>\n"

            summary += "\n💬 <i>" + t("trails.complete_comment_hint", locale) + "</i>"

            sent_msg = await context.bot.send_message(
                chat_id=chat_id, text=summary, parse_mode="HTML"
            )

            # Track this message in reply context so replies go to Claude
            _track_trail_review_completion(
                message_id=sent_msg.message_id,
                chat_id=chat_id,
                user_id=update.poll_answer.user.id if update.poll_answer.user else 0,
                trail_name=result["trail_name"],
                trail_path=result.get("trail_path", trail_path),
                answers=result.get("answers", {}),
            )

        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ "
                + t("trails.complete_error", locale, error=result.get("error")),
                parse_mode="HTML",
            )

    else:
        # Send next poll
        trail = state["trail"]
        await _send_trail_poll(context, chat_id, trail, next_poll)


def _track_trail_review_completion(
    message_id: int,
    chat_id: int,
    user_id: int,
    trail_name: str,
    trail_path: str,
    answers: dict,
) -> None:
    """Track trail review completion message in reply context for follow-up."""
    try:
        from ...services.reply_context import MessageType, get_reply_context_service

        reply_service = get_reply_context_service()
        reply_service.track_message(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_type=MessageType.POLL_RESPONSE,
            poll_question=f"Trail review: {trail_name}",
            poll_selected_answer=str(answers),
            original_text=f"Trail review completed for {trail_name}",
            trail_path=trail_path,
            trail_name=trail_name,
            trail_answers=answers,
        )

        logger.info(
            f"Tracked trail review completion: msg={message_id}, "
            f"trail={trail_name}, path={trail_path}"
        )
    except Exception as e:
        logger.error(f"Error tracking trail review completion: {e}", exc_info=True)


# send_scheduled_trail_review moved to services/trail_scheduler.py
# Re-export for backward compatibility
from ...services.trail_scheduler import send_scheduled_trail_review  # noqa: F401, E402


def register_trail_handlers(application) -> None:
    """Register trail review handlers with the application."""
    application.add_handler(CommandHandler("trail", trail_command))
    application.add_handler(PollAnswerHandler(handle_trail_poll_answer))
    logger.info("Trail review handlers registered")
