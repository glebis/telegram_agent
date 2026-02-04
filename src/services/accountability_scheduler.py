"""
Accountability check-in scheduler.

Schedules daily check-in reminders per user based on their configured
check_in_time. Uses the bot's job_queue for scheduling.
"""

import logging
from datetime import datetime
from datetime import time as dt_time
from datetime import timedelta
from typing import Dict

from sqlalchemy import select

from ..core.database import get_db_session
from ..models.tracker import Tracker
from ..models.user_settings import UserSettings

logger = logging.getLogger(__name__)

# Track scheduled jobs by user_id for rescheduling
_scheduled_jobs: Dict[int, str] = {}


def _parse_time(time_str: str) -> dt_time:
    """Parse HH:MM time string to datetime.time."""
    try:
        parts = time_str.split(":")
        return dt_time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return dt_time(19, 0)  # Default: 7 PM


def _is_quiet_hours(
    now: datetime,
    quiet_start: str = "22:00",
    quiet_end: str = "07:00",
) -> bool:
    """Check if current time is within quiet hours."""
    start = _parse_time(quiet_start)
    end = _parse_time(quiet_end)
    current = now.time()

    if start > end:
        # Quiet hours span midnight (e.g., 22:00 - 07:00)
        return current >= start or current <= end
    else:
        return start <= current <= end


