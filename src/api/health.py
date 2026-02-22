"""
Enhanced health endpoint for observability.

Returns structured health info: uptime, version, database connectivity,
and bot status. Lightweight and requires no authentication.
"""

import logging
import time
from typing import Any, Dict, List

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


async def check_subsystem_health(subsystem: str) -> Dict[str, Any]:
    """Check health of a specific subsystem.

    Args:
        subsystem: Name of the subsystem ("database", "bot").

    Returns:
        Dict with "name" and "status" ("ok" or "error").
    """
    if subsystem == "database":
        healthy = await check_database_health()
        return {
            "name": "database",
            "status": "ok" if healthy else "error",
        }
    elif subsystem == "bot":
        initialized = _is_bot_initialized()
        return {
            "name": "bot",
            "status": "ok" if initialized else "error",
        }
    else:
        return {"name": subsystem, "status": "unknown"}


def _get_error_counts() -> Dict[str, int]:
    """Get error counts from the error reporting module if available."""
    try:
        from ..utils.error_reporting import get_error_counter

        counter = get_error_counter()
        return {k.value: v for k, v in counter.get_counts().items()}
    except ImportError:
        return {}


def _get_bot_status() -> tuple:
    """Get bot status and last error from BotInitState.

    Returns:
        (bot_status, last_error) tuple.
        bot_status is one of: "ok", "retrying", "initializing", "not_started".
    """
    try:
        from ..lifecycle import _bot_init_state

        state = _bot_init_state.state
        last_error = _bot_init_state.last_error
        status_map = {
            "initialized": "ok",
            "failed": "retrying",
            "initializing": "initializing",
            "not_started": "not_started",
        }
        return status_map.get(state, state), last_error
    except Exception:
        return "unknown", None


async def build_enriched_health() -> Dict[str, Any]:
    """Build enriched health payload with subsystem breakdown.

    Returns:
        Dict with status, subsystems list, error_details, and error_counts.
    """
    subsystems: List[Dict[str, Any]] = []
    error_details: Dict[str, str] = {}

    # Check each subsystem
    for name in ("database", "bot"):
        result = await check_subsystem_health(name)
        subsystems.append(result)
        if result["status"] == "error":
            error_details[name] = f"{name} check failed"

    # Overall status
    if error_details:
        status = "degraded"
    else:
        status = "healthy"

    bot_status, last_error = _get_bot_status()

    payload: Dict[str, Any] = {
        "status": status,
        "service": "telegram-agent",
        "version": _get_version(),
        "uptime_seconds": round(get_uptime_seconds(), 2),
        "bot_initialized": _is_bot_initialized(),
        "bot_status": bot_status,
        "subsystems": subsystems,
        "error_counts": _get_error_counts(),
    }

    if error_details:
        payload["error_details"] = error_details

    if last_error:
        payload["last_error"] = last_error

    return payload


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
