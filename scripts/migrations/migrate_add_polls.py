#!/usr/bin/env python3
"""
Database migration: Add poll_responses and poll_templates tables.

This script creates the tables needed for the polling system.
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.database import init_database, get_engine
from src.models.poll_response import PollResponse, PollTemplate
from src.models.base import Base

async def main():
    """Run migration."""
    print("🔧 Creating poll tables...")

    # Initialize database
    await init_database()
    engine = get_engine()

    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(PollResponse.__table__.create, checkfirst=True)
        await conn.run_sync(PollTemplate.__table__.create, checkfirst=True)

    print("✅ Poll tables created successfully!")
    print("")
    print("Tables created:")
    print("  - poll_responses")
    print("  - poll_templates")

if __name__ == "__main__":
    asyncio.run(main())
