"""
Poll Handlers - Handle poll responses and commands.

Manages:
- Poll answer callbacks
- /polls commands for manual control
- Poll statistics and insights
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, PollAnswerHandler, CommandHandler
from typing import Optional

from ...services.polling_service import get_polling_service

logger = logging.getLogger(__name__)


async def handle_poll_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
    if 'poll_context' not in context.bot_data:
        logger.warning(f"No poll_context in bot_data for poll {poll_id}")
        return

    if poll_id not in context.bot_data['poll_context']:
        logger.warning(f"Poll {poll_id} not found in poll_context")
        return

    poll_ctx = context.bot_data['poll_context'][poll_id]

    # Extract poll details
    question = poll_ctx.get('question')
    options = poll_ctx.get('options', [])
    poll_type = poll_ctx.get('poll_type')
    poll_category = poll_ctx.get('poll_category')
    template_id = poll_ctx.get('template_id')
    chat_id = poll_ctx.get('chat_id')
    message_id = poll_ctx.get('message_id')

    # Get selected option
    selected_option_id = option_ids[0]
    selected_option_text = options[selected_option_id] if selected_option_id < len(options) else "Unknown"

    logger.info(
        f"Poll answer received: poll_id={poll_id}, user={user.first_name}, "
        f"type={poll_type}, answer='{selected_option_text}'"
    )

    # Save response
    polling_service = get_polling_service()

    try:
        context_metadata = {
            'template_id': template_id,
            'user_first_name': user.first_name,
            'user_id': user.id,
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

        # Clean up context
        del context.bot_data['poll_context'][poll_id]

        # Send acknowledgment (optional)
        # await context.bot.send_message(
        #     chat_id=chat_id,
        #     text=f"✅ Recorded: {selected_option_text}",
        # )

    except Exception as e:
        logger.error(f"Error saving poll response: {e}", exc_info=True)


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

    # Parse subcommand
    command_text = update.message.text.split()[0]
    subcommand = None

    if ':' in command_text:
        subcommand = command_text.split(':', 1)[1]

    polling_service = get_polling_service()

    # /polls:send - manually trigger next poll
    if subcommand == 'send':
        await _send_poll_now(update, context, polling_service, chat_id)
        return

    # /polls:stats - detailed statistics
    if subcommand == 'stats':
        await _show_statistics(update, context, polling_service, chat_id)
        return

    # /polls:pause - pause automatic polls
    if subcommand == 'pause':
        # Set flag in chat settings
        if 'poll_settings' not in context.chat_data:
            context.chat_data['poll_settings'] = {}
        context.chat_data['poll_settings']['paused'] = True

        await update.message.reply_text(
            "⏸️ <b>Automatic polls paused</b>\n\n"
            "Use /polls:resume to restart.",
            parse_mode='HTML'
        )
        return

    # /polls:resume - resume automatic polls
    if subcommand == 'resume':
        if 'poll_settings' in context.chat_data:
            context.chat_data['poll_settings']['paused'] = False

        await update.message.reply_text(
            "▶️ <b>Automatic polls resumed</b>\n\n"
            "Polls will be sent according to schedule.",
            parse_mode='HTML'
        )
        return

    # /polls or /polls:status - show status
    await _show_status(update, context, polling_service, chat_id)


async def _send_poll_now(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    polling_service,
    chat_id: int
) -> None:
    """Send next poll immediately."""
    try:
        poll_template = await polling_service.get_next_poll(chat_id)

        if not poll_template:
            await update.message.reply_text(
                "⏰ No poll available right now.\n\n"
                "Try again later (respecting quiet hours and frequency limits).",
                parse_mode='HTML'
            )
            return

        # Send poll
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=poll_template['question'],
            options=poll_template['options'],
            is_anonymous=False,
            allows_multiple_answers=False
        )

        # Store poll context
        if 'poll_context' not in context.bot_data:
            context.bot_data['poll_context'] = {}

        context.bot_data['poll_context'][poll_message.poll.id] = {
            'question': poll_template['question'],
            'options': poll_template['options'],
            'poll_type': poll_template['type'],
            'poll_category': poll_template.get('category'),
            'template_id': poll_template['id'],
            'chat_id': chat_id,
            'message_id': poll_message.message_id,
        }

        logger.info(f"Sent poll {poll_template['id']} to chat {chat_id}")

    except Exception as e:
        logger.error(f"Error sending poll: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error sending poll: {str(e)}",
            parse_mode='HTML'
        )


async def _show_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    polling_service,
    chat_id: int
) -> None:
    """Show poll status and basic stats."""
    try:
        # Check if paused
        paused = context.chat_data.get('poll_settings', {}).get('paused', False)

        # Get recent stats
        stats = await polling_service.get_statistics(chat_id, days=7)

        message = "📊 <b>Poll Status</b>\n\n"

        if paused:
            message += "⏸️ <b>Status:</b> Paused\n\n"
        else:
            message += "▶️ <b>Status:</b> Active\n\n"

        message += f"<b>Last 7 days:</b>\n"
        message += f"• Total responses: {stats.get('total_responses', 0)}\n"
        message += f"• Avg per day: {stats.get('avg_per_day', 0):.1f}\n\n"

        if stats.get('by_type'):
            message += "<b>By type:</b>\n"
            for poll_type, count in stats['by_type'].items():
                message += f"  {poll_type}: {count}\n"
            message += "\n"

        message += "<b>Commands:</b>\n"
        message += "/polls:send - Send poll now\n"
        message += "/polls:stats - Detailed statistics\n"
        message += "/polls:pause - Pause polls\n"
        message += "/polls:resume - Resume polls\n"

        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Error showing poll status: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {str(e)}",
            parse_mode='HTML'
        )


async def _show_statistics(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    polling_service,
    chat_id: int
) -> None:
    """Show detailed poll statistics."""
    try:
        # Parse days argument
        args = update.message.text.split()
        days = int(args[1]) if len(args) > 1 else 7

        stats = await polling_service.get_statistics(chat_id, days=days)

        message = f"📊 <b>Poll Statistics ({days} days)</b>\n\n"

        message += f"<b>Total responses:</b> {stats.get('total_responses', 0)}\n"
        message += f"<b>Avg per day:</b> {stats.get('avg_per_day', 0):.1f}\n\n"

        if stats.get('by_type'):
            message += "<b>By type:</b>\n"
            for poll_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
                message += f"  • {poll_type}: {count}\n"
            message += "\n"

        if stats.get('by_category'):
            message += "<b>By category:</b>\n"
            for category, count in sorted(stats['by_category'].items(), key=lambda x: x[1], reverse=True):
                message += f"  • {category}: {count}\n"
            message += "\n"

        if stats.get('by_day'):
            message += "<b>By day of week:</b>\n"
            for day, count in stats['by_day'].items():
                message += f"  • {day}: {count}\n"
            message += "\n"

        if stats.get('by_hour'):
            message += "<b>Peak hours:</b>\n"
            # Show top 5 hours
            top_hours = sorted(stats['by_hour'], key=lambda x: x[1], reverse=True)[:5]
            for hour, count in top_hours:
                message += f"  • {hour:02d}:00 - {count} responses\n"

        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Error showing statistics: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {str(e)}",
            parse_mode='HTML'
        )


async def send_scheduled_poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to send polls automatically.

    This should be called periodically (e.g., every 30 minutes) via job queue.
    """
    polling_service = get_polling_service()

    # Get all active chats (for now, use configured chat IDs)
    # TODO: Store per-user poll preferences in database
    import os
    chat_ids_str = os.getenv('POLLING_CHAT_IDS', '')

    if not chat_ids_str:
        logger.debug("No polling chat IDs configured")
        return

    chat_ids = [int(cid.strip()) for cid in chat_ids_str.split(',') if cid.strip()]

    for chat_id in chat_ids:
        try:
            # Check if paused for this chat
            if context.application.chat_data.get(chat_id, {}).get('poll_settings', {}).get('paused', False):
                logger.info(f"Polls paused for chat {chat_id}, skipping")
                continue

            # Get next poll
            poll_template = await polling_service.get_next_poll(chat_id)

            if not poll_template:
                logger.debug(f"No poll available for chat {chat_id}")
                continue

            # Send poll
            poll_message = await context.bot.send_poll(
                chat_id=chat_id,
                question=poll_template['question'],
                options=poll_template['options'],
                is_anonymous=False,
                allows_multiple_answers=False
            )

            # Store poll context
            if 'poll_context' not in context.bot_data:
                context.bot_data['poll_context'] = {}

            context.bot_data['poll_context'][poll_message.poll.id] = {
                'question': poll_template['question'],
                'options': poll_template['options'],
                'poll_type': poll_template['type'],
                'poll_category': poll_template.get('category'),
                'template_id': poll_template['id'],
                'chat_id': chat_id,
                'message_id': poll_message.message_id,
            }

            logger.info(
                f"Sent scheduled poll {poll_template['id']} to chat {chat_id}: "
                f"'{poll_template['question'][:50]}...'"
            )

        except Exception as e:
            logger.error(f"Error sending scheduled poll to chat {chat_id}: {e}", exc_info=True)


def register_poll_handlers(application) -> None:
    """Register poll handlers with the application."""
    application.add_handler(CommandHandler("polls", polls_command))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    logger.info("Poll handlers registered")
