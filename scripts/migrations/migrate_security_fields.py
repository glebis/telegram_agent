#!/usr/bin/env python3
"""
Apply security & privacy database migration.

Adds columns to existing tables:
- users: consent_given (bool), consent_given_at (datetime)
- user_settings: health_data_consent (bool)

Usage:
    python scripts/migrate_security_fields.py
"""

import asyncio
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import init_database, get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIGRATIONS = [
    ("users", "consent_given", "ALTER TABLE users ADD COLUMN consent_given BOOLEAN NOT NULL DEFAULT 0"),
    ("users", "consent_given_at", "ALTER TABLE users ADD COLUMN consent_given_at DATETIME"),
    ("user_settings", "health_data_consent", "ALTER TABLE user_settings ADD COLUMN health_data_consent BOOLEAN NOT NULL DEFAULT 0"),
]


async def main():
    await init_database()
    engine = get_engine()

    async with engine.begin() as conn:
        for table, column, sql in MIGRATIONS:
            # Check if column already exists
            result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
            columns = [row[1] for row in result.fetchall()]

            if column in columns:
                logger.info(f"Column {table}.{column} already exists, skipping")
                continue

            try:
                await conn.exec_driver_sql(sql)
                logger.info(f"Added {table}.{column}")
            except Exception as e:
                logger.error(f"Failed to add {table}.{column}: {e}")

    logger.info("Migration complete")


if __name__ == "__main__":
    asyncio.run(main())
