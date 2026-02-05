"""
Accountability tracker command handlers.

Commands:
- /track — Overview: show active trackers with today's status
- /track:add <type> <name> — Create a new tracker
- /track:list — List all trackers (active + archived)
- /track:done <name> — Mark tracker as completed for today
- /track:skip <name> — Mark as skipped with optional note
- /track:remove <name> — Archive (soft-delete) a tracker
- /streak — Visual streak dashboard
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...core.database import get_chat_by_telegram_id, get_db_session
from ...core.i18n import get_user_locale_from_update, t
from ...models.tracker import CheckIn, Tracker
from ...models.user_settings import UserSettings
from ...utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)

TRACKER_TYPES = ("habit", "medication", "value", "commitment")
TYPE_EMOJI = {
    "habit": "🔄",
    "medication": "💊",
    "value": "💎",
    "commitment": "🎯",
}
STATUS_EMOJI = {
    "completed": "✅",
    "skipped": "⏭",
    "partial": "🔶",
    None: "⬜",
}


async def _find_tracker(
    session: AsyncSession, user_id: int, name: str, active_only: bool = True
) -> Optional[Tracker]:
    """Find tracker by name with fuzzy matching (case-insensitive, partial)."""
    # Try exact match first (case-insensitive)
    stmt = select(Tracker).where(
        Tracker.user_id == user_id,
        func.lower(Tracker.name) == name.lower(),
    )
    if active_only:
        stmt = stmt.where(Tracker.active == True)  # noqa: E712
    result = await session.execute(stmt)
    tracker = result.scalar_one_or_none()
    if tracker:
        return tracker

    # Try partial match (contains, case-insensitive)
    stmt = select(Tracker).where(
        Tracker.user_id == user_id,
        func.lower(Tracker.name).contains(name.lower()),
    )
    if active_only:
        stmt = stmt.where(Tracker.active == True)  # noqa: E712
    result = await session.execute(stmt)
    trackers = list(result.scalars().all())

    if len(trackers) == 1:
        return trackers[0]
    return None


async def _get_today_checkin(
    session: AsyncSession, user_id: int, tracker_id: int
) -> Optional[CheckIn]:
    """Get today's check-in for a tracker."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(CheckIn).where(
            CheckIn.user_id == user_id,
            CheckIn.tracker_id == tracker_id,
            CheckIn.created_at >= today_start,
        )
    )
    return result.scalar_one_or_none()


async def _get_streak(session: AsyncSession, user_id: int, tracker_id: int) -> int:
    """Calculate current streak for a tracker."""
    result = await session.execute(
        select(CheckIn)
        .where(
            CheckIn.user_id == user_id,
            CheckIn.tracker_id == tracker_id,
            CheckIn.status.in_(["completed", "partial"]),
        )
        .order_by(CheckIn.created_at.desc())
    )
    check_ins = list(result.scalars().all())

    if not check_ins:
        return 0

    streak = 0
    current_date = datetime.now().date()

    for check_in in check_ins:
        check_in_date = check_in.created_at.date()
        if check_in_date == current_date:
            streak += 1
            current_date -= timedelta(days=1)
        elif check_in_date < current_date:
            break

    return streak


async def _get_best_streak(session: AsyncSession, user_id: int, tracker_id: int) -> int:
    """Calculate best streak ever for a tracker."""
    result = await session.execute(
        select(CheckIn)
        .where(
            CheckIn.user_id == user_id,
            CheckIn.tracker_id == tracker_id,
            CheckIn.status.in_(["completed", "partial"]),
        )
        .order_by(CheckIn.created_at.asc())
    )
    check_ins = list(result.scalars().all())

    if not check_ins:
        return 0

    best = 0
    current = 1

    for i in range(1, len(check_ins)):
        prev_date = check_ins[i - 1].created_at.date()
        curr_date = check_ins[i].created_at.date()

        if curr_date == prev_date:
            continue  # Same day, skip
        elif curr_date == prev_date + timedelta(days=1):
            current += 1
        else:
            best = max(best, current)
            current = 1

    return max(best, current)


