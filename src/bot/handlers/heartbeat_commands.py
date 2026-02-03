"""
Heartbeat command handler.

/heartbeat — Runs a full system health check (admin only).
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ...services import claude_code_service
from ...utils import task_tracker

logger = logging.getLogger(__name__)


async def heartbeat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /heartbeat command — admin-only system health check."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    # Admin check
    if not await claude_code_service.is_claude_code_admin(chat.id):
        if update.message:
            await update.message.reply_text("This command is restricted to admins.")
        return

    logger.info("Heartbeat command from user %d in chat %d", user.id, chat.id)

    # Send status message
    if update.message:
        await update.message.reply_text("Running health checks...")

    # Run heartbeat in tracked task
    from ...services.heartbeat_service import get_heartbeat_service

    service = get_heartbeat_service()

    async def _run() -> None:
        result = await service.run_and_deliver(chat.id)
        logger.info(
            "Heartbeat command result: status=%s, duration=%.2fs",
            result.status,
            result.duration_seconds,
        )

    task_tracker.create_tracked_task(_run(), name="heartbeat_command")
