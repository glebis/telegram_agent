"""
HeartbeatService — Two-phase system health monitor.

Phase 1: Concrete checks (DB, API keys, errors, webhook, disk, uptime, staleness, task queue).
Phase 2: LLM triage via LiteLLM (only when issues found).

Delivery via send_message_sync() (subprocess-isolated).
"""

import asyncio
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

from ..core.config import get_config_value, get_settings

logger = logging.getLogger(__name__)

# Module-level start time for uptime check
_start_time = datetime.utcnow()


@dataclass
class CheckResult:
    name: str
    status: str  # "ok" | "warning" | "critical"
    message: str
    value: Any = None


@dataclass
class HeartbeatResult:
    status: str  # "ok" | "warning" | "critical" | "skipped"
    checks: List[CheckResult] = field(default_factory=list)
    summary: Optional[str] = None
    skipped_reason: Optional[str] = None
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class HeartbeatService:
    """Runs health checks and optionally triages issues via LLM."""

    def __init__(self) -> None:
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Phase 1: Concrete checks
    # ------------------------------------------------------------------

    async def check_db(self) -> CheckResult:
        """Check database connectivity."""
        try:
            from sqlalchemy import text

            from ..core.database import get_db_session

            async with get_db_session() as session:
                await session.execute(text("SELECT 1"))
            return CheckResult("database", "ok", "Connected")
        except Exception as e:
            return CheckResult("database", "critical", f"Unreachable: {e}")

    async def check_api_keys(self) -> CheckResult:
        """Check that essential API keys are present in env."""
        missing = []
        warnings = []

        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            missing.append("TELEGRAM_BOT_TOKEN")

        # Optional but useful keys
        for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            if not os.getenv(key):
                warnings.append(key)

        if missing:
            return CheckResult(
                "api_keys",
                "critical",
                f"Missing: {', '.join(missing)}",
                value=missing,
            )
        if warnings:
            return CheckResult(
                "api_keys",
                "warning",
                f"Optional missing: {', '.join(warnings)}",
                value=warnings,
            )
        return CheckResult("api_keys", "ok", "All keys present")

    async def check_recent_errors(self) -> CheckResult:
        """Count ERROR lines in logs/app.log within the configured window."""
        window_hours = get_config_value("heartbeat.error_window_hours", 6)
        warn_threshold = get_config_value("heartbeat.error_rate_warning", 10)
        crit_threshold = get_config_value("heartbeat.error_rate_critical", 50)

        log_path = Path.cwd() / "logs" / "app.log"
        if not log_path.exists():
            return CheckResult("recent_errors", "ok", "No log file found", value=0)

        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        error_count = 0

        try:

            def _count_errors() -> int:
                count = 0
                with open(log_path, "r", errors="replace") as f:
                    for line in f:
                        if " ERROR " not in line:
                            continue
                        # Try to parse timestamp from log line
                        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                        if m:
                            try:
                                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                                if ts >= cutoff:
                                    count += 1
                            except ValueError:
                                count += 1  # Count if we can't parse timestamp
                        else:
                            count += 1
                return count

            error_count = await asyncio.to_thread(_count_errors)
        except Exception as e:
            return CheckResult(
                "recent_errors", "warning", f"Log read error: {e}", value=0
            )

        if error_count >= crit_threshold:
            status = "critical"
        elif error_count >= warn_threshold:
            status = "warning"
        else:
            status = "ok"

        return CheckResult(
            "recent_errors",
            status,
            f"{error_count} errors in last {window_hours}h",
            value=error_count,
        )

    async def check_webhook(self) -> CheckResult:
        """Check Telegram webhook status via getWebhookInfo."""
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            return CheckResult("webhook", "critical", "No bot token")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
                )
                data = resp.json()

            if not data.get("ok"):
                return CheckResult("webhook", "critical", "API returned error")

            result = data["result"]
            url = result.get("url", "")
            pending = result.get("pending_update_count", 0)
            last_error = result.get("last_error_message", "")

            if not url:
                return CheckResult("webhook", "critical", "No webhook URL set")

            issues = []
            status = "ok"

            if pending > 10:
                issues.append(f"{pending} pending updates")
                status = "warning"
            if pending > 100:
                status = "critical"

            if last_error:
                issues.append(f"Last error: {last_error}")
                if status == "ok":
                    status = "warning"

            msg = f"URL set, {pending} pending"
            if issues:
                msg += " | " + "; ".join(issues)

            return CheckResult("webhook", status, msg, value=pending)
        except Exception as e:
            return CheckResult("webhook", "critical", f"Check failed: {e}")

    async def check_disk_space(self) -> CheckResult:
        """Check disk space using shutil.disk_usage (cross-platform)."""
        warn_pct = get_config_value("heartbeat.disk_space_warning_percent", 85)
        crit_pct = get_config_value("heartbeat.disk_space_critical_percent", 95)

        try:
            usage = shutil.disk_usage(Path.cwd())
            used_pct = round((usage.used / usage.total) * 100, 1)
            free_gb = round(usage.free / (1024**3), 1)

            if used_pct >= crit_pct:
                status = "critical"
            elif used_pct >= warn_pct:
                status = "warning"
            else:
                status = "ok"

            return CheckResult(
                "disk_space",
                status,
                f"{used_pct}% used, {free_gb}GB free",
                value=used_pct,
            )
        except Exception as e:
            return CheckResult("disk_space", "warning", f"Check failed: {e}")

    async def check_uptime(self) -> CheckResult:
        """Report process uptime (informational, always ok)."""
        delta = datetime.utcnow() - _start_time
        hours = delta.total_seconds() / 3600
        if hours < 1:
            msg = f"{int(delta.total_seconds() / 60)}m"
        elif hours < 24:
            msg = f"{hours:.1f}h"
        else:
            msg = f"{hours / 24:.1f}d"

        return CheckResult("uptime", "ok", f"Up {msg}", value=round(hours, 2))

    async def check_message_staleness(self) -> CheckResult:
        """Check how recently the last message was stored."""
        threshold_minutes = get_config_value(
            "heartbeat.stale_message_warning_minutes", 120
        )

        try:
            from sqlalchemy import desc, select

            from ..core.database import get_db_session
            from ..models.message import Message

            async with get_db_session() as session:
                result = await session.execute(
                    select(Message.created_at)
                    .order_by(desc(Message.created_at))
                    .limit(1)
                )
                row = result.scalar_one_or_none()

            if row is None:
                return CheckResult(
                    "message_staleness", "ok", "No messages yet", value=None
                )

            # row is a datetime (possibly timezone-aware)
            last_ts = row
            if hasattr(last_ts, "replace"):
                last_ts = last_ts.replace(tzinfo=None)
            age = datetime.utcnow() - last_ts
            age_minutes = age.total_seconds() / 60

            if age_minutes > threshold_minutes:
                return CheckResult(
                    "message_staleness",
                    "warning",
                    f"Last message {int(age_minutes)}m ago",
                    value=int(age_minutes),
                )
            return CheckResult(
                "message_staleness",
                "ok",
                f"Last message {int(age_minutes)}m ago",
                value=int(age_minutes),
            )
        except Exception as e:
            return CheckResult("message_staleness", "warning", f"Check failed: {e}")

    async def check_task_queue(self) -> CheckResult:
        """Check job queue status (pending/failed counts)."""
        try:
            from .job_queue_service import get_job_queue_service

            service = get_job_queue_service()
            status_dict = service.get_queue_status()
            pending = status_dict.get("pending", 0)
            failed = status_dict.get("failed", 0)

            if failed > 0:
                return CheckResult(
                    "task_queue",
                    "warning",
                    f"{pending} pending, {failed} failed",
                    value=status_dict,
                )
            return CheckResult(
                "task_queue",
                "ok",
                f"{pending} pending, {failed} failed",
                value=status_dict,
            )
        except Exception as e:
            return CheckResult("task_queue", "ok", f"Queue not available: {e}")

    # ------------------------------------------------------------------
    # Phase 1: Run all checks
    # ------------------------------------------------------------------

    async def run_phase1(self) -> List[CheckResult]:
        """Run all Phase 1 checks concurrently."""
        results = await asyncio.gather(
            self.check_db(),
            self.check_api_keys(),
            self.check_recent_errors(),
            self.check_webhook(),
            self.check_disk_space(),
            self.check_uptime(),
            self.check_message_staleness(),
            self.check_task_queue(),
            return_exceptions=True,
        )

        checks = []
        for r in results:
            if isinstance(r, Exception):
                checks.append(CheckResult("unknown", "critical", f"Check crashed: {r}"))
            else:
                checks.append(r)
        return checks

    # ------------------------------------------------------------------
    # Phase 2: LLM triage
    # ------------------------------------------------------------------

    async def run_triage(self, checks: List[CheckResult]) -> Optional[str]:
        """Run LLM triage on check results. Returns summary or None."""
        triage_enabled = get_config_value("heartbeat.triage_enabled", True)
        if not triage_enabled:
            return None

        model = get_config_value("heartbeat.triage_model", "gpt-4o-mini")
        max_tokens = get_config_value("heartbeat.triage_max_tokens", 300)

        # Build structured input
        lines = []
        for c in checks:
            lines.append(f"- {c.name}: [{c.status}] {c.message}")
        checks_text = "\n".join(lines)

        prompt = (
            "You are a DevOps assistant. Below are system health check results "
            "for a Telegram bot. Summarize the issues and suggest brief actions. "
            "Max 500 chars. Be concise. Use plain text only — no markdown, "
            "no bold, no bullet points.\n\n" + checks_text
        )

        try:
            import litellm

            response = await asyncio.to_thread(
                litellm.completion,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("LLM triage failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    async def run(self, chat_id: int) -> HeartbeatResult:
        """Run full heartbeat (Phase 1 + conditional Phase 2). Does NOT send."""
        start = datetime.utcnow()
        checks = await self.run_phase1()

        # Determine overall status
        statuses = [c.status for c in checks]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "ok"

        # Phase 2: only if issues found
        summary = None
        if overall != "ok":
            summary = await self.run_triage(checks)

        duration = (datetime.utcnow() - start).total_seconds()

        return HeartbeatResult(
            status=overall,
            checks=checks,
            summary=summary,
            duration_seconds=round(duration, 2),
        )

    async def run_and_deliver(self, chat_id: int) -> HeartbeatResult:
        """Run heartbeat and deliver results to Telegram."""
        result = await self.run(chat_id)

        show_ok = get_config_value("heartbeat.show_ok", False)
        if result.status == "ok" and not show_ok:
            result.status = "skipped"
            result.skipped_reason = "All checks OK, show_ok=false"
            logger.info("Heartbeat all OK, skipping delivery (show_ok=false)")
            return result

        # Format and send
        msg = self._format_message(result)
        from ..bot.handlers.base import send_message_sync

        send_message_sync(chat_id, msg, parse_mode="HTML")

        return result

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_message(self, result: HeartbeatResult) -> str:
        """Format HeartbeatResult as HTML for Telegram."""
        status_emoji = {
            "ok": "\u2705",  # green check
            "warning": "\u26a0\ufe0f",  # warning
            "critical": "\u274c",  # red X
        }

        check_emoji = {
            "ok": "\u2705",
            "warning": "\u26a0\ufe0f",
            "critical": "\u274c",
        }

        fallback = "\u2753"
        emoji = status_emoji.get(result.status, fallback)
        header = f"{emoji} <b>Heartbeat: {result.status.upper()}</b>"
        lines = [header, ""]

        for c in result.checks:
            icon = check_emoji.get(c.status, fallback)
            lines.append(f"{icon} <b>{c.name}</b>: {c.message}")

        lines.append("")
        lines.append(f"<i>Duration: {result.duration_seconds}s</i>")

        if result.summary:
            lines.append("")
            lines.append(f"<b>Triage:</b>\n{result.summary}")

        return "\n".join(lines)


# Singleton
_heartbeat_service: Optional[HeartbeatService] = None


def get_heartbeat_service() -> HeartbeatService:
    """Get the global HeartbeatService instance."""
    global _heartbeat_service
    if _heartbeat_service is None:
        _heartbeat_service = HeartbeatService()
    return _heartbeat_service
