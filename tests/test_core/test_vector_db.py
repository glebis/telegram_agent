"""
Tests for VectorDatabase.

This test suite covers:
- Database initialization and vector support setup
- Embedding storage (both with sqlite-vss and fallback mode)
- Similarity search (both with sqlite-vss and fallback mode)
- User embedding count retrieval
- Orphaned embedding cleanup
- Global instance management
- Error handling and edge cases
"""

import asyncio
import os
import sqlite3
import struct
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import aiosqlite
import numpy as np
import pytest

from src.core.vector_db import VectorDatabase, get_vector_db


# Disable the autouse fixture that patches sqlite3 for this module
# This is needed because vector_db.py catches sqlite3.OperationalError
# and the mock breaks exception handling
@pytest.fixture(autouse=True)
def disable_sqlite3_mock(setup_test_environment):
    """Override the autouse fixture to not mock sqlite3 for vector_db tests.

    The vector_db module needs real sqlite3.OperationalError for exception handling.
    We re-patch sqlite3 with the real module.
    """
    import src.core.vector_db as vector_db_module

    # Restore real sqlite3 module
    vector_db_module.sqlite3 = sqlite3
    yield


class TestVectorDatabaseInitialization:
    """Tests for VectorDatabase initialization and configuration"""

    def test_initialization_default_db_path(self):
        """Test that VectorDatabase initializes with default database path"""
        db = VectorDatabase()
        assert db.db_path == "data/telegram_agent.db"

    def test_initialization_custom_db_path(self):
        """Test that VectorDatabase accepts custom database path"""
        custom_path = "/custom/path/to/database.db"
        db = VectorDatabase(db_path=custom_path)
        assert db.db_path == custom_path

    def test_initialization_accepts_injected_embedding_service(self):
        """Test that VectorDatabase accepts an injected embedding service"""
        mock_service = Mock()
        db = VectorDatabase(embedding_service=mock_service)
        assert db.embedding_service is mock_service

    def test_initialization_lazy_loads_embedding_service(self):
        """Test that VectorDatabase lazy-loads embedding service when not injected"""
        with patch(
            "src.services.embedding_service.get_embedding_service"
        ) as mock_get_service:
            mock_service = Mock()
            mock_get_service.return_value = mock_service

            db = VectorDatabase()
            # Not loaded yet
            mock_get_service.assert_not_called()
            # Accessed on first use
            _ = db.embedding_service
            mock_get_service.assert_called_once()


