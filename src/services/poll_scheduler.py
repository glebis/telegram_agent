"""
Poll Scheduler - Schedule automatic poll delivery via job queue.

Sends polls periodically throughout the day based on configuration.
"""

import logging
import os
from typing import List, Optional

from telegram.ext import Application

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
    from ..bot.handlers.poll_handlers import send_scheduled_poll

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


def get_poll_scheduler_config() -> PollSchedulerConfig:
    """Get the global poll scheduler configuration."""
    global _config
    if _config is None:
        _config = PollSchedulerConfig()
    return _config
