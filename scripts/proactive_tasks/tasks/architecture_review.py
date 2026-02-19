#!/usr/bin/env python3
"""
Architecture Review Task

Runs every 12 hours to analyze logs, database, and code health.
Sends a summary via Telegram and creates detailed issue reports.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.proactive_tasks.base_task import BaseTask, TaskResult

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "telegram_agent.db"
ERROR_LOG = PROJECT_ROOT / "logs" / "errors.log"
APP_LOG = PROJECT_ROOT / "logs" / "app.log"
ISSUES_DIR = PROJECT_ROOT / "issues"


class ArchitectureReviewTask(BaseTask):
    """
    12-hour architecture review that:
    1. Scans error logs for new/recurring patterns
    2. Queries database for session and usage stats
    3. Checks for known anti-patterns (import errors, crashes, resource leaks)
    4. Creates issue files with description, acceptance criteria, DoD, testing approach
    5. Sends summary via Telegram
    """

    @property
    def name(self) -> str:
        return "architecture-review"

    @property
    def description(self) -> str:
        return "12-hour system health review with issue tracking and Telegram delivery"

    def validate_config(self) -> List[str]:
        errors = []
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            errors.append("Missing TELEGRAM_BOT_TOKEN")
        if not DB_PATH.exists():
            errors.append(f"Database not found: {DB_PATH}")
        return errors

    async def execute(self) -> TaskResult:
        """Run the architecture review."""
        self._logger.info("Starting 12-hour architecture review...")

        report_sections = []
        issues_created = []

        # 1. Error log analysis (last 12 hours)
        error_summary, error_issues = self._analyze_error_logs()
        report_sections.append(error_summary)
        issues_created.extend(error_issues)

        # 2. Database health
        db_summary = self._analyze_database()
        report_sections.append(db_summary)

        # 3. Session statistics
        session_summary = self._analyze_sessions()
        report_sections.append(session_summary)

        # 4. Check improvement plan progress
        plan_summary = self._check_plan_progress()
        if plan_summary:
            report_sections.append(plan_summary)

        # 5. Save issues — beads for tracking, flat files for detail
        ISSUES_DIR.mkdir(exist_ok=True)
        beads_ids = await self._file_beads_issues(issues_created)
        for issue in issues_created:
            self._save_issue(issue)

        # 6. Build full report
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_report = f"<b>Architecture Review — {timestamp}</b>\n\n"
        full_report += "\n\n".join(report_sections)

        if issues_created:
            full_report += f"\n\n<b>New Issues Created:</b> {len(issues_created)}"
            for i, issue in enumerate(issues_created):
                bd_id = beads_ids[i] if i < len(beads_ids) else ""
                prefix = f"[{bd_id}] " if bd_id else ""
                full_report += f"\n• {prefix}{issue['title']}"

        # 7. Send via Telegram
        chat_id = self.config.get("chat_id") or os.getenv("TRAIL_REVIEW_CHAT_ID") or "161427550"
        sent = self._send_telegram(int(chat_id), full_report)

        return TaskResult(
            success=True,
            message=f"Review complete: {len(issues_created)} issues created, report sent={sent}",
            outputs={
                "issues_created": len(issues_created),
                "report_sent": sent,
                "sections": len(report_sections),
            },
        )

    def _analyze_error_logs(self) -> tuple:
        """Analyze error logs from the last 12 hours."""
        summary_lines = ["<b>Error Log Analysis (12h)</b>"]
        issues = []
        cutoff = datetime.now() - timedelta(hours=12)

        if not ERROR_LOG.exists():
            summary_lines.append("No error log found.")
            return "\n".join(summary_lines), issues

        error_counts = Counter()
        recent_errors = []

        try:
            with open(ERROR_LOG, "r") as f:
                for line in f:
                    # Parse timestamp from log line
                    match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                    if not match:
                        continue
                    try:
                        ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                    if ts < cutoff:
                        continue

                    # Categorize the error
                    if "ImportError" in line or "ModuleNotFoundError" in line:
                        error_counts["Import/Module errors"] += 1
                        recent_errors.append(("import", line.strip()[:200]))
                    elif "ANTHROPIC_API_KEY not set" in line:
                        error_counts["API key missing"] += 1
                    elif "Failed to retrieve file_id" in line:
                        error_counts["Callback data lost"] += 1
                    elif "bytes-like object" in line:
                        error_counts["Embedding type error"] += 1
                    elif "TimedOut" in line or "timed out" in line.lower():
                        error_counts["Timeouts"] += 1
                    elif "ERROR" in line:
                        error_counts["Other errors"] += 1

        except Exception as e:
            summary_lines.append(f"Error reading log: {e}")
            return "\n".join(summary_lines), issues

        total = sum(error_counts.values())
        summary_lines.append(f"Total errors: <b>{total}</b>")

        for category, count in error_counts.most_common(10):
            summary_lines.append(f"  • {category}: {count}")

        # Create issues for significant error patterns
        if error_counts.get("Import/Module errors", 0) > 0:
            # Deduplicate import errors
            import_modules = set()
            for err_type, err_line in recent_errors:
                if err_type == "import":
                    mod_match = re.search(r"No module named '([^']+)'", err_line)
                    imp_match = re.search(r"cannot import name '([^']+)' from '([^']+)'", err_line)
                    if mod_match:
                        import_modules.add(mod_match.group(1))
                    elif imp_match:
                        import_modules.add(f"{imp_match.group(1)} from {imp_match.group(2)}")

            for mod in import_modules:
                issues.append({
                    "title": f"Import error: {mod}",
                    "priority": "P0",
                    "description": f"Module import fails at runtime: {mod}",
                    "acceptance_criteria": "No ImportError for this module in error logs after fix",
                    "definition_of_done": "Import resolves correctly. Error log clean for 24h.",
                    "testing": "Restart service; trigger the code path; verify no ImportError in logs.",
                })

        if error_counts.get("API key missing", 0) > 5:
            issues.append({
                "title": "ANTHROPIC_API_KEY frequently missing from environment",
                "priority": "P0",
                "description": f"API key reported missing {error_counts['API key missing']} times in 12h. "
                              "Likely caused by env var race condition in concurrent Claude sessions.",
                "acceptance_criteria": "Session naming succeeds consistently when API key is configured",
                "definition_of_done": "Zero 'API key not set' errors over 24h with normal usage.",
                "testing": "Run concurrent Claude sessions; check session_naming logs.",
            })

        return "\n".join(summary_lines), issues

    def _analyze_database(self) -> str:
        """Check database health."""
        lines = ["<b>Database Health</b>"]

        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            # Table sizes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]
            lines.append(f"Tables: {len(tables)}")

            # Key table counts
            for table in ["claude_sessions", "messages", "poll_responses", "images"]:
                if table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    lines.append(f"  • {table}: {count} rows")

            # Active sessions
            cursor.execute("SELECT COUNT(*) FROM claude_sessions WHERE is_active=1")
            active = cursor.fetchone()[0]
            lines.append(f"  • Active sessions: {active}")

            # Sessions in last 12h
            cursor.execute(
                "SELECT COUNT(*) FROM claude_sessions WHERE last_used > datetime('now', '-12 hours')"
            )
            recent = cursor.fetchone()[0]
            lines.append(f"  • Sessions (12h): {recent}")

            # DB file size
            db_size = DB_PATH.stat().st_size / (1024 * 1024)
            lines.append(f"DB size: {db_size:.1f} MB")

            conn.close()
        except Exception as e:
            lines.append(f"Error: {e}")

        return "\n".join(lines)

    def _analyze_sessions(self) -> str:
        """Analyze Claude session patterns."""
        lines = ["<b>Session Activity</b>"]

        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT date(last_used) as day, COUNT(*) as cnt
                FROM claude_sessions
                WHERE last_used > datetime('now', '-7 days')
                GROUP BY day ORDER BY day
            """)
            rows = cursor.fetchall()
            for day, count in rows:
                bar = "█" * min(count, 20)
                lines.append(f"  {day}: {bar} {count}")

            conn.close()
        except Exception as e:
            lines.append(f"Error: {e}")

        return "\n".join(lines)

    def _check_plan_progress(self) -> Optional[str]:
        """Check if docs/UNIFIED_IMPROVEMENT_PLAN.md exists and report status."""
        plan_path = PROJECT_ROOT / "docs" / "UNIFIED_IMPROVEMENT_PLAN.md"
        if not plan_path.exists():
            return None

        lines = ["<b>Improvement Plan</b>"]
        try:
            content = plan_path.read_text()
            p0_count = content.count("### P0-")
            p1_count = content.count("### P1-")
            p2_count = content.count("### P2-")
            checked = content.count("[x]") + content.count("[X]")
            unchecked = content.count("[ ]")
            lines.append(f"  P0: {p0_count} items | P1: {p1_count} | P2: {p2_count}")
            if unchecked > 0:
                lines.append(f"  P3 checklist: {checked}/{checked + unchecked} done")
        except Exception as e:
            lines.append(f"Error reading plan: {e}")

        return "\n".join(lines)

    async def _file_beads_issues(self, issues: list) -> list:
        """Try to create beads issues for tracking. Returns list of bd IDs."""
        if not issues:
            return []

        try:
            from src.services.beads_service import get_beads_service

            service = get_beads_service()
            if not await service.is_available():
                self._logger.info("Beads not available, skipping bd issue creation")
                return []
        except Exception:
            return []

        priority_map = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        ids = []
        for issue in issues:
            try:
                pri = priority_map.get(issue.get("priority", "P2"), 2)
                result = await service.create_issue(
                    issue["title"], priority=pri, issue_type="bug"
                )
                bd_id = result.get("id", "")
                ids.append(bd_id)
                self._logger.info(f"Created beads issue {bd_id}: {issue['title']}")
            except Exception as e:
                self._logger.warning(f"Failed to create beads issue: {e}")
                ids.append("")
        return ids

    def _save_issue(self, issue: dict) -> None:
        """Save an issue to the issues directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", issue["title"].lower())[:50]
        filename = f"{timestamp}_{issue['priority']}_{slug}.md"
        filepath = ISSUES_DIR / filename

        content = f"""# {issue['title']}

**Priority:** {issue['priority']}
**Created:** {datetime.now().isoformat()}
**Source:** Automated architecture review

## Description
{issue['description']}

## Acceptance Criteria
{issue['acceptance_criteria']}

## Definition of Done
{issue['definition_of_done']}

## Testing Approach
{issue['testing']}
"""
        filepath.write_text(content)
        self._logger.info(f"Created issue: {filepath}")

    def _send_telegram(self, chat_id: int, text: str) -> bool:
        """Send message via Telegram API."""
        import requests

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            self._logger.error("No TELEGRAM_BOT_TOKEN set")
            return False

        # Telegram has a 4096 char limit; truncate if needed
        if len(text) > 4000:
            text = text[:3990] + "\n\n[truncated]"

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            result = response.json()
            if result.get("ok"):
                self._logger.info(f"Report sent to chat {chat_id}")
                return True
            else:
                self._logger.error(f"Telegram send failed: {result.get('description')}")
                return False
        except Exception as e:
            self._logger.error(f"Failed to send Telegram message: {e}")
            return False
