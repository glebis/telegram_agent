import json
import logging
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..core.i18n import t
from ..models.chat import Chat
from ..models.image import Image

logger = logging.getLogger(__name__)


class GalleryService:
    """Service for managing user image galleries with pagination"""

    def __init__(self):
        self.images_per_page = 10

    async def get_user_images_paginated(
        self,
        user_id: int,
        page: int = 1,
        per_page: Optional[int] = None,
        locale: str = "en",
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
                        Chat.user_id == user_id, Image.processing_status == "completed"
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
                        analysis_data = {
                            "description": t("commands.gallery.parsing_error", locale)
                        }

                    # Get first 50 characters of description
                    no_desc = t("commands.gallery.no_description", locale)
                    description = analysis_data.get("description", no_desc)
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

    async def get_image_by_id(
        self, image_id: int, user_id: int, locale: str = "en"
    ) -> Optional[Dict]:
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
                    analysis_data = {
                        "description": t("commands.gallery.parsing_error", locale)
                    }

                return {
                    "id": image.id,
                    "file_id": image.file_id,
                    "created_at": image.created_at,
                    "mode_used": image.mode_used or "default",
                    "preset_used": image.preset_used,
                    "full_description": analysis_data.get(
                        "description",
                        t("commands.gallery.no_description", locale),
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
        self,
        images: List[Dict],
        page: int,
        total_pages: int,
        total_images: int,
        locale: str = "en",
    ) -> str:
        """Format a gallery page for display"""
        title = t("commands.gallery.title", locale)

        if not images:
            hint = t("commands.gallery.empty_hint", locale)
            return f"🖼️ <b>{title}</b>\n\n📭 <i>{hint}</i>"

        # Header
        response = f"🖼️ <b>{title}</b>" f" (Page {page}/{total_pages})\n"
        total_label = t(
            "commands.gallery.total_images",
            locale,
            count=total_images,
        )
        response += f"📊 {total_label}\n\n"

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

            n = (page - 1) * 10 + i
            img_label = t("commands.gallery.image_label", locale, n=n)
            response += f"📸 <b>{img_label}</b> - {mode_display}\n"
            response += f"   📅 {date_str}\n"
            response += f"   💬 \"{image['short_description']}\"\n\n"

        return response

    def format_image_details(self, image_data: Dict, locale: str = "en") -> str:
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

        dtitle = t("commands.gallery.details_title", locale)
        response = f"🖼️ <b>{dtitle}</b>\n\n"
        mode_l = t("commands.gallery.mode_label", locale)
        response += f"📋 <b>{mode_l}</b> {mode_display}\n"
        date_l = t("commands.gallery.date_label", locale)
        response += f"📅 <b>{date_l}</b> {date_str}\n"

        if image_data.get("width") and image_data.get("height"):
            size_l = t("commands.gallery.size_label", locale)
            w = image_data["width"]
            h = image_data["height"]
            response += f"📐 <b>{size_l}</b> {w}×{h}\n"

        if image_data.get("processing_time"):
            pt = image_data["processing_time"]
            proc_l = t(
                "commands.gallery.processed_label",
                locale,
                time=f"{pt:.1f}",
            )
            response += f"⚡ {proc_l}\n"

        if image_data.get("similar_count", 0) > 0:
            sim_l = t(
                "commands.gallery.similar_label",
                locale,
                count=image_data["similar_count"],
            )
            response += f"🔍 {sim_l}\n"

        analysis_l = t("commands.gallery.analysis_label", locale)
        response += f"\n<b>{analysis_l}</b>\n"
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


def get_gallery_service() -> GalleryService:
    """Get the global gallery service instance (delegates to DI container)."""
    from ..core.services import Services, get_service

    return get_service(Services.GALLERY)
