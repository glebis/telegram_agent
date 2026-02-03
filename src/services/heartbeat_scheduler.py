"""
Heartbeat Scheduler — Wires HeartbeatService into the JobQueueBackend.

Reads config, creates a ScheduledJob, and registers it.
The callback checks active hours before running.
"""

import logging
import os
from datetime import datetime

from telegram.ext import Application, ContextTypes

from ..core.config import get_config_value

logger = logging.getLogger(__name__)


async def _heartbeat_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job queue callback: run heartbeat for all configured chat IDs."""
    # Active hours gate
    hour_start = get_config_value("heartbeat.active_hours_start", 8)
    hour_end = get_config_value("heartbeat.active_hours_end", 23)
    now_hour = datetime.now().hour

    if not (hour_start <= now_hour < hour_end):
        logger.debug(
            "Heartbeat skipped: outside active hours (%d-%d, current=%d)",
            hour_start,
            hour_end,
            now_hour,
        )
        return

    chat_ids_str = os.getenv("HEARTBEAT_CHAT_IDS", "")
    if not chat_ids_str.strip():
        logger.debug("Heartbeat skipped: no HEARTBEAT_CHAT_IDS configured")
        return

    chat_ids = [int(cid.strip()) for cid in chat_ids_str.split(",") if cid.strip()]

    from .heartbeat_service import get_heartbeat_service

    service = get_heartbeat_service()

    for chat_id in chat_ids:
        try:
            result = await service.run_and_deliver(chat_id)
            logger.info(
                "Heartbeat for chat %d: status=%s, duration=%.2fs",
                chat_id,
                result.status,
                result.duration_seconds,
            )
        except Exception as e:
            logger.error("Heartbeat failed for chat %d: %s", chat_id, e)


def setup_heartbeat_scheduler(application: Application) -> None:
    """Register heartbeat as a repeating job on the application's job queue."""
    enabled = get_config_value("heartbeat.enabled", True)
    if not enabled:
        logger.info("Heartbeat scheduler disabled (heartbeat.enabled=false)")
        return

    chat_ids_str = os.getenv("HEARTBEAT_CHAT_IDS", "")
    if not chat_ids_str.strip():
        logger.info("Heartbeat scheduler disabled: no HEARTBEAT_CHAT_IDS configured")
        return

    if not application.job_queue:
        logger.warning("Job queue not available, heartbeat scheduler disabled")
        return

    interval_minutes = get_config_value("heartbeat.interval_minutes", 30)
    interval_seconds = interval_minutes * 60

    from .scheduler import JobQueueBackend, ScheduledJob, ScheduleType

    backend = JobQueueBackend(application)
    job = ScheduledJob(
        name="heartbeat",
        callback=_heartbeat_callback,
        schedule_type=ScheduleType.INTERVAL,
        interval_seconds=interval_seconds,
        first_delay_seconds=120,  # First run after 2 minutes
    )
    backend.schedule(job)

    logger.info("Heartbeat scheduler configured: every %d minutes", interval_minutes)
