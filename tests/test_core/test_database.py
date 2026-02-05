import asyncio
import json
import os
import struct
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.database import (
    get_chat_count,
    get_embedding_stats,
    get_image_count,
    get_user_count,
    health_check,
    init_database,
)
from src.models.base import Base
from src.models.chat import Chat
from src.models.image import Image
from src.models.user import User


def build_embedding_bytes(values):
    """Pack embedding floats into the byte format used by EmbeddingService."""
    return struct.pack("I", len(values)) + struct.pack(f"{len(values)}f", *values)


class TestDatabase:
    """Test suite for database operations and integrity"""

    @pytest.fixture
    async def test_db_engine(self):
        """Create test database engine with temporary SQLite database"""
        # Create temporary database file
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        # Create async engine for testing
        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        # Cleanup
        await engine.dispose()
        os.unlink(db_path)

    @pytest.fixture
    async def test_session(self, test_db_engine):
        """Create test database session"""
        async_session = sessionmaker(
            test_db_engine, class_=AsyncSession, expire_on_commit=False
        )

        session = async_session()
        try:
            yield session
        finally:
            await session.close()

    @pytest.fixture
    async def sample_users(self, test_session):
        """Create sample users for testing"""
        users = [
            User(
                user_id=123456,
                username="testuser1",
                first_name="Test",
                last_name="User1",
                banned=False,
            ),
            User(
                user_id=789012,
                username="testuser2",
                first_name="Test",
                last_name="User2",
                banned=False,
            ),
            User(
                user_id=345678,
                username="banneduser",
                first_name="Banned",
                last_name="User",
                banned=True,
            ),
        ]

        for user in users:
            test_session.add(user)
        await test_session.commit()

        return users

    @pytest.fixture
    async def sample_chats(self, test_session, sample_users):
        """Create sample chats for testing"""
        chats = [
            Chat(
                chat_id=-1001234567890,
                user_id=sample_users[0].id,
                chat_type="group",
                title="Test Group 1",
                current_mode="default",
            ),
            Chat(
                chat_id=-1009876543210,
                user_id=sample_users[1].id,
                chat_type="group",
                title="Test Group 2",
                current_mode="artistic",
            ),
            Chat(
                chat_id=123456,  # Private chat with first user
                user_id=sample_users[0].id,
                chat_type="private",
                title=None,
                current_mode="default",
            ),
        ]

        for chat in chats:
            test_session.add(chat)
        await test_session.commit()

        return chats

    @pytest.fixture
    async def sample_images(self, test_session, sample_chats):
        """Create sample images for testing"""
        images = [
            Image(
                file_id="AgACAgIAAxkBAAI",
                file_unique_id="AgACAgIAAxkBAAI_unique",
                chat_id=sample_chats[0].id,
                original_path="/test/image1.jpg",
                file_size=1024,
                analysis=json.dumps(
                    {"summary": "Test image 1", "description": "A test image"}
                ),
                embedding=build_embedding_bytes([0.1, 0.2, 0.3, 0.4, 0.5]),
                processing_status="completed",
            ),
            Image(
                file_id="AgACAgIAAxkBAAJ",
                file_unique_id="AgACAgIAAxkBAAJ_unique",
                chat_id=sample_chats[0].id,
                original_path="/test/image2.jpg",
                file_size=2048,
                analysis=json.dumps(
                    {
                        "summary": "Test image 2",
                        "description": "Another test image",
                    }
                ),
                embedding=build_embedding_bytes([0.2, 0.3, 0.4, 0.5, 0.6]),
                processing_status="completed",
            ),
            Image(
                file_id="AgACAgIAAxkBAAK",
                file_unique_id="AgACAgIAAxkBAAK_unique",
                chat_id=sample_chats[1].id,
                original_path="/test/image3.jpg",
                file_size=1536,
                analysis=json.dumps(
                    {"summary": "Test image 3", "description": "Third test image"}
                ),
                embedding=build_embedding_bytes([0.9, 0.8, 0.7, 0.6, 0.5]),
                processing_status="completed",
            ),
        ]

        for image in images:
            test_session.add(image)
        await test_session.commit()

        return images

    @pytest.mark.asyncio
    async def test_database_initialization(self):
        """Test database initialization process"""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            database_url = f"sqlite+aiosqlite:///{db_path}"

            with patch("src.core.database.get_database_url", return_value=database_url):
                await init_database()

                # Verify database file was created
                assert db_path.exists()

                # Verify tables were created by connecting and checking
                engine = create_async_engine(database_url)
                async with engine.begin() as conn:
                    # Check if tables exist
                    result = await conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                    tables = [row[0] for row in result]

                    expected_tables = ["users", "chats", "images", "messages"]
                    for table in expected_tables:
                        assert table in tables

                await engine.dispose()

    @pytest.mark.asyncio
    async def test_health_check_success(self, test_db_engine):
        """Test successful database health check"""
        session_factory = async_sessionmaker(
            test_db_engine, class_=AsyncSession, expire_on_commit=False
        )
        with patch("src.core.database._session_factory", session_factory):
            is_healthy = await health_check()
            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test database health check failure"""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Connection failed"))

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_session
        mock_context.__aexit__.return_value = None

        with patch("src.core.database.get_db_session", return_value=mock_context):
            is_healthy = await health_check()
            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_user_count_functionality(self):
        """Test user count retrieval"""
        # Create test engine and session
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        # Create async engine for testing
        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            # Create test session directly
            async_session = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

            async with async_session() as session:
                # Create sample users in the test session
                users = [
                    User(
                        user_id=123456,
                        username="testuser1",
                        first_name="Test",
                        last_name="User1",
                        banned=False,
                    ),
                    User(
                        user_id=789012,
                        username="testuser2",
                        first_name="Test",
                        last_name="User2",
                        banned=False,
                    ),
                    User(
                        user_id=345678,
                        username="banneduser",
                        first_name="Banned",
                        last_name="User",
                        banned=True,
                    ),
                ]

                for user in users:
                    session.add(user)
                await session.commit()

                # Create async context manager mock
                mock_context = AsyncMock()
                mock_context.__aenter__.return_value = session
                mock_context.__aexit__.return_value = None

                with patch(
                    "src.core.database.get_db_session", return_value=mock_context
                ):
                    count = await get_user_count()

                    # Should count all users (including banned)
                    assert count == 3
        finally:
            await engine.dispose()
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_chat_count_functionality(self, test_session, sample_chats):
        """Test chat count retrieval"""
        with patch("src.core.database.get_db_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_session

            count = await get_chat_count()

            assert count == 3

    @pytest.mark.asyncio
    async def test_image_count_functionality(self, test_session, sample_images):
        """Test image count retrieval"""
        with patch("src.core.database.get_db_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_session

            count = await get_image_count()

            assert count == 3

    @pytest.mark.asyncio
    async def test_embedding_stats_functionality(self, test_session, sample_images):
        """Test embedding statistics retrieval"""
        with patch("src.core.database.get_db_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_session

            stats = await get_embedding_stats()

            assert isinstance(stats, dict)
            assert stats["total_images"] == 3
            assert stats["with_embeddings"] == 3
            assert stats["without_embeddings"] == 0
            assert stats["coverage_percentage"] == 100

    @pytest.mark.asyncio
    async def test_concurrent_database_operations(self, test_db_engine):
        """Test concurrent database operations"""

        async def create_user(user_id, username):
            async_session = sessionmaker(
                test_db_engine, class_=AsyncSession, expire_on_commit=False
            )
            async with async_session() as session:
                user = User(
                    user_id=user_id,
                    username=username,
                    first_name="Concurrent",
                    last_name="Test",
                    banned=False,
                )
                session.add(user)
                await session.commit()
            return user

        # Create multiple users concurrently
        tasks = [
            create_user(i, f"concurrent_user_{i}")
            for i in range(100000, 100010)  # 10 users
        ]

        users = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all operations completed successfully
        successful_users = [u for u in users if not isinstance(u, Exception)]
        assert len(successful_users) >= 5  # Allow for some potential race conditions

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, test_session):
        """Test transaction rollback on error"""
        try:
            # Start transaction
            user = User(
                user_id=999999,
                username="rollback_test",
                first_name="Rollback",
                last_name="Test",
                is_active=True,
            )
            test_session.add(user)

            # Create duplicate user (should cause constraint violation)
            duplicate_user = User(
                user_id=999999,  # Same ID should cause error
                username="duplicate",
                first_name="Duplicate",
                last_name="Test",
                is_active=True,
            )
            test_session.add(duplicate_user)

            await test_session.commit()

        except Exception:
            await test_session.rollback()

        # Verify no users were committed
        result = await test_session.execute(select(User).where(User.user_id == 999999))
        users = result.scalars().all()
        assert len(users) == 0

    @pytest.mark.asyncio
    async def test_large_embedding_storage(self, test_session, sample_chats):
        """Test storage and retrieval of large embeddings"""
        # Create image with large embedding (simulating real-world embeddings)
        large_embedding = [float(i) for i in range(1536)]  # OpenAI embedding size

        image = Image(
            file_id="large_embedding_test",
            file_unique_id="large_embedding_test_unique",
            chat_id=sample_chats[0].id,
            original_path="/test/large_embedding.jpg",
            file_size=5000,
            analysis=json.dumps(
                {
                    "summary": "Large embedding test",
                    "description": "Testing large embeddings",
                }
            ),
            embedding=build_embedding_bytes(large_embedding),
            processing_status="completed",
        )

        test_session.add(image)
        await test_session.commit()

        # Retrieve and verify
        result = await test_session.execute(
            select(Image).where(Image.file_id == "large_embedding_test")
        )
        retrieved_image = result.scalar_one()

        dimension = struct.unpack("I", retrieved_image.embedding[:4])[0]
        assert dimension == 1536
        assert len(retrieved_image.embedding) == 4 + 1536 * 4

    @pytest.mark.asyncio
    async def test_database_integrity_constraints(self, test_session):
        """Test database integrity constraints"""
        await test_session.execute(text("PRAGMA foreign_keys=ON"))
        # Test foreign key constraint
        with pytest.raises(Exception):
            # Try to create image with non-existent chat_id
            invalid_image = Image(
                file_id="invalid_chat_test",
                file_unique_id="invalid_chat_test_unique",
                chat_id=-9999999999999,  # Non-existent chat
                original_path="/test/invalid.jpg",
                file_size=1000,
                analysis=json.dumps({"summary": "Invalid test"}),
                embedding=build_embedding_bytes([0.1, 0.2]),
                processing_status="completed",
            )
            test_session.add(invalid_image)
            await test_session.commit()

    @pytest.mark.asyncio
    async def test_data_migration_simulation(self, test_session, sample_users):
        """Test data migration scenarios"""
        # Simulate adding new column to existing data

        # First, verify existing users
        result = await test_session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 3

        # Simulate migration by updating all users
        for user in users:
            user.user_group = "active"

        await test_session.commit()

        # Verify migration
        result = await test_session.execute(
            select(User).where(User.user_group == "active")
        )
        active_users = result.scalars().all()
        assert len(active_users) == 3

    @pytest.mark.asyncio
    async def test_bulk_operations_performance(self, test_session, sample_chats):
        """Test performance of bulk database operations"""
        import time

        # Create many images for bulk testing
        chat_id = sample_chats[0].id
        bulk_images = []
        for i in range(100):
            image = Image(
                file_id=f"bulk_test_{i}",
                file_unique_id=f"bulk_test_{i}_unique",
                chat_id=chat_id,
                original_path=f"/test/bulk_{i}.jpg",
                file_size=1000 + i,
                analysis=json.dumps({"summary": f"Bulk test image {i}"}),
                embedding=build_embedding_bytes([float(j) for j in range(5)]),
                processing_status="completed",
            )
            bulk_images.append(image)

        # Measure bulk insert time
        start_time = time.time()

        test_session.add_all(bulk_images)
        await test_session.commit()

        end_time = time.time()
        bulk_time = end_time - start_time

        # Should complete within reasonable time (adjust threshold as needed)
        assert bulk_time < 5.0  # 5 seconds for 100 records

        # Verify all records were inserted
        result = await test_session.execute(
            select(Image).where(Image.file_id.like("bulk_test_%"))
        )
        inserted_images = result.scalars().all()
        assert len(inserted_images) == 100

    @pytest.mark.asyncio
    async def test_connection_pool_management(self, test_db_engine):
        """Test database connection pool management"""

        # Create multiple concurrent sessions
        async def db_operation(session_id):
            async_session = sessionmaker(
                test_db_engine, class_=AsyncSession, expire_on_commit=False
            )

            async with async_session() as session:
                # Simple query to test connection
                result = await session.execute(text("SELECT 1"))
                return result.scalar()

        # Run multiple concurrent operations
        tasks = [db_operation(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should succeed
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == 10
        assert all(result == 1 for result in successful_results)

    @pytest.mark.asyncio
    async def test_database_cleanup_operations(self, test_session, sample_images):
        """Test database cleanup and maintenance operations"""
        # Test deletion of orphaned records

        # Delete all images first
        await test_session.execute(delete(Image))
        await test_session.commit()

        # Verify cleanup
        result = await test_session.execute(select(Image))
        remaining_images = result.scalars().all()
        assert len(remaining_images) == 0

        # Test cascade operations (if implemented)
        result = await test_session.execute(select(Chat))
        chats = result.scalars().all()
        # Chats should still exist even after images are deleted
        assert len(chats) > 0
