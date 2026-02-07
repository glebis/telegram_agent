#!/usr/bin/env python3
"""
Daily Health Review - Scheduled task to query sleep/HRV data and send via Telegram.
Runs at 9:30am daily via launchd.

Uses health-data skill for data collection and doctorg-style LLM analysis
for evidence-based personalized insights.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path.home() / ".env")
load_dotenv(project_root / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Telegram config
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = 161427550

# Health data paths
HEALTH_DB = Path.home() / "data" / "health.db"
HEALTH_QUERY_SCRIPT = (
    Path.home() / ".claude" / "skills" / "health-data" / "scripts" / "health_query.py"
)

# Staleness threshold
STALE_HOURS = 24

# Evidence-based health targets (used in LLM prompt)
HEALTH_TARGETS = {
    "sleep_hours": 7.5,
    "hrv_ms": 50,
    "resting_hr_bpm": 65,
    "steps_daily": 8000,
    "exercise_min_weekly": 150,
    "spo2_pct": 95,
}


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram-compatible HTML."""
    placeholder = f"CODEBLOCK{uuid.uuid4().hex[:8]}"

    text = _escape_html(text)

    # Preserve code blocks
    code_blocks: List[str] = []

    def save_code_block(match):
        code_blocks.append(match.group(1))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    text = re.sub(r"```(?:\w+)?\n?(.*?)```", save_code_block, text, flags=re.DOTALL)

    # Convert markdown tables to ASCII
    def convert_table(match):
        try:
            from tabulate import tabulate

            table_text = match.group(0)
            lines = [ln.strip() for ln in table_text.strip().split("\n") if ln.strip()]
            rows = []
            for line in lines:
                if re.match(r"^\|[\s\-:]+\|$", line):
                    continue
                cells = [c.strip() for c in line.split("|")]
                cells = [c for c in cells if c]
                if cells:
                    rows.append(cells)
            if len(rows) >= 1:
                headers = rows[0]
                data = rows[1:] if len(rows) > 1 else []
                ascii_table = tabulate(data, headers=headers, tablefmt="simple")
                code_blocks.append(ascii_table)
                return f"{placeholder}{len(code_blocks) - 1}{placeholder}"
        except Exception as e:
            logger.warning(f"Table conversion failed: {e}")
        code_blocks.append(match.group(0))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    table_pattern = r"(?:^\|.+\|$\n?)+"
    text = re.sub(table_pattern, convert_table, text, flags=re.MULTILINE)

    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"(?<![a-zA-Z0-9])\*([^*]+)\*(?![a-zA-Z0-9])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)
    # Headers -> bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"{placeholder}{i}{placeholder}", f"<pre>{block}</pre>")

    return text


# ============================================================
# Telegram helpers
# ============================================================


async def send_telegram_message(text: str) -> bool:
    """Send a message via Telegram bot."""
    import aiohttp

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                logger.info("Message sent successfully")
                return True
            else:
                body = await resp.text()
                logger.error(f"Failed to send message: {body}")
                return False


async def send_telegram_photo(photo_path: str, caption: str = "") -> bool:
    """Send a photo via Telegram bot."""
    import aiohttp

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    async with aiohttp.ClientSession() as session:
        with open(photo_path, "rb") as photo:
            data = aiohttp.FormData()
            data.add_field("chat_id", str(CHAT_ID))
            data.add_field("photo", photo, filename=os.path.basename(photo_path))
            if caption:
                data.add_field("caption", caption)
                data.add_field("parse_mode", "HTML")

            async with session.post(url, data=data) as resp:
                if resp.status == 200:
                    logger.info(f"Photo sent: {photo_path}")
                    return True
                else:
                    logger.error(f"Failed to send photo: {await resp.text()}")
                    return False


# ============================================================
# Health data collection
# ============================================================


def check_data_freshness() -> Tuple[bool, Optional[str]]:
    """Check if health data is fresh (imported within STALE_HOURS).

    Returns:
        (is_fresh, last_record_timestamp) — timestamp is ISO string or None.
    """
    import sqlite3

    if not HEALTH_DB.exists():
        return False, None

    try:
        conn = sqlite3.connect(HEALTH_DB)
        cursor = conn.execute("SELECT MAX(start_date) FROM health_records")
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            return False, None

        last_ts = row[0]
        # Parse — format may include timezone like "+0100"
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
            try:
                last_dt = datetime.strptime(last_ts, fmt)
                if last_dt.tzinfo:
                    last_dt = last_dt.replace(tzinfo=None)
                break
            except ValueError:
                continue
        else:
            # Fallback: just take first 19 chars
            last_dt = datetime.strptime(last_ts[:19], "%Y-%m-%d %H:%M:%S")

        age = datetime.now() - last_dt
        is_fresh = age < timedelta(hours=STALE_HOURS)
        return is_fresh, last_ts[:19]

    except Exception as e:
        logger.error(f"Error checking data freshness: {e}")
        return False, None


