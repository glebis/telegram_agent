"""
Poll Scheduler - Schedule automatic poll delivery via job queue.

Sends polls periodically throughout the day based on configuration.
Also contains the send_scheduled_poll job callback (moved from
poll_handlers to keep the service→handler dependency direction correct).
"""

import logging
import os
from typing import List, Optional

from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)


class PollSchedulerConfig:
    """Configuration for poll scheduler."""

    def __init__(self):
        """Load config from environment."""
        self.enabled = os.getenv("POLLING_ENABLED", "true").lower() == "true"
        self.chat_ids_str = os.getenv("POLLING_CHAT_IDS", "")
        self.interval_minutes = int(os.getenv("POLLING_INTERVAL_MINUTES", "30"))

    def is_enabled(self) -> bool:
        """Check if polling is enabled."""
        return self.enabled and bool(self.chat_ids_str.strip())

    def get_chat_ids(self) -> List[int]:
        """Get list of chat IDs to send polls to."""
        if not self.chat_ids_str:
            return []
        return [int(cid.strip()) for cid in self.chat_ids_str.split(",") if cid.strip()]

    def get_interval_minutes(self) -> int:
        """Get polling interval in minutes."""
        return self.interval_minutes


def setup_poll_scheduler(application: Application) -> None:
    """
    Set up the poll scheduler with job queue.

    Polls are sent automatically at configured intervals.

    Environment variables:
    - POLLING_ENABLED: true/false (default: true)
    - POLLING_CHAT_IDS: Comma-separated chat IDs (e.g., "161427550,123456789")
    - POLLING_INTERVAL_MINUTES: Interval in minutes (default: 30)
    """
    config = PollSchedulerConfig()

    if not config.is_enabled():
        logger.info("Poll scheduler disabled (POLLING_ENABLED=false or no chat IDs)")
        return

    if not application.job_queue:
        logger.warning("Job queue not available, poll scheduler disabled")
        return

    # Schedule polls at interval
    interval_minutes = config.get_interval_minutes()
    application.job_queue.run_repeating(
        send_scheduled_poll,
        interval=interval_minutes * 60,  # Convert to seconds
        first=60,  # Start after 1 minute
        name=f"auto_polls_every_{interval_minutes}min",
    )

    chat_ids = config.get_chat_ids()
    logger.info(
        f"✅ Poll scheduler configured: {len(chat_ids)} chats, "
        f"every {interval_minutes} minutes"
    )

    # Clean up any polls that expired while bot was down
    from .poll_lifecycle import get_poll_lifecycle_tracker

    tracker = get_poll_lifecycle_tracker()
    expired = tracker.get_expired_polls()
    if expired:
        logger.info(
            f"Found {len(expired)} polls that expired during downtime, scheduling cleanup"
        )
        for poll_data in expired:
            # Schedule immediate expiration (delay=1 second to let bot fully initialize)
            application.job_queue.run_once(
                _startup_expire_callback,
                when=1,
                name=f"startup_expire_{poll_data['poll_id']}",
                data=poll_data,
            )


# Singleton instance
_config: Optional[PollSchedulerConfig] = None


