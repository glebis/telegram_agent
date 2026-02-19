"""
Trail Review Scheduler - Manages scheduled trail review polls.

Configures daily scheduled polls at configurable times.
Also contains the send_scheduled_trail_review job callback (moved from
trail_handlers to keep the service→handler dependency direction correct).
"""

import logging
import os
from datetime import time
from typing import Awaitable, Callable, List, Optional

from telegram.ext import Application, ContextTypes

from ..core.i18n import t
from ..core.typed_config import TrailSchedule
from ..core.typed_config_loader import load_trail_schedule
from .trail_review_service import get_trail_review_service

logger = logging.getLogger(__name__)

# Callback type: async (context, chat_id, trail, poll_data) -> None
SendTrailPollFn = Callable[
    [ContextTypes.DEFAULT_TYPE, int, dict, dict], Awaitable[None]
]

# Module-level callback injected by the bot layer at setup time
_send_trail_poll_fn: Optional[SendTrailPollFn] = None


class TrailSchedulerConfig:
    """Configuration for trail review scheduling.

    Internally delegates to a typed TrailSchedule object for validation
    and immutability, while preserving the existing public API.
    """

    def __init__(self):
        self._schedule = load_trail_schedule()
        # Backward-compat attributes (kept for any direct access)
        self.poll_times = list(self._schedule.poll_times)
        self.enabled = self._schedule.enabled
        self.chat_id = self._schedule.chat_id

    @classmethod
    def from_schedule(cls, schedule: TrailSchedule) -> "TrailSchedulerConfig":
        """Construct from an existing typed TrailSchedule."""
        instance = cls.__new__(cls)
        instance._schedule = schedule
        instance.poll_times = list(schedule.poll_times)
        instance.enabled = schedule.enabled
        instance.chat_id = schedule.chat_id
        return instance

    @property
    def schedule(self) -> TrailSchedule:
        """Typed, immutable view of the schedule configuration."""
        return self._schedule

    def get_poll_times(self) -> List[time]:
        """Get configured poll times."""
        return self.poll_times

    def is_enabled(self) -> bool:
        """Check if scheduled reviews are enabled."""
        return self.enabled and self.chat_id is not None


def setup_trail_scheduler(
    application: Application,
    send_trail_poll: Optional[SendTrailPollFn] = None,
) -> None:
    """
    Set up scheduled trail review polls.

    Configures job queue to send trail review polls at specified times.

    Args:
        application: The telegram Application instance.
        send_trail_poll: Callback to send a trail poll. Injected by the
            bot handler layer so the service never imports from bot/.
    """
    global _send_trail_poll_fn
    if send_trail_poll is not None:
        _send_trail_poll_fn = send_trail_poll
    config = TrailSchedulerConfig()

    if not config.is_enabled():
        logger.info(
            "Trail review scheduler disabled (TRAIL_REVIEW_ENABLED=false or no chat ID)"
        )
        return

    if not application.job_queue:
        logger.warning("Job queue not available, trail scheduler disabled")
        return

    # Schedule polls at configured times
    for poll_time in config.get_poll_times():
        application.job_queue.run_daily(
            send_scheduled_trail_review,
            time=poll_time,
            name=f"trail_review_{poll_time.hour}:{poll_time.minute:02d}",
        )
        logger.info(
            f"📅 Scheduled trail review at {poll_time.hour}:{poll_time.minute:02d}"
        )

    logger.info(
        f"✅ Trail review scheduler configured with {len(config.get_poll_times())} daily polls"
    )


# Singleton instance
_config: Optional[TrailSchedulerConfig] = None


async def send_scheduled_trail_review(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scheduled job to send trail review polls.

    Call this via job queue at configured times.
    """
    trail_service = get_trail_review_service()

    # Get random active trail
    trail = trail_service.get_random_active_trail()

    if not trail:
        logger.info("No trails available for scheduled review")
        return

    # Get configured chat ID (from environment or settings)
    chat_id = os.getenv("TRAIL_REVIEW_CHAT_ID")

    if not chat_id:
        logger.warning("TRAIL_REVIEW_CHAT_ID not configured, skipping scheduled review")
        return

    chat_id_int = int(chat_id)

    # Start poll sequence
    first_poll = trail_service.start_poll_sequence(chat_id_int, trail)

    if not first_poll:
        logger.error(f"Error starting scheduled review for {trail['name']}")
        return

    # Send intro message
    intro = (
        "🔔 <b>" + t("trails.scheduled_title", "en", name=trail["name"]) + "</b>\n\n"
    )
    intro += t("trails.review_intro_status", "en", status=trail["status"]) + "\n"
    intro += t("trails.review_intro_velocity", "en", velocity=trail["velocity"]) + "\n"
    if trail.get("next_review"):
        intro += t("trails.review_intro_due", "en", date=trail["next_review"]) + "\n"
    intro += "\n<i>" + t("trails.review_intro_hint", "en") + "</i>"

    await context.bot.send_message(chat_id=chat_id_int, text=intro, parse_mode="HTML")

    # Send first poll via the injected callback (set by bot layer at startup)
    if _send_trail_poll_fn is None:
        logger.error(
            "send_trail_poll callback not registered; "
            "call setup_trail_scheduler with send_trail_poll= first"
        )
        return

    await _send_trail_poll_fn(context, chat_id_int, trail, first_poll)

    logger.info(
        f"Sent scheduled trail review for {trail['name']} to chat {chat_id_int}"
    )


def get_trail_scheduler_config() -> TrailSchedulerConfig:
    """Get the global trail scheduler configuration."""
    global _config
    if _config is None:
        _config = TrailSchedulerConfig()
    return _config
