"""Resource Monitor — fast-loop alert service for system resources.

Runs independently of the heartbeat scheduler. Checks CPU, memory, disk,
and database size every N minutes. Only sends alerts when thresholds are
breached, with per-resource cooldown to avoid alert spam.

Delivery via send_message_sync() (subprocess-isolated).

Opt-in via RESOURCE_MONITOR_CHAT_IDS env var (falls back to HEARTBEAT_CHAT_IDS).
If neither is set the monitor does not start.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from ..core.config import get_config_value
from ..utils.telegram_api import send_message_sync
from .heartbeat_service import CheckResult, get_heartbeat_service

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Monitors system resources and sends alerts when thresholds are breached."""

    def __init__(self, cooldown_minutes: int = 30) -> None:
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._last_alert: Dict[str, datetime] = {}

    def _should_alert(self, resource_name: str) -> bool:
        """Return True if enough time has passed since the last alert for this resource."""
        last = self._last_alert.get(resource_name)
        if last is None:
            return True
        return datetime.utcnow() - last >= self._cooldown

    def _record_alert(self, resource_name: str) -> None:
        """Record that an alert was sent for this resource now."""
        self._last_alert[resource_name] = datetime.utcnow()

    async def check_and_alert(self, chat_ids: List[int]) -> None:
        """Run resource checks and deliver alerts for any breached thresholds.

        Only fires for checks that are warning/critical AND not currently on
        cooldown. Updates cooldown timestamps after delivery.
        """
        service = get_heartbeat_service()

        # Run only the four resource-related checks (fast subset of Phase 1)
        raw = await asyncio.gather(
            service.check_memory(),
            service.check_cpu(),
            service.check_disk_space(),
            service.check_database_size(),
            return_exceptions=True,
        )

        alerts: List[CheckResult] = []
        for result in raw:
            if isinstance(result, BaseException):
                logger.warning("Resource check crashed: %s", result)
                continue
            assert isinstance(result, CheckResult)
            if result.status in ("warning", "critical"):
                if self._should_alert(result.name):
                    alerts.append(result)

        if not alerts:
            return

        msg = self._format_alert(alerts)
        for chat_id in chat_ids:
            try:
                send_message_sync(chat_id, msg, parse_mode="HTML")
                logger.info(
                    "Resource alert sent to chat %d: %s",
                    chat_id,
                    ", ".join(a.name for a in alerts),
                )
            except Exception as e:
                logger.error(
                    "Resource alert delivery failed for chat %d: %s", chat_id, e
                )

        for alert in alerts:
            self._record_alert(alert.name)

    @staticmethod
    def _format_alert(alerts: list) -> str:
        """Format a list of CheckResults as an HTML Telegram alert."""
        status_emoji = {"warning": "\u26a0\ufe0f", "critical": "\u274c"}
        lines = ["\u26a0\ufe0f <b>Resource Alert</b>", ""]
        for a in alerts:
            icon = status_emoji.get(a.status, "\u2753")
            lines.append(f"{icon} <b>{a.name}</b>: {a.message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chat ID resolution
# ---------------------------------------------------------------------------


def _get_chat_ids() -> List[int]:
    """Resolve chat IDs for resource alert delivery.

    Priority: RESOURCE_MONITOR_CHAT_IDS → HEARTBEAT_CHAT_IDS.
    Returns an empty list if neither variable is set (monitor disabled).
    """
    raw = os.getenv("RESOURCE_MONITOR_CHAT_IDS", "").strip()
    if not raw:
        raw = os.getenv("HEARTBEAT_CHAT_IDS", "").strip()
    if not raw:
        return []
    return [int(cid.strip()) for cid in raw.split(",") if cid.strip()]


# ---------------------------------------------------------------------------
# Periodic loop
# ---------------------------------------------------------------------------


async def run_periodic_resource_monitor(
    interval_minutes: float = 5.0,
    cooldown_minutes: int = 30,
) -> None:
    """Run the resource monitor in a continuous async loop.

    Follows the same pattern as run_periodic_tunnel_monitor / run_periodic_cleanup.
    Intended to be launched via create_tracked_task() at bot startup.

    Args:
        interval_minutes: How often to check resources (default: 5 min).
        cooldown_minutes: Minimum time between repeated alerts per resource.
    """
    chat_ids = _get_chat_ids()
    if not chat_ids:
        logger.info("Resource monitor disabled: no chat IDs configured")
        return

    logger.info(
        "Starting resource monitor (every %.0f min, cooldown %d min)",
        interval_minutes,
        cooldown_minutes,
    )

    monitor = ResourceMonitor(cooldown_minutes=cooldown_minutes)

    # Brief initial delay to let the system settle after startup
    await asyncio.sleep(180)

    while True:
        try:
            # Reuse heartbeat active-hours gate so alerts don't wake you up at 3am
            hour_start = get_config_value("heartbeat.active_hours_start", 8)
            hour_end = get_config_value("heartbeat.active_hours_end", 23)
            now_hour = datetime.now().hour

            if hour_start <= now_hour < hour_end:
                await monitor.check_and_alert(chat_ids)
            else:
                logger.debug(
                    "Resource monitor skipped: outside active hours (%d-%d, now=%d)",
                    hour_start,
                    hour_end,
                    now_hour,
                )

            await asyncio.sleep(interval_minutes * 60)

        except asyncio.CancelledError:
            logger.info("Resource monitor task cancelled")
            break
        except Exception as e:
            logger.error("Resource monitor error: %s", e, exc_info=True)
            await asyncio.sleep(interval_minutes * 60)
