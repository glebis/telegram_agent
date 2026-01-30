"""
Trail Review Handlers - Telegram bot handlers for trail review system.

Provides /trail commands and poll handlers for reviewing vault trails.
"""

import logging
from telegram import Update, Poll
from telegram.ext import ContextTypes, PollAnswerHandler, CommandHandler
from typing import Optional

from ...services.trail_review_service import get_trail_review_service

logger = logging.getLogger(__name__)


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

    if ':' in command_text:
        subcommand = command_text.split(':', 1)[1]

    trail_service = get_trail_review_service()

    # /trail:list - show all trails due
    if subcommand == 'list':
        await _trail_list(update, context, trail_service)
        return

    # /trail:review <name> - review specific trail
    if subcommand == 'review':
        await _trail_review_specific(update, context, trail_service)
        return

    # /trail or /trail:status - start review for next due trail
    await _trail_status(update, context, trail_service)


async def _trail_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trail_service
) -> None:
    """List all trails due for review."""
    trails = trail_service.get_trails_for_review()

    if not trails:
        await update.message.reply_text(
            "✅ No trails due for review!",
            parse_mode='HTML'
        )
        return

    # Format list
    message = "📋 <b>Trails Due for Review</b>\n\n"

    for trail in trails[:10]:  # Limit to 10
        urgency_emoji = "🔴" if trail['urgency'] > 7 else "🟡" if trail['urgency'] > 0 else "🟢"
        velocity_emoji = {
            'high': '🔥',
            'medium': '⚡',
            'low': '🐢'
        }.get(trail['velocity'], '❓')

        if trail['next_review']:
            message += f"{urgency_emoji} <b>{trail['name']}</b>\n"
            message += f"   {velocity_emoji} {trail['velocity']} · {trail['status']}\n"
            message += f"   Due: {trail['next_review']}"
            if trail['urgency'] > 0:
                message += f" ({trail['urgency']} days overdue)"
            message += "\n\n"
        else:
            message += f"{urgency_emoji} <b>{trail['name']}</b>\n"
            message += f"   {velocity_emoji} {trail['velocity']} · {trail['status']}\n"
            message += f"   No review scheduled\n\n"

    message += f"\nUse /trail to review next trail"

    await update.message.reply_text(message, parse_mode='HTML')


async def _trail_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trail_service
) -> None:
    """Start review for most urgent trail."""
    trails = trail_service.get_trails_for_review()

    if not trails:
        await update.message.reply_text(
            "✅ No trails due for review!",
            parse_mode='HTML'
        )
        return

    # Get most urgent trail
    trail = trails[0]

    # Start poll sequence
    await _start_trail_review(update, context, trail_service, trail)


async def _trail_review_specific(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trail_service
) -> None:
    """Review a specific trail by name."""
    if not update.message:
        return

    # Parse trail name from command arguments
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Please specify trail name: /trail:review <name>",
            parse_mode='HTML'
        )
        return

    trail_name = args[1].strip()

    # Find trail
    trails = trail_service.get_trails_for_review()
    matching = [t for t in trails if trail_name.lower() in t['name'].lower()]

    if not matching:
        await update.message.reply_text(
            f"❌ Trail not found: {trail_name}",
            parse_mode='HTML'
        )
        return

    if len(matching) > 1:
        # Multiple matches, show options
        message = f"Multiple trails match '{trail_name}':\n\n"
        for t in matching:
            message += f"• {t['name']}\n"
        message += "\nPlease be more specific."

        await update.message.reply_text(message, parse_mode='HTML')
        return

    # Start review
    await _start_trail_review(update, context, trail_service, matching[0])


