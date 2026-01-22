"""
SRS Command Handlers
Handlers for spaced repetition system commands
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from src.services.srs_service import srs_service

logger = logging.getLogger(__name__)


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /review command - show next cards due for review."""
    # Parse optional limit argument
    limit = 5
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 20)  # Max 20 cards

    await srs_service.handle_review_command(update, context, limit=limit)


async def srs_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /srs_stats command - show SRS statistics."""
    try:
        stats = srs_service.get_stats()

        if not stats:
            await update.message.reply_text("📊 No SRS cards found.")
            return

        response = "📊 <b>SRS Statistics</b>\n\n"

        for note_type, data in stats.items():
            emoji = {
                'idea': '💡',
                'trail': '🛤️',
                'moc': '🗺️',
                'other': '📝'
            }.get(note_type, '📝')

            response += f"{emoji} <b>{note_type.title()}</b>\n"
            response += f"  Total: {data['total']}\n"
            response += f"  Due now: {data['due_now']}\n"
            response += f"  Avg ease: {data['avg_ease']}\n"
            response += f"  Avg interval: {data['avg_interval']} days\n\n"

        await update.message.reply_text(response, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Error showing SRS stats: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def srs_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle SRS button callbacks."""
    from pathlib import Path
    from src.bot.handlers.claude_commands import execute_claude_prompt

    query = update.callback_query

    # Check if this is an SRS callback
    if not query.data.startswith('srs_'):
        return

    result = await srs_service.handle_rating_callback(update, context)

    # If "Develop" button was clicked, start Agent SDK session
    if result.get('action') == 'develop':
        note_path = result['note_path']

        # Get development context
        dev_context = srs_service.get_develop_context(note_path)

        # Store full note path for Claude to access
        vault_full_path = dev_context['vault_path']

        # Start Claude Code session with context
        # Create a new update object that looks like the user sent a message
        await execute_claude_prompt(
            update=update,
            context=context,
            prompt=dev_context['context_prompt'],
            force_new=True,  # Start fresh session for this note
            custom_cwd=str(Path(vault_full_path).parent)  # Set working dir to vault
        )


# Register handlers
def register_srs_handlers(application):
    """Register SRS handlers with the application."""
    application.add_handler(CommandHandler("review", review_command))
    application.add_handler(CommandHandler("srs_stats", srs_stats_command))
    application.add_handler(CallbackQueryHandler(srs_callback_handler, pattern=r'^srs_'))

    logger.info("SRS handlers registered")