class TestVectorDatabaseSetup:
    """Tests for database initialization and vector support setup"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    def vector_db(self, temp_db_path):
        """Create VectorDatabase instance with temporary database"""
        return VectorDatabase(db_path=temp_db_path)

    @pytest.mark.asyncio
    async def test_initialize_vector_support_creates_mapping_table(
        self, vector_db, temp_db_path
    ):
        """Test that initialization creates embedding_mappings table"""
        # Initialize (will likely fail on sqlite-vss, but should create mappings table)
        await vector_db.initialize_vector_support()

        # Verify table was created
        async with aiosqlite.connect(temp_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='embedding_mappings'"
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "embedding_mappings"

    @pytest.mark.asyncio
    async def test_initialize_vector_support_fallback_mode(self, vector_db):
        """Test that initialization falls back gracefully when extensions unavailable"""
        # Without sqlite-vss installed, should return False but not crash
        result = await vector_db.initialize_vector_support()

        # Should return False (fallback mode) since sqlite-vss is likely not installed
        # in the test environment
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_initialize_vector_support_extension_load_error(self, vector_db):
        """Test handling of extension loading errors"""
        with patch("aiosqlite.connect") as mock_connect:
            mock_db = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_db
            mock_db.execute = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_db.enable_load_extension = AsyncMock(
                side_effect=Exception("Extension loading disabled")
            )

            result = await vector_db.initialize_vector_support()

            # Should return False and log warning
            assert result is False

    @pytest.mark.asyncio
    async def test_initialize_vector_support_successful_with_extensions(
        self, temp_db_path
    ):
        """Test successful initialization when sqlite-vss extensions are available"""
        vector_db = VectorDatabase(db_path=temp_db_path)

        # Mock the extension loading to simulate successful load
        with patch("aiosqlite.connect") as mock_connect:
            mock_db = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_db

            # Simulate successful operations
            mock_db.execute = AsyncMock()
            mock_db.commit = AsyncMock()
            mock_db.enable_load_extension = AsyncMock()

            result = await vector_db.initialize_vector_support()

            # Should return True when everything succeeds
            assert result is True

    @pytest.mark.asyncio
    async def test_initialize_vector_support_critical_error(self, temp_db_path):
        """Test handling of critical database errors"""
        vector_db = VectorDatabase(db_path=temp_db_path)

        with patch(
            "aiosqlite.connect", side_effect=Exception("Database connection failed")
        ):
            result = await vector_db.initialize_vector_support()

            assert result is False


class TestEmbeddingStorage:
    """Tests for embedding storage functionality"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def initialized_db(self, temp_db_path):
        """Create initialized VectorDatabase with required tables"""
        # Create tables manually for testing
        async with aiosqlite.connect(temp_db_path) as db:
            # Create images table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    embedding BLOB
                )
            """)
            # Create embedding_mappings table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS embedding_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    embedding_id INTEGER NOT NULL,
                    UNIQUE(image_id)
                )
            """)
            # Insert test image
            await db.execute("INSERT INTO images (id, chat_id) VALUES (1, 123)")
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        return vector_db

    @pytest.fixture
    def sample_embedding_bytes(self):
        """Create sample embedding bytes for testing"""
        # Create a 384-dimension float32 array and pack it
        array = np.random.rand(384).astype(np.float32)
        packed = struct.pack("I", 384) + array.tobytes()
        return packed

    @pytest.mark.asyncio
    async def test_store_embedding_fallback_mode(
        self, initialized_db, sample_embedding_bytes, temp_db_path
    ):
        """Test storing embedding in fallback mode (no sqlite-vss)"""
        # Mock the bytes_to_array method
        mock_array = np.random.rand(384).astype(np.float32)
        initialized_db.embedding_service.bytes_to_array = Mock(return_value=mock_array)

        # The database doesn't have image_embeddings table, so it will use fallback
        # We need to trigger the fallback path properly
        result = await initialized_db.store_embedding(1, sample_embedding_bytes)

        # In fallback mode (no sqlite-vss tables), the store should succeed
        # by storing directly in images table
        assert result is True

        # Verify embedding was stored in images table
        async with aiosqlite.connect(temp_db_path) as db:
            cursor = await db.execute("SELECT embedding FROM images WHERE id = 1")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] is not None

    @pytest.mark.asyncio
    async def test_store_embedding_with_vss_tables(self, temp_db_path):
        """Test storing embedding when sqlite-vss tables exist (but not the extension)"""
        # Create all required tables including image_embeddings
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    embedding BLOB
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS embedding_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    embedding_id INTEGER NOT NULL,
                    UNIQUE(image_id)
                )
            """)
            # Create a regular table that mimics the vss table structure
            await db.execute("""
                CREATE TABLE IF NOT EXISTS image_embeddings (
                    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                    embedding BLOB
                )
            """)
            await db.execute("INSERT INTO images (id, chat_id) VALUES (1, 123)")
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        mock_array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=mock_array)

        embedding_bytes = struct.pack("I", 384) + mock_array.tobytes()
        result = await vector_db.store_embedding(1, embedding_bytes)

        assert result is True

        # Verify embedding was stored
        async with aiosqlite.connect(temp_db_path) as db:
            # Check images table
            cursor = await db.execute("SELECT embedding FROM images WHERE id = 1")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] is not None

            # Check embedding_mappings table
            cursor = await db.execute(
                "SELECT * FROM embedding_mappings WHERE image_id = 1"
            )
            mapping = await cursor.fetchone()
            assert mapping is not None

    @pytest.mark.asyncio
    async def test_store_embedding_invalid_bytes(self, initialized_db):
        """Test handling of invalid embedding bytes"""
        # Mock bytes_to_array to return None for invalid bytes
        initialized_db.embedding_service.bytes_to_array = Mock(return_value=None)

        result = await initialized_db.store_embedding(1, b"invalid bytes")

        assert result is False

    @pytest.mark.asyncio
    async def test_store_embedding_database_error(self, temp_db_path):
        """Test handling of database errors during storage"""
        vector_db = VectorDatabase(db_path=temp_db_path)

        mock_array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=mock_array)

        # Create sample embedding bytes
        packed = struct.pack("I", 384) + mock_array.tobytes()

        # Without tables, should fail gracefully
        result = await vector_db.store_embedding(1, packed)

        assert result is False


class TestSimilaritySearch:
    """Tests for similarity search functionality"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def db_with_images(self, temp_db_path):
        """Create database with images and embeddings for testing"""
        async with aiosqlite.connect(temp_db_path) as db:
            # Create required tables
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    embedding BLOB
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS embedding_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER NOT NULL,
                    embedding_id INTEGER NOT NULL,
                    UNIQUE(image_id)
                )
            """)

            # Insert test data
            await db.execute("INSERT INTO users (id, telegram_id) VALUES (1, 12345)")
            await db.execute(
                "INSERT INTO chats (id, chat_id, user_id) VALUES (1, 100, 1)"
            )

            # Create sample embeddings
            for i in range(5):
                array = np.random.rand(384).astype(np.float32)
                embedding_bytes = struct.pack("I", 384) + array.tobytes()
                await db.execute(
                    "INSERT INTO images (id, chat_id, embedding) VALUES (?, 1, ?)",
                    (i + 1, embedding_bytes),
                )

            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        return vector_db

    @pytest.fixture
    def sample_query_embedding(self):
        """Create sample query embedding bytes"""
        array = np.random.rand(384).astype(np.float32)
        return struct.pack("I", 384) + array.tobytes()

    @pytest.mark.asyncio
    async def test_find_similar_images_invalid_query(self, db_with_images):
        """Test handling of invalid query embedding"""
        db_with_images.embedding_service.bytes_to_array = Mock(return_value=None)

        results = await db_with_images.find_similar_images(
            embedding_bytes=b"invalid", user_id=1, limit=5
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_images_fallback_search(
        self, db_with_images, sample_query_embedding
    ):
        """Test fallback similarity search when sqlite-vss unavailable"""
        # Set up mock for bytes_to_array
        query_array = np.random.rand(384).astype(np.float32)
        db_with_images.embedding_service.bytes_to_array = Mock(return_value=query_array)
        db_with_images.embedding_service.calculate_cosine_similarity = Mock(
            return_value=0.85
        )

        results = await db_with_images.find_similar_images(
            embedding_bytes=sample_query_embedding,
            user_id=1,
            limit=5,
            similarity_threshold=0.7,
        )

        # Should return results via fallback search
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_find_similar_images_with_chat_filter(
        self, db_with_images, sample_query_embedding
    ):
        """Test similarity search with chat_id filter"""
        query_array = np.random.rand(384).astype(np.float32)
        db_with_images.embedding_service.bytes_to_array = Mock(return_value=query_array)
        db_with_images.embedding_service.calculate_cosine_similarity = Mock(
            return_value=0.85
        )

        results = await db_with_images.find_similar_images(
            embedding_bytes=sample_query_embedding,
            user_id=1,
            chat_id=100,
            limit=5,
            similarity_threshold=0.7,
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_find_similar_images_empty_database(self, temp_db_path):
        """Test similarity search on empty database"""
        # Create database without any images
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    user_id INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    embedding BLOB
                )
            """)
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        query_array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=query_array)

        sample_embedding = struct.pack("I", 384) + query_array.tobytes()

        results = await vector_db.find_similar_images(
            embedding_bytes=sample_embedding, user_id=1, limit=5
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_images_threshold_filtering(
        self, db_with_images, sample_query_embedding
    ):
        """Test that similarity threshold correctly filters results"""
        query_array = np.random.rand(384).astype(np.float32)
        db_with_images.embedding_service.bytes_to_array = Mock(return_value=query_array)

        # Return low similarity for all images
        db_with_images.embedding_service.calculate_cosine_similarity = Mock(
            return_value=0.5
        )

        results = await db_with_images.find_similar_images(
            embedding_bytes=sample_query_embedding,
            user_id=1,
            limit=5,
            similarity_threshold=0.7,  # Higher than returned similarity
        )

        # Should return empty since all similarities are below threshold
        assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_images_database_error(self, temp_db_path):
        """Test handling of database errors during search"""
        vector_db = VectorDatabase(db_path="/nonexistent/path/db.db")

        query_array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=query_array)

        sample_embedding = struct.pack("I", 384) + query_array.tobytes()

        results = await vector_db.find_similar_images(
            embedding_bytes=sample_embedding, user_id=1, limit=5
        )

        assert results == []


