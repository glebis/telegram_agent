"""
Stale Claude session cleanup service (Issue #45).

Periodically deactivates Claude sessions that have been inactive beyond
a configurable threshold, preventing unbounded accumulation of active
sessions in the claude_sessions table.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from ..core.database import get_db_session
from ..models.claude_session import ClaudeSession

logger = logging.getLogger(__name__)


async def cleanup_stale_sessions(max_age_days: int = 7) -> int:
    """
    Deactivate Claude sessions that have been inactive for too long.

    A session is considered stale if:
    - is_active is True, AND
    - last_used < (now - max_age_days), OR
    - last_used is NULL and updated_at < (now - max_age_days)

    Args:
        max_age_days: Sessions inactive for more than this many days
                      are deactivated. Default: 7.

    Returns:
        Number of sessions deactivated.
    """
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    deactivated = 0

    try:
        async with get_db_session() as session:
            # Find active sessions with last_used before the cutoff,
            # or sessions where last_used is NULL but updated_at is stale.
            # We fetch and iterate (rather than bulk UPDATE) so we can
            # handle the NULL last_used fallback in Python.
            stmt = select(ClaudeSession).where(
                ClaudeSession.is_active == True,  # noqa: E712
            )
            result = await session.execute(stmt)
            active_sessions = result.scalars().all()

            for sess in active_sessions:
                # Determine the effective "last activity" timestamp
                effective_time = sess.last_used or sess.updated_at or sess.created_at

                if effective_time and effective_time < cutoff:
                    sess.is_active = False
                    deactivated += 1

            if deactivated > 0:
                await session.commit()
                logger.info(
                    f"Session cleanup: deactivated {deactivated} stale session(s) "
                    f"(inactive for >{max_age_days} days, cutoff={cutoff.isoformat()})"
                )
            else:
                logger.debug("Session cleanup: no stale sessions found")

    except Exception as e:
        logger.error(f"Session cleanup failed: {e}", exc_info=True)

    return deactivated


async def run_periodic_session_cleanup(
    interval_hours: float = 1.0,
    max_age_days: int = 7,
) -> None:
    """
    Run stale session cleanup periodically.

    Runs once immediately on startup, then repeats every interval_hours.

    Args:
        interval_hours: How often to run cleanup (default: every hour).
        max_age_days: Sessions older than this are deactivated (default: 7 days).
    """
    logger.info(
        f"Starting periodic session cleanup "
        f"(every {interval_hours}h, max_age={max_age_days}d)"
    )
    while True:
        try:
            count = await cleanup_stale_sessions(max_age_days=max_age_days)
            if count > 0:
                logger.info(
                    f"Periodic session cleanup complete: "
                    f"{count} session(s) deactivated"
                )
        except asyncio.CancelledError:
            logger.info("Periodic session cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Periodic session cleanup error: {e}", exc_info=True)

        try:
            await asyncio.sleep(interval_hours * 3600)
        except asyncio.CancelledError:
            logger.info("Periodic session cleanup task cancelled")
            break