async def send_checkin_reminder(context) -> None:
    """Job callback: send check-in reminders for all active trackers.

    This is called by job_queue at the user's configured check-in time.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from ..bot.handlers.accountability_commands import (
        TYPE_EMOJI,
        _get_streak,
        _get_today_checkin,
    )

    job = context.job
    user_id = job.data.get("user_id")
    chat_id = job.data.get("chat_id")

    if not user_id or not chat_id:
        logger.error(f"Checkin reminder job missing user_id or chat_id: {job.data}")
        return

    # Check quiet hours
    if _is_quiet_hours(datetime.now()):
        logger.info(f"Skipping check-in for user {user_id}: quiet hours")
        return

    try:
        async with get_db_session() as session:
            # Get active trackers
            result = await session.execute(
                select(Tracker).where(
                    Tracker.user_id == user_id,
                    Tracker.active == True,  # noqa: E712
                )
            )
            trackers = list(result.scalars().all())

            if not trackers:
                return

            # Find trackers not yet checked in today
            unchecked = []
            for tracker in trackers:
                checkin = await _get_today_checkin(session, user_id, tracker.id)
                if not checkin:
                    streak = await _get_streak(session, user_id, tracker.id)
                    unchecked.append((tracker, streak))

            if not unchecked:
                logger.info(f"All trackers checked in for user {user_id}")
                return

            # Build reminder message
            lines = ["⏰ <b>Check-in Reminder</b>\n"]
            lines.append("You haven't checked in yet for:\n")

            keyboard = []
            for tracker, streak in unchecked:
                emoji = TYPE_EMOJI.get(tracker.type, "📋")
                streak_text = f" (🔥{streak})" if streak > 0 else ""
                lines.append(f"  {emoji} {tracker.name}{streak_text}")

                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"✅ {tracker.name}",
                            callback_data=f"checkin_done:{tracker.id}",
                        ),
                        InlineKeyboardButton(
                            "⏭ Skip",
                            callback_data=f"checkin_skip:{tracker.id}",
                        ),
                    ]
                )

            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            logger.info(
                f"Sent check-in reminder to user {user_id}: "
                f"{len(unchecked)} unchecked trackers"
            )

    except Exception as e:
        logger.error(f"Error sending check-in reminder for user {user_id}: {e}")


async def check_struggles(context) -> None:
    """Job callback: check for struggling users (consecutive misses)."""
    job = context.job
    user_id = job.data.get("user_id")
    chat_id = job.data.get("chat_id")

    if not user_id or not chat_id:
        return

    try:
        from ..services.accountability_service import AccountabilityService

        struggles = await AccountabilityService.check_for_struggles(user_id)

        if not struggles:
            return

        async with get_db_session() as session:
            settings_result = await session.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            settings = settings_result.scalar_one_or_none()
            personality = settings.partner_personality if settings else "supportive"

            for tracker_id, misses in struggles.items():
                tracker_result = await session.execute(
                    select(Tracker).where(Tracker.id == tracker_id)
                )
                tracker = tracker_result.scalar_one_or_none()
                if not tracker:
                    continue

                msg = AccountabilityService.generate_struggle_message(
                    personality=personality,
                    tracker_name=tracker.name,
                    consecutive_misses=misses,
                )

                # Strip voice tags for text delivery
                import re

                msg = re.sub(r"\[.*?\]", "", msg).strip()
                msg = re.sub(r"<\w+>", "", msg).strip()

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"💬 {msg}",
                )

                logger.info(
                    f"Sent struggle alert for user {user_id}, "
                    f"tracker {tracker.name}: {misses} misses"
                )

    except Exception as e:
        logger.error(f"Error checking struggles for user {user_id}: {e}")


async def schedule_user_checkins(job_queue, user_id: int, chat_id: int) -> None:
    """Schedule daily check-in jobs for a user."""
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            settings = result.scalar_one_or_none()

        check_time_str = settings.check_in_time if settings else "19:00"
        check_time = _parse_time(check_time_str)

        # Remove existing job if any
        job_name = f"checkin_{user_id}"
        existing_jobs = job_queue.get_jobs_by_name(job_name)
        for job in existing_jobs:
            job.schedule_removal()

        # Schedule daily check-in
        job_queue.run_daily(
            send_checkin_reminder,
            time=check_time,
            data={"user_id": user_id, "chat_id": chat_id},
            name=job_name,
        )

        # Schedule daily struggle check (1 hour after check-in)
        struggle_time_dt = datetime.combine(datetime.today(), check_time) + timedelta(
            hours=1
        )
        struggle_time = struggle_time_dt.time()

        struggle_name = f"struggle_{user_id}"
        existing_struggle_jobs = job_queue.get_jobs_by_name(struggle_name)
        for job in existing_struggle_jobs:
            job.schedule_removal()

        job_queue.run_daily(
            check_struggles,
            time=struggle_time,
            data={"user_id": user_id, "chat_id": chat_id},
            name=struggle_name,
        )

        _scheduled_jobs[user_id] = job_name
        logger.info(
            f"Scheduled check-in for user {user_id} at {check_time_str}, "
            f"struggle check at {struggle_time}"
        )

    except Exception as e:
        logger.error(f"Error scheduling check-ins for user {user_id}: {e}")


async def restore_all_schedules(job_queue) -> None:
    """Restore check-in schedules for all users with active trackers on startup."""
    try:
        async with get_db_session() as session:
            # Get all users with active trackers
            result = await session.execute(
                select(Tracker.user_id)
                .where(Tracker.active == True)  # noqa: E712
                .distinct()
            )
            user_ids = [row[0] for row in result.all()]

        if not user_ids:
            logger.info("No users with active trackers to schedule")
            return

        # For each user, find their chat_id and schedule
        for user_id in user_ids:
            try:
                async with get_db_session() as session:
                    # Get chat_id from the chats table
                    from ..models.chat import Chat

                    result = await session.execute(
                        select(Chat.chat_id).where(Chat.user_id == user_id).limit(1)
                    )
                    row = result.first()
                    if row:
                        chat_id = row[0]
                        await schedule_user_checkins(job_queue, user_id, chat_id)
            except Exception as e:
                logger.error(f"Error restoring schedule for user {user_id}: {e}")

        logger.info(f"Restored check-in schedules for {len(user_ids)} users")

    except Exception as e:
        logger.error(f"Error restoring schedules: {e}")
