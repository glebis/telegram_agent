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

async def check_images_in_db():
    """Check if there are any images in the database"""
    print("\nChecking for images in the database...")
    
    try:
        from sqlalchemy import select, func, text
        from src.core.database import get_db_session
        from src.models.image import Image
        from src.models.chat import Chat
        
        async with get_db_session() as session:
            # Check if images table exists
            try:
                # Use raw SQL to check if table exists
                check_table_query = text("SELECT name FROM sqlite_master WHERE type='table' AND name='images'")
                result = await session.execute(check_table_query)
                table_exists = result.scalar() is not None
                print(f"Images table exists: {table_exists}")
                
                if not table_exists:
                    print("⚠️ The 'images' table doesn't exist in the database!")
                    print("This indicates the database schema hasn't been properly initialized.")
                    return False
            except Exception as e:
                print(f"Error checking table existence: {e}")
            
            # Count total images
            count_query = select(func.count(Image.id))
            result = await session.execute(count_query)
            total_images = result.scalar() or 0
            print(f"Total images in database: {total_images}")
            
            # Get images by processing status
            status_query = select(Image.processing_status, func.count(Image.id)).group_by(Image.processing_status)
            result = await session.execute(status_query)
            status_counts = result.all()
            print("Images by status:")
            if status_counts:
                for status, count in status_counts:
                    print(f"  - {status}: {count}")
            else:
                print("  No images found with any status")
            
            # Get a sample of recent images if any exist
            if total_images > 0:
                images_query = select(Image).order_by(Image.created_at.desc()).limit(5)
                result = await session.execute(images_query)
                recent_images = result.scalars().all()
                
                print("\nRecent images:")
                for img in recent_images:
                    print(f"  - ID: {img.id}, File ID: {img.file_id[:20]}..., Status: {img.processing_status}")
                    print(f"    Mode: {img.mode_used or 'N/A'}, Chat ID: {img.chat_id}")
                    print(f"    File paths: Original={img.original_path}, Compressed={img.compressed_path}")
                    print(f"    Dimensions: {img.width}x{img.height}, Size: {img.file_size or 0} bytes")
                    print(f"    Created: {img.created_at}")
                    
                    # Check if analysis is valid JSON
                    if img.analysis:
                        try:
                            import json
                            analysis = json.loads(img.analysis)
                            print(f"    Analysis: Valid JSON with {len(analysis)} keys")
                        except json.JSONDecodeError:
                            print(f"    Analysis: INVALID JSON")
                    else:
                        print(f"    Analysis: None")
                    print("")
            else:
                print("\n⚠️ No images found in the database!")
                print("Possible reasons:")
                print("  1. No images have been uploaded yet")
                print("  2. Image processing is failing")
                print("  3. Database storage is not working correctly")
            
            # Check if there are any completed images
            completed_query = select(func.count(Image.id)).where(Image.processing_status == "completed")
            result = await session.execute(completed_query)
            completed_images = result.scalar() or 0
            print(f"\nCompleted images: {completed_images}")
            
            if completed_images == 0 and total_images > 0:
                print("⚠️ There are images in the database but none are marked as 'completed'")
                print("This could indicate that image processing is failing or not finishing properly.")
            
            # Check user-image relationships
            user_query = select(Chat.user_id, func.count(Image.id)).join(Image, Chat.id == Image.chat_id, isouter=True).group_by(Chat.user_id)
            result = await session.execute(user_query)
            user_counts = result.all()
            print("\nImages by user:")
            if user_counts:
                for user_id, count in user_counts:
                    print(f"  - User {user_id}: {count} images")
            else:
                print("  No users with images found")
                
                # Check if there are any users at all
                users_query = select(func.count(Chat.id))
                result = await session.execute(users_query)
                total_users = result.scalar() or 0
                print(f"  Total users in database: {total_users}")
            
            # Check for orphaned images (no associated chat)
            orphaned_query = select(func.count(Image.id)).outerjoin(Chat).where(Chat.id == None)
            result = await session.execute(orphaned_query)
            orphaned_images = result.scalar() or 0
            if orphaned_images > 0:
                print(f"\n⚠️ Found {orphaned_images} orphaned images with no associated chat!")
            
            return total_images > 0
    except Exception as e:
        print(f"Error checking images: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_database_connection())
    asyncio.run(check_images_in_db())
