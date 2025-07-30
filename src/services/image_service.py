import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image
from telegram import Bot

from .llm_service import get_llm_service
from .embedding_service import get_embedding_service
from ..core.vector_db import get_vector_db

logger = logging.getLogger(__name__)


class ImageService:
    """Service for downloading and processing images from Telegram"""
    
    def __init__(self):
        self.data_dir = Path("data")
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "img"
        
        # Create directories if they don't exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        self.llm_service = get_llm_service()
        self.embedding_service = get_embedding_service()
        self.vector_db = get_vector_db()
    
    async def process_image(
        self,
        bot: Bot,
        file_id: str,
        mode: str = "default",
        preset: Optional[str] = None
    ) -> Dict:
        """Complete image processing pipeline"""
        start_time = time.time()
        
        try:
            # Step 1: Download image from Telegram
            logger.info(f"Downloading image: {file_id}")
            image_data, file_info = await self._download_image(bot, file_id)
            
            # Step 2: Save original image
            original_path = await self._save_original(file_id, image_data)
            
            # Step 3: Process and compress image
            processed_path, dimensions = await self._process_image(file_id, image_data)
            
            # Step 4: Analyze with LLM
            logger.info(f"Analyzing image with LLM: mode={mode}, preset={preset}")
            analysis = await self.llm_service.analyze_image(
                image_data=image_data,
                mode=mode,
                preset=preset
            )
            
            # Step 5: Generate embedding for artistic mode
            embedding_bytes = None
            if mode == "artistic":
                logger.info("Generating embedding for artistic mode")
                embedding_bytes = await self.embedding_service.generate_embedding(image_data)
                if embedding_bytes:
                    logger.info("Embedding generated successfully")
                else:
                    logger.warning("Failed to generate embedding")
            
            # Step 6: Add processing metadata
            processing_time = time.time() - start_time
            analysis.update({
                "processing_time": processing_time,
                "file_id": file_id,
                "original_path": str(original_path),
                "processed_path": str(processed_path),
                "dimensions": dimensions,
                "file_size": len(image_data),
                "telegram_file_info": file_info,
                "embedding_generated": embedding_bytes is not None,
                "embedding_bytes": embedding_bytes  # Include for similarity search
            })
            
            logger.info(f"Image processing completed in {processing_time:.2f}s")
            return analysis
            
        except Exception as e:
            logger.error(f"Error processing image {file_id}: {e}")
            raise
    
    async def _download_image(self, bot: Bot, file_id: str) -> Tuple[bytes, Dict]:
        """Download image from Telegram"""
        try:
            # Get file info
            file = await bot.get_file(file_id)
            
            # Download file data
            image_data = await file.download_as_bytearray()
            
            file_info = {
                "file_path": file.file_path,
                "file_size": file.file_size,
                "file_unique_id": file.file_unique_id
            }
            
            logger.info(f"Downloaded image: {len(image_data)} bytes")
            return bytes(image_data), file_info
            
        except Exception as e:
            logger.error(f"Error downloading image {file_id}: {e}")
            raise
    
    async def _save_original(self, file_id: str, image_data: bytes) -> Path:
        """Save original image to raw directory"""
        try:
            # Create filename with timestamp
            timestamp = int(time.time())
            filename = f"{file_id}_{timestamp}.jpg"
            file_path = self.raw_dir / filename
            
            # Save file
            with open(file_path, "wb") as f:
                f.write(image_data)
            
            logger.info(f"Saved original image: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving original image: {e}")
            raise
    
    async def _process_image(self, file_id: str, image_data: bytes) -> Tuple[Path, Dict]:
        """Process and compress image"""
        try:
            # Open image with PIL
            image = Image.open(BytesIO(image_data))
            original_size = image.size
            
            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Resize if too large (max 1024px on longest side)
            max_size = 1024
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image from {original_size} to {new_size}")
            
            # Save processed image
            timestamp = int(time.time())
            filename = f"{file_id}_{timestamp}_processed.jpg"
            file_path = self.processed_dir / filename
            
            # Save with compression
            image.save(file_path, "JPEG", quality=85, optimize=True)
            
            # Get final file size
            final_size = os.path.getsize(file_path)
            
            dimensions = {
                "original": original_size,
                "processed": image.size,
                "original_file_size": len(image_data),
                "processed_file_size": final_size
            }
            
            logger.info(f"Processed image: {file_path} ({final_size} bytes)")
            return file_path, dimensions
            
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            raise


# Add missing import
from io import BytesIO


# Global service instance
_image_service: Optional[ImageService] = None


def get_image_service() -> ImageService:
    """Get the global image service instance"""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service