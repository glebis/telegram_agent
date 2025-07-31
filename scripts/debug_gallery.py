#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_gallery_for_user(user_id: int):
    """Debug gallery functionality for a specific user"""
    from sqlalchemy import select, func
    from src.core.database import get_db_session, init_database
    from src.models.image import Image
    from src.models.chat import Chat
    from src.services.gallery_service import get_gallery_service
    
    logger.info(f"Debugging gallery for user {user_id}")
    
    # Initialize database
    logger.info("Initializing database...")
    await init_database()
    
    try:
        # Get gallery service
        gallery_service = get_gallery_service()
        
        # Check user existence
        async with get_db_session() as session:
            user_query = select(Chat).where(Chat.user_id == user_id)
            result = await session.execute(user_query)
            user_chats = result.scalars().all()
            
            if not user_chats:
                logger.warning(f"No chats found for user {user_id}")
                return
            
            logger.info(f"Found {len(user_chats)} chats for user {user_id}")
            for chat in user_chats:
                logger.info(f"  - Chat ID: {chat.id}, Telegram Chat ID: {chat.chat_id}")
            
            # Check images for this user
            images_query = select(func.count(Image.id)).join(Image.chat).where(Chat.user_id == user_id)
            result = await session.execute(images_query)
            image_count = result.scalar() or 0
            
            logger.info(f"User {user_id} has {image_count} images in database")
            
            # Check completed images
            completed_query = select(func.count(Image.id)).join(Image.chat).where(
                Chat.user_id == user_id, 
                Image.processing_status == "completed"
            )
            result = await session.execute(completed_query)
            completed_count = result.scalar() or 0
            
            logger.info(f"User {user_id} has {completed_count} completed images")
            
            # List recent images
            recent_query = (
                select(Image)
                .join(Image.chat)
                .where(Chat.user_id == user_id)
                .order_by(Image.created_at.desc())
                .limit(5)
            )
            result = await session.execute(recent_query)
            recent_images = result.scalars().all()
            
            logger.info(f"Recent images for user {user_id}:")
            for img in recent_images:
                analysis_status = "Valid JSON" if img.analysis and is_valid_json(img.analysis) else "INVALID JSON"
                logger.info(f"  - ID: {img.id}, File ID: {img.file_id[:20]}..., Status: {img.processing_status}")
                logger.info(f"    Chat ID: {img.chat_id}, Analysis: {analysis_status}")
                logger.info(f"    Paths: Original={img.original_path}, Compressed={img.compressed_path}")
        
        # Test gallery pagination
        logger.info("Testing gallery pagination...")
        images, total_images, total_pages = await gallery_service.get_user_images_paginated(user_id=user_id, page=1)
        
        logger.info(f"Gallery pagination: {len(images)} images, {total_images} total, {total_pages} pages")
        
        # Format gallery page
        if images:
            formatted_page = gallery_service.format_gallery_page(
                images=images, page=1, total_pages=total_pages, total_images=total_images
            )
            logger.info("Gallery page formatted successfully:")
            logger.info(formatted_page)
        else:
            logger.warning("No images found for gallery display")
            
    except Exception as e:
        logger.error(f"Error debugging gallery: {e}")
        import traceback
        traceback.print_exc()

def is_valid_json(json_str: str) -> bool:
    """Check if a string is valid JSON"""
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

async def fix_image_paths():
    """Fix missing image paths in the database"""
    from sqlalchemy import select, update
    from src.core.database import get_db_session
    from src.models.image import Image
    
    logger.info("Fixing missing image paths...")
    
    try:
        async with get_db_session() as session:
            # Find images with missing paths
            missing_paths_query = select(Image).where(
                (Image.original_path == None) | 
                (Image.compressed_path == None)
            )
            result = await session.execute(missing_paths_query)
            images_with_missing_paths = result.scalars().all()
            
            logger.info(f"Found {len(images_with_missing_paths)} images with missing paths")
            
            # Fix each image
            for img in images_with_missing_paths:
                # Generate default paths based on file_id
                if not img.original_path:
                    img.original_path = f"data/images/original/{img.file_id[-10:]}.jpg"
                
                if not img.compressed_path:
                    img.compressed_path = f"data/images/processed/{img.file_id[-10:]}.jpg"
                
                session.add(img)
            
            # Commit changes
            await session.commit()
            logger.info(f"Fixed paths for {len(images_with_missing_paths)} images")
            
    except Exception as e:
        logger.error(f"Error fixing image paths: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Get user_id from command line or use default
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    
    # Run the debug function
    asyncio.run(fix_image_paths())
    asyncio.run(debug_gallery_for_user(user_id))