async def _get_completion_rate(
    session: AsyncSession, user_id: int, tracker_id: int, days: int
) -> float:
    """Calculate completion rate over last N days."""
    start_date = datetime.now() - timedelta(days=days)
    result = await session.execute(
        select(func.count(CheckIn.id)).where(
            CheckIn.user_id == user_id,
            CheckIn.tracker_id == tracker_id,
            CheckIn.status == "completed",
            CheckIn.created_at >= start_date,
        )
    )
    completed = result.scalar() or 0

    if days == 0:
        return 0.0
    return min(completed / days, 1.0)


def _streak_grid(check_ins: List[CheckIn], days: int = 7) -> str:
    """Generate visual streak grid for last N days."""
    today = datetime.now().date()
    status_by_date = {}

    for ci in check_ins:
        d = ci.created_at.date()
        if d not in status_by_date or ci.status == "completed":
            status_by_date[d] = ci.status

    grid = ""
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        status = status_by_date.get(d)
        if status == "completed":
            grid += "🟩"
        elif status == "skipped":
            grid += "🟨"
        elif status == "partial":
            grid += "🟧"
        else:
            grid += "⬜"
    return grid


async def _ensure_user_settings(session: AsyncSession, user_id: int) -> UserSettings:
    """Ensure UserSettings exists for user, create if not."""
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user_id)
        session.add(settings)
        await session.flush()
    return settings


async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /track command with subcommands."""
    user = update.effective_user
    if not user:
        return

    text = update.message.text if update.message else ""
    parts = text.split(None, 2) if text else []
    command = parts[0] if parts else "/track"
    args = parts[1:] if len(parts) > 1 else []

    # Parse subcommand from /track:sub format
    if ":" in command:
        sub = command.split(":", 1)[1].lower()
    elif args:
        # Check if first arg is a subcommand
        if args[0].lower() in ("add", "list", "done", "skip", "remove", "help"):
            sub = args[0].lower()
            args = args[1:] if len(args) > 1 else []
            # Re-parse remaining args from original text
            remaining = text.split(None, 2)
            args_text = remaining[2] if len(remaining) > 2 else ""
            args = args_text.split(None, 1) if args_text else []
        else:
            sub = "overview"
    else:
        sub = "overview"

    logger.info(f"Track command: sub={sub}, args={args}, user={user.id}")

    if sub == "overview":
        await _track_overview(update, user.id)
    elif sub == "add":
        # Parse: /track:add <type> <name> OR /track:add <name> (default: habit)
        raw_args = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        # Remove subcommand if present as separate word
        if raw_args.lower().startswith("add "):
            raw_args = raw_args[4:].strip()
        await _track_add(update, user.id, raw_args)
    elif sub == "done":
        name = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        if name.lower().startswith("done "):
            name = name[5:].strip()
        await _track_done(update, user.id, name)
    elif sub == "skip":
        name = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        if name.lower().startswith("skip "):
            name = name[5:].strip()
        await _track_skip(update, user.id, name)
    elif sub == "list":
        await _track_list(update, user.id)
    elif sub == "remove":
        name = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        if name.lower().startswith("remove "):
            name = name[7:].strip()
        await _track_remove(update, user.id, name)
    elif sub == "help":
        await _track_help(update)
    else:
        await _track_help(update)


async def _track_overview(update: Update, user_id: int) -> None:
    """Show active trackers with today's status."""
    locale = get_user_locale_from_update(update)
    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker)
            .where(
                Tracker.user_id == user_id,
                Tracker.active == True,  # noqa: E712
            )
            .order_by(Tracker.type, Tracker.name)
        )
        trackers = list(result.scalars().all())

        if not trackers:
            msg = (
                "📊 <b>Accountability Tracker</b>\n\n"
                "No active trackers yet.\n\n"
                "Get started:\n"
                "<code>/track:add habit Exercise</code>\n"
                "<code>/track:add medication Vitamins</code>\n"
                "<code>/track:add commitment Read 30min</code>\n\n"
                "Type <code>/track:help</code> for all commands."
            )
            if update.message:
                await update.message.reply_text(msg, parse_mode="HTML")
            return

        lines = ["📊 <b>Today's Trackers</b>\n"]

        current_type = None
        for tracker in trackers:
            if tracker.type != current_type:
                current_type = tracker.type
                emoji = TYPE_EMOJI.get(tracker.type, "📋")
                lines.append(f"\n{emoji} <b>{tracker.type.title()}s</b>")

            checkin = await _get_today_checkin(session, user_id, tracker.id)
            status = checkin.status if checkin else None
            status_icon = STATUS_EMOJI.get(status, "⬜")
            streak = await _get_streak(session, user_id, tracker.id)
            streak_text = f" 🔥{streak}" if streak > 0 else ""

            lines.append(f"  {status_icon} {tracker.name}{streak_text}")

        # Add quick action buttons
        keyboard = []
        unchecked = []
        for tracker in trackers:
            checkin = await _get_today_checkin(session, user_id, tracker.id)
            if not checkin:
                unchecked.append(tracker)

        if unchecked:
            lines.append("\n<i>Tap to check in:</i>")
            row = []
            for tr in unchecked[:4]:  # Max 4 buttons per row
                row.append(
                    InlineKeyboardButton(
                        f"✅ {tr.name}",
                        callback_data=f"track_done:{tr.id}",
                    )
                )
            keyboard.append(row)

            if len(unchecked) > 4:
                row2 = []
                for tr in unchecked[4:8]:
                    row2.append(
                        InlineKeyboardButton(
                            f"✅ {tr.name}",
                            callback_data=f"track_done:{tr.id}",
                        )
                    )
                keyboard.append(row2)

        keyboard.append(
            [
                InlineKeyboardButton(
                    t("inline.tracker.streaks", locale),
                    callback_data="track_streaks",
                ),
                InlineKeyboardButton(
                    t("inline.tracker.add", locale),
                    callback_data="track_add_menu",
                ),
            ]
        )

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    if update.message:
        await update.message.reply_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=reply_markup
        )


