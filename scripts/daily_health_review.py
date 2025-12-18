#!/usr/bin/env python3
"""
Daily Health Review - Scheduled task to query sleep/HRV data and send via Telegram.
Runs at 9:30am daily via launchd.
"""

import asyncio
import os
import sys
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


async def run_claude_health_query() -> str:
    """Run Claude Code to query health data."""
    from claude_code_sdk import ClaudeCodeOptions, query, TextBlock, AssistantMessage

    prompt = """Use the health-data skill to get my sleep and HRV data from the last 7 days.

Create a brief morning health review that includes:
1. Last night's sleep quality and duration
2. HRV trend over the past week
3. Any notable patterns or concerns
4. A motivational health tip for today

Keep it concise and actionable. Format for Telegram (use markdown).
If you generate any charts/graphs, include the file path."""

    # Unset API key to use subscription
    original_key = os.environ.pop("ANTHROPIC_API_KEY", None)

    options = ClaudeCodeOptions(
        cwd=str(Path.home() / "Research" / "vault"),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Grep", "Skill"],
    )

    result_text = ""
    file_paths = []

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text

        # Extract file paths from result
        import re
        path_pattern = r'(?:/[^\s<>"|*?`]+\.(?:png|jpg|pdf))'
        for match in re.finditer(path_pattern, result_text):
            path = match.group(0).rstrip('.,;:!?)')
            if os.path.isfile(path):
                file_paths.append(path)

        return result_text, file_paths

    finally:
        if original_key:
            os.environ["ANTHROPIC_API_KEY"] = original_key


async def main():
    """Main entry point for daily health review."""
    logger.info("Starting daily health review...")

    try:
        # Get health data from Claude
        result_text, file_paths = await run_claude_health_query()

        if not result_text:
            result_text = "Unable to generate health review. Please check the health data skill."

        # Send the review
        today = datetime.now().strftime("%A, %B %d")
        header = f"<b>🌅 Good Morning! Health Review for {today}</b>\n\n"

        await send_telegram_message(header + result_text[:4000])

        # Send any generated charts
        for path in file_paths:
            await send_telegram_photo(path, f"📊 {os.path.basename(path)}")

        logger.info("Daily health review completed")

    except Exception as e:
        logger.error(f"Error in daily health review: {e}", exc_info=True)
        await send_telegram_message(f"❌ Daily health review failed: {str(e)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