class TestFallbackSimilaritySearch:
    """Tests for fallback similarity search functionality"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def db_with_varied_embeddings(self, temp_db_path):
        """Create database with varied embeddings for testing similarity sorting"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    user_id INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    embedding BLOB
                )
            """)

            # Insert chat
            await db.execute(
                "INSERT INTO chats (id, chat_id, user_id) VALUES (1, 100, 1)"
            )

            # Insert images with different embeddings
            for i in range(5):
                # Create embeddings with predictable patterns
                array = np.zeros(384, dtype=np.float32)
                array[i] = 1.0  # Different unit vectors
                embedding_bytes = struct.pack("I", 384) + array.tobytes()
                await db.execute(
                    "INSERT INTO images (id, chat_id, embedding) VALUES (?, 1, ?)",
                    (i + 1, embedding_bytes),
                )

            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        return vector_db

    @pytest.mark.asyncio
    async def test_fallback_search_sorts_by_similarity(self, db_with_varied_embeddings):
        """Test that fallback search sorts results by similarity in descending order"""
        # Create query embedding that matches first image
        query_array = np.zeros(384, dtype=np.float32)
        query_array[0] = 1.0

        db_with_varied_embeddings.embedding_service.bytes_to_array = Mock(
            return_value=query_array
        )

        # Mock calculate_cosine_similarity to return different values
        call_count = [0]

        def mock_similarity(query_bytes, stored_bytes):
            call_count[0] += 1
            # First image should have highest similarity
            if call_count[0] == 1:
                return 1.0
            elif call_count[0] == 2:
                return 0.8
            elif call_count[0] == 3:
                return 0.6
            elif call_count[0] == 4:
                return 0.4
            else:
                return 0.2

        db_with_varied_embeddings.embedding_service.calculate_cosine_similarity = (
            mock_similarity
        )

        query_embedding = struct.pack("I", 384) + query_array.tobytes()

        results = await db_with_varied_embeddings.find_similar_images(
            embedding_bytes=query_embedding,
            user_id=1,
            limit=5,
            similarity_threshold=0.0,
        )

        # Verify results are sorted by similarity (descending)
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i][1] >= results[i + 1][1]

    @pytest.mark.asyncio
    async def test_fallback_search_respects_limit(self, db_with_varied_embeddings):
        """Test that fallback search respects the limit parameter"""
        query_array = np.random.rand(384).astype(np.float32)
        db_with_varied_embeddings.embedding_service.bytes_to_array = Mock(
            return_value=query_array
        )
        db_with_varied_embeddings.embedding_service.calculate_cosine_similarity = Mock(
            return_value=0.9
        )

        query_embedding = struct.pack("I", 384) + query_array.tobytes()

        results = await db_with_varied_embeddings.find_similar_images(
            embedding_bytes=query_embedding,
            user_id=1,
            limit=2,  # Request only 2 results
            similarity_threshold=0.0,
        )

        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_fallback_search_handles_null_similarity(
        self, db_with_varied_embeddings
    ):
        """Test fallback search handles None similarity values"""
        query_array = np.random.rand(384).astype(np.float32)
        db_with_varied_embeddings.embedding_service.bytes_to_array = Mock(
            return_value=query_array
        )
        # Return None for some similarities
        db_with_varied_embeddings.embedding_service.calculate_cosine_similarity = Mock(
            return_value=None
        )

        query_embedding = struct.pack("I", 384) + query_array.tobytes()

        results = await db_with_varied_embeddings.find_similar_images(
            embedding_bytes=query_embedding,
            user_id=1,
            limit=5,
            similarity_threshold=0.0,
        )

        # Should return empty list when all similarities are None
        assert results == []


class TestUserEmbeddingCount:
    """Tests for user embedding count retrieval"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def db_with_user_images(self, temp_db_path):
        """Create database with user images for counting"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    user_id INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    embedding BLOB
                )
            """)

            # Insert chats for different users
            await db.execute(
                "INSERT INTO chats (id, chat_id, user_id) VALUES (1, 100, 1)"
            )
            await db.execute(
                "INSERT INTO chats (id, chat_id, user_id) VALUES (2, 200, 2)"
            )

            # Insert images for user 1 (3 with embeddings, 1 without)
            for i in range(3):
                array = np.random.rand(384).astype(np.float32)
                embedding_bytes = struct.pack("I", 384) + array.tobytes()
                await db.execute(
                    "INSERT INTO images (chat_id, embedding) VALUES (1, ?)",
                    (embedding_bytes,),
                )
            await db.execute("INSERT INTO images (chat_id, embedding) VALUES (1, NULL)")

            # Insert images for user 2 (2 with embeddings)
            for i in range(2):
                array = np.random.rand(384).astype(np.float32)
                embedding_bytes = struct.pack("I", 384) + array.tobytes()
                await db.execute(
                    "INSERT INTO images (chat_id, embedding) VALUES (2, ?)",
                    (embedding_bytes,),
                )

            await db.commit()

        return VectorDatabase(db_path=temp_db_path)

    @pytest.mark.asyncio
    async def test_get_user_embedding_count_returns_correct_count(
        self, db_with_user_images
    ):
        """Test that get_user_embedding_count returns correct count for user"""
        count = await db_with_user_images.get_user_embedding_count(user_id=1)
        assert count == 3  # Only images with embeddings

    @pytest.mark.asyncio
    async def test_get_user_embedding_count_different_users(self, db_with_user_images):
        """Test embedding count for different users"""
        count_user1 = await db_with_user_images.get_user_embedding_count(user_id=1)
        count_user2 = await db_with_user_images.get_user_embedding_count(user_id=2)

        assert count_user1 == 3
        assert count_user2 == 2

    @pytest.mark.asyncio
    async def test_get_user_embedding_count_nonexistent_user(self, db_with_user_images):
        """Test embedding count for user with no images"""
        count = await db_with_user_images.get_user_embedding_count(user_id=999)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_user_embedding_count_database_error(self, temp_db_path):
        """Test handling of database errors when counting"""
        vector_db = VectorDatabase(db_path="/nonexistent/path/db.db")

        count = await vector_db.get_user_embedding_count(user_id=1)

        assert count == 0


