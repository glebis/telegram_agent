"""
Enhanced health endpoint for observability.

Returns structured health info: uptime, version, database connectivity,
and bot status. Lightweight and requires no authentication.
"""

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Start time for uptime calculation
_start_time: float = time.monotonic()


def set_start_time() -> None:
    """Reset the start time (called during app startup)."""
    global _start_time
    _start_time = time.monotonic()


def get_uptime_seconds() -> float:
    """Return seconds since the process started."""
    return time.monotonic() - _start_time


async def check_database_health() -> bool:
    """Check database connectivity.

    Returns True if database is reachable, False otherwise.
    """
    try:
        from ..core.database import health_check

        return await health_check()
    except Exception as e:
        logger.warning("Database health check failed: %s", e)
        return False


def _get_version() -> str:
    """Get the application version string."""
    try:
        from ..version import __version__

        return __version__
    except Exception:
        return "unknown"


def _is_bot_initialized() -> bool:
    """Check if the bot is fully initialized."""
    try:
        from ..main import is_bot_initialized

        return is_bot_initialized()
    except Exception:
        return False


def create_health_router() -> APIRouter:
    """Create and return the health check router.

    This is a factory so the router can be included in the main app
    or used standalone in tests.
    """
    router = APIRouter()

    @router.get("/health")
    async def health_endpoint() -> Dict[str, Any]:
        """Lightweight health check endpoint (no auth required).

        Returns:
            JSON with status, uptime, version, database, and bot status.
        """
        db_healthy = await check_database_health()
        bot_initialized = _is_bot_initialized()

        # Determine status
        if not db_healthy:
            status = "degraded"
        elif not bot_initialized:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "service": "telegram-agent",
            "version": _get_version(),
            "uptime_seconds": round(get_uptime_seconds(), 2),
            "database": "connected" if db_healthy else "disconnected",
            "bot_initialized": bot_initialized,
        }

    return router
