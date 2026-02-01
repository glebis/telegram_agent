#!/usr/bin/env python3
"""
Migration script to add voice and accountability system tables.

This script will:
1. Check for existing tables
2. Create new tables if they don't exist
3. Add indexes for performance
4. Verify migration success
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect, text
from src.core.database import init_database, get_db_session, get_engine
from src.models import (
    UserSettings,
    Tracker,
    CheckIn,
    AccountabilityPartner,
    PartnerTrackerOverride,
    PartnerNotificationSchedule,
    PartnerQuietHours,
    PartnerPermission,
    PartnerNotification,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_tables_exist() -> dict:
    """Check which tables already exist."""
    engine = get_engine()

    async with engine.connect() as conn:
        inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))
        tables = await conn.run_sync(lambda sync_conn: inspector.get_table_names())

    new_tables = {
        "user_settings": "user_settings" in tables,
        "trackers": "trackers" in tables,
        "check_ins": "check_ins" in tables,
        "accountability_partners": "accountability_partners" in tables,
        "partner_tracker_overrides": "partner_tracker_overrides" in tables,
        "partner_notification_schedule": "partner_notification_schedule" in tables,
        "partner_quiet_hours": "partner_quiet_hours" in tables,
        "partner_permissions": "partner_permissions" in tables,
        "partner_notifications": "partner_notifications" in tables,
    }

    return new_tables


async def create_tables():
    """Create all new tables using SQLAlchemy metadata."""
    from src.models.base import Base

    engine = get_engine()

    logger.info("Creating new tables...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("✅ Tables created successfully")


async def create_indexes():
    """Create indexes for better query performance."""
    logger.info("Creating indexes...")

    async with get_db_session() as session:
        # Indexes for trackers
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_trackers_user_id
            ON trackers(user_id)
        """)
        )
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_trackers_active
            ON trackers(active)
        """)
        )

        # Indexes for check_ins
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_check_ins_user_id
            ON check_ins(user_id)
        """)
        )
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_check_ins_tracker_id
            ON check_ins(tracker_id)
        """)
        )
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_check_ins_created_at
            ON check_ins(created_at)
        """)
        )

        # Indexes for accountability_partners
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_accountability_partners_user_id
            ON accountability_partners(user_id)
        """)
        )
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_accountability_partners_partner_id
            ON accountability_partners(partner_telegram_id)
        """)
        )
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_accountability_partners_active
            ON accountability_partners(active)
        """)
        )

        # Indexes for partner notifications
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_partner_notifications_partnership_id
            ON partner_notifications(partnership_id)
        """)
        )
        await session.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_partner_notifications_created_at
            ON partner_notifications(created_at)
        """)
        )

        await session.commit()

    logger.info("✅ Indexes created successfully")


async def verify_migration():
    """Verify that migration was successful."""
    logger.info("Verifying migration...")

    tables = await check_tables_exist()

    all_exist = all(tables.values())

    if all_exist:
        logger.info("✅ All tables verified successfully")
        logger.info("\nCreated tables:")
        for table_name in tables.keys():
            logger.info(f"  - {table_name}")
        return True
    else:
        logger.error("❌ Some tables are missing:")
        for table_name, exists in tables.items():
            status = "✅" if exists else "❌"
            logger.error(f"  {status} {table_name}")
        return False


async def main():
    """Run migration."""
    logger.info("=" * 60)
    logger.info("Voice & Accountability System Migration")
    logger.info("=" * 60)

    # Initialize database connection
    logger.info("\n1. Initializing database connection...")
    await init_database()

    # Check existing tables
    logger.info("\n2. Checking existing tables...")
    existing_tables = await check_tables_exist()
    existing_count = sum(existing_tables.values())
    logger.info(f"Found {existing_count}/{len(existing_tables)} tables already exist")

    if existing_count == len(existing_tables):
        logger.info("⚠️  All tables already exist. No migration needed.")
        return

    # Create new tables
    logger.info("\n3. Creating new tables...")
    await create_tables()

    # Create indexes
    logger.info("\n4. Creating indexes...")
    await create_indexes()

    # Verify migration
    logger.info("\n5. Verifying migration...")
    success = await verify_migration()

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("✅ Migration completed successfully!")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Restart the Telegram bot")
        logger.info("2. Test voice synthesis with /voice_settings")
        logger.info("3. Add trackers with /trackers")
        logger.info("4. Configure accountability partners with /partners")
    else:
        logger.error("\n" + "=" * 60)
        logger.error("❌ Migration failed - see errors above")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