async def _startup_expire_callback(context):
    """Clean up a poll that expired during bot downtime."""
    from ..utils.telegram_api import _run_telegram_api_sync
    from .poll_lifecycle import get_poll_lifecycle_tracker

    poll_data = context.job.data
    poll_id = poll_data["poll_id"]
    chat_id = poll_data["chat_id"]
    message_id = poll_data["message_id"]

    tracker = get_poll_lifecycle_tracker()
    tracker.record_expired(poll_id)

    logger.info(f"Startup cleanup: expiring poll {poll_id} in chat {chat_id}")

    _run_telegram_api_sync(
        "stopPoll",
        {
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )
    _run_telegram_api_sync(
        "deleteMessage",
        {
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )


async def send_scheduled_poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to send polls automatically.

    This should be called periodically (e.g., every 30 minutes) via job queue.
    """
    from .polling_service import get_polling_service

    polling_service = get_polling_service()

    chat_ids_str = os.getenv("POLLING_CHAT_IDS", "")
    if not chat_ids_str:
        logger.debug("No polling chat IDs configured")
        return

    chat_ids = [int(cid.strip()) for cid in chat_ids_str.split(",") if cid.strip()]

    for chat_id in chat_ids:
        try:
            # Check if paused for this chat
            if (
                context.application.chat_data.get(chat_id, {})
                .get("poll_settings", {})
                .get("paused", False)
            ):
                logger.info(f"Polls paused for chat {chat_id}, skipping")
                continue

            # Check poll lifecycle: backpressure and unanswered count
            from .poll_lifecycle import get_poll_lifecycle_tracker

            tracker = get_poll_lifecycle_tracker()
            allowed, reason = tracker.should_send(chat_id)
            if not allowed:
                logger.info(f"Poll suppressed for chat {chat_id}: {reason}")
                continue

            # Get next poll
            poll_template = await polling_service.get_next_poll(chat_id)

            if not poll_template:
                logger.debug(f"No poll available for chat {chat_id}")
                continue

            # Send poll
            poll_message = await context.bot.send_poll(
                chat_id=chat_id,
                question=poll_template["question"],
                options=poll_template["options"],
                is_anonymous=False,
                allows_multiple_answers=False,
            )

            # Check for recent voice context to track poll origin
            from .reply_context import MessageType, get_reply_context_service

            reply_service = get_reply_context_service()
            recent_voice = reply_service.get_recent_context_by_type(
                chat_id, MessageType.VOICE_TRANSCRIPTION, max_age_minutes=10
            )

            origin_info = {
                "source_type": "scheduled",
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
            tracker.record_sent(
                poll_id=poll_message.poll.id,
                chat_id=chat_id,
                message_id=poll_message.message_id,
                template_id=poll_template["id"],
                question=poll_template["question"],
            )

            # Schedule expiration job
            _schedule_poll_expiration(
                context, poll_message.poll.id, tracker.ttl_minutes
            )

            # Update send counter in database
            await polling_service.increment_send_count(poll_template["question"])

            logger.info(
                f"Sent scheduled poll {poll_template['id']} to chat {chat_id}: "
                f"'{poll_template['question'][:50]}...'"
            )

        except Exception as e:
            logger.error(
                f"Error sending scheduled poll to chat {chat_id}: {e}", exc_info=True
            )


def _schedule_poll_expiration(
    context: ContextTypes.DEFAULT_TYPE,
    poll_id: str,
    ttl_minutes: int,
) -> None:
    """Schedule a one-shot job to expire a poll after TTL."""
    if not context.application.job_queue:
        logger.warning("No job queue, cannot schedule poll expiration")
        return

    context.application.job_queue.run_once(
        _expire_poll_callback,
        when=ttl_minutes * 60,  # seconds
        name=f"expire_poll_{poll_id}",
        data={"poll_id": poll_id},
    )
    logger.debug(f"Scheduled expiration for poll {poll_id} in {ttl_minutes}min")


async def _expire_poll_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job queue callback: expire a single poll.

    Deletes the poll message from chat and updates lifecycle tracker.
    Uses _run_telegram_api_sync for subprocess isolation.
    """
    poll_id = context.job.data.get("poll_id")
    if not poll_id:
        return

    from ..utils.telegram_api import _run_telegram_api_sync
    from .poll_lifecycle import get_poll_lifecycle_tracker

    tracker = get_poll_lifecycle_tracker()
    poll_info = tracker.record_expired(poll_id)

    if not poll_info:
        logger.debug(f"Poll {poll_id} already answered/cleaned up before expiration")
        return

    chat_id = poll_info["chat_id"]
    message_id = poll_info["message_id"]

    logger.info(
        f"Expiring poll {poll_id} in chat {chat_id} "
        f"(msg {message_id}, question='{poll_info.get('question', '')[:40]}...')"
    )

    # Step 1: Stop the poll (closes it in-place so users see it's expired)
    _run_telegram_api_sync(
        "stopPoll",
        {
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )

    # Step 2: Delete the poll message from chat
    _run_telegram_api_sync(
        "deleteMessage",
        {
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )

    # Step 3: Clean up bot_data
    if "poll_context" in context.bot_data:
        context.bot_data["poll_context"].pop(poll_id, None)

    logger.info(f"Poll {poll_id} expired and deleted from chat {chat_id}")


def get_poll_scheduler_config() -> PollSchedulerConfig:
    """Get the global poll scheduler configuration."""
    global _config
    if _config is None:
        _config = PollSchedulerConfig()
    return _config
