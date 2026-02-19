"""
Life Weeks Scheduler — Wires Life Weeks notifications into the JobQueueBackend.

Reads user settings, generates and sends weekly life visualization images.
Uses heartbeat scheduler pattern with daily checks for per-user schedules.
"""

import logging
from datetime import datetime, time

from sqlalchemy import select
from telegram.ext import Application, ContextTypes

from ..core.database import get_db_session
from ..models.life_weeks_settings import LifeWeeksSettings
from ..utils.telegram_api import send_photo_sync
from .life_weeks_image import calculate_weeks_lived, generate_life_weeks_grid

logger = logging.getLogger(__name__)


async def _life_weeks_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job queue callback: send life weeks visualization to all enabled users."""
    logger.info("Running life weeks notification task")

    try:
        # Query all users with life_weeks_enabled=True
        async with get_db_session() as session:
            result = await session.execute(
                select(LifeWeeksSettings).where(
                    LifeWeeksSettings.life_weeks_enabled.is_(True)
                )
            )
            users = result.scalars().all()

        if not users:
            logger.debug("No users with life_weeks_enabled=True")
            return

        logger.info(f"Found {len(users)} users with life weeks enabled")

        # Process each user
        for user_settings in users:
            try:
                await _send_life_weeks_notification(user_settings)
            except Exception as e:
                logger.error(
                    f"Failed to send life weeks notification to user "
                    f"{user_settings.user_id}: {e}"
                )

    except Exception as e:
        logger.error(f"Life weeks notification task failed: {e}")


async def _send_life_weeks_notification(user_settings: LifeWeeksSettings) -> None:
    """Send life weeks visualization to a single user."""
    user_id = user_settings.user_id

    # Check if it's the right day for this user
    if not _should_send_today(user_settings):
        logger.debug(f"Skipping user {user_id}: not their scheduled day")
        return

    # Check if it's the right time
    if not _is_time_to_send(user_settings):
        logger.debug(f"Skipping user {user_id}: not their scheduled time yet")
        return

    # Calculate weeks lived
    if not user_settings.date_of_birth:
        logger.warning(
            f"User {user_id} has life_weeks_enabled " f"but no date_of_birth set"
        )
        return

    try:
        weeks_lived = calculate_weeks_lived(user_settings.date_of_birth)
    except ValueError as e:
        logger.error(
            f"Invalid date_of_birth for user {user_id}: "
            f"{user_settings.date_of_birth} - {e}"
        )
        return

    # Generate image
    try:
        image_path = generate_life_weeks_grid(weeks_lived, user_settings.date_of_birth)
        logger.info(
            f"Generated life weeks image for user {user_id}: {image_path}"
        )  # noqa: E501
    except Exception as e:
        logger.error(f"Failed to generate image for user {user_id}: {e}")  # noqa: E501
        return

    # Send photo via subprocess isolation
    caption = (
        f"✨ <b>Week {weeks_lived:,} of Your Life</b>\n\n"
        f"Reflect on this week? Reply to this message with your thoughts."
    )

    try:
        response = send_photo_sync(
            chat_id=user_id, photo_path=str(image_path), caption=caption
        )

        if response and response.get("ok"):
            message_id = response["result"]["message_id"]
            logger.info(
                f"Sent life weeks notification to user {user_id}, "
                f"message_id={message_id}"
            )

            # Track reply context
            await _track_reply_context(user_id, message_id, weeks_lived, user_settings)
        else:
            desc = response.get("description") if response else "No response"
            logger.error(f"Failed to send photo to user {user_id}: {desc}")

    except Exception as e:
        logger.error(f"Error sending photo to user {user_id}: {e}")


def _should_send_today(user_settings: LifeWeeksSettings) -> bool:
    """Check if today is the user's scheduled day."""
    if user_settings.life_weeks_day is None:
        # If not set, assume any day is OK (default behavior)
        return True

    today_weekday = datetime.now().weekday()  # 0=Monday, 6=Sunday
    return today_weekday == user_settings.life_weeks_day


def _is_time_to_send(user_settings: LifeWeeksSettings) -> bool:
    """Check if current time matches user's scheduled time."""
    scheduled_time_str = user_settings.life_weeks_time
    now = datetime.now()

    try:
        # Parse HH:MM format
        hour, minute = map(int, scheduled_time_str.split(":"))
        scheduled_time = time(hour, minute)

        # Check if we're within the same hour
        # (Since this runs multiple times per day, we don't want to spam)
        return now.hour == scheduled_time.hour and now.minute >= scheduled_time.minute
    except Exception as e:
        logger.error(
            f"Invalid life_weeks_time format: {scheduled_time_str} "
            f"for user {user_settings.user_id} - {e}"
        )
        return True  # Send anyway if format is invalid


async def _track_reply_context(
    user_id: int, message_id: int, weeks_lived: int, user_settings: LifeWeeksSettings
) -> None:
    """Track reply context for vault routing."""
    try:
        from .reply_context import MessageType, get_reply_context_service

        reply_service = get_reply_context_service()
        reply_service.track_message(
            message_id=message_id,
            chat_id=user_id,
            user_id=user_id,
            message_type=MessageType.LIFE_WEEKS_REFLECTION,
            weeks_lived=weeks_lived,
            life_weeks_reply_destination=user_settings.life_weeks_reply_destination,
            life_weeks_custom_path=user_settings.life_weeks_custom_path,
        )
        logger.debug(f"Tracked reply context for message {message_id}")
    except Exception as e:
        logger.warning(f"Failed to track reply context: {e}")


def setup_life_weeks_scheduler(application: Application) -> None:
    """Register life weeks notification as a repeating job on the application's job queue."""
    from ..core.config import get_config_value

    enabled = get_config_value("life_weeks.enabled", True)
    if not enabled:
        logger.info("Life weeks scheduler disabled (life_weeks.enabled=false)")
        return

    if not application.job_queue:
        logger.warning("Job queue not available, life weeks scheduler disabled")
        return

    # Run daily at multiple times to catch all user schedules
    # We'll check each user's schedule internally
    from .scheduler import JobQueueBackend, ScheduledJob, ScheduleType

    backend = JobQueueBackend(application)

    # Run 4 times per day to cover all time zones
    daily_times = [
        time(hour=6, minute=0),  # Early morning
        time(hour=9, minute=0),  # Morning
        time(hour=12, minute=0),  # Noon
        time(hour=18, minute=0),  # Evening
    ]

    job = ScheduledJob(
        name="life-weeks-notification",
        callback=_life_weeks_callback,
        schedule_type=ScheduleType.DAILY,
        daily_times=daily_times,
        first_delay_seconds=120,  # First run after 2 minutes
    )

    backend.schedule(job)

    times_str = ", ".join(str(t) for t in daily_times)
    logger.info(f"Life weeks scheduler configured: daily at {times_str}")
