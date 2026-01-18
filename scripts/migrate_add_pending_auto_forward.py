#!/usr/bin/env python3
"""
Migration script to add pending_auto_forward_claude column to chats table.

This script adds a new boolean column to support auto-forwarding messages to Claude
after the "New Session" button is pressed.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.core.database import get_db_session, init_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Add pending_auto_forward_claude column to chats table."""
    logger.info("Starting migration: add pending_auto_forward_claude column")

    try:
        await init_database()

        async with get_db_session() as session:
            # Check if column already exists
            check_query = """
                SELECT COUNT(*)
                FROM pragma_table_info('chats')
                WHERE name='pending_auto_forward_claude'
            """
            result = await session.execute(text(check_query))
            exists = result.scalar() > 0

            if exists:
                logger.info("Column pending_auto_forward_claude already exists, skipping migration")
                return

            # Add the new column
            alter_query = """
                ALTER TABLE chats
                ADD COLUMN pending_auto_forward_claude BOOLEAN
                DEFAULT 0 NOT NULL
            """
            await session.execute(text(alter_query))
            await session.commit()

            logger.info("Successfully added pending_auto_forward_claude column")

            # Verify the column was added
            verify_query = """
                SELECT COUNT(*)
                FROM pragma_table_info('chats')
                WHERE name='pending_auto_forward_claude'
            """
            result = await session.execute(text(verify_query))
            if result.scalar() > 0:
                logger.info("Migration verified successfully")
            else:
                logger.error("Migration verification failed")
                sys.exit(1)

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(migrate())
    logger.info("Migration completed successfully")