async def _track_add(update: Update, user_id: int, args_text: str) -> None:
    """Add a new tracker."""
    if not args_text.strip():
        msg = (
            "➕ <b>Add Tracker</b>\n\n"
            "Usage: <code>/track:add [type] name</code>\n\n"
            "Types: habit, medication, value, commitment\n"
            "Default type: habit\n\n"
            "Examples:\n"
            "<code>/track:add habit Exercise</code>\n"
            "<code>/track:add medication Vitamins</code>\n"
            "<code>/track:add Read 30 min</code>"
        )
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML")
        return

    # Parse type and name
    words = args_text.strip().split(None, 1)
    if words[0].lower() in TRACKER_TYPES:
        tracker_type = words[0].lower()
        name = words[1] if len(words) > 1 else ""
    else:
        tracker_type = "habit"
        name = args_text.strip()

    if not name:
        if update.message:
            await update.message.reply_text(
                "Please provide a name for the tracker.\n"
                "Example: <code>/track:add habit Exercise</code>",
                parse_mode="HTML",
            )
        return

    async with get_db_session() as session:
        # Ensure user settings exist
        await _ensure_user_settings(session, user_id)

        # Check for duplicate
        existing = await _find_tracker(session, user_id, name)
        if existing:
            if update.message:
                await update.message.reply_text(
                    f"Tracker <b>{existing.name}</b> already exists.\n"
                    f"Type: {TYPE_EMOJI.get(existing.type, '📋')} {existing.type}",
                    parse_mode="HTML",
                )
            return

        # Create tracker
        tracker = Tracker(
            user_id=user_id,
            type=tracker_type,
            name=name,
            check_frequency="daily",
            active=True,
        )
        session.add(tracker)
        await session.commit()

        emoji = TYPE_EMOJI.get(tracker_type, "📋")
        msg = (
            f"✅ <b>Tracker Created</b>\n\n"
            f"{emoji} <b>{name}</b>\n"
            f"Type: {tracker_type}\n"
            f"Frequency: daily\n\n"
            f"Check in with: <code>/track:done {name}</code>"
        )
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML")


