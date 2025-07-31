import json
import logging
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..models.chat import Chat
from ..models.image import Image

logger = logging.getLogger(__name__)


class GalleryService:
    """Service for managing user image galleries with pagination"""

    def __init__(self):
        self.images_per_page = 10

    async def get_user_images_paginated(
        self, user_id: int, page: int = 1, per_page: Optional[int] = None
    ) -> Tuple[List[Dict], int, int]:
        """
        Get paginated images for a user

        Returns:
            - List of image data dictionaries
            - Total number of images
            - Total number of pages
        """
        if per_page is None:
            per_page = self.images_per_page

        offset = (page - 1) * per_page

        try:
            async with get_db_session() as session:
                # Get total count
                count_query = (
                    select(func.count(Image.id))
                    .select_from(Image)
                    .join(Image.chat)
                    .where(
                        Chat.user_id == user_id, Image.processing_status == "completed"
                    )
                )

                count_result = await session.execute(count_query)
                total_images = count_result.scalar() or 0
                total_pages = (
                    math.ceil(total_images / per_page) if total_images > 0 else 1
                )

                # Get paginated images - handle both direct and indirect relationships
                # First try to get images directly linked to user_id through chat
                images_query = (
                    select(Image)
                    .join(Image.chat)
                    .where(
                        Chat.user_id == user_id, 
                        Image.processing_status == "completed"
                    )
                    .order_by(Image.created_at.desc())
                    .offset(offset)
                    .limit(per_page)
                    .options(selectinload(Image.chat))
                )

                images_result = await session.execute(images_query)
                images = images_result.scalars().all()

                # Convert to dictionaries with parsed analysis
                image_data = []
                for image in images:
                    try:
                        analysis_data = (
                            json.loads(image.analysis) if image.analysis else {}
                        )
                    except json.JSONDecodeError:
                        analysis_data = {"description": "Analysis parsing error"}

                    # Get first 50 characters of description
                    description = analysis_data.get(
                        "description", "No description available"
                    )
                    short_description = (
                        (description[:50] + "...")
                        if len(description) > 50
                        else description
                    )

                    image_data.append(
                        {
                            "id": image.id,
                            "file_id": image.file_id,
                            "created_at": image.created_at,
                            "mode_used": image.mode_used or "default",
                            "preset_used": image.preset_used,
                            "full_description": description,
                            "short_description": short_description,
                            "analysis_data": analysis_data,
                            "width": image.width,
                            "height": image.height,
                            "file_size": image.file_size,
                        }
                    )

                logger.info(
                    f"Retrieved {len(image_data)} images for user {user_id}, page {page}/{total_pages}"
                )
                return image_data, total_images, total_pages

        except Exception as e:
            logger.error(f"Error getting user images for user {user_id}: {e}")
            return [], 0, 1

    async def get_image_by_id(self, image_id: int, user_id: int) -> Optional[Dict]:
        """Get a specific image by ID, ensuring it belongs to the user"""
        try:
            async with get_db_session() as session:
                query = (
                    select(Image)
                    .join(Image.chat)
                    .where(
                        Image.id == image_id,
                        Chat.user_id == user_id,
                        Image.processing_status == "completed",
                    )
                    .options(selectinload(Image.chat))
                )

                result = await session.execute(query)
                image = result.scalar_one_or_none()

                if not image:
                    return None

                try:
                    analysis_data = json.loads(image.analysis) if image.analysis else {}
                except json.JSONDecodeError:
                    analysis_data = {"description": "Analysis parsing error"}

                return {
                    "id": image.id,
                    "file_id": image.file_id,
                    "created_at": image.created_at,
                    "mode_used": image.mode_used or "default",
                    "preset_used": image.preset_used,
                    "full_description": analysis_data.get(
                        "description", "No description available"
                    ),
                    "analysis_data": analysis_data,
                    "width": image.width,
                    "height": image.height,
                    "file_size": image.file_size,
                    "processing_time": analysis_data.get("processing_time", 0),
                    "similar_count": analysis_data.get("similar_count", 0),
                }

        except Exception as e:
            logger.error(f"Error getting image {image_id} for user {user_id}: {e}")
            return None

    def format_gallery_page(
        self, images: List[Dict], page: int, total_pages: int, total_images: int
    ) -> str:
        """Format a gallery page for display"""

        if not images:
            return (
                "🖼️ <b>Your Image Gallery</b>\n\n"
                "📭 <i>No images found yet!</i>\n\n"
                "Send me some images to get started with analysis!"
            )

        # Header
        response = f"🖼️ <b>Your Image Gallery</b> (Page {page}/{total_pages})\n"
        response += f"📊 Total Images: {total_images}\n\n"

        # Images
        for i, image in enumerate(images, 1):
            mode_display = image["mode_used"].title()
            if image["preset_used"]:
                mode_display += f" - {image['preset_used']}"

            # Format date
            created_date = image["created_at"]
            if isinstance(created_date, datetime):
                date_str = created_date.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = str(created_date)

            response += f"📸 <b>Image {(page - 1) * 10 + i}</b> - {mode_display}\n"
            response += f"   📅 {date_str}\n"
            response += f"   💬 \"{image['short_description']}\"\n\n"

        return response

    def format_image_details(self, image_data: Dict) -> str:
        """Format detailed view of a single image"""
        mode_display = image_data["mode_used"].title()
        if image_data["preset_used"]:
            mode_display += f" - {image_data['preset_used']}"

        # Format date
        created_date = image_data["created_at"]
        if isinstance(created_date, datetime):
            date_str = created_date.strftime("%Y-%m-%d %H:%M")
        else:
            date_str = str(created_date)

        response = "🖼️ <b>Image Details</b>\n\n"
        response += f"📋 <b>Mode:</b> {mode_display}\n"
        response += f"📅 <b>Date:</b> {date_str}\n"

        if image_data.get("width") and image_data.get("height"):
            response += (
                f"📐 <b>Size:</b> {image_data['width']}×{image_data['height']}\n"
            )

        if image_data.get("processing_time"):
            response += (
                f"⚡ <b>Processed in:</b> {image_data['processing_time']:.1f}s\n"
            )

        if image_data.get("similar_count", 0) > 0:
            response += (
                f"🔍 <b>Similar Images:</b> {image_data['similar_count']} found\n"
            )

        response += "\n<b>Analysis:</b>\n"
        response += self._markdown_to_html(image_data["full_description"])

        return response

    def _markdown_to_html(self, text: str) -> str:
        """Convert basic markdown formatting to HTML for Telegram"""
        import re

        # First escape HTML characters
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")

        # Convert **bold** to <b>bold</b>
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

        # Convert *italic* to <i>italic</i>
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)

        # Convert numbered lists to proper format
        text = re.sub(r"(\d+)\.\s*\*\*(.*?)\*\*:", r"\1. <b>\2</b>:", text)

        return text


# Global service instance
_gallery_service: Optional[GalleryService] = None


def get_gallery_service() -> GalleryService:
    """Get the global gallery service instance"""
    global _gallery_service
    if _gallery_service is None:
        _gallery_service = GalleryService()
    return _gallery_service
