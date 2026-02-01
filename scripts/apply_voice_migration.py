#!/usr/bin/env python3
"""
Apply voice and accountability system database migration.

This script creates the new tables for:
- UserSettings (voice preferences)
- Tracker (habits, medications, values, commitments)
- CheckIn (tracker completion records)
- AccountabilityPartner (social accountability)
- Supporting tables for notifications and permissions

Usage:
    python scripts/apply_voice_migration.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import init_database, get_db_session
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
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def verify_tables_created():
    """Verify that all new tables were created successfully."""
    from sqlalchemy import text

    async with get_db_session() as session:
        # Check each table exists
        tables_to_check = [
            "user_settings",
            "trackers",
            "check_ins",
            "accountability_partners",
            "partner_tracker_overrides",
            "partner_notification_schedule",
            "partner_quiet_hours",
            "partner_permissions",
            "partner_notifications",
        ]

        logger.info("Verifying tables were created...")

        for table_name in tables_to_check:
            try:
                result = await session.execute(
                    text(
                        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
                    )
                )
                exists = result.scalar() is not None

                if exists:
                    logger.info(f"✅ Table '{table_name}' exists")
                else:
                    logger.error(f"❌ Table '{table_name}' NOT FOUND")
                    return False
            except Exception as e:
                logger.error(f"Error checking table {table_name}: {e}")
                return False

        return True


async def create_test_data():
    """Create sample test data to verify functionality."""
    async with get_db_session() as session:
        logger.info("Creating sample test data...")

        # Create test user settings
        test_settings = UserSettings(
            user_id=123456789,  # Test user ID
            username="test_user",
            voice_enabled=True,
            voice_model="diana",
            emotion_style="cheerful",
            response_mode="smart",
            check_in_times='["09:00", "21:00"]',
            reminder_style="gentle",
            timezone="UTC",
            privacy_level="private",
        )
        session.add(test_settings)

        # Create test tracker
        test_tracker = Tracker(
            user_id=123456789,
            type="habit",
            name="Morning Meditation",
            description="10 minutes of mindfulness",
            check_frequency="daily",
            check_time="09:00",
            active=True,
        )
        session.add(test_tracker)

        await session.commit()
        logger.info("✅ Sample test data created")


async def main():
    """Main migration function."""
    try:
        logger.info("=" * 60)
        logger.info("Starting Voice & Accountability System Migration")
        logger.info("=" * 60)

        # Initialize database (this will create all tables)
        logger.info("\nInitializing database and creating tables...")
        await init_database()

        # Verify tables were created
        logger.info("\nVerifying table creation...")
        tables_ok = await verify_tables_created()

        if not tables_ok:
            logger.error("\n❌ Migration failed - some tables missing")
            return 1

        # Create sample test data
        logger.info("\nCreating sample test data...")
        await create_test_data()

        logger.info("\n" + "=" * 60)
        logger.info("✅ Migration completed successfully!")
        logger.info("=" * 60)
        logger.info("\nNew tables created:")
        logger.info("  • user_settings - Voice and assistant preferences")
        logger.info("  • trackers - Habits, medications, values, commitments")
        logger.info("  • check_ins - Tracker completion records")
        logger.info("  • accountability_partners - Social accountability")
        logger.info("  • partner_tracker_overrides - Per-tracker privacy")
        logger.info("  • partner_notification_schedule - Notification timing")
        logger.info("  • partner_quiet_hours - Do not disturb settings")
        logger.info("  • partner_permissions - Granular access control")
        logger.info("  • partner_notifications - Delivery history")
        logger.info("\nSample test data created for user_id=123456789")
        logger.info("\nNext steps:")
        logger.info("  1. Test voice synthesis with /voice_settings command")
        logger.info("  2. Add trackers with /trackers command")
        logger.info("  3. Configure accountability partners")
        logger.info("\n")

        return 0

    except Exception as e:
        logger.error(f"\n❌ Migration failed with error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
