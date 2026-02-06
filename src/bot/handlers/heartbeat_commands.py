"""
Heartbeat command handler.

/heartbeat — Runs a full system health check (owner only).
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ...core.authorization import AuthTier, require_tier
from ...core.i18n import get_user_locale_from_update, t
from ...utils import task_tracker

logger = logging.getLogger(__name__)


@require_tier(AuthTier.OWNER)
async def heartbeat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /heartbeat command — owner-only system health check."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info("Heartbeat command from user %d in chat %d", user.id, chat.id)

    # Send status message
    locale = get_user_locale_from_update(update)
    if update.message:
        await update.message.reply_text(t("heartbeat.running", locale))

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