async def _start_trail_review(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trail_service,
    trail: dict
) -> None:
    """Start poll sequence for trail review."""
    if not update.effective_chat:
        return

    chat_id = update.effective_chat.id

    # Get first poll
    first_poll = trail_service.start_poll_sequence(chat_id, trail)

    if not first_poll:
        await update.message.reply_text(
            f"❌ Error starting review for {trail['name']}",
            parse_mode='HTML'
        )
        return

    # Send intro message
    intro = f"🔍 <b>Trail Review: {trail['name']}</b>\n\n"
    intro += f"Status: {trail['status']}\n"
    intro += f"Velocity: {trail['velocity']}\n"
    if trail.get('next_review'):
        intro += f"Last review: {trail['next_review']}\n"
    intro += f"\n<i>Answer the following questions to update this trail:</i>"

    await update.message.reply_text(intro, parse_mode='HTML')

    # Send first poll
    await _send_poll(update, context, trail, first_poll)


async def _send_poll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trail: dict,
    poll_data: dict
) -> None:
    """Send a poll to the user."""
    if not update.effective_chat:
        return

    # Store trail path in poll context for later retrieval
    poll_message = await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=poll_data['question'],
        options=poll_data['options'],
        is_anonymous=False,
        allows_multiple_answers=False
    )

    # Store mapping: poll_id -> trail_path for callback handling
    if 'trail_polls' not in context.bot_data:
        context.bot_data['trail_polls'] = {}

    context.bot_data['trail_polls'][poll_message.poll.id] = {
        'trail_path': trail['path'],
        'field': poll_data['field'],
        'chat_id': update.effective_chat.id
    }


