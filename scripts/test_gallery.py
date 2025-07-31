#!/usr/bin/env python
"""
Test script to diagnose and fix image gallery issues.
This script will:
1. Check database connectivity
2. Verify image records exist in the database
3. Test the gallery service's ability to retrieve images
4. Insert a test image if no images are found
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from src.core.database import get_db_session
from src.models.chat import Chat
from src.models.image import Image
from src.services.gallery_service import get_gallery_service

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_database_connection():
    """Check if the database connection is working"""
    logger.info("Checking database connection...")
    try:
        async with get_db_session() as session:
            # Simple query to check connection
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            if value == 1:
                logger.info("✅ Database connection successful")
                return True
            else:
                logger.error("❌ Database connection failed: unexpected result")
                return False
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


async def count_images():
    """Count the number of images in the database"""
    logger.info("Counting images in database...")
    try:
        async with get_db_session() as session:
            # Count images
            result = await session.execute(select(func.count(Image.id)))
            count = result.scalar() or 0
            logger.info(f"Found {count} images in database")
            return count
    except Exception as e:
        logger.error(f"Error counting images: {e}")
        return 0


async def check_chat_records():
    """Check if there are chat records in the database"""
    logger.info("Checking chat records...")
    try:
        async with get_db_session() as session:
            # Count chats
            result = await session.execute(select(func.count(Chat.id)))
            count = result.scalar() or 0
            logger.info(f"Found {count} chat records in database")
            
            # Get a sample chat if any exist
            if count > 0:
                chat_result = await session.execute(select(Chat).limit(1))
                chat = chat_result.scalar_one_or_none()
                if chat:
                    logger.info(f"Sample chat: ID={chat.id}, chat_id={chat.chat_id}, user_id={chat.user_id}")
            
            return count
    except Exception as e:
        logger.error(f"Error checking chat records: {e}")
        return 0


async def test_gallery_service(user_id=None):
    """Test the gallery service's ability to retrieve images"""
    logger.info("Testing gallery service...")
    
    if user_id is None:
        # Try to get a user_id from the database
        try:
            async with get_db_session() as session:
                chat_result = await session.execute(select(Chat).limit(1))
                chat = chat_result.scalar_one_or_none()
                if chat:
                    user_id = chat.user_id
                    logger.info(f"Using user_id {user_id} from database")
                else:
                    user_id = 12345  # Default test user ID
                    logger.info(f"No chats found, using default test user_id {user_id}")
        except Exception as e:
            logger.error(f"Error getting user_id: {e}")
            user_id = 12345  # Default test user ID
    
    try:
        gallery_service = get_gallery_service()
        images, total_images, total_pages = await gallery_service.get_user_images_paginated(
            user_id=user_id, page=1, per_page=10
        )
        
        logger.info(f"Gallery service returned {len(images)} images (total: {total_images})")
        
        if images:
            logger.info("Sample image data:")
            logger.info(f"ID: {images[0]['id']}")
            logger.info(f"File ID: {images[0]['file_id']}")
            logger.info(f"Mode: {images[0]['mode_used']}")
            logger.info(f"Created: {images[0]['created_at']}")
            
            # Test formatting
            formatted = gallery_service.format_gallery_page(
                images=images, page=1, total_pages=total_pages, total_images=total_images
            )
            logger.info("Gallery formatting successful")
        else:
            logger.warning("No images returned by gallery service")
            
        return images, total_images, total_pages
    except Exception as e:
        logger.error(f"Error testing gallery service: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return [], 0, 0


async def insert_test_image(user_id=None):
    """Insert a test image into the database"""
    logger.info("Inserting test image...")
    
    if user_id is None:
        # Try to get a user_id from the database
        try:
            async with get_db_session() as session:
                chat_result = await session.execute(select(Chat).limit(1))
                chat = chat_result.scalar_one_or_none()
                if chat:
                    user_id = chat.user_id
                    chat_id = chat.id  # Database ID, not Telegram chat_id
                    logger.info(f"Using existing chat: id={chat_id}, user_id={user_id}")
                else:
                    # Create a new chat record
                    user_id = 12345  # Default test user ID
                    telegram_chat_id = 67890  # Default test chat ID
                    logger.info(f"No chats found, creating test chat with user_id={user_id}")
                    
                    chat = Chat(
                        chat_id=telegram_chat_id,
                        user_id=user_id,
                        username="test_user",
                        first_name="Test",
                        last_name="User",
                        current_mode="default",
                        current_preset=None
                    )
                    session.add(chat)
                    await session.commit()
                    await session.refresh(chat)
                    chat_id = chat.id
                    logger.info(f"Created new chat: id={chat_id}, user_id={user_id}")
        except Exception as e:
            logger.error(f"Error getting/creating chat: {e}")
            return False
    
    try:
        # Create a test analysis object
        analysis = {
            "description": "This is a test image for gallery functionality",
            "tags": ["test", "gallery", "debug"],
            "confidence": 0.95,
            "processing_time": 1.2,
            "dimensions": {"original": [800, 600], "processed": [800, 600]},
            "file_size": 12345,
            "telegram_file_info": {
                "file_id": "test_file_id_" + datetime.now().strftime("%Y%m%d%H%M%S"),
                "file_unique_id": "test_unique_id_" + datetime.now().strftime("%Y%m%d%H%M%S"),
            }
        }
        
        async with get_db_session() as session:
            # Create image record
            image = Image(
                chat_id=chat_id,  # Use the database ID, not the Telegram chat_id
                file_id=analysis["telegram_file_info"]["file_id"],
                file_unique_id=analysis["telegram_file_info"]["file_unique_id"],
                file_size=analysis["file_size"],
                width=analysis["dimensions"]["processed"][0],
                height=analysis["dimensions"]["processed"][1],
                format="jpg",
                analysis=json.dumps(analysis),
                mode_used="default",
                preset_used=None,
                processing_status="completed"  # Important: must be "completed" to show in gallery
            )
            
            session.add(image)
            await session.commit()
            await session.refresh(image)
            
            logger.info(f"✅ Test image inserted successfully with ID {image.id}")
            return True
    except Exception as e:
        logger.error(f"Error inserting test image: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def fix_orphaned_images():
    """Fix images with invalid chat_id references"""
    logger.info("Checking for orphaned images...")
    
    try:
        async with get_db_session() as session:
            # Find images with chat_id that doesn't exist in chats table
            query = """
            SELECT i.id, i.chat_id, i.file_id 
            FROM images i 
            LEFT JOIN chats c ON i.chat_id = c.id 
            WHERE c.id IS NULL
            """
            result = await session.execute(text(query))
            orphaned = result.all()
            
            if not orphaned:
                logger.info("✅ No orphaned images found")
                return 0
                
            logger.warning(f"Found {len(orphaned)} orphaned images")
            
            # Get a valid chat_id to reassign to
            chat_result = await session.execute(select(Chat).limit(1))
            chat = chat_result.scalar_one_or_none()
            
            if not chat:
                logger.error("No valid chat found to reassign orphaned images")
                return 0
                
            valid_chat_id = chat.id
            logger.info(f"Will reassign orphaned images to chat_id={valid_chat_id}")
            
            # Update orphaned images
            fixed = 0
            for orphan in orphaned:
                try:
                    update_query = text(f"UPDATE images SET chat_id = :chat_id WHERE id = :image_id")
                    await session.execute(update_query, {"chat_id": valid_chat_id, "image_id": orphan.id})
                    fixed += 1
                except Exception as e:
                    logger.error(f"Error fixing orphaned image {orphan.id}: {e}")
            
            await session.commit()
            logger.info(f"✅ Fixed {fixed} orphaned images")
            return fixed
    except Exception as e:
        logger.error(f"Error fixing orphaned images: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0


async def check_processing_status():
    """Check for images with non-completed processing status"""
    logger.info("Checking image processing status...")
    
    try:
        async with get_db_session() as session:
            # Count images by processing status
            query = text("""
            SELECT processing_status, COUNT(*) as count 
            FROM images 
            GROUP BY processing_status
            """)
            result = await session.execute(query)
            status_counts = result.all()
            
            for status, count in status_counts:
                logger.info(f"Status '{status}': {count} images")
                
            # Fix any stuck "pending" or "processing" images that are older than 1 hour
            update_query = text("""
            UPDATE images 
            SET processing_status = 'completed' 
            WHERE processing_status IN ('pending', 'processing') 
            AND created_at < datetime('now', '-1 hour')
            """)
            result = await session.execute(update_query)
            await session.commit()
            
            rows_updated = result.rowcount if hasattr(result, 'rowcount') else 0
            if rows_updated > 0:
                logger.info(f"✅ Fixed {rows_updated} stuck images")
                
            return status_counts
    except Exception as e:
        logger.error(f"Error checking processing status: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


async def main():
    """Main function"""
    logger.info("=== Starting Gallery Diagnostic Tool ===")
    
    # Step 1: Check database connection
    db_ok = await check_database_connection()
    if not db_ok:
        logger.error("Database connection failed, cannot proceed")
        return
    
    # Step 2: Check chat records
    chat_count = await check_chat_records()
    
    # Step 3: Count images
    image_count = await count_images()
    
    # Step 4: Fix orphaned images if any
    if image_count > 0:
        await fix_orphaned_images()
    
    # Step 5: Check processing status
    await check_processing_status()
    
    # Step 6: Test gallery service
    images, total_images, total_pages = await test_gallery_service()
    
    # Step 7: Insert test image if needed
    if total_images == 0:
        logger.info("No images found, inserting test image...")
        success = await insert_test_image()
        if success:
            # Test gallery service again
            await test_gallery_service()
    
    logger.info("=== Gallery Diagnostic Complete ===")
    
    if total_images == 0:
        logger.info("""
RECOMMENDATION:
1. Make sure DEBUG=true is set in your environment
2. Try sending an image to the bot
3. Check the logs for any errors in image processing
4. Run this script again to verify the image was saved
""")


if __name__ == "__main__":
    asyncio.run(main())