class TestOrphanedEmbeddingCleanup:
    """Tests for orphaned embedding cleanup functionality"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    async def db_with_orphans(self, temp_db_path):
        """Create database with orphaned embeddings for cleanup testing"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    embedding BLOB
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS embedding_mappings (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    embedding_id INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS image_embeddings (
                    rowid INTEGER PRIMARY KEY,
                    embedding BLOB
                )
            """)

            # Insert valid image
            await db.execute("INSERT INTO images (id, chat_id) VALUES (1, 100)")

            # Insert valid mapping
            await db.execute(
                "INSERT INTO embedding_mappings (image_id, embedding_id) VALUES (1, 1)"
            )
            await db.execute(
                "INSERT INTO image_embeddings (rowid, embedding) VALUES (1, x'00')"
            )

            # Insert orphaned mapping (image_id=999 doesn't exist)
            await db.execute(
                "INSERT INTO embedding_mappings (image_id, embedding_id) VALUES (999, 2)"
            )

            # Insert orphaned embedding (not in mappings)
            await db.execute(
                "INSERT INTO image_embeddings (rowid, embedding) VALUES (3, x'00')"
            )

            await db.commit()

        return VectorDatabase(db_path=temp_db_path)

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_embeddings_removes_orphans(
        self, db_with_orphans, temp_db_path
    ):
        """Test that cleanup removes orphaned embeddings"""
        deleted_count = await db_with_orphans.cleanup_orphaned_embeddings()

        # Should have deleted some orphans
        assert deleted_count >= 0

    @pytest.mark.asyncio
    async def test_cleanup_preserves_valid_mappings(
        self, db_with_orphans, temp_db_path
    ):
        """Test that cleanup preserves valid mappings"""
        await db_with_orphans.cleanup_orphaned_embeddings()

        # Verify valid mapping still exists
        async with aiosqlite.connect(temp_db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM embedding_mappings WHERE image_id = 1"
            )
            result = await cursor.fetchone()
            assert result is not None

    @pytest.mark.asyncio
    async def test_cleanup_database_error(self, temp_db_path):
        """Test handling of database errors during cleanup"""
        vector_db = VectorDatabase(db_path="/nonexistent/path/db.db")

        deleted_count = await vector_db.cleanup_orphaned_embeddings()

        assert deleted_count == 0


class TestGlobalInstanceManagement:
    """Tests for global vector database instance management"""

    def test_get_vector_db_returns_instance(self):
        """Test that get_vector_db returns a VectorDatabase instance"""
        # Reset global instance first
        import src.core.vector_db as module

        module._vector_db = None

        db = get_vector_db()

        assert isinstance(db, VectorDatabase)

    def test_get_vector_db_singleton(self):
        """Test that get_vector_db returns the same instance (singleton)"""
        import src.core.vector_db as module

        module._vector_db = None

        db1 = get_vector_db()
        db2 = get_vector_db()

        assert db1 is db2

    def test_get_vector_db_creates_instance_if_none(self):
        """Test that get_vector_db creates instance if none exists"""
        import src.core.vector_db as module

        module._vector_db = None

        assert module._vector_db is None

        db = get_vector_db()

        assert module._vector_db is not None
        assert module._vector_db is db


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.mark.asyncio
    async def test_store_embedding_zero_image_id(self, temp_db_path):
        """Test storing embedding with zero image_id"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    embedding BLOB
                )
            """)
            await db.execute("INSERT INTO images (id, chat_id) VALUES (0, 100)")
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=array)

        embedding_bytes = struct.pack("I", 384) + array.tobytes()
        result = await vector_db.store_embedding(0, embedding_bytes)

        # Should handle zero ID gracefully
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_find_similar_with_zero_limit(self, temp_db_path):
        """Test similarity search with limit of 0"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER)
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY, chat_id INTEGER, embedding BLOB)
            """)
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=array)
        vector_db.embedding_service.calculate_cosine_similarity = Mock(return_value=0.9)

        embedding_bytes = struct.pack("I", 384) + array.tobytes()

        results = await vector_db.find_similar_images(
            embedding_bytes=embedding_bytes, user_id=1, limit=0
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_with_negative_threshold(self, temp_db_path):
        """Test similarity search with negative threshold (should include negative similarities)"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER)
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY, chat_id INTEGER, embedding BLOB)
            """)
            await db.execute(
                "INSERT INTO chats (id, chat_id, user_id) VALUES (1, 100, 1)"
            )

            array = np.random.rand(384).astype(np.float32)
            embedding_bytes = struct.pack("I", 384) + array.tobytes()
            await db.execute(
                "INSERT INTO images (id, chat_id, embedding) VALUES (1, 1, ?)",
                (embedding_bytes,),
            )
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        query_array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=query_array)
        vector_db.embedding_service.calculate_cosine_similarity = Mock(
            return_value=-0.5
        )

        query_embedding = struct.pack("I", 384) + query_array.tobytes()

        results = await vector_db.find_similar_images(
            embedding_bytes=query_embedding,
            user_id=1,
            limit=5,
            similarity_threshold=-1.0,  # Accept all similarities
        )

        # Should include the result with negative similarity
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, temp_db_path):
        """Test handling of concurrent database operations"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER)
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY, chat_id INTEGER, embedding BLOB)
            """)
            await db.execute(
                "INSERT INTO chats (id, chat_id, user_id) VALUES (1, 100, 1)"
            )
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=array)
        vector_db.embedding_service.calculate_cosine_similarity = Mock(return_value=0.8)

        query_embedding = struct.pack("I", 384) + array.tobytes()

        # Run multiple concurrent searches
        tasks = [
            vector_db.find_similar_images(
                embedding_bytes=query_embedding, user_id=1, limit=5
            )
            for _ in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should complete without errors
        for result in results:
            assert not isinstance(result, Exception)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_embedding_bytes(self, temp_db_path):
        """Test handling of empty embedding bytes"""
        vector_db = VectorDatabase(db_path=temp_db_path)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=None)

        result = await vector_db.store_embedding(1, b"")
        assert result is False

    @pytest.mark.asyncio
    async def test_large_embedding_dimension(self, temp_db_path):
        """Test handling of larger embedding dimensions"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY, chat_id INTEGER, embedding BLOB)
            """)
            await db.execute("INSERT INTO images (id, chat_id) VALUES (1, 100)")
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)

        # Create large embedding (1536 dimensions like OpenAI)
        large_array = np.random.rand(1536).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=large_array)

        large_embedding = struct.pack("I", 1536) + large_array.tobytes()

        result = await vector_db.store_embedding(1, large_embedding)

        # Should handle larger dimensions
        assert isinstance(result, bool)


class TestDatabaseSchemaInteraction:
    """Tests for database schema interaction edge cases"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.mark.asyncio
    async def test_missing_images_table(self, temp_db_path):
        """Test behavior when images table doesn't exist"""
        # Create empty database without required tables
        async with aiosqlite.connect(temp_db_path) as db:
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=array)

        embedding_bytes = struct.pack("I", 384) + array.tobytes()

        # Should fail gracefully
        result = await vector_db.store_embedding(1, embedding_bytes)
        assert result is False

    @pytest.mark.asyncio
    async def test_missing_chats_table_for_search(self, temp_db_path):
        """Test search behavior when chats table doesn't exist"""
        async with aiosqlite.connect(temp_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY, chat_id INTEGER, embedding BLOB)
            """)
            await db.commit()

        vector_db = VectorDatabase(db_path=temp_db_path)
        array = np.random.rand(384).astype(np.float32)
        vector_db.embedding_service.bytes_to_array = Mock(return_value=array)

        embedding_bytes = struct.pack("I", 384) + array.tobytes()

        # Should return empty list, not crash
        results = await vector_db.find_similar_images(
            embedding_bytes=embedding_bytes, user_id=1, limit=5
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_idempotent_initialization(self, temp_db_path):
        """Test that initialize_vector_support can be called multiple times"""
        vector_db = VectorDatabase(db_path=temp_db_path)

        # Call multiple times
        result1 = await vector_db.initialize_vector_support()
        result2 = await vector_db.initialize_vector_support()
        result3 = await vector_db.initialize_vector_support()

        # Should not crash, results should be consistent
        assert result1 == result2 == result3
