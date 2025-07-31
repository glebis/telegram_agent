import asyncio
import logging
import time
import os
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Any

from PIL import Image
from telegram import Bot
from io import BytesIO

from .llm_service import get_llm_service
from .embedding_service import get_embedding_service
from ..core.vector_db import get_vector_db
from ..utils.logging import (
    get_image_logger,
    log_image_processing_error,
    log_image_processing_step,
    ImageProcessingLogContext,
)

logger = logging.getLogger(__name__)
image_logger = get_image_logger("image_service")


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
        preset: Optional[str] = None,
        local_image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process an image from Telegram or local path

        Args:
            bot: Telegram bot instance
            file_id: Telegram file ID
            mode: Analysis mode
            preset: Analysis preset
            local_image_path: Optional path to local image file

        Returns:
            Dictionary with processed image info
        """
        """Complete image processing pipeline"""

        # Set up logging context
        log_context = {
            "file_id": file_id,
            "mode": mode,
            "preset": preset,
            "local_image_path": local_image_path,
        }

        with ImageProcessingLogContext("complete_image_processing", **log_context):
            start_time = time.time()

            try:
                # Step 1: Get image data (either from Telegram or local file)
                image_data = None
                local_path_used = False
                download_path = None
                file_info = {}  # Initialize file_info to avoid undefined variable error

                if local_image_path:
                    log_image_processing_step(
                        "local_image_read", {"path": local_image_path}, image_logger
                    )
                    logger.info(f"Local image path provided: {local_image_path}")

                    # Check if path is a string and not empty
                    if (
                        not isinstance(local_image_path, str)
                        or not local_image_path.strip()
                    ):
                        logger.warning(
                            f"Invalid local image path format: {local_image_path}"
                        )
                    else:
                        # Validate local image path
                        if os.path.exists(local_image_path):
                            try:
                                with open(local_image_path, "rb") as f:
                                    image_data = f.read()

                                if len(image_data) > 0:
                                    logger.info(
                                        f"Successfully read image from local path: {len(image_data)} bytes"
                                    )
                                    local_path_used = True
                                else:
                                    logger.warning(
                                        f"Local image file exists but is empty: {local_image_path}"
                                    )
                                    image_data = None
                            except Exception as e:
                                logger.error(f"Error reading local image file: {e}")
                                import traceback

                                logger.error(
                                    f"Local file read error details: {traceback.format_exc()}"
                                )
                                image_data = None
                        else:
                            logger.warning(
                                f"Local image path does not exist: {local_image_path}"
                            )

                # If local path failed or wasn't provided, download from Telegram
                if not image_data:
                    log_image_processing_step(
                        "telegram_download", {"file_id": file_id}, image_logger
                    )
                    if not file_id:
                        logger.error("No file_id provided and local image path failed")
                        raise ValueError(
                            "No valid file_id or local image path available"
                        )

                    try:
                        logger.info(
                            f"Downloading image from Telegram with file_id: {file_id}"
                        )
                        image_data, file_info = await self._download_image(bot, file_id)

                        if not image_data or len(image_data) == 0:
                            logger.error("Downloaded image data is empty")
                            raise ValueError("Downloaded image data is empty")

                        logger.info(
                            f"Successfully downloaded image from Telegram: {len(image_data)} bytes"
                        )
                    except Exception as e:
                        logger.error(f"Error downloading image from Telegram: {e}")
                        import traceback

                        logger.error(
                            f"Download error details: {traceback.format_exc()}"
                        )

                        # Last resort: try local path again if it was provided but failed earlier
                        if local_image_path and not local_path_used:
                            logger.info(
                                f"Telegram download failed, retrying local path: {local_image_path}"
                            )
                            try:
                                if os.path.exists(local_image_path):
                                    with open(local_image_path, "rb") as f:
                                        image_data = f.read()

                                    if len(image_data) > 0:
                                        logger.info(
                                            f"Successfully read image from local path (retry): {len(image_data)} bytes"
                                        )
                                    else:
                                        logger.error(
                                            f"Local image file exists but is empty (retry): {local_image_path}"
                                        )
                                        raise ValueError("Local image file is empty")
                                else:
                                    logger.error(
                                        f"Local image path does not exist (retry): {local_image_path}"
                                    )
                                    raise FileNotFoundError(
                                        f"Local image file not found: {local_image_path}"
                                    )
                            except Exception as local_error:
                                logger.error(
                                    f"Error reading local image file (retry): {local_error}"
                                )
                                import traceback

                                logger.error(
                                    f"Local file retry error details: {traceback.format_exc()}"
                                )
                                raise Exception(
                                    f"Failed to get image from both Telegram and local path: {e} / {local_error}"
                                )
                        else:
                            # No local path or already tried it
                            raise e

                # Step 2: Save original image
                log_image_processing_step(
                    "save_original", {"file_id": file_id}, image_logger
                )
                original_path = await self._save_original(file_id, image_data)

                # Step 3: Process and compress image
                log_image_processing_step(
                    "compress_image", {"file_id": file_id}, image_logger
                )
                processed_path, dimensions = await self._process_image(
                    file_id, image_data
                )

                # Step 4: Analyze with LLM
                log_image_processing_step(
                    "llm_analysis", {"mode": mode, "preset": preset}, image_logger
                )
                logger.info(f"Analyzing image with LLM: mode={mode}, preset={preset}")
                analysis = await self.llm_service.analyze_image(
                    image_data=image_data, mode=mode, preset=preset
                )

                # Step 5: Generate embedding for all modes to support gallery functionality
                log_image_processing_step(
                    "generate_embedding", {"mode": mode}, image_logger
                )
                embedding_bytes = None
                try:
                    logger.info(f"Generating embedding for {mode} mode")
                    embedding_bytes = await self.embedding_service.generate_embedding(
                        image_data
                    )
                    if embedding_bytes:
                        logger.info("Embedding generated successfully")
                    else:
                        logger.warning("Failed to generate embedding")
                except Exception as e:
                    logger.error(f"Error generating embedding: {e}")
                    # Continue processing even if embedding generation fails

                # Step 6: Add processing metadata
                processing_time = time.time() - start_time
                analysis.update(
                    {
                        "processing_time": processing_time,
                        "file_id": file_id,
                        "original_path": str(original_path),
                        "processed_path": str(processed_path),
                        "dimensions": dimensions,
                        "file_size": len(image_data),
                        "telegram_file_info": file_info,
                        "embedding_generated": embedding_bytes is not None,
                        "embedding_bytes": embedding_bytes,  # Include for similarity search
                    }
                )

                logger.info(f"Image processing completed in {processing_time:.2f}s")
                return analysis

            except Exception as e:
                # Log comprehensive error details
                error_context = {
                    "file_id": file_id,
                    "mode": mode,
                    "preset": preset,
                    "local_image_path": local_image_path,
                    "operation": "complete_image_processing",
                }
                log_image_processing_error(e, error_context, image_logger)
                logger.error(f"Error processing image {file_id}: {e}", exc_info=True)
                raise

    async def _download_image(self, bot: Bot, file_id: str) -> Tuple[bytes, Dict]:
        """Download image from Telegram"""
        try:
            # Get file info
            logger.info(f"Requesting file info for file_id: {file_id}")
            try:
                file = await bot.get_file(file_id)
            except Exception as file_error:
                logger.error(f"Failed to get file info: {file_error}")
                import traceback

                logger.error(f"File info error details: {traceback.format_exc()}")
                raise ValueError(f"Failed to get file info for {file_id}: {file_error}")

            # Download file data
            logger.info(f"Downloading file data from path: {file.file_path}")
            try:
                image_data = await file.download_as_bytearray()
            except Exception as download_error:
                logger.error(f"Failed to download file data: {download_error}")
                import traceback

                logger.error(f"Download error details: {traceback.format_exc()}")
                raise ValueError(f"Failed to download file data: {download_error}")

            file_info = {
                "file_path": file.file_path,
                "file_size": file.file_size,
                "file_unique_id": file.file_unique_id,
            }

            logger.info(f"Successfully downloaded image: {len(image_data)} bytes")
            return bytes(image_data), file_info

        except Exception as e:
            logger.error(f"Error downloading image {file_id}: {e}")
            import traceback

            logger.error(f"Download error traceback: {traceback.format_exc()}")
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

    async def _process_image(
        self, file_id: str, image_data: bytes
    ) -> Tuple[Path, Dict]:
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
                "processed_file_size": final_size,
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
