#!/usr/bin/env python3
"""
Daily Health Review - Scheduled task to query sleep/HRV data and send via Telegram.
Runs at 9:30am daily via launchd.
"""

import asyncio
import os
import sys
import re
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path.home() / ".env")
load_dotenv(project_root / ".env")

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Telegram config
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = 161427550  # Your chat ID


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram-compatible HTML."""
    placeholder = f"CODEBLOCK{uuid.uuid4().hex[:8]}"

    # First escape HTML entities
    text = _escape_html(text)

    # Process code blocks first (```code```) - preserve them
    code_blocks = []
    def save_code_block(match):
        code_blocks.append(match.group(1))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    text = re.sub(r'```(?:\w+)?\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

    # Detect and convert markdown tables to ASCII tables
    def convert_table(match):
        try:
            from tabulate import tabulate
            table_text = match.group(0)
            lines = [l.strip() for l in table_text.strip().split('\n') if l.strip()]

            rows = []
            for line in lines:
                if re.match(r'^\|[\s\-:]+\|$', line):
                    continue
                cells = [c.strip() for c in line.split('|')]
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

    table_pattern = r'(?:^\|.+\|$\n?)+'
    text = re.sub(table_pattern, convert_table, text, flags=re.MULTILINE)

    # Inline code (`code`)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Bold (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic (*text* or _text_)
    text = re.sub(r'(?<![a-zA-Z0-9])\*([^*]+)\*(?![a-zA-Z0-9])', r'<i>\1</i>', text)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)

    # Headers (# Header) -> bold
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Markdown links [text](url) -> <a href="url">text</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"{placeholder}{i}{placeholder}", f"<pre>{block}</pre>")

    return text


async def send_telegram_message(text: str) -> bool:
    """Send a message via Telegram bot."""
    import aiohttp

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                logger.info("Message sent successfully")
                return True
            else:
                logger.error(f"Failed to send message: {await resp.text()}")
                return False


async def send_telegram_photo(photo_path: str, caption: str = "") -> bool:
    """Send a photo via Telegram bot."""
    import aiohttp

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    async with aiohttp.ClientSession() as session:
        with open(photo_path, 'rb') as photo:
            data = aiohttp.FormData()
            data.add_field('chat_id', str(CHAT_ID))
            data.add_field('photo', photo, filename=os.path.basename(photo_path))
            if caption:
                data.add_field('caption', caption)
                data.add_field('parse_mode', 'HTML')

            async with session.post(url, data=data) as resp:
                if resp.status == 200:
                    logger.info(f"Photo sent: {photo_path}")
                    return True
                else:
                    logger.error(f"Failed to send photo: {await resp.text()}")
                    return False


async def run_claude_health_query() -> tuple:
    """Query actual health data using health-data skill scripts."""
    import subprocess
    import json
    from datetime import datetime, timedelta

    health_script = Path.home() / ".claude" / "skills" / "health-data" / "scripts" / "health_query.py"

    if not health_script.exists():
        logger.warning(f"Health script not found at {health_script}")
        return "⚠️ Health data script not installed. Run skill setup first.", []

    try:
        # Get sleep data for last night
        sleep_result = subprocess.run(
            ["python3", str(health_script), "--format", "json", "sleep", "--days", "1"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Get vitals (HRV)
        vitals_result = subprocess.run(
            ["python3", str(health_script), "--format", "json", "vitals"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Get weekly trends
        weekly_result = subprocess.run(
            ["python3", str(health_script), "--format", "json", "weekly", "--weeks", "1"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Parse results
        sleep_data = json.loads(sleep_result.stdout) if sleep_result.returncode == 0 else {}
        vitals_data = json.loads(vitals_result.stdout) if vitals_result.returncode == 0 else {}
        weekly_data = json.loads(weekly_result.stdout) if weekly_result.returncode == 0 else {}

        # Build markdown report
        report_parts = []

        # Sleep section
        if sleep_data and sleep_data.get('nights'):
            report_parts.append("## 😴 Last Night's Sleep")
            nights = sleep_data.get('nights', [])
            if nights:
                last_night = nights[0]
                duration = last_night.get('duration_hours', 'N/A')
                report_parts.append(f"- **Duration**: {duration}h")

                # Sleep stages if available
                stages = last_night.get('sleep_stages', {})
                if stages:
                    deep = stages.get('Deep', 'N/A')
                    rem = stages.get('REM', 'N/A')
                    if deep != 'N/A':
                        report_parts.append(f"- **Deep Sleep**: {deep}")
                    if rem != 'N/A':
                        report_parts.append(f"- **REM Sleep**: {rem}")
            report_parts.append("")

        # HRV section
        if vitals_data:
            report_parts.append("## ❤️ Vitals")
            vitals = vitals_data.get('vitals', {})

            if 'HRV' in vitals:
                hrv_value = vitals['HRV'].get('value', 'N/A')
                hrv_recorded = vitals['HRV'].get('recorded', '')
                if hrv_value and hrv_value != 'N/A':
                    report_parts.append(f"- **HRV**: {hrv_value} ms")
                    if hrv_recorded:
                        report_parts.append(f"  *{hrv_recorded}*")

            if 'Resting HR' in vitals:
                rhr = vitals['Resting HR'].get('value', 'N/A')
                if rhr and rhr != 'N/A':
                    report_parts.append(f"- **Resting HR**: {rhr} bpm")

            if 'Blood Oxygen' in vitals:
                spo2 = vitals['Blood Oxygen'].get('value', 'N/A')
                if spo2 and spo2 != 'N/A':
                    report_parts.append(f"- **Blood Oxygen**: {spo2}%")

            report_parts.append("")

        # Weekly activity
        if weekly_data:
            report_parts.append("## 📊 This Week's Activity")
            weeks = weekly_data.get('weeks', [])
            if weeks:
                current_week = weeks[0]
                metrics = current_week.get('metrics', {})

                avg_steps = metrics.get('avg_daily_steps', 'N/A')
                total_exercise = metrics.get('total_exercise_min', 'N/A')
                workouts = metrics.get('workouts', 0)

                # Format steps
                if isinstance(avg_steps, (int, float)):
                    report_parts.append(f"- **Avg Daily Steps**: {avg_steps:,.0f}")
                else:
                    report_parts.append(f"- **Avg Daily Steps**: {avg_steps}")

                # Format exercise (total for week, calculate daily average)
                if isinstance(total_exercise, (int, float)):
                    daily_avg = total_exercise / 7
                    report_parts.append(f"- **Exercise**: {daily_avg:.0f} min/day ({total_exercise:.0f} total)")
                else:
                    report_parts.append(f"- **Exercise**: {total_exercise}")

                report_parts.append(f"- **Workouts**: {workouts}")
            report_parts.append("")

        # Add motivational tip
        report_parts.append("## 💡 Today's Focus")
        report_parts.append("*Start your day with movement*. A morning walk boosts mood and sets positive momentum. 🚶‍♂️")

        result_text = "\n".join(report_parts)

        if not result_text.strip():
            result_text = "⚠️ No health data available. Check database connection."

        return result_text, []

    except subprocess.TimeoutExpired:
        logger.error("Health data query timed out")
        return "⏱️ Health data query timed out. Try again later.", []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse health data JSON: {e}")
        return f"⚠️ Error parsing health data: {str(e)}", []
    except Exception as e:
        logger.error(f"Error querying health data: {e}")
        return f"❌ Error: {str(e)}", []


async def main():
    """Main entry point for daily health review."""
    logger.info("Starting daily health review...")

    try:
        # Get health data from Claude
        result_text, file_paths = await run_claude_health_query()

        if not result_text:
            result_text = "Unable to generate health review. Please check the health data skill."

        # Convert markdown to Telegram HTML
        html_text = _markdown_to_telegram_html(result_text)

        # Send the review
        today = datetime.now().strftime("%A, %B %d")
        header = f"<b>🌅 Good Morning! Health Review for {today}</b>\n\n"

        await send_telegram_message(header + html_text[:4000])

        # Send any generated charts
        for path in file_paths:
            await send_telegram_photo(path, f"📊 {os.path.basename(path)}")

        logger.info("Daily health review completed")

    except Exception as e:
        logger.error(f"Error in daily health review: {e}", exc_info=True)
        await send_telegram_message(f"❌ Daily health review failed: {str(e)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
