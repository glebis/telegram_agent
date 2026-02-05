"""
Trail Review Scheduler - Manages scheduled trail review polls.

Configures daily scheduled polls at configurable times.
"""

import logging
import os
from datetime import time
from typing import List, Optional

from telegram.ext import Application

logger = logging.getLogger(__name__)


class TrailSchedulerConfig:
    """Configuration for trail review scheduling."""

    def __init__(self):
        # Default poll times: morning, afternoon, evening
        self.poll_times = self._load_poll_times()
        self.enabled = os.getenv("TRAIL_REVIEW_ENABLED", "true").lower() == "true"
        self.chat_id = os.getenv("TRAIL_REVIEW_CHAT_ID")

    def _load_poll_times(self) -> List[time]:
        """Load poll times from environment or use defaults."""
        times_str = os.getenv("TRAIL_REVIEW_TIMES", "09:00,14:00,20:00")

        times = []
        for time_str in times_str.split(","):
            try:
                hour, minute = time_str.strip().split(":")
                times.append(time(int(hour), int(minute)))
            except ValueError:
                logger.warning(f"Invalid time format: {time_str}, skipping")

        # Fallback to defaults if parsing failed
        if not times:
            times = [time(9, 0), time(14, 0), time(20, 0)]

        return times

    def get_poll_times(self) -> List[time]:
        """Get configured poll times."""
        return self.poll_times

    def is_enabled(self) -> bool:
        """Check if scheduled reviews are enabled."""
        return self.enabled and self.chat_id is not None


def setup_trail_scheduler(application: Application) -> None:
    """
    Set up scheduled trail review polls.

    Configures job queue to send trail review polls at specified times.
    """
    from ..bot.handlers.trail_handlers import send_scheduled_trail_review

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


def get_trail_scheduler_config() -> TrailSchedulerConfig:
    """Get the global trail scheduler configuration."""
    global _config
    if _config is None:
        _config = TrailSchedulerConfig()
    return _config
