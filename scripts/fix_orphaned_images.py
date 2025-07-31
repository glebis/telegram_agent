#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fix_orphaned_images():
    """Fix orphaned images in the database by properly linking them to chats"""
    from sqlalchemy import select, update, text
    from src.core.database import get_db_session, init_database
    from src.models.image import Image
    from src.models.chat import Chat
    
    logger.info("Initializing database...")
    await init_database()
    
    try:
        async with get_db_session() as session:
            # 1. Find all orphaned images (images with no valid chat_id)
            orphaned_query = select(Image).outerjoin(Chat, Image.chat_id == Chat.id).where(Chat.id == None)
            result = await session.execute(orphaned_query)
            orphaned_images = result.scalars().all()
            
            logger.info(f"Found {len(orphaned_images)} orphaned images")
            
            if not orphaned_images:
                logger.info("No orphaned images found")
                return
            
            # 2. Get all available chats
            chats_query = select(Chat)
            result = await session.execute(chats_query)
            chats = result.scalars().all()
            
            if not chats:
                logger.warning("No chats found in database. Creating a default chat...")
                # Create a default chat if none exists
                default_chat = Chat(
                    chat_id=0,  # Default Telegram chat ID
                    user_id=0,  # Default user ID
                    username="default",
                    first_name="Default",
                    last_name="User",
                    current_mode="default",
                )
                session.add(default_chat)
                await session.commit()
                await session.refresh(default_chat)
                chats = [default_chat]
            
            default_chat = chats[0]
            logger.info(f"Using chat ID {default_chat.id} (Telegram chat ID: {default_chat.chat_id}) for orphaned images")
            
            # 3. Fix each orphaned image
            for img in orphaned_images:
                logger.info(f"Fixing image ID {img.id}, file_id: {img.file_id[:20]}...")
                
                # Fix chat_id
                img.chat_id = default_chat.id
                
                # Fix analysis JSON if invalid
                if img.analysis:
                    try:
                        json.loads(img.analysis)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in image {img.id}, resetting to empty object")
                        img.analysis = json.dumps({
                            "description": "Analysis data was corrupted and has been reset",
                            "cached": False
                        })
                else:
                    img.analysis = json.dumps({
                        "description": "No analysis data available",
                        "cached": False
                    })
                
                # Set processing status to completed if not already
                if img.processing_status != "completed":
                    img.processing_status = "completed"
                
                # Set default dimensions if missing
                if not img.width or not img.height:
                    img.width = 800
                    img.height = 600
                
                # Set default file size if missing
                if not img.file_size:
                    img.file_size = 0
                
                session.add(img)
            
            # Commit all changes
            await session.commit()
            logger.info(f"Fixed {len(orphaned_images)} orphaned images")
            
    except Exception as e:
        logger.error(f"Error fixing orphaned images: {e}")
        import traceback
        traceback.print_exc()

async def verify_fix():
    """Verify that the fix was applied correctly"""
    from sqlalchemy import select, func
    from src.core.database import get_db_session
    from src.models.image import Image
    from src.models.chat import Chat
    
    try:
        async with get_db_session() as session:
            # Check for any remaining orphaned images
            orphaned_query = select(func.count(Image.id)).outerjoin(Chat, Image.chat_id == Chat.id).where(Chat.id == None)
            result = await session.execute(orphaned_query)
            orphaned_count = result.scalar() or 0
            
            if orphaned_count > 0:
                logger.warning(f"Still found {orphaned_count} orphaned images after fix!")
            else:
                logger.info("No orphaned images found after fix - success!")
            
            # Check user-image relationships
            user_query = select(Chat.user_id, func.count(Image.id)).join(Image, Chat.id == Image.chat_id).group_by(Chat.user_id)
            result = await session.execute(user_query)
            user_counts = result.all()
            
            logger.info("Images by user after fix:")
            for user_id, count in user_counts:
                logger.info(f"  - User {user_id}: {count} images")
            
    except Exception as e:
        logger.error(f"Error verifying fix: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(fix_orphaned_images())
    asyncio.run(verify_fix())
