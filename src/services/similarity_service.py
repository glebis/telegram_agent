import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any

from ..core.database import get_db_session
from ..core.vector_db import get_vector_db
from ..models.image import Image
from ..services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class SimilarityService:
    """Service for finding similar images with user scoping"""

    def __init__(self):
        self.vector_db = get_vector_db()
        self.embedding_service = get_embedding_service()

    def calculate_similarity(
        self, embedding1: List[float], embedding2: List[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings"""
        try:
            # Convert to numpy arrays
            vec1 = np.array(embedding1, dtype=np.float32)
            vec2 = np.array(embedding2, dtype=np.float32)

            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0

    async def find_similar_images(
        self, query_embedding: List[float], limit: int = 10, threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Find similar images based on query embedding"""
        try:
            results = await self.vector_db.search_similar(
                query_embedding=query_embedding, limit=limit, threshold=threshold
            )

            # Filter by threshold and sort by similarity
            filtered_results = [
                result for result in results if result.get("similarity", 0) >= threshold
            ]

            # Sort by similarity descending
            filtered_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

            return filtered_results[:limit]
        except Exception as e:
            logger.error(f"Error finding similar images: {e}")
            return []

    async def batch_find_similar(
        self, query_embeddings: List[List[float]], limit: int = 5
    ) -> List[List[Dict[str, Any]]]:
        """Find similar images for multiple query embeddings"""
        results = []
        for embedding in query_embeddings:
            similar = await self.find_similar_images(embedding, limit=limit)
            results.append(similar)
        return results

    async def find_duplicates(
        self, query_embedding: List[float], duplicate_threshold: float = 0.97
    ) -> List[Dict[str, Any]]:
        """Find potential duplicate images"""
        return await self.find_similar_images(
            query_embedding=query_embedding, threshold=duplicate_threshold, limit=100
        )

    async def search_by_text(
        self, text_query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for images using text description"""
        try:
            # Generate embedding for text query
            text_embedding = await self.embedding_service.generate_text_embedding(
                text_query
            )

            # Find similar images
            return await self.find_similar_images(
                query_embedding=text_embedding, limit=limit
            )
        except Exception as e:
            logger.error(f"Error in text-based search: {e}")
            return []

    def cluster_by_similarity(
        self,
        embeddings: List[List[float]],
        image_ids: List[str],
        similarity_threshold: float = 0.8,
    ) -> List[List[str]]:
        """Cluster images by similarity"""
        try:
            clusters = []
            used_indices = set()

            for i, embedding1 in enumerate(embeddings):
                if i in used_indices:
                    continue

                cluster = [image_ids[i]]
                used_indices.add(i)

                for j, embedding2 in enumerate(embeddings):
                    if j in used_indices or i == j:
                        continue

                    similarity = self.calculate_similarity(embedding1, embedding2)
                    if similarity >= similarity_threshold:
                        cluster.append(image_ids[j])
                        used_indices.add(j)

                clusters.append(cluster)

            return clusters
        except Exception as e:
            logger.error(f"Error clustering images: {e}")
            return [
                [img_id] for img_id in image_ids
            ]  # Fallback: each image in its own cluster

    async def find_similar_images_by_id(
        self,
        image_id: int,
        user_id: int,
        scope: str = "user",  # "user", "chat", "group"
        limit: int = 5,
        similarity_threshold: float = 0.7,
    ) -> List[Dict]:
        """Find similar images with specified scope"""

        try:
            # Get the query image and its embedding
            async with get_db_session() as session:
                from sqlalchemy import select

                result = await session.execute(
                    select(Image).where(Image.id == image_id)
                )
                query_image = result.scalar_one_or_none()

                if not query_image or not query_image.embedding:
                    logger.warning(f"No embedding found for image {image_id}")
                    return []

                # Get chat_id for chat-scoped searches
                chat_id = query_image.chat_id if scope == "chat" else None

                # Find similar images using vector database
                similar_results = await self.vector_db.find_similar_images(
                    embedding_bytes=query_image.embedding,
                    user_id=user_id,
                    chat_id=chat_id,
                    limit=limit,
                    similarity_threshold=similarity_threshold,
                )

                if not similar_results:
                    return []

                # Get image details for similar images
                similar_image_ids = [img_id for img_id, _ in similar_results]
                similarity_scores = {img_id: score for img_id, score in similar_results}

                # Fetch image details
                result = await session.execute(
                    select(Image).where(Image.id.in_(similar_image_ids))
                )
                similar_images = result.scalars().all()

                # Format results
                formatted_results = []
                for image in similar_images:
                    if image.id != image_id:  # Exclude the query image itself
                        similarity_score = similarity_scores.get(image.id, 0.0)

                        formatted_results.append(
                            {
                                "id": image.id,
                                "file_id": image.file_id,
                                "file_unique_id": image.file_unique_id,
                                "similarity_score": similarity_score,
                                "analysis": image.analysis,
                                "mode_used": image.mode_used,
                                "preset_used": image.preset_used,
                                "created_at": (
                                    image.created_at.isoformat()
                                    if image.created_at
                                    else None
                                ),
                                "file_path": getattr(image, "file_path", None),
                            }
                        )

                # Sort by similarity score (highest first)
                formatted_results.sort(
                    key=lambda x: x["similarity_score"], reverse=True
                )

                logger.info(
                    f"Found {len(formatted_results)} similar images for image {image_id}"
                )
                return formatted_results

        except Exception as e:
            logger.error(f"Error finding similar images for {image_id}: {e}")
            return []

    async def find_similar_by_embedding(
        self,
        embedding_bytes: bytes,
        user_id: int,
        scope: str = "user",
        chat_id: Optional[int] = None,
        limit: int = 5,
        similarity_threshold: float = 0.7,
    ) -> List[Dict]:
        """Find similar images by embedding (for new uploads)"""

        try:
            # Determine chat_id based on scope
            search_chat_id = chat_id if scope == "chat" else None

            # Find similar images
            similar_results = await self.vector_db.find_similar_images(
                embedding_bytes=embedding_bytes,
                user_id=user_id,
                chat_id=search_chat_id,
                limit=limit,
                similarity_threshold=similarity_threshold,
            )

            if not similar_results:
                return []

            # Get image details
            async with get_db_session() as session:
                from sqlalchemy import select

                similar_image_ids = [img_id for img_id, _ in similar_results]
                similarity_scores = {img_id: score for img_id, score in similar_results}

                result = await session.execute(
                    select(Image).where(Image.id.in_(similar_image_ids))
                )
                similar_images = result.scalars().all()

                # Format results
                formatted_results = []
                for image in similar_images:
                    similarity_score = similarity_scores.get(image.id, 0.0)

                    formatted_results.append(
                        {
                            "id": image.id,
                            "file_id": image.file_id,
                            "file_unique_id": image.file_unique_id,
                            "similarity_score": similarity_score,
                            "analysis": image.analysis,
                            "mode_used": image.mode_used,
                            "preset_used": image.preset_used,
                            "created_at": (
                                image.created_at.isoformat()
                                if image.created_at
                                else None
                            ),
                        }
                    )

                # Sort by similarity score
                formatted_results.sort(
                    key=lambda x: x["similarity_score"], reverse=True
                )

                logger.info(
                    f"Found {len(formatted_results)} similar images by embedding"
                )
                return formatted_results

        except Exception as e:
            logger.error(f"Error finding similar images by embedding: {e}")
            return []

    async def get_user_similarity_stats(self, user_id: int) -> Dict:
        """Get similarity search statistics for a user"""

        try:
            embedding_count = await self.vector_db.get_user_embedding_count(user_id)

            async with get_db_session() as session:
                from sqlalchemy import select, func

                # Get total image count
                result = await session.execute(
                    select(func.count(Image.id))
                    .select_from(Image)
                    .join(Image.chat)
                    .where(Image.chat.has(user_id=user_id))
                )
                total_images = result.scalar() or 0

                # Get images with embeddings count (artistic mode only)
                result = await session.execute(
                    select(func.count(Image.id))
                    .select_from(Image)
                    .join(Image.chat)
                    .where(Image.chat.has(user_id=user_id), Image.embedding.isnot(None))
                )
                embedded_images = result.scalar() or 0

                return {
                    "user_id": user_id,
                    "total_images": total_images,
                    "embedded_images": embedded_images,
                    "embedding_coverage": (
                        embedded_images / total_images if total_images > 0 else 0
                    ),
                    "similarity_search_enabled": embedded_images > 0,
                }

        except Exception as e:
            logger.error(f"Error getting similarity stats for user {user_id}: {e}")
            return {
                "user_id": user_id,
                "total_images": 0,
                "embedded_images": 0,
                "embedding_coverage": 0,
                "similarity_search_enabled": False,
            }

    async def regenerate_missing_embeddings(
        self, user_id: Optional[int] = None, limit: int = 100, all_modes: bool = False
    ) -> int:
        """Regenerate embeddings for images that don't have them

        Args:
            user_id: Only process images for this user
            limit: Maximum number of images to process
            all_modes: If True, process images from all modes. If False, only artistic mode (backward compatibility)
        """

        try:
            async with get_db_session() as session:
                from sqlalchemy import select

                # Query for images without embeddings
                query = select(Image).where(
                    Image.embedding.is_(None), Image.processing_status == "completed"
                )

                # Filter by mode if not processing all modes
                if not all_modes:
                    query = query.where(Image.mode_used == "artistic")

                if user_id:
                    query = query.join(Image.chat).where(
                        Image.chat.has(user_id=user_id)
                    )

                query = query.limit(limit)

                result = await session.execute(query)
                images_without_embeddings = result.scalars().all()

                if not images_without_embeddings:
                    mode_msg = "all modes" if all_modes else "artistic mode"
                    logger.info(
                        f"No images found that need embedding regeneration ({mode_msg})"
                    )
                    return 0

                mode_msg = "all modes" if all_modes else "artistic mode only"
                logger.info(
                    f"Regenerating embeddings for {len(images_without_embeddings)} images ({mode_msg})"
                )

                # Process images in batches
                regenerated_count = 0
                batch_size = 10

                for i in range(0, len(images_without_embeddings), batch_size):
                    batch = images_without_embeddings[i : i + batch_size]

                    # Load image data and generate embeddings
                    for image in batch:
                        try:
                            # Find accessible file path
                            file_path = None
                            if (
                                hasattr(image, "compressed_path")
                                and image.compressed_path
                            ):
                                from pathlib import Path

                                file_path = Path(image.compressed_path)
                            elif (
                                hasattr(image, "original_path") and image.original_path
                            ):
                                from pathlib import Path

                                file_path = Path(image.original_path)
                            elif hasattr(image, "file_path") and image.file_path:
                                from pathlib import Path

                                file_path = Path(image.file_path)

                            if file_path and file_path.exists():
                                with open(file_path, "rb") as f:
                                    image_data = f.read()

                                # Generate embedding
                                embedding_bytes = (
                                    await self.embedding_service.generate_embedding(
                                        image_data
                                    )
                                )

                                if embedding_bytes:
                                    # Update database
                                    image.embedding = embedding_bytes
                                    image.embedding_model = (
                                        self.embedding_service.model_name
                                    )

                                    # Store in vector database
                                    await self.vector_db.store_embedding(
                                        image.id, embedding_bytes
                                    )

                                    regenerated_count += 1
                                    logger.info(
                                        f"Regenerated embedding for image {image.id}"
                                    )
                                else:
                                    logger.warning(
                                        f"Failed to generate embedding for image {image.id}"
                                    )
                            else:
                                logger.warning(
                                    f"No accessible file path for image {image.id}"
                                )

                        except Exception as e:
                            logger.error(
                                f"Error regenerating embedding for image {image.id}: {e}"
                            )

                    # Commit batch
                    await session.commit()

                logger.info(f"Successfully regenerated {regenerated_count} embeddings")
                return regenerated_count

        except Exception as e:
            logger.error(f"Error regenerating embeddings: {e}")
            return 0


# Global service instance
_similarity_service: Optional[SimilarityService] = None


def get_similarity_service() -> SimilarityService:
    """Get the global similarity service instance"""
    global _similarity_service
    if _similarity_service is None:
        _similarity_service = SimilarityService()
    return _similarity_service
