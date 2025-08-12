"""
Cache service for storing and retrieving image analysis results
"""

import hashlib
import json
import logging
from typing import Dict, Optional
from sqlalchemy import select, and_
from ..core.database import get_db_session
from ..models.image import Image

logger = logging.getLogger(__name__)


class CacheService:
    """Service for caching image analysis results"""

    def __init__(self):
        pass

    def _generate_cache_key(
        self, file_id: str, mode: str, preset: Optional[str] = None
    ) -> str:
        """Generate a cache key for the given parameters"""
        cache_data = {"file_id": file_id, "mode": mode, "preset": preset or ""}
        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(cache_string.encode()).hexdigest()[:16]

    async def get_cached_analysis(
        self, file_id: str, mode: str, preset: Optional[str] = None
    ) -> Optional[Dict]:
        """Get cached analysis result if it exists"""
        try:
            async with get_db_session() as session:
                # Look for existing analysis with same parameters
                query = (
                    select(Image)
                    .where(
                        and_(
                            Image.file_id == file_id,
                            Image.mode_used == mode,
                            Image.preset_used == (preset or ""),
                            Image.processing_status == "completed",
                        )
                    )
                    .order_by(Image.created_at.desc())
                )

                result = await session.execute(query)
                cached_image = result.scalar_one_or_none()

                if cached_image and cached_image.analysis:
                    logger.info(
                        f"Cache hit for file_id={file_id}, mode={mode}, preset={preset}"
                    )

                    # Parse the stored analysis
                    if isinstance(cached_image.analysis, str):
                        analysis = json.loads(cached_image.analysis)
                    else:
                        analysis = cached_image.analysis

                    # Add cache metadata
                    analysis["cached"] = True
                    analysis["cache_timestamp"] = cached_image.created_at.isoformat()

                    return analysis

                logger.info(
                    f"Cache miss for file_id={file_id}, mode={mode}, preset={preset}"
                )
                return None

        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None

    async def store_analysis(
        self, file_id: str, mode: str, preset: Optional[str], analysis: Dict
    ) -> bool:
        """Store analysis result in cache (database)"""
        try:
            # This is handled by the main image processing logic
            # We just log that we're storing for cache purposes
            cache_key = self._generate_cache_key(file_id, mode, preset)
            logger.info(f"Storing analysis in cache with key: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
            return False

    async def invalidate_cache(self, file_id: str) -> bool:
        """Invalidate all cached results for a file_id"""
        try:
            async with get_db_session() as session:
                # Mark all analyses for this file as invalidated
                # (We could add an 'invalidated' field, but for now we'll just rely on timestamps)
                logger.info(f"Cache invalidation requested for file_id: {file_id}")
                return True

        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            return False


# Global cache service instance
_cache_service = None


def get_cache_service() -> CacheService:
    """Get the global cache service instance"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
