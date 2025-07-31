#!/usr/bin/env python
"""
Fix script for image mode values in the database.
This script properly fixes mode values to ensure they match expected formats.
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
from src.models.image import Image

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def fix_image_modes():
    """Fix mode values in the database to standard values"""
    logger.info("Fixing image mode values...")
    
    valid_modes = ["default", "artistic", "coach", "creative", "formal", "quick"]
    
    try:
        async with get_db_session() as session:
            # Get all images
            result = await session.execute(select(Image))
            images = result.scalars().all()
            
            fixed_count = 0
            for image in images:
                # Check if mode is valid
                current_mode = image.mode_used
                if current_mode not in valid_modes:
                    # Try to extract mode from analysis JSON if available
                    try:
                        if image.analysis:
                            analysis_data = json.loads(image.analysis)
                            if "mode" in analysis_data and analysis_data["mode"] in valid_modes:
                                new_mode = analysis_data["mode"]
                            else:
                                # Default to "default" mode
                                new_mode = "default"
                        else:
                            # Default to "default" mode
                            new_mode = "default"
                        
                        # Update the mode
                        image.mode_used = new_mode
                        fixed_count += 1
                        logger.info(f"Fixed image {image.id}: changed mode from '{current_mode}' to '{new_mode}'")
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse analysis JSON for image {image.id}")
                        image.mode_used = "default"
                        fixed_count += 1
                
                # Also fix analysis JSON if needed
                if image.analysis:
                    try:
                        analysis_data = json.loads(image.analysis)
                        
                        # If mode in analysis doesn't match the image mode, update it
                        if "mode" not in analysis_data or analysis_data["mode"] != image.mode_used:
                            analysis_data["mode"] = image.mode_used
                            image.analysis = json.dumps(analysis_data)
                            fixed_count += 1
                            logger.info(f"Updated mode in analysis JSON for image {image.id}")
                    except json.JSONDecodeError:
                        # Create a simple valid JSON object
                        image.analysis = json.dumps({
                            "description": "This image was analyzed with " + image.mode_used + " mode",
                            "tags": ["fixed", image.mode_used],
                            "mode": image.mode_used
                        })
                        fixed_count += 1
                        logger.info(f"Recreated analysis JSON for image {image.id}")
            
            # Commit changes
            if fixed_count > 0:
                await session.commit()
                logger.info(f"✅ Fixed {fixed_count} mode-related issues")
            else:
                logger.info("No mode issues found")
            
            return fixed_count
    except Exception as e:
        logger.error(f"Error fixing image modes: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 0


async def verify_gallery_data():
    """Verify that all images have proper data for gallery display"""
    logger.info("Verifying gallery data...")
    
    try:
        async with get_db_session() as session:
            # Get all images
            result = await session.execute(select(Image))
            images = result.scalars().all()
            
            fixed_count = 0
            for image in images:
                needs_update = False
                
                # Ensure mode is capitalized for display
                if image.mode_used and image.mode_used[0].islower():
                    image.mode_used = image.mode_used.capitalize()
                    needs_update = True
                
                # Ensure analysis has a description
                if image.analysis:
                    try:
                        analysis_data = json.loads(image.analysis)
                        if "description" not in analysis_data or not analysis_data["description"]:
                            analysis_data["description"] = f"Image analyzed with {image.mode_used} mode"
                            image.analysis = json.dumps(analysis_data)
                            needs_update = True
                    except json.JSONDecodeError:
                        pass
                
                if needs_update:
                    fixed_count += 1
            
            # Commit changes
            if fixed_count > 0:
                await session.commit()
                logger.info(f"✅ Fixed {fixed_count} display issues")
            else:
                logger.info("No display issues found")
            
            return fixed_count
    except Exception as e:
        logger.error(f"Error verifying gallery data: {e}")
        return 0


async def main():
    """Main function"""
    logger.info("=== Starting Image Mode Fix Tool ===")
    
    # Step 1: Fix mode values
    await fix_image_modes()
    
    # Step 2: Verify gallery display data
    await verify_gallery_data()
    
    logger.info("=== Image Mode Fix Complete ===")
    logger.info("""
The image gallery should now display correctly with proper mode values.
Use the /gallery command in your Telegram bot to verify.
""")


if __name__ == "__main__":
    asyncio.run(main())
