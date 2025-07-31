#!/usr/bin/env python
"""
Fix script for gallery issues.
This script will:
1. Fix invalid mode values in the database
2. Ensure processing_status is set to 'completed'
3. Test the gallery command functionality
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Optional

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, text, update
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


async def fix_image_modes():
    """Fix invalid mode values in the database"""
    logger.info("Fixing invalid mode values...")
    
    try:
        async with get_db_session() as session:
            # Get all images
            result = await session.execute(select(Image))
            images = result.scalars().all()
            
            fixed_count = 0
            for image in images:
                # Check if mode is valid
                valid_modes = ["default", "artistic", "coach", "creative", "formal", "quick"]
                
                if image.mode_used not in valid_modes:
                    old_mode = image.mode_used
                    # Try to extract mode from analysis JSON if available
                    try:
                        if image.analysis:
                            analysis_data = json.loads(image.analysis)
                            if "mode" in analysis_data:
                                image.mode_used = analysis_data["mode"]
                            else:
                                # Default to "default" mode
                                image.mode_used = "default"
                        else:
                            # Default to "default" mode
                            image.mode_used = "default"
                        
                        fixed_count += 1
                        logger.info(f"Fixed image {image.id}: changed mode from '{old_mode}' to '{image.mode_used}'")
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse analysis JSON for image {image.id}")
                        image.mode_used = "default"
                        fixed_count += 1
            
            # Commit changes
            if fixed_count > 0:
                await session.commit()
                logger.info(f"✅ Fixed {fixed_count} images with invalid modes")
            else:
                logger.info("No images with invalid modes found")
            
            return fixed_count
    except Exception as e:
        logger.error(f"Error fixing image modes: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0


async def ensure_completed_status():
    """Ensure all images have processing_status='completed'"""
    logger.info("Ensuring all images have 'completed' status...")
    
    try:
        async with get_db_session() as session:
            # Update all non-completed images
            stmt = (
                update(Image)
                .where(Image.processing_status != "completed")
                .values(processing_status="completed")
            )
            result = await session.execute(stmt)
            await session.commit()
            
            updated = result.rowcount
            if updated > 0:
                logger.info(f"✅ Updated {updated} images to 'completed' status")
            else:
                logger.info("All images already have 'completed' status")
            
            return updated
    except Exception as e:
        logger.error(f"Error updating image status: {e}")
        return 0


async def test_gallery_display():
    """Test the gallery display for a user"""
    logger.info("Testing gallery display...")
    
    try:
        # Get a user_id from the database
        async with get_db_session() as session:
            chat_result = await session.execute(select(Chat).limit(1))
            chat = chat_result.scalar_one_or_none()
            
            if not chat:
                logger.error("No chat records found, cannot test gallery")
                return False
            
            user_id = chat.user_id
        
        # Test gallery service
        gallery_service = get_gallery_service()
        images, total_images, total_pages = await gallery_service.get_user_images_paginated(
            user_id=user_id, page=1, per_page=10
        )
        
        if not images:
            logger.warning(f"No images found for user {user_id}")
            return False
        
        # Test gallery formatting
        formatted = gallery_service.format_gallery_page(
            images=images, page=1, total_pages=total_pages, total_images=total_images
        )
        
        # Check if the formatted text contains the "No images found" message
        if "No images found" in formatted:
            logger.error("Gallery still showing 'No images found' message")
            return False
        
        logger.info(f"✅ Gallery successfully displays {len(images)} images")
        logger.info("Sample gallery output:")
        logger.info("---")
        logger.info(formatted[:500] + "..." if len(formatted) > 500 else formatted)
        logger.info("---")
        
        return True
    except Exception as e:
        logger.error(f"Error testing gallery display: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def fix_analysis_json():
    """Fix any invalid JSON in the analysis field"""
    logger.info("Checking for invalid JSON in analysis field...")
    
    try:
        async with get_db_session() as session:
            # Get all images
            result = await session.execute(select(Image))
            images = result.scalars().all()
            
            fixed_count = 0
            for image in images:
                if not image.analysis:
                    continue
                
                try:
                    # Try to parse the JSON
                    json.loads(image.analysis)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON found in image {image.id}")
                    # Create a simple valid JSON object
                    image.analysis = json.dumps({
                        "description": "Analysis data could not be parsed",
                        "tags": ["error", "fixed"],
                        "mode": image.mode_used or "default"
                    })
                    fixed_count += 1
            
            # Commit changes
            if fixed_count > 0:
                await session.commit()
                logger.info(f"✅ Fixed {fixed_count} images with invalid JSON")
            else:
                logger.info("No images with invalid JSON found")
            
            return fixed_count
    except Exception as e:
        logger.error(f"Error fixing JSON: {e}")
        return 0


async def main():
    """Main function"""
    logger.info("=== Starting Gallery Fix Tool ===")
    
    # Step 1: Fix invalid mode values
    await fix_image_modes()
    
    # Step 2: Fix any invalid JSON
    await fix_analysis_json()
    
    # Step 3: Ensure all images have completed status
    await ensure_completed_status()
    
    # Step 4: Test gallery display
    success = await test_gallery_display()
    
    if success:
        logger.info("✅ Gallery fix completed successfully!")
        logger.info("""
NEXT STEPS:
1. Try using the /gallery command in your Telegram bot
2. Images should now appear correctly
3. If issues persist, check the bot logs for errors
""")
    else:
        logger.error("❌ Gallery fix did not resolve all issues")
        logger.error("""
TROUBLESHOOTING:
1. Check if the bot has permission to send messages
2. Verify the database is accessible to the bot
3. Look for errors in the bot logs
4. Try sending a new image to see if it appears in the gallery
""")
    
    logger.info("=== Gallery Fix Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
