import logging
import os
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

import aiosqlite

from ..services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class VectorDatabase:
    """Vector database operations using sqlite-vss"""

    def __init__(self, db_path: str = "data/telegram_agent.db"):
        self.db_path = db_path
        self.embedding_service = get_embedding_service()

    async def initialize_vector_support(self):
        """Initialize sqlite-vss extension and create vector index"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Check if embedding_mappings table exists (for fallback mode)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS embedding_mappings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        image_id INTEGER NOT NULL,
                        embedding_id INTEGER NOT NULL,
                        FOREIGN KEY (image_id) REFERENCES images (id),
                        UNIQUE(image_id)
                    )
                """)

                # Enable sqlite-vss extension
                try:
                    await db.enable_load_extension(True)
                except Exception as ext_error:
                    logger.error(f"Failed to enable extensions: {ext_error}")
                    logger.warning(
                        "Will operate in fallback mode without vector search"
                    )
                    await db.commit()
                    return False

                try:
                    # Load extensions in the correct order: vector0 first, then vss0
                    _default_ext_path = str(
                        Path(__file__).resolve().parent.parent.parent / "extensions"
                    )
                    extension_path = Path(
                        os.environ.get("SQLITE_EXTENSIONS_PATH", _default_ext_path)
                    )

                    # Detect platform-specific extension suffix
                    suffix = os.environ.get("SQLITE_EXTENSION_SUFFIX")
                    if not suffix:
                        if os.name == "nt":
                            suffix = ".dll"
                        else:
                            try:
                                if os.uname().sysname.lower().startswith("darwin"):
                                    suffix = ".dylib"
                                else:
                                    suffix = ".so"
                            except AttributeError:
                                suffix = ".so"

                    vector0_file = extension_path / f"vector0{suffix}"
                    vss0_file = extension_path / f"vss0{suffix}"

                    # Load vector0 extension first
                    await db.execute(f"SELECT load_extension('{vector0_file}')")
                    logger.info(f"sqlite-vector extension loaded from {vector0_file}")

                    # Then load vss0 extension
                    await db.execute(f"SELECT load_extension('{vss0_file}')")
                    logger.info(f"sqlite-vss extension loaded from {vss0_file}")

                    # Create virtual tables for vector operations
                    # First create the vector table
                    await db.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS image_vector_embeddings
                        USING vector0(
                            embedding(384)
                        )
                    """)

                    # Then create the VSS table for similarity search
                    await db.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS image_embeddings
                        USING vss0(
                            embedding(384)
                        )
                    """)

                    await db.commit()
                    logger.info("Vector database initialized successfully")
                    return True

                except aiosqlite.OperationalError as sql_error:
                    logger.warning(f"Could not load sqlite-vss extension: {sql_error}")
                    logger.warning(
                        "Will operate in fallback mode without vector search"
                    )
                    await db.commit()
                    return False
                except Exception as e:
                    logger.error(f"Unexpected error initializing vector database: {e}")
                    logger.warning(
                        "Will operate in fallback mode without vector search"
                    )
                    await db.commit()
                    return False

        except Exception as e:
            logger.error(f"Critical error initializing vector database: {e}")
            import traceback

            logger.error(
                f"Vector DB initialization traceback: {traceback.format_exc()}"
            )
            return False

    async def store_embedding(self, image_id: int, embedding_bytes: bytes) -> bool:
        """Store embedding in vector database"""
        try:
            # Convert bytes to array for vector storage
            embedding_array = self.embedding_service.bytes_to_array(embedding_bytes)
            if embedding_array is None:
                logger.error(f"Invalid embedding bytes for image {image_id}")
                return False

            async with aiosqlite.connect(self.db_path) as db:
                # Check if sqlite-vss is available
                try:
                    await db.execute("SELECT 1 FROM image_embeddings LIMIT 1")
                except sqlite3.OperationalError:
                    # sqlite-vss not available, just store in images table
                    await db.execute(
                        "UPDATE images SET embedding = ? WHERE id = ?",
                        (embedding_bytes, image_id),
                    )
                    await db.commit()
                    logger.info(
                        f"Stored embedding for image {image_id} (fallback mode)"
                    )
                    return True

                # Insert into vector table
                cursor = await db.execute(
                    "INSERT INTO image_embeddings(embedding) VALUES (?)",
                    (embedding_array.tobytes(),),
                )

                embedding_id = cursor.lastrowid

                # Create mapping
                await db.execute(
                    "INSERT OR REPLACE INTO embedding_mappings (image_id, embedding_id) VALUES (?, ?)",
                    (image_id, embedding_id),
                )

                # Also store in images table for backup
                await db.execute(
                    "UPDATE images SET embedding = ? WHERE id = ?",
                    (embedding_bytes, image_id),
                )

                await db.commit()
                logger.info(
                    f"Stored embedding for image {image_id} with embedding_id {embedding_id}"
                )
                return True

        except Exception as e:
            logger.error(f"Error storing embedding for image {image_id}: {e}")
            return False

    async def find_similar_images(
        self,
        embedding_bytes: bytes,
        user_id: int,
        chat_id: Optional[int] = None,
        limit: int = 5,
        similarity_threshold: float = 0.7,
    ) -> List[Tuple[int, float]]:
        """Find similar images using vector similarity search"""
        try:
            embedding_array = self.embedding_service.bytes_to_array(embedding_bytes)
            if embedding_array is None:
                logger.error("Invalid query embedding bytes")
                return []

            async with aiosqlite.connect(self.db_path) as db:
                # Try vector similarity search first
                try:
                    # Use sqlite-vss for efficient similarity search
                    query = """
                        SELECT
                            em.image_id,
                            distance(ie.embedding, ?) as similarity_score
                        FROM image_embeddings ie
                        JOIN embedding_mappings em ON ie.rowid = em.embedding_id
                        JOIN images i ON em.image_id = i.id
                        JOIN chats c ON i.chat_id = c.id
                        WHERE c.user_id = ?
                        ORDER BY similarity_score DESC
                        LIMIT ?
                    """

                    params = [
                        embedding_array.tobytes(),
                        user_id,
                        limit * 2,
                    ]  # Get more results to filter

                    # Add chat filter if specified
                    if chat_id:
                        query = query.replace(
                            "WHERE c.user_id = ?",
                            "WHERE c.user_id = ? AND c.chat_id = ?",
                        )
                        params.insert(-1, chat_id)

                    async with db.execute(query, params) as cursor:
                        results = await cursor.fetchall()

                    # Filter by similarity threshold and limit
                    filtered_results = [
                        (image_id, similarity)
                        for image_id, similarity in results
                        if similarity >= similarity_threshold
                    ][:limit]

                    logger.info(
                        f"Found {len(filtered_results)} similar images using vector search"
                    )
                    return filtered_results

                except sqlite3.OperationalError:
                    # Fallback to manual similarity calculation
                    logger.info("Using fallback similarity search")
                    return await self._fallback_similarity_search(
                        db,
                        embedding_bytes,
                        user_id,
                        chat_id,
                        limit,
                        similarity_threshold,
                    )

        except Exception as e:
            logger.error(f"Error finding similar images: {e}")
            return []

    async def _fallback_similarity_search(
        self,
        db: aiosqlite.Connection,
        query_embedding_bytes: bytes,
        user_id: int,
        chat_id: Optional[int],
        limit: int,
        similarity_threshold: float,
    ) -> List[Tuple[int, float]]:
        """Fallback similarity search using manual cosine similarity calculation"""

        # Get all images with embeddings for this user
        query = """
            SELECT i.id, i.embedding
            FROM images i
            JOIN chats c ON i.chat_id = c.id
            WHERE c.user_id = ? AND i.embedding IS NOT NULL
        """

        params = [user_id]

        if chat_id:
            query += " AND c.chat_id = ?"
            params.append(chat_id)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        # Calculate similarities
        similarities = []
        for image_id, embedding_bytes in rows:
            if embedding_bytes:
                similarity = self.embedding_service.calculate_cosine_similarity(
                    query_embedding_bytes, embedding_bytes
                )
                if similarity is not None and similarity >= similarity_threshold:
                    similarities.append((image_id, similarity))

        # Sort by similarity and limit results
        similarities.sort(key=lambda x: x[1], reverse=True)
        results = similarities[:limit]

        logger.info(f"Found {len(results)} similar images using fallback search")
        return results

    async def get_user_embedding_count(self, user_id: int) -> int:
        """Get count of images with embeddings for a user"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                query = """
                    SELECT COUNT(*)
                    FROM images i
                    JOIN chats c ON i.chat_id = c.id
                    WHERE c.user_id = ? AND i.embedding IS NOT NULL
                """

                async with db.execute(query, [user_id]) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0

        except Exception as e:
            logger.error(f"Error getting embedding count for user {user_id}: {e}")
            return 0

    async def cleanup_orphaned_embeddings(self) -> int:
        """Clean up embeddings for deleted images"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Delete orphaned embedding mappings
                await db.execute("""
                    DELETE FROM embedding_mappings
                    WHERE image_id NOT IN (SELECT id FROM images)
                """)

                # Delete orphaned embeddings from vector table
                await db.execute("""
                    DELETE FROM image_embeddings
                    WHERE rowid NOT IN (SELECT embedding_id FROM embedding_mappings)
                """)

                deleted_count = db.total_changes
                await db.commit()

                logger.info(f"Cleaned up {deleted_count} orphaned embeddings")
                return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up orphaned embeddings: {e}")
            return 0


# Global instance
_vector_db: Optional[VectorDatabase] = None


def get_vector_db() -> VectorDatabase:
    """Get the global vector database instance"""
    global _vector_db
    if _vector_db is None:
        _vector_db = VectorDatabase()
    return _vector_db