def _run_health_query(command: str, *args: str) -> Optional[Dict[str, Any]]:
    """Run a health_query.py command and return parsed JSON."""
    if not HEALTH_QUERY_SCRIPT.exists():
        logger.warning(f"Health script not found: {HEALTH_QUERY_SCRIPT}")
        return None

    cmd = [
        "python3",
        str(HEALTH_QUERY_SCRIPT),
        "--format",
        "json",
        command,
        *args,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error(f"health_query {command} failed: {result.stderr[:200]}")
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.error(f"health_query {command} timed out")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"health_query {command} bad JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"health_query {command} error: {e}")
        return None


def collect_health_data() -> Dict[str, Any]:
    """Collect all health data needed for the morning review.

    Returns dict with keys: sleep, vitals, weekly, weekly_prev, workouts,
    freshness.
    """
    data: Dict[str, Any] = {}

    # Data freshness
    is_fresh, last_ts = check_data_freshness()
    data["freshness"] = {"is_fresh": is_fresh, "last_record": last_ts}

    # Sleep — last 7 days
    data["sleep"] = _run_health_query("sleep", "--days", "7")

    # Latest vitals
    data["vitals"] = _run_health_query("vitals")

    # Weekly trends — 2 weeks for comparison
    data["weekly"] = _run_health_query("weekly", "--weeks", "2")

    # Workouts — last 7 days
    data["workouts"] = _run_health_query("workouts", "--days", "7")

    return data


# ============================================================
# Report formatting
# ============================================================


def format_data_report(data: Dict[str, Any]) -> str:
    """Build the data section of the morning report (no LLM)."""
    parts: List[str] = []

    # --- Freshness warning ---
    freshness = data.get("freshness", {})
    if not freshness.get("is_fresh", True):
        last = freshness.get("last_record", "unknown")
        parts.append(f"⚠️ **Health data may be stale** — last import: {last}\n")

    # --- Sleep ---
    sleep = data.get("sleep")
    if sleep and sleep.get("nights"):
        parts.append("## 😴 Last Night's Sleep")
        last_night = sleep["nights"][0]
        hours = last_night.get("total_hours", "N/A")
        parts.append(f"- **Duration**: {hours}h")

        stages = last_night.get("stages", {})
        deep = stages.get("Deep")
        rem = stages.get("REM")
        if deep is not None:
            parts.append(f"- **Deep Sleep**: {deep:.0f} min")
        if rem is not None:
            parts.append(f"- **REM Sleep**: {rem:.0f} min")

        # Weekly average
        summary = sleep.get("summary", {})
        avg = summary.get("avg_sleep_hours")
        if avg:
            parts.append(f"- **7-day avg**: {avg}h/night")
        parts.append("")

    # --- Vitals ---
    vitals = data.get("vitals")
    if vitals and vitals.get("vitals"):
        parts.append("## ❤️ Vitals")
        v = vitals["vitals"]
        for name in ("HRV", "Resting HR", "Blood Oxygen"):
            info = v.get(name)
            if info and info.get("value") is not None:
                unit = {"HRV": "ms", "Resting HR": "bpm", "Blood Oxygen": "%"}
                parts.append(f"- **{name}**: {info['value']} {unit.get(name, '')}")
        parts.append("")

    # --- Weekly trends ---
    weekly = data.get("weekly")
    if weekly and weekly.get("weeks"):
        weeks = weekly["weeks"]
        parts.append("## 📊 Weekly Trends")
        current = weeks[-1] if weeks else {}
        prev = weeks[-2] if len(weeks) >= 2 else {}

        cm = current.get("metrics", {})
        pm = prev.get("metrics", {})

        # Steps
        steps = cm.get("avg_daily_steps", 0)
        prev_steps = pm.get("avg_daily_steps", 0)
        delta_steps = _delta_str(steps, prev_steps)
        if isinstance(steps, (int, float)):
            parts.append(f"- **Avg Steps**: {steps:,.0f}/day {delta_steps}")
        else:
            parts.append(f"- **Avg Steps**: {steps}")

        # Exercise
        exercise = cm.get("total_exercise_min", 0)
        prev_exercise = pm.get("total_exercise_min", 0)
        delta_ex = _delta_str(exercise, prev_exercise)
        if isinstance(exercise, (int, float)):
            parts.append(f"- **Exercise**: {exercise:.0f} min {delta_ex}")
        else:
            parts.append(f"- **Exercise**: {exercise}")

        # Resting HR
        rhr = cm.get("avg_resting_hr")
        prev_rhr = pm.get("avg_resting_hr")
        if rhr:
            delta_rhr = _delta_str(rhr, prev_rhr, lower_is_better=True)
            parts.append(f"- **Avg Resting HR**: {rhr} bpm {delta_rhr}")

        # Workouts
        workouts_count = cm.get("workouts", 0)
        parts.append(f"- **Workouts**: {workouts_count}")
        parts.append("")

    # --- Recent workouts ---
    workouts = data.get("workouts")
    if workouts and workouts.get("workouts"):
        w_list = workouts["workouts"][:5]
        if w_list:
            parts.append("## 🏋️ Recent Workouts")
            for w in w_list:
                wtype = w.get("type", "Unknown")
                dur = w.get("duration_min", 0)
                cal = w.get("calories", 0)
                date_str = (w.get("date", ""))[5:10]
                parts.append(f"- {date_str} {wtype}: {dur:.0f}min, {cal:.0f}cal")
            parts.append("")

    return "\n".join(parts)


def _delta_str(
    current: Any,
    previous: Any,
    lower_is_better: bool = False,
) -> str:
    """Format a delta indicator (↑/↓) comparing current vs previous."""
    if (
        current is None
        or previous is None
        or not isinstance(current, (int, float))
        or not isinstance(previous, (int, float))
        or previous == 0
    ):
        return ""
    diff = current - previous
    pct = abs(diff / previous) * 100
    if abs(pct) < 1:
        return ""
    if diff > 0:
        arrow = "↓" if lower_is_better else "↑"
    else:
        arrow = "↑" if lower_is_better else "↓"
    return f"({arrow}{pct:.0f}% vs prev week)"


# ============================================================
# LLM insight generation (doctorg-style)
# ============================================================

INSIGHT_PROMPT_TEMPLATE = """\
You are a health analyst providing a brief morning briefing. Based on the \
user's Apple Health data below, write 3-5 short sentences of personalized, \
evidence-based insights.

Guidelines:
- Reference specific numbers from the data
- Compare against evidence-based targets: \
sleep {sleep_target}h, HRV >{hrv_target}ms, resting HR <{rhr_target}bpm, \
steps >{steps_target}/day, exercise >{exercise_target}min/week
- Mention one specific actionable suggestion
- If data is stale (noted below), mention the limitation
- Keep it concise — this goes in a Telegram message
- Do NOT use markdown headers or bullet points — just flowing sentences
- Do NOT include greetings or sign-offs

Health Data:
{health_data_json}
"""


async def generate_llm_insight(data: Dict[str, Any]) -> Optional[str]:
    """Call Claude Agent SDK to generate doctorg-style personalized insight."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
        from claude_agent_sdk.types import AssistantMessage, TextBlock

        prompt = INSIGHT_PROMPT_TEMPLATE.format(
            sleep_target=HEALTH_TARGETS["sleep_hours"],
            hrv_target=HEALTH_TARGETS["hrv_ms"],
            rhr_target=HEALTH_TARGETS["resting_hr_bpm"],
            steps_target=HEALTH_TARGETS["steps_daily"],
            exercise_target=HEALTH_TARGETS["exercise_min_weekly"],
            health_data_json=json.dumps(data, indent=2, default=str)[:3000],
        )

        # Ensure ANTHROPIC_API_KEY is not set so SDK uses subscription
        env_key = os.environ.pop("ANTHROPIC_API_KEY", None)

        try:
            options = ClaudeAgentOptions(
                model="sonnet",
                allowed_tools=[],
                max_turns=1,
            )

            text_parts: List[str] = []
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)

            content = "\n".join(text_parts).strip()
            return content if content else None
        finally:
            # Restore key if it was set
            if env_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = env_key

    except Exception as e:
        logger.error(f"LLM insight generation failed: {e}")
        return None


# ============================================================
# Main
# ============================================================


async def main():
    """Main entry point for daily health review."""
    logger.info("Starting daily health review...")

    # Check prerequisites
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    if not HEALTH_DB.exists():
        logger.error(f"Health database not found: {HEALTH_DB}")
        await send_telegram_message(
            "❌ <b>Daily Health Review</b>\n\n"
            f"Health database not found at <code>{HEALTH_DB}</code>.\n"
            "Run the health import script first."
        )
        return

    try:
        # Collect health data
        data = collect_health_data()

        # Format data report
        data_report = format_data_report(data)

        if not data_report.strip():
            data_report = "⚠️ No health data available."

        # Generate LLM insight
        insight = await generate_llm_insight(data)

        # Assemble final message
        today = datetime.now().strftime("%A, %B %d")
        parts = [f"🌅 **Good Morning! Health Review for {today}**\n"]
        parts.append(data_report)

        if insight:
            parts.append("## 🧠 Insights")
            parts.append(insight)
            parts.append("")

        report_md = "\n".join(parts)
        html_text = _markdown_to_telegram_html(report_md)

        # Truncate to Telegram limit
        if len(html_text) > 4000:
            html_text = html_text[:3950] + "\n\n<i>... truncated</i>"

        await send_telegram_message(html_text)
        logger.info("Daily health review completed")

    except Exception as e:
        logger.error(f"Error in daily health review: {e}", exc_info=True)
        await send_telegram_message(
            f"❌ Daily health review failed: {_escape_html(str(e)[:200])}"
        )


if __name__ == "__main__":
    asyncio.run(main())
