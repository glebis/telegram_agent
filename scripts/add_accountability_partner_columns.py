#!/usr/bin/env python3
"""
Add virtual accountability partner columns to chats table.

Adds:
- partner_personality (gentle, supportive, direct, assertive, tough_love)
- partner_voice_override (optional voice override)
- check_in_time (HH:MM format)
- struggle_threshold (consecutive misses before alert)
- celebration_style (quiet, moderate, enthusiastic)
- auto_adjust_personality (AI-suggested personality changes)

Usage:
    python scripts/add_accountability_partner_columns.py
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

        has_personality = "partner_personality" in columns
        has_voice_override = "partner_voice_override" in columns
        has_check_in_time = "check_in_time" in columns
        has_struggle_threshold = "struggle_threshold" in columns
        has_celebration_style = "celebration_style" in columns
        has_auto_adjust = "auto_adjust_personality" in columns

        logger.info(
            f"Column check: partner_personality={has_personality}, "
            f"partner_voice_override={has_voice_override}, "
            f"check_in_time={has_check_in_time}, "
            f"struggle_threshold={has_struggle_threshold}, "
            f"celebration_style={has_celebration_style}, "
            f"auto_adjust_personality={has_auto_adjust}"
        )

        return all([
            has_personality,
            has_voice_override,
            has_check_in_time,
            has_struggle_threshold,
            has_celebration_style,
            has_auto_adjust,
        ])


async def add_columns():
    """Add accountability partner columns to chats table."""
    async with get_db_session() as session:
        try:
            # Add partner_personality column
            logger.info("Adding partner_personality column...")
            await session.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN partner_personality VARCHAR(50) DEFAULT 'supportive' NOT NULL"
                )
            )

            # Add partner_voice_override column
            logger.info("Adding partner_voice_override column...")
            await session.execute(
                text("ALTER TABLE chats ADD COLUMN partner_voice_override VARCHAR(50)")
            )

            # Add check_in_time column
            logger.info("Adding check_in_time column...")
            await session.execute(
                text("ALTER TABLE chats ADD COLUMN check_in_time VARCHAR(10) DEFAULT '19:00' NOT NULL")
            )

            # Add struggle_threshold column
            logger.info("Adding struggle_threshold column...")
            await session.execute(
                text("ALTER TABLE chats ADD COLUMN struggle_threshold INTEGER DEFAULT 3 NOT NULL")
            )

            # Add celebration_style column
            logger.info("Adding celebration_style column...")
            await session.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN celebration_style VARCHAR(50) DEFAULT 'moderate' NOT NULL"
                )
            )

            # Add auto_adjust_personality column
            logger.info("Adding auto_adjust_personality column...")
            await session.execute(
                text("ALTER TABLE chats ADD COLUMN auto_adjust_personality BOOLEAN DEFAULT 0 NOT NULL")
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
        logger.info("Adding Virtual Accountability Partner Columns to Chats Table")
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
            logger.info("  • partner_personality - AI partner personality level")
            logger.info("      Options: gentle, supportive (default), direct, assertive, tough_love")
            logger.info("  • partner_voice_override - Optional voice override (NULL = use personality default)")
            logger.info("  • check_in_time - Daily check-in time (default: 19:00)")
            logger.info("  • struggle_threshold - Consecutive misses before alert (default: 3)")
            logger.info("  • celebration_style - Milestone celebration intensity")
            logger.info("      Options: quiet, moderate (default), enthusiastic")
            logger.info("  • auto_adjust_personality - AI suggests personality changes (default: False)")
            logger.info("\nNext steps:")
            logger.info("  1. Restart the bot to pick up schema changes")
            logger.info("  2. Use /settings → Accountability Partners to configure")
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
