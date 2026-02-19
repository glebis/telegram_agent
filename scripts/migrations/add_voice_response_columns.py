#!/usr/bin/env python3
"""
Add voice response mode columns to chats table.

Adds:
- voice_response_mode (always_voice, smart, voice_on_request, text_only)
- voice_name (diana, hannah, autumn, austin, daniel, troy)
- voice_emotion (cheerful, neutral, whisper)

Usage:
    python scripts/add_voice_response_columns.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.core.database import get_db_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_columns_exist():
    """Check if columns already exist."""
    async with get_db_session() as session:
        result = await session.execute(text("PRAGMA table_info(chats)"))
        columns = [row[1] for row in result.fetchall()]

        has_mode = "voice_response_mode" in columns
        has_name = "voice_name" in columns
        has_emotion = "voice_emotion" in columns

        logger.info(f"Column check: voice_response_mode={has_mode}, voice_name={has_name}, voice_emotion={has_emotion}")
        return has_mode and has_name and has_emotion


async def add_columns():
    """Add voice response columns to chats table."""
    async with get_db_session() as session:
        try:
            # Add voice_response_mode column
            logger.info("Adding voice_response_mode column...")
            await session.execute(
                text("ALTER TABLE chats ADD COLUMN voice_response_mode VARCHAR(20) DEFAULT 'text_only' NOT NULL")
            )

            # Add voice_name column
            logger.info("Adding voice_name column...")
            await session.execute(
                text("ALTER TABLE chats ADD COLUMN voice_name VARCHAR(20) DEFAULT 'diana' NOT NULL")
            )

            # Add voice_emotion column
            logger.info("Adding voice_emotion column...")
            await session.execute(
                text("ALTER TABLE chats ADD COLUMN voice_emotion VARCHAR(20) DEFAULT 'cheerful' NOT NULL")
            )

            await session.commit()
            logger.info("✅ Columns added successfully")
            return True

        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.info("Columns already exist, skipping...")
                return True
            else:
                logger.error(f"Error adding columns: {e}")
                raise


async def main():
    """Main migration function."""
    try:
        logger.info("=" * 60)
        logger.info("Adding Voice Response Columns to Chats Table")
        logger.info("=" * 60)

        # Check if columns already exist
        if await check_columns_exist():
            logger.info("\n✅ All columns already exist, no migration needed")
            return 0

        # Add columns
        logger.info("\nAdding new columns...")
        await add_columns()

        # Verify columns were added
        if await check_columns_exist():
            logger.info("\n" + "=" * 60)
            logger.info("✅ Migration completed successfully!")
            logger.info("=" * 60)
            logger.info("\nNew columns added to chats table:")
            logger.info("  • voice_response_mode - Voice response behavior (text_only, smart, always_voice, voice_on_request)")
            logger.info("  • voice_name - Voice model (diana, hannah, autumn, austin, daniel, troy)")
            logger.info("  • voice_emotion - Emotion style (cheerful, neutral, whisper)")
            logger.info("\nNext steps:")
            logger.info("  1. Restart the bot to pick up schema changes")
            logger.info("  2. Use /voice_settings to configure voice preferences")
            logger.info("\n")
            return 0
        else:
            logger.error("\n❌ Migration failed - columns not found after adding")
            return 1

    except Exception as e:
        logger.error(f"\n❌ Migration failed with error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
