#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def test_database_connection():
    """Test the database connection directly"""
    print("Testing database connection...")
    
    try:
        from src.core.database import get_database_url, init_database, health_check
        
        # Get database URL
        db_url = get_database_url()
        print(f"Database URL: {db_url}")
        
        # Initialize database
        print("Initializing database...")
        await init_database()
        print("Database initialized")
        
        # Check database health
        print("Checking database health...")
        is_healthy = await health_check()
        print(f"Database health: {'Healthy' if is_healthy else 'Unhealthy'}")
        
        return is_healthy
    except Exception as e:
        print(f"Error testing database: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_database_connection())
