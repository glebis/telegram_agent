"""Health check alerting service.

Tracks consecutive health check failures and sends Telegram alerts
to the admin when failures exceed a threshold. Sends recovery alerts
when service returns to healthy after a failure sequence.

State is persisted to a JSON file so it survives process restarts.
Called from scripts/health_check.sh (runs outside the bot process).
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = "/tmp/telegram_agent_health_state.json"
DEFAULT_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 600  # 10 minutes


@dataclass
class HealthAlertState:
    """Tracks consecutive health check failures and alert history."""

    consecutive_failures: int = 0
    last_failure_reason: str = ""
    last_alert_time: float = 0.0
    first_failure_time: float = 0.0

    def record_failure(self, reason: str) -> None:
        """Record a health check failure."""
        if self.consecutive_failures == 0:
            self.first_failure_time = time.time()
        self.consecutive_failures += 1
        self.last_failure_reason = reason

    def record_recovery(self) -> None:
        """Reset state after successful health check."""
        self.consecutive_failures = 0
        self.last_failure_reason = ""
        self.first_failure_time = 0.0

    def should_alert(
        self,
        threshold: int = DEFAULT_THRESHOLD,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> bool:
        """Determine if an alert should be sent.

        Returns True if consecutive failures >= threshold and
        enough time has passed since the last alert (cooldown).
        """
        if self.consecutive_failures < threshold:
            return False
        if self.last_alert_time > 0:
            elapsed = time.time() - self.last_alert_time
            if elapsed < cooldown_seconds:
                return False
        return True

    def should_send_recovery(self) -> bool:
        """Determine if a recovery alert should be sent.

        Returns True if we previously sent an alert (last_alert_time > 0)
        and there were failures (meaning the admin was notified of an issue).
        """
        return self.last_alert_time > 0 and self.consecutive_failures > 0

    def save(self, path: str) -> None:
        """Persist state to a JSON file."""
        data = {
            "consecutive_failures": self.consecutive_failures,
            "last_failure_reason": self.last_failure_reason,
            "last_alert_time": self.last_alert_time,
            "first_failure_time": self.first_failure_time,
        }
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.error("Failed to save health alert state to %s: %s", path, e)

    @classmethod
    def load(cls, path: str) -> "HealthAlertState":
        """Load state from a JSON file. Returns fresh state if file missing/corrupt."""
        try:
            with open(path) as f:
                data = json.load(f)
            return cls(
                consecutive_failures=data.get("consecutive_failures", 0),
                last_failure_reason=data.get("last_failure_reason", ""),
                last_alert_time=data.get("last_alert_time", 0.0),
                first_failure_time=data.get("first_failure_time", 0.0),
            )
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            logger.debug("Loading fresh health alert state (%s): %s", path, e)
            return cls()


def format_alert_message(consecutive_failures: int, reason: str) -> str:
    """Format a failure alert message for Telegram."""
    return (
        f"⚠️ <b>Health Check Alert</b>\n\n"
        f"Service has failed <b>{consecutive_failures}</b> consecutive health checks.\n"
        f"Reason: <code>{reason}</code>\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
    )


def format_recovery_message(total_downtime_checks: int) -> str:
    """Format a recovery message for Telegram."""
    return (
        f"✅ <b>Service Recovered</b>\n\n"
        f"Health checks restored after {total_downtime_checks} failed checks.\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
    )


def _send_alert(chat_id: int, message: str) -> None:
    """Send an alert message via Telegram API.

    Uses requests directly since this runs outside the bot process
    (from the health check launchd service), so there's no async
    event loop conflict.
    """
    import requests

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set — cannot send health alert")
        return

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=30,
        )
        if not resp.json().get("ok"):
            logger.error("Telegram alert failed: %s", resp.text)
    except Exception as e:
        logger.error("Failed to send health alert: %s", e)


def process_health_result(
    success: bool,
    reason: str,
    state_file: str = DEFAULT_STATE_FILE,
    admin_chat_id: Optional[int] = None,
    threshold: int = DEFAULT_THRESHOLD,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> None:
    """Process a health check result — update state, alert if needed.

    Args:
        success: Whether the health check passed.
        reason: Failure reason (empty string on success).
        state_file: Path to the JSON state file.
        admin_chat_id: Telegram chat ID to send alerts to.
        threshold: Number of consecutive failures before alerting.
        cooldown_seconds: Minimum seconds between alerts.
    """
    if admin_chat_id is None:
        logger.debug("No admin_chat_id configured — skipping health alerts")
        return

    state = HealthAlertState.load(state_file)

    if success:
        if state.should_send_recovery():
            total_failed = state.consecutive_failures
            msg = format_recovery_message(total_failed)
            _send_alert(admin_chat_id, msg)
        state.record_recovery()
        state.last_alert_time = 0.0
    else:
        state.record_failure(reason)
        if state.should_alert(threshold=threshold, cooldown_seconds=cooldown_seconds):
            msg = format_alert_message(state.consecutive_failures, reason)
            _send_alert(admin_chat_id, msg)
            state.last_alert_time = time.time()

    state.save(state_file)