async def _maybe_celebrate_milestone(
    bot, chat_id: int, user_id: int, tracker_id: int, streak: int
) -> None:
    """Send voice celebration if accountability partner is enabled."""
    try:
        async with get_db_session() as session:
            chat_obj = await get_chat_by_telegram_id(session, chat_id)
            if not chat_obj or not chat_obj.accountability_enabled:
                return

        from ...services.accountability_service import AccountabilityService

        result = await AccountabilityService.celebrate_milestone(
            user_id, tracker_id, streak
        )
        if result:
            _text, audio = result
            await bot.send_voice(chat_id=chat_id, voice=audio)
    except Exception as e:
        logger.error(f"Voice celebration failed for user {user_id}: {e}")


async def _track_done(update: Update, user_id: int, name: str) -> None:
    """Mark tracker as completed for today."""
    if not name.strip():
        if update.message:
            await update.message.reply_text(
                "Usage: <code>/track:done tracker name</code>",
                parse_mode="HTML",
            )
        return

    async with get_db_session() as session:
        tracker = await _find_tracker(session, user_id, name.strip())
        if not tracker:
            if update.message:
                await update.message.reply_text(
                    f"Tracker not found: <b>{name}</b>\n"
                    f"Use <code>/track:list</code> to see your trackers.",
                    parse_mode="HTML",
                )
            return

        # Check if already done today
        existing = await _get_today_checkin(session, user_id, tracker.id)
        if existing and existing.status == "completed":
            streak = await _get_streak(session, user_id, tracker.id)
            if update.message:
                await update.message.reply_text(
                    f"Already checked in for <b>{tracker.name}</b> today! ✅\n"
                    f"🔥 Current streak: {streak} days",
                    parse_mode="HTML",
                )
            return

        # Create or update check-in
        if existing:
            existing.status = "completed"
        else:
            checkin = CheckIn(
                user_id=user_id,
                tracker_id=tracker.id,
                status="completed",
            )
            session.add(checkin)

        await session.commit()

        streak = await _get_streak(session, user_id, tracker.id)
        emoji = TYPE_EMOJI.get(tracker.type, "📋")

        # Check milestones
        milestones = [3, 7, 14, 30, 60, 90, 180, 365]
        milestone_msg = ""
        if streak in milestones:
            milestone_msg = f"\n\n🎉 <b>Milestone: {streak} days!</b> Amazing work!"
            # Fire voice celebration in background
            chat = update.effective_chat
            if chat:
                create_tracked_task(
                    _maybe_celebrate_milestone(
                        update.get_bot(),
                        chat.id,
                        user_id,
                        tracker.id,
                        streak,
                    ),
                    name=f"celebrate_{tracker.name}_{streak}",
                )

        msg = (
            f"{emoji} <b>{tracker.name}</b> — Done! ✅\n"
            f"🔥 Streak: {streak} days{milestone_msg}"
        )
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML")


async def _track_skip(update: Update, user_id: int, name: str) -> None:
    """Mark tracker as skipped for today."""
    if not name.strip():
        if update.message:
            await update.message.reply_text(
                "Usage: <code>/track:skip tracker name</code>",
                parse_mode="HTML",
            )
        return

    async with get_db_session() as session:
        tracker = await _find_tracker(session, user_id, name.strip())
        if not tracker:
            if update.message:
                await update.message.reply_text(
                    f"Tracker not found: <b>{name}</b>",
                    parse_mode="HTML",
                )
            return

        existing = await _get_today_checkin(session, user_id, tracker.id)
        if existing:
            existing.status = "skipped"
        else:
            checkin = CheckIn(
                user_id=user_id,
                tracker_id=tracker.id,
                status="skipped",
            )
            session.add(checkin)

        await session.commit()

        msg = f"⏭ <b>{tracker.name}</b> — Skipped for today"
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML")


