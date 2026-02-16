"""
Shared tracker query helpers.

Moved from bot/handlers/accountability_commands.py to the service layer
so that both handlers and services (e.g. accountability_scheduler) can
import them without creating a service→handler dependency.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tracker import CheckIn

TYPE_EMOJI = {
    "habit": "🔄",
    "medication": "💊",
    "value": "💎",
    "commitment": "🎯",
}


async def get_today_checkin(
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


async def get_streak(session: AsyncSession, user_id: int, tracker_id: int) -> int:
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
