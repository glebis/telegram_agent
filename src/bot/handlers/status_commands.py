"""
/status command — admin-only bot health diagnostics.

Returns a compact, mobile-friendly summary of bot health:
uptime, DB, webhook, CPU/memory/disk, recent errors.
"""

import logging
import re
from typing import Any, Dict, Optional

from telegram import Update
from telegram.ext import ContextTypes

from ...api.health import (
    _get_version,
    _is_bot_initialized,
    check_database_health,
    get_uptime_seconds,
)
from ...core.authorization import AuthTier, require_tier
from ...services.heartbeat_service import get_heartbeat_service
from ...utils.error_reporting import handle_errors

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Uptime formatting
# ---------------------------------------------------------------------------


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into a human-readable string."""
    total_minutes = int(seconds // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours >= 24:
        days = hours // 24
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours}h"

    return f"{hours}h {minutes}m"


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def _parse_disk_free(message: str) -> Optional[float]:
    """Extract free GB from a disk_space message like '55% used, 120GB free'."""
    match = re.search(r"([\d.]+)GB free", message)
    if match:
        return float(match.group(1))
    return None


async def _collect_status_data() -> Dict[str, Any]:
    """Collect status data from health checks and heartbeat service.

    Returns a dict with all fields needed for formatting.
    Handles individual check failures gracefully.
    """
    # Core health (fast, local)
    db_healthy = await check_database_health()
    bot_init = _is_bot_initialized()
    version = _get_version()
    uptime_secs = get_uptime_seconds()

    # Resource checks via heartbeat service
    service = get_heartbeat_service()

    memory_pct = None
    cpu_pct = None
    disk_pct = None
    disk_free_gb = None
    webhook_ok = True
    webhook_pending = 0
    recent_errors = 0
    error_window_hours = 6

    # Run resource checks individually to isolate failures
    try:
        mem_result = await service.check_memory()
        memory_pct = mem_result.value
    except Exception:
        logger.warning("Status: memory check failed")

    try:
        cpu_result = await service.check_cpu()
        cpu_pct = cpu_result.value
    except Exception:
        logger.warning("Status: CPU check failed")

    try:
        disk_result = await service.check_disk_space()
        disk_pct = disk_result.value
        disk_free_gb = _parse_disk_free(disk_result.message)
    except Exception:
        logger.warning("Status: disk check failed")

    try:
        webhook_result = await service.check_webhook()
        webhook_ok = webhook_result.status == "ok"
        webhook_pending = webhook_result.value or 0
    except Exception:
        logger.warning("Status: webhook check failed")
        webhook_ok = False

    try:
        error_result = await service.check_recent_errors()
        recent_errors = error_result.value or 0
        # Parse window from message like "3 errors in last 6h"
        match = re.search(r"last (\d+)h", error_result.message)
        if match:
            error_window_hours = int(match.group(1))
    except Exception:
        logger.warning("Status: error count check failed")

    # Determine overall status
    if not db_healthy:
        status = "degraded"
    elif not bot_init:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "uptime": _format_uptime(uptime_secs),
        "version": version,
        "database": "connected" if db_healthy else "disconnected",
        "bot_initialized": bot_init,
        "memory_pct": memory_pct,
        "cpu_pct": cpu_pct,
        "disk_pct": disk_pct,
        "disk_free_gb": disk_free_gb,
        "webhook_ok": webhook_ok,
        "webhook_pending": webhook_pending,
        "recent_errors": recent_errors,
        "error_window_hours": error_window_hours,
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _fmt_pct(value: Optional[float]) -> str:
    """Format a percentage value, handling None."""
    if value is None:
        return "n/a"
    return f"{value}%"


def _format_status_message(data: Dict[str, Any]) -> str:
    """Format status data as compact HTML for Telegram mobile display."""
    status = data["status"].upper()
    status_icon = "\u2705" if status == "HEALTHY" else "\u26a0\ufe0f"

    db_icon = "\u2705" if data["database"] == "connected" else "\u274c"
    wh_icon = "\u2705" if data["webhook_ok"] else "\u26a0\ufe0f"

    # Memory/CPU warning thresholds for visual cue
    mem_str = _fmt_pct(data["memory_pct"])
    cpu_str = _fmt_pct(data["cpu_pct"])
    disk_str = _fmt_pct(data["disk_pct"])

    errors = data["recent_errors"]
    err_window = data["error_window_hours"]

    pending = data["webhook_pending"]
    pending_str = str(pending) if pending < 5 else f"\u26a0\ufe0f {pending}"

    disk_free = data.get("disk_free_gb")
    disk_detail = f" ({disk_free}GB free)" if disk_free else ""

    lines = [
        f"{status_icon} <b>Status: {status}</b>",
        "",
        "<pre>",
        f"Uptime    {data['uptime']}",
        f"Version   {data['version']}",
        "</pre>",
        "",
        f"{db_icon} DB: {data['database']}",
        f"{wh_icon} Webhook: "
        + ("ok" if data["webhook_ok"] else "issues")
        + (f" ({pending_str} pending)" if pending > 0 else ""),
        "",
        "<pre>",
        f"Memory    {mem_str}",
        f"CPU       {cpu_str}",
        f"Disk      {disk_str}{disk_detail}",
        f"Errors    {errors} (last {err_window}h)",
        "</pre>",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------


@require_tier(AuthTier.ADMIN)
@handle_errors("status_command")
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command — admin-only bot health snapshot."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    logger.info("Status command from user %d in chat %d", user.id, chat.id)

    data = await _collect_status_data()
    msg = _format_status_message(data)

    if update.message:
        await update.message.reply_text(msg, parse_mode="HTML")