async def handle_trail_poll_answer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle poll answer from user - supports both trail and general polls."""
    if not update.poll_answer:
        return

    poll_id = update.poll_answer.poll_id
    option_ids = update.poll_answer.option_ids

    if not option_ids:
        return

    # Try trail polls first
    if 'trail_polls' not in context.bot_data or poll_id not in context.bot_data['trail_polls']:
        # Not a trail poll - delegate to general poll handler
        # Must use poll_context from bot_data + PollingService (database-backed)
        if 'poll_context' in context.bot_data and poll_id in context.bot_data['poll_context']:
            from ...services.polling_service import get_polling_service
            poll_ctx = context.bot_data['poll_context'][poll_id]
            user = update.poll_answer.user
            selected_option_id = option_ids[0]
            poll_options = poll_ctx.get('options', [])
            selected_option_text = poll_options[selected_option_id] if selected_option_id < len(poll_options) else "Unknown"

            try:
                polling_service = get_polling_service()
                response = await polling_service.save_response(
                    chat_id=poll_ctx.get('chat_id'),
                    poll_id=poll_id,
                    message_id=poll_ctx.get('message_id'),
                    question=poll_ctx.get('question'),
                    options=poll_options,
                    selected_option_id=selected_option_id,
                    selected_option_text=selected_option_text,
                    poll_type=poll_ctx.get('poll_type'),
                    poll_category=poll_ctx.get('poll_category'),
                    context_metadata={
                        'template_id': poll_ctx.get('template_id'),
                        'user_first_name': user.first_name,
                        'user_id': user.id,
                    },
                )
                logger.info(f"Saved general poll response via trail handler: {response.id}")
                del context.bot_data['poll_context'][poll_id]
            except Exception as e:
                logger.error(f"Error saving general poll response: {e}", exc_info=True)
        else:
            logger.warning(f"Poll {poll_id} not found in trail_polls or poll_context")
        return

    poll_context = context.bot_data['trail_polls'][poll_id]
    trail_path = poll_context['trail_path']
    chat_id = poll_context['chat_id']

    # Get the poll to retrieve the selected option text
    # Note: We need to get the poll from the update
    # For now, we'll reconstruct from the service

    trail_service = get_trail_review_service()

    # Get selected answer from poll
    # Poll answers come as option IDs, need to map back to text
    # We'll store the sequence in the poll context
    if chat_id not in trail_service._poll_states:
        logger.warning(f"No poll state for chat {chat_id}")
        return

    if trail_path not in trail_service._poll_states[chat_id]:
        logger.warning(f"No poll state for trail {trail_path}")
        return

    state = trail_service._poll_states[chat_id][trail_path]
    current_poll = state['sequence'][state['current_index']]
    selected_option = current_poll['options'][option_ids[0]]

    # Record answer and get next poll
    next_poll, is_complete = trail_service.get_next_poll(
        chat_id, trail_path, selected_option
    )

    if is_complete:
        # Finalize review
        result = trail_service.finalize_review(chat_id, trail_path)

        if result['success']:
            # Send summary
            summary = f"✅ <b>Trail Review Complete: {result['trail_name']}</b>\n\n"
            summary += "<b>Updates:</b>\n"
            for change in result['changes']:
                summary += f"• {change}\n"

            await context.bot.send_message(
                chat_id=chat_id,
                text=summary,
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Error updating trail: {result.get('error')}",
                parse_mode='HTML'
            )

        # Clean up poll context
        del context.bot_data['trail_polls'][poll_id]

    else:
        # Send next poll
        # We need to create a fake update to pass trail info
        # Instead, we'll send directly via bot
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=next_poll['question'],
            options=next_poll['options'],
            is_anonymous=False,
            allows_multiple_answers=False
        )

        # Store new poll context
        context.bot_data['trail_polls'][poll_message.poll.id] = {
            'trail_path': trail_path,
            'field': next_poll['field'],
            'chat_id': chat_id
        }

        # Clean up old poll context
        del context.bot_data['trail_polls'][poll_id]


async def send_scheduled_trail_review(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to send trail review polls.

    Call this via job queue at configured times.
    """
    from ...models.user_settings import get_user_settings

    # Get all users with trail review enabled
    # For now, use a configured chat ID from settings
    # TODO: Store per-user settings in database

    trail_service = get_trail_review_service()

    # Get random active trail
    trail = trail_service.get_random_active_trail()

    if not trail:
        logger.info("No trails available for scheduled review")
        return

    # Get configured chat ID (from environment or settings)
    import os
    chat_id = os.getenv('TRAIL_REVIEW_CHAT_ID')

    if not chat_id:
        logger.warning("TRAIL_REVIEW_CHAT_ID not configured, skipping scheduled review")
        return

    chat_id = int(chat_id)

    # Start poll sequence
    first_poll = trail_service.start_poll_sequence(chat_id, trail)

    if not first_poll:
        logger.error(f"Error starting scheduled review for {trail['name']}")
        return

    # Send intro message
    intro = f"🔔 <b>Scheduled Trail Review: {trail['name']}</b>\n\n"
    intro += f"Status: {trail['status']}\n"
    intro += f"Velocity: {trail['velocity']}\n"
    if trail.get('next_review'):
        intro += f"Next review: {trail['next_review']}\n"
    intro += f"\n<i>Answer the following questions to update this trail:</i>"

    await context.bot.send_message(
        chat_id=chat_id,
        text=intro,
        parse_mode='HTML'
    )

    # Send first poll
    poll_message = await context.bot.send_poll(
        chat_id=chat_id,
        question=first_poll['question'],
        options=first_poll['options'],
        is_anonymous=False,
        allows_multiple_answers=False
    )

    # Store poll context
    if 'trail_polls' not in context.bot_data:
        context.bot_data['trail_polls'] = {}

    context.bot_data['trail_polls'][poll_message.poll.id] = {
        'trail_path': trail['path'],
        'field': first_poll['field'],
        'chat_id': chat_id
    }

    logger.info(f"Sent scheduled trail review for {trail['name']} to chat {chat_id}")


def register_trail_handlers(application) -> None:
    """Register trail review handlers with the application."""
    application.add_handler(CommandHandler("trail", trail_command))
    application.add_handler(PollAnswerHandler(handle_trail_poll_answer))
    logger.info("Trail review handlers registered")
