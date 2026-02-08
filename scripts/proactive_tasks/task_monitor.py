#!/usr/bin/env python3
"""
Task Failure Monitor

Scans proactive task logs for failures, stale runs, and missing logs.
Sends consolidated Telegram alerts with de-duplication via state file.

Usage:
    python -m scripts.proactive_tasks.task_monitor
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Load environment
load_dotenv(Path.home() / ".env")
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = 161427550
STALE_HOURS = 25  # Alert if no successful run in this window
STATE_FILE = PROJECT_ROOT / "data" / "task_monitor_state.json"
LOG_DIR = PROJECT_ROOT / "logs"


def load_registry() -> Dict[str, Any]:
    """Load task registry."""
    registry_path = Path(__file__).parent / "task_registry.yaml"
    with open(registry_path, "r") as f:
        return yaml.safe_load(f)


def _parse_last_result(log_path: Path) -> Optional[Dict[str, Any]]:
    """Parse the last Result JSON block from a task log file.

    Looks for lines starting with 'Result: {' and reads the subsequent
    JSON block (which is pretty-printed across multiple lines).
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        return None

    text = log_path.read_text(errors="replace")

    # Find all "Result: {" blocks — take the last one
    pattern = r"^Result: \{.*?^\}"
    matches = list(re.finditer(pattern, text, re.MULTILINE | re.DOTALL))
    if not matches:
        return None

    last_match = matches[-1].group()
    json_str = last_match[len("Result: ") :]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse Result JSON from {log_path}")
        return None


def _load_state() -> Dict[str, Any]:
    """Load persisted monitor state for de-duplication."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"alerted": {}}


def _save_state(state: Dict[str, Any]) -> None:
    """Persist monitor state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _get_i18n_text(key: str, **kwargs: Any) -> str:
    """Get translated text, falling back to English."""
    try:
        from src.core.i18n import t

        return t(f"task_monitor.{key}", **kwargs)
    except Exception:
        # Fallback translations if i18n module can't load
        fallback = {
            "alert_title": "Task Failures Detected",
            "icon_failure": "FAIL",
            "icon_stale": "STALE",
            "icon_missing": "NO LOG",
            "alert_footer": "{count} issue(s) need attention",
            "all_healthy": "All tasks healthy",
        }
        template = fallback.get(key, key)
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template


def check_tasks(registry: Dict[str, Any]) -> List[Dict[str, str]]:
    """Check all enabled tasks for problems.

    Returns list of issues, each with keys: task_id, kind, detail.
    kind is one of: failure, stale, missing.
    """
    issues: List[Dict[str, str]] = []
    tasks = registry.get("tasks", {})
    now = datetime.now()

    for task_id, task_config in tasks.items():
        if not task_config.get("enabled", True):
            continue

        log_path = LOG_DIR / f"{task_id}.log"

        if not log_path.exists() or log_path.stat().st_size == 0:
            issues.append(
                {
                    "task_id": task_id,
                    "kind": "missing",
                    "detail": f"No log file: {log_path.name}",
                }
            )
            continue

        result = _parse_last_result(log_path)
        if result is None:
            issues.append(
                {
                    "task_id": task_id,
                    "kind": "missing",
                    "detail": "No Result block found in log",
                }
            )
            continue

        # Check for failure
        if not result.get("success", False):
            msg = result.get("message", "unknown error")
            issues.append(
                {
                    "task_id": task_id,
                    "kind": "failure",
                    "detail": msg[:120],
                }
            )
            continue

        # Check for staleness
        started_at = result.get("started_at")
        if started_at:
            try:
                run_time = datetime.fromisoformat(started_at)
                age = now - run_time
                if age > timedelta(hours=STALE_HOURS):
                    hours_ago = int(age.total_seconds() / 3600)
                    issues.append(
                        {
                            "task_id": task_id,
                            "kind": "stale",
                            "detail": f"Last success {hours_ago}h ago",
                        }
                    )
            except ValueError:
                pass

    return issues


def _dedup_issues(
    issues: List[Dict[str, str]], state: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Filter out issues that were already alerted.

    An issue is considered "already alerted" if the same task_id + kind + detail
    combination was sent previously. Clears old alerts for tasks that are now healthy.
    """
    alerted = state.get("alerted", {})
    current_keys = set()
    new_issues = []

    for issue in issues:
        key = f"{issue['task_id']}:{issue['kind']}:{issue['detail']}"
        current_keys.add(key)
        if key not in alerted:
            new_issues.append(issue)
            alerted[key] = datetime.now().isoformat()

    # Clean up alerts for issues that no longer exist
    stale_keys = [k for k in alerted if k not in current_keys]
    for k in stale_keys:
        del alerted[k]

    state["alerted"] = alerted
    return new_issues


def format_alert(issues: List[Dict[str, str]]) -> str:
    """Format issues into a Telegram HTML message."""
    icon_map = {
        "failure": _get_i18n_text("icon_failure"),
        "stale": _get_i18n_text("icon_stale"),
        "missing": _get_i18n_text("icon_missing"),
    }
    emoji_map = {
        "failure": "\u274c",  # red X
        "stale": "\u23f3",  # hourglass
        "missing": "\u2753",  # question mark
    }

    title = _get_i18n_text("alert_title")
    lines = [f"\u26a0\ufe0f <b>{title}</b>\n"]

    for issue in issues:
        emoji = emoji_map.get(issue["kind"], "\u2022")
        icon = icon_map.get(issue["kind"], issue["kind"])
        lines.append(
            f"{emoji} <b>[{icon}]</b> <code>{issue['task_id']}</code>\n"
            f"    {issue['detail']}"
        )

    footer = _get_i18n_text("alert_footer", count=len(issues))
    lines.append(f"\n{footer}")

    return "\n".join(lines)


async def send_telegram_message(text: str) -> bool:
    """Send a message via Telegram bot API."""
    import aiohttp

    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                logger.info("Alert sent successfully")
                return True
            else:
                body = await resp.text()
                logger.error(f"Failed to send alert: {body}")
                return False


async def main() -> int:
    """Main entry point."""
    logger.info("Running task monitor...")

    try:
        registry = load_registry()
    except FileNotFoundError as e:
        logger.error(f"Registry not found: {e}")
        return 1

    all_issues = check_tasks(registry)
    if not all_issues:
        logger.info("All tasks healthy")
        return 0

    logger.info(f"Found {len(all_issues)} issue(s) across tasks")
    for issue in all_issues:
        logger.info(f"  {issue['kind']}: {issue['task_id']} — {issue['detail']}")

    # De-duplicate
    state = _load_state()
    new_issues = _dedup_issues(all_issues, state)
    _save_state(state)

    if not new_issues:
        logger.info("No new issues to alert (already notified)")
        return 0

    logger.info(f"Sending alert for {len(new_issues)} new issue(s)")
    alert_text = format_alert(new_issues)
    await send_telegram_message(alert_text)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
