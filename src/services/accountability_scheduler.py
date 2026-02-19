"""
Accountability check-in scheduler.

Schedules daily check-in reminders per user based on their configured
check_in_time. Uses the centralized JobQueueBackend for scheduling.
"""

import logging
import re
from datetime import datetime
from datetime import time as dt_time
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from ..core.database import get_db_session
from ..core.i18n import t
from ..models.chat import Chat
from ..models.tracker import Tracker
from ..models.user import User
from .scheduler.base import ScheduledJob, ScheduleType
from .scheduler.job_queue_backend import JobQueueBackend

logger = logging.getLogger(__name__)


def _parse_time(time_str: str) -> dt_time:
    """Parse HH:MM time string to datetime.time."""
    try:
        parts = time_str.split(":")
        return dt_time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return dt_time(19, 0)  # Default: 7 PM


def _strip_voice_tags(text: str) -> str:
    """Remove voice/emotion markup tags for text display."""
    text = re.sub(r"\[.*?\]", "", text)  # [whisper], [cheerful], etc.
    text = re.sub(r"<\w+>", "", text)  # <sigh>, <chuckle>, etc.
    return text.strip()


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


async def _is_accountability_enabled(chat_id: int) -> bool:
    """Check if accountability partner is enabled for this chat."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Chat.accountability_enabled).where(Chat.chat_id == chat_id)
        )
        row = result.first()
        return bool(row and row[0])


async def send_checkin_reminder(context) -> None:
    """Job callback: send check-in reminders for all active trackers.

    This is called by JobQueueBackend at the user's configured check-in time.
    """
    from src.bot.adapters.telegram_keyboards import inline_keyboard_from_rows

    from .tracker_queries import TYPE_EMOJI, get_streak, get_today_checkin

    job = context.job
    user_id = job.data.get("user_id")
    chat_id = job.data.get("chat_id")
    locale = job.data.get("locale")

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
                checkin = await get_today_checkin(session, user_id, tracker.id)
                if not checkin:
                    streak = await get_streak(session, user_id, tracker.id)
                    unchecked.append((tracker, streak))

            if not unchecked:
                logger.info(f"All trackers checked in for user {user_id}")
                return

            # Build reminder message
            reminder_title = t("accountability.checkin_reminder_title", locale)
            lines = [f"⏰ <b>{reminder_title}</b>\n"]
            not_checked = t("accountability.checkin_not_checked", locale)
            lines.append(f"{not_checked}\n")

            keyboard_rows = []
            for tracker, streak in unchecked:
                emoji = TYPE_EMOJI.get(tracker.type, "📋")
                streak_text = f" (🔥{streak})" if streak > 0 else ""
                lines.append(f"  {emoji} {tracker.name}{streak_text}")

                keyboard_rows.append(
                    [
                        {
                            "text": f"✅ {tracker.name}",
                            "callback_data": f"checkin_done:{tracker.id}",
                        },
                        {
                            "text": t("inline.accountability.skip", locale),
                            "callback_data": f"checkin_skip:{tracker.id}",
                        },
                    ]
                )

            reply_markup = inline_keyboard_from_rows(keyboard_rows)

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

        # Voice check-in (only if accountability partner enabled)
        if await _is_accountability_enabled(chat_id):
            try:
                from .accountability_service import AccountabilityService

                svc = AccountabilityService()
                for tracker, streak in unchecked:
                    result = await svc.send_check_in(
                        user_id, tracker.id
                    )
                    if result:
                        text, audio = result
                        await context.bot.send_voice(
                            chat_id=chat_id,
                            voice=audio,
                        )
            except Exception as e:
                logger.error(f"Voice check-in failed for user {user_id}: {e}")

    except Exception as e:
        logger.error(f"Error sending check-in reminder for user {user_id}: {e}")


async def check_struggles(context) -> None:
    """Job callback: check for struggling users (consecutive misses)."""
    job = context.job
    user_id = job.data.get("user_id")
    chat_id = job.data.get("chat_id")

    if not user_id or not chat_id:
        return

    # Skip if accountability partner is disabled
    if not await _is_accountability_enabled(chat_id):
        return

    try:
        from .accountability_service import AccountabilityService

        svc = AccountabilityService()
        struggles = await AccountabilityService.check_for_struggles(user_id)

        if not struggles:
            return

        for tracker_id, misses in struggles.items():
            result = await svc.send_struggle_alert(
                user_id, tracker_id, misses
            )
            if result:
                text, audio = result
                # Send text message
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"💬 {text}",
                )
                # Send voice message
                try:
                    await context.bot.send_voice(
                        chat_id=chat_id,
                        voice=audio,
                    )
                except Exception as e:
                    logger.error(f"Voice struggle alert failed: {e}")
            else:
                # Fallback: text-only struggle message
                async with get_db_session() as session:
                    from ..models.accountability_profile import AccountabilityProfile

                    settings_result = await session.execute(
                        select(AccountabilityProfile).where(
                            AccountabilityProfile.user_id == user_id
                        )
                    )
                    settings = settings_result.scalar_one_or_none()
                    personality = (
                        settings.partner_personality if settings else "supportive"
                    )

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
                    msg = _strip_voice_tags(msg)

                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"💬 {msg}",
                    )

            logger.info(
                f"Sent struggle alert for user {user_id}, "
                f"tracker {tracker_id}: {misses} misses"
            )

    except Exception as e:
        logger.error(f"Error checking struggles for user {user_id}: {e}")


async def schedule_user_checkins(
    application: Any, user_id: int, chat_id: int
) -> None:
    """Schedule daily check-in and struggle-check jobs for a user."""
    try:
        async with get_db_session() as session:
            chat_result = await session.execute(
                select(Chat).where(Chat.chat_id == chat_id)
            )
            chat_obj = chat_result.scalar_one_or_none()

        check_time_str = chat_obj.check_in_time if chat_obj else "19:00"
        check_time = _parse_time(check_time_str)

        backend = JobQueueBackend(application)

        # Cancel existing jobs for this user
        checkin_name = f"checkin_{user_id}"
        struggle_name = f"struggle_{user_id}"
        backend.cancel(checkin_name)
        backend.cancel(struggle_name)

        job_data = {"user_id": user_id, "chat_id": chat_id}

        # Schedule daily check-in
        backend.schedule(
            ScheduledJob(
                name=checkin_name,
                callback=send_checkin_reminder,
                schedule_type=ScheduleType.DAILY,
                daily_times=[check_time],
                data=job_data,
            )
        )

        # Schedule daily struggle check (1 hour after check-in)
        struggle_time_dt = datetime.combine(datetime.today(), check_time) + timedelta(
            hours=1
        )
        struggle_time = struggle_time_dt.time()

        backend.schedule(
            ScheduledJob(
                name=struggle_name,
                callback=check_struggles,
                schedule_type=ScheduleType.DAILY,
                daily_times=[struggle_time],
                data=job_data,
            )
        )

        logger.info(
            f"Scheduled check-in for user {user_id} at {check_time_str}, "
            f"struggle check at {struggle_time}"
        )

    except Exception as e:
        logger.error(f"Error scheduling check-ins for user {user_id}: {e}")


async def cancel_user_checkins(application: Any, user_id: int) -> None:
    """Cancel all scheduled accountability jobs for a user."""
    backend = JobQueueBackend(application)
    backend.cancel(f"checkin_{user_id}")
    backend.cancel(f"struggle_{user_id}")
    logger.info(f"Cancelled accountability jobs for user {user_id}")


async def restore_all_schedules(application: Any) -> None:
    """Restore check-in schedules for all users with active trackers on startup."""
    try:
        async with get_db_session() as session:
            # Get all users with active trackers who have accountability enabled
            result = await session.execute(
                select(Tracker.user_id)
                .where(Tracker.active == True)  # noqa: E712
                .distinct()
            )
            user_ids = [row[0] for row in result.all()]

        if not user_ids:
            logger.info("No users with active trackers to schedule")
            return

        scheduled_count = 0
        for user_id in user_ids:
            try:
                async with get_db_session() as session:
                    # Tracker.user_id is the Telegram user ID, but
                    # Chat.user_id references users.id (internal PK).
                    # Join through User to map correctly.
                    result = await session.execute(
                        select(Chat.chat_id, Chat.accountability_enabled)
                        .join(User, Chat.user_id == User.id)
                        .where(User.user_id == user_id)
                        .limit(1)
                    )
                    row = result.first()
                    if row:
                        chat_id, enabled = row
                        if enabled:
                            await schedule_user_checkins(application, user_id, chat_id)
                            scheduled_count += 1
            except Exception as e:
                logger.error(f"Error restoring schedule for user {user_id}: {e}")

        logger.info(
            f"Restored check-in schedules for {scheduled_count}/{len(user_ids)} users"
        )

    except Exception as e:
        logger.error(f"Error restoring schedules: {e}")