async def _track_list(update: Update, user_id: int) -> None:
    """List all trackers (active + archived)."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker)
            .where(Tracker.user_id == user_id)
            .order_by(Tracker.active.desc(), Tracker.type, Tracker.name)
        )
        trackers = list(result.scalars().all())

        if not trackers:
            if update.message:
                await update.message.reply_text(
                    "No trackers found. Create one:\n"
                    "<code>/track:add habit Exercise</code>",
                    parse_mode="HTML",
                )
            return

        lines = ["📋 <b>All Trackers</b>\n"]
        active = [tr for tr in trackers if tr.active]
        archived = [tr for tr in trackers if not tr.active]

        if active:
            lines.append("<b>Active:</b>")
            for tr in active:
                emoji = TYPE_EMOJI.get(tr.type, "📋")
                streak = await _get_streak(session, user_id, tr.id)
                streak_text = f" 🔥{streak}" if streak > 0 else ""
                freq = tr.check_frequency or "daily"
                lines.append(
                    f"  {emoji} <b>{tr.name}</b> ({tr.type}, {freq}){streak_text}"
                )

        if archived:
            lines.append("\n<b>Archived:</b>")
            for tr in archived:
                emoji = TYPE_EMOJI.get(tr.type, "📋")
                lines.append(f"  {emoji} <s>{tr.name}</s> ({tr.type})")

        if update.message:
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _track_remove(update: Update, user_id: int, name: str) -> None:
    """Archive (soft-delete) a tracker."""
    if not name.strip():
        if update.message:
            await update.message.reply_text(
                "Usage: <code>/track:remove tracker name</code>",
                parse_mode="HTML",
            )
        return

    async with get_db_session() as session:
        tracker = await _find_tracker(session, user_id, name.strip())
        if not tracker:
            if update.message:
                await update.message.reply_text(
                    f"Tracker not found: <b>{name}</b>",
                    parse_mode="HTML",
                )
            return

        tracker.active = False
        await session.commit()

        msg = (
            f"🗑 <b>{tracker.name}</b> archived.\n\n"
            f"Your check-in history is preserved.\n"
            f"It will appear in <code>/track:list</code> under Archived."
        )
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML")


async def _track_help(update: Update) -> None:
    """Show track command help."""
    msg = (
        "📊 <b>Accountability Tracker</b>\n\n"
        "<b>Commands:</b>\n"
        "<code>/track</code> — Today's overview\n"
        "<code>/track:add [type] name</code> — Create tracker\n"
        "<code>/track:done name</code> — Mark as done\n"
        "<code>/track:skip name</code> — Skip today\n"
        "<code>/track:list</code> — All trackers\n"
        "<code>/track:remove name</code> — Archive tracker\n"
        "<code>/streak</code> — Streak dashboard\n\n"
        "<b>Types:</b> habit, medication, value, commitment\n\n"
        "<b>Examples:</b>\n"
        "<code>/track:add habit Exercise</code>\n"
        "<code>/track:add medication Vitamins</code>\n"
        "<code>/track:done Exercise</code>\n"
        "<code>/streak</code>"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="HTML")


async def streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /streak command — visual streak dashboard."""
    user = update.effective_user
    if not user:
        return

    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker)
            .where(
                Tracker.user_id == user.id,
                Tracker.active == True,  # noqa: E712
            )
            .order_by(Tracker.type, Tracker.name)
        )
        trackers = list(result.scalars().all())

        if not trackers:
            if update.message:
                await update.message.reply_text(
                    "📈 <b>Streak Dashboard</b>\n\n"
                    "No trackers yet. Use <code>/track:add</code> to start!",
                    parse_mode="HTML",
                )
            return

        lines = ["📈 <b>Streak Dashboard</b>\n"]
        total_streak = 0
        total_rate_7 = 0.0

        for tracker in trackers:
            emoji = TYPE_EMOJI.get(tracker.type, "📋")
            streak = await _get_streak(session, user.id, tracker.id)
            best = await _get_best_streak(session, user.id, tracker.id)
            rate_7 = await _get_completion_rate(session, user.id, tracker.id, 7)
            rate_30 = await _get_completion_rate(session, user.id, tracker.id, 30)

            total_streak += streak
            total_rate_7 += rate_7

            # Get last 7 days of check-ins for grid
            week_ago = datetime.now() - timedelta(days=7)
            result = await session.execute(
                select(CheckIn).where(
                    CheckIn.user_id == user.id,
                    CheckIn.tracker_id == tracker.id,
                    CheckIn.created_at >= week_ago,
                )
            )
            recent_checkins = list(result.scalars().all())
            grid = _streak_grid(recent_checkins, 7)

            lines.append(f"\n{emoji} <b>{tracker.name}</b>")
            lines.append(f"  {grid}")
            lines.append(f"  🔥 Streak: {streak} days (best: {best})")
            lines.append(f"  7d: {rate_7:.0%} | 30d: {rate_30:.0%}")

        # Overall summary
        avg_rate = total_rate_7 / len(trackers) if trackers else 0
        lines.append(f"\n{'─' * 20}")
        lines.append(f"📊 <b>Overall</b>: {avg_rate:.0%} (7-day avg)")

        # Encouragement based on performance
        if avg_rate >= 0.9:
            lines.append("🌟 Outstanding consistency!")
        elif avg_rate >= 0.7:
            lines.append("💪 Great work, keep it up!")
        elif avg_rate >= 0.5:
            lines.append("📈 Making progress!")
        elif avg_rate > 0:
            lines.append("🌱 Every day is a new opportunity.")
        else:
            lines.append("🆕 Start checking in to build streaks!")

        if update.message:
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def handle_track_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Route tracker callback queries to appropriate handlers.

    IMPORTANT: This handler manages its own query.answer() calls.
    The parent callback_handlers.py must NOT pre-answer the query.
    """
    query = update.callback_query
    user = update.effective_user

    if not query or not user:
        return

    locale = get_user_locale_from_update(update)

    if data.startswith("track_done:"):
        tracker_id = int(data.split(":")[1])
        await _handle_inline_done(query, user.id, tracker_id, locale=locale)

    elif data == "track_streaks":
        await query.answer()
        # Show streak dashboard inline
        await streak_command(update, context)

    elif data == "track_add_menu":
        await query.answer()
        msg = (
            "➕ <b>Add Tracker</b>\n\n"
            "Send a command:\n"
            "<code>/track:add habit Exercise</code>\n"
            "<code>/track:add medication Vitamins</code>\n"
            "<code>/track:add value Gratitude</code>\n"
            "<code>/track:add commitment Read 30min</code>"
        )
        await query.message.reply_text(msg, parse_mode="HTML")

    elif data.startswith("track_skip:"):
        tracker_id = int(data.split(":")[1])
        await _handle_inline_skip(query, user.id, tracker_id)

    elif data.startswith("checkin_done:"):
        tracker_id = int(data.split(":")[1])
        await _handle_inline_done(query, user.id, tracker_id, locale=locale)

    elif data.startswith("checkin_skip:"):
        tracker_id = int(data.split(":")[1])
        await _handle_inline_skip(query, user.id, tracker_id)

    elif data.startswith("checkin_note:"):
        tracker_id = int(data.split(":")[1])
        await query.answer("Send a note as your next message (coming soon)")

    else:
        await query.answer()
        logger.warning(f"Unknown track callback: {data}")


async def _handle_inline_done(
    query, user_id: int, tracker_id: int, locale: Optional[str] = None
) -> None:
    """Handle inline ✅ Done button press."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker).where(Tracker.id == tracker_id, Tracker.user_id == user_id)
        )
        tracker = result.scalar_one_or_none()

        if not tracker:
            await query.answer("Tracker not found", show_alert=True)
            return

        existing = await _get_today_checkin(session, user_id, tracker_id)
        if existing and existing.status == "completed":
            streak = await _get_streak(session, user_id, tracker_id)
            await query.answer(f"Already done! 🔥 {streak}-day streak", show_alert=True)
            return

        if existing:
            existing.status = "completed"
        else:
            checkin = CheckIn(
                user_id=user_id,
                tracker_id=tracker_id,
                status="completed",
            )
            session.add(checkin)

        await session.commit()
        streak = await _get_streak(session, user_id, tracker_id)

        # Check milestones
        milestones = [3, 7, 14, 30, 60, 90, 180, 365]
        if streak in milestones:
            await query.answer(
                f"🎉 {streak}-day milestone for {tracker.name}!", show_alert=True
            )
            # Fire voice celebration in background
            create_tracked_task(
                _maybe_celebrate_milestone(
                    query.get_bot(),
                    query.message.chat_id,
                    user_id,
                    tracker_id,
                    streak,
                ),
                name=f"celebrate_{tracker.name}_{streak}",
            )
        else:
            await query.answer(f"✅ {tracker.name} — 🔥 {streak} days")

        # Update the overview message
        try:
            # Re-render overview
            result = await session.execute(
                select(Tracker)
                .where(
                    Tracker.user_id == user_id,
                    Tracker.active == True,  # noqa: E712
                )
                .order_by(Tracker.type, Tracker.name)
            )
            trackers = list(result.scalars().all())

            lines = ["📊 <b>Today's Trackers</b>\n"]
            current_type = None
            unchecked = []

            for tr in trackers:
                if tr.type != current_type:
                    current_type = tr.type
                    emoji = TYPE_EMOJI.get(tr.type, "📋")
                    lines.append(f"\n{emoji} <b>{tr.type.title()}s</b>")

                ci = await _get_today_checkin(session, user_id, tr.id)
                status = ci.status if ci else None
                status_icon = STATUS_EMOJI.get(status, "⬜")
                s = await _get_streak(session, user_id, tr.id)
                streak_text = f" 🔥{s}" if s > 0 else ""
                lines.append(f"  {status_icon} {tr.name}{streak_text}")

                if not ci:
                    unchecked.append(tr)

            keyboard = []
            if unchecked:
                lines.append("\n<i>Tap to check in:</i>")
                row = []
                for tr in unchecked[:4]:
                    row.append(
                        InlineKeyboardButton(
                            f"✅ {tr.name}",
                            callback_data=f"track_done:{tr.id}",
                        )
                    )
                keyboard.append(row)

            keyboard.append(
                [
                    InlineKeyboardButton(
                        t("inline.tracker.streaks", locale),
                        callback_data="track_streaks",
                    ),
                    InlineKeyboardButton(
                        t("inline.tracker.add", locale),
                        callback_data="track_add_menu",
                    ),
                ]
            )

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "\n".join(lines), parse_mode="HTML", reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error updating track overview: {e}")


async def _handle_inline_skip(query, user_id: int, tracker_id: int) -> None:
    """Handle inline ⏭ Skip button press."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Tracker).where(Tracker.id == tracker_id, Tracker.user_id == user_id)
        )
        tracker = result.scalar_one_or_none()

        if not tracker:
            await query.answer("Tracker not found", show_alert=True)
            return

        existing = await _get_today_checkin(session, user_id, tracker_id)
        if existing:
            existing.status = "skipped"
        else:
            checkin = CheckIn(
                user_id=user_id,
                tracker_id=tracker_id,
                status="skipped",
            )
            session.add(checkin)

        await session.commit()
        await query.answer(f"⏭ {tracker.name} skipped")


def register_accountability_handlers(application) -> None:
    """Register accountability command handlers with the application."""
    from telegram.ext import CommandHandler

    application.add_handler(CommandHandler("track", track_command))
    application.add_handler(CommandHandler("streak", streak_command))
