"""
Data retention enforcement service.

Periodically deletes records older than each user's configured retention period.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from ..core.database import get_db_session
from ..models.chat import Chat
from ..models.collect_session import CollectSession
from ..models.image import Image
from ..models.message import Message
from ..models.poll_response import PollResponse
from ..models.tracker import CheckIn
from ..models.user_settings import UserSettings

logger = logging.getLogger(__name__)

# Mapping from retention setting to timedelta
RETENTION_PERIODS = {
    "1_month": timedelta(days=30),
    "6_months": timedelta(days=180),
    "1_year": timedelta(days=365),
    "forever": None,  # No deletion
}


async def enforce_data_retention() -> dict:
    """
    Delete records older than each user's retention setting.

    Returns dict of {user_id: deleted_count} for users with deletions.
    """
    results = {}

    try:
        async with get_db_session() as session:
            # Get all users with their retention settings
            stmt = select(UserSettings).where(UserSettings.data_retention != "forever")
            result = await session.execute(stmt)
            settings_list = result.scalars().all()

            for settings in settings_list:
                period = RETENTION_PERIODS.get(settings.data_retention)
                if period is None:
                    continue

                cutoff = datetime.utcnow() - period
                user_id = settings.user_id
                total_deleted = 0

                # Subqueries for user's chats - two ID spaces:
                # Chat.id = database PK (used by Message.chat_id via FK)
                # Chat.chat_id = Telegram chat ID (used by PollResponse.chat_id)
                user_db_chat_ids = select(Chat.id).where(
                    Chat.user_id == user_id
                )
                user_telegram_chat_ids = select(Chat.chat_id).where(
                    Chat.user_id == user_id
                )

                # Delete old messages scoped to this user's chats
                # Message.chat_id is FK to chats.id (database PK)
                result = await session.execute(
                    delete(Message).where(
                        Message.chat_id.in_(user_db_chat_ids),
                        Message.created_at < cutoff,
                    )
                )
                total_deleted += result.rowcount

                # Delete old check-ins
                result = await session.execute(
                    delete(CheckIn).where(
                        CheckIn.user_id == user_id,
                        CheckIn.created_at < cutoff,
                    )
                )
                total_deleted += result.rowcount

                # Delete old poll responses scoped to this user's chats
                # PollResponse.chat_id stores Telegram chat IDs (no FK)
                result = await session.execute(
                    delete(PollResponse).where(
                        PollResponse.chat_id.in_(user_telegram_chat_ids),
                        PollResponse.created_at < cutoff,
                    )
                )
                total_deleted += result.rowcount

                if total_deleted > 0:
                    results[user_id] = total_deleted
                    logger.info(
                        f"Data retention: deleted {total_deleted} records for user {user_id} "
                        f"(retention={settings.data_retention}, cutoff={cutoff.isoformat()})"
                    )

            await session.commit()

    except Exception as e:
        logger.error(f"Data retention enforcement failed: {e}", exc_info=True)

    return results


async def run_periodic_retention(interval_hours: float = 24.0) -> None:
    """Run data retention enforcement periodically."""
    logger.info(f"Starting periodic data retention (every {interval_hours}h)")
    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            results = await enforce_data_retention()
            if results:
                total = sum(results.values())
                logger.info(
                    f"Data retention cycle complete: {total} records deleted "
                    f"for {len(results)} users"
                )
            else:
                logger.debug("Data retention cycle: no records to delete")
        except asyncio.CancelledError:
            logger.info("Periodic data retention task cancelled")
            break
        except Exception as e:
            logger.error(f"Data retention cycle error: {e}", exc_info=True)
