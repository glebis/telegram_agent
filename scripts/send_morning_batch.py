#!/usr/bin/env python3
"""
Send Morning SRS Batch Script
Called by cron to send morning review cards
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from telegram import Bot
from telegram.ext import ApplicationBuilder
from src.bot.adapters.telegram_keyboard_builder import TelegramKeyboardBuilder
from src.services.srs.srs_scheduler import should_send_morning_batch, send_morning_batch, get_config
from src.services.srs_service import srs_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def send_batch():
    """Send morning batch of SRS cards."""
    try:
        # Check if batch should be sent
        if not should_send_morning_batch():
            logger.info("Morning batch already sent today or not time yet")
            return

        # Get bot token from env
        import os
        from dotenv import load_dotenv

        env_path = project_root / '.env'
        load_dotenv(env_path)

        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN not found in .env")
            return

        # Get chat ID from config
        chat_id = get_config('telegram_chat_id')
        if not chat_id:
            logger.error("telegram_chat_id not configured in SRS database")
            return

        # Create bot application
        application = ApplicationBuilder().token(token).build()

        # Inject keyboard builder (normally done by bot.py at startup,
        # but this script runs standalone outside the bot process)
        srs_service.keyboard_builder = TelegramKeyboardBuilder()

        # Send morning batch
        logger.info(f"Sending morning batch to chat {chat_id}")
        count = await srs_service.send_morning_batch(int(chat_id), application)

        logger.info(f"Successfully sent {count} cards")

    except Exception as e:
        logger.error(f"Error sending morning batch: {e}", exc_info=True)


if __name__ == '__main__':
    asyncio.run(send_batch())
