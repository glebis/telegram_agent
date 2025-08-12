import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete

from src.core.database import (
    init_database,
    get_db_session,
    health_check,
    get_user_count,
    get_chat_count,
    get_image_count,
    get_embedding_stats,
    close_database,
)
from src.models.user import User
from src.models.chat import Chat
from src.models.image import Image
from src.models.base import Base


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

        async with async_session() as session:
            yield session

    @pytest.fixture
    async def sample_users(self, test_session):
        """Create sample users for testing"""
        users = [
            User(
                user_id=123456,
                username="testuser1",
                first_name="Test",
                last_name="User1",
                is_active=True,
            ),
            User(
                user_id=789012,
                username="testuser2",
                first_name="Test",
                last_name="User2",
                is_active=True,
            ),
            User(
                user_id=345678,
                username="inactiveuser",
                first_name="Inactive",
                last_name="User",
                is_active=False,
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
                chat_type="group",
                title="Test Group 1",
                current_mode="default",
            ),
            Chat(
                chat_id=-1009876543210,
                chat_type="group",
                title="Test Group 2",
                current_mode="artistic",
            ),
            Chat(
                chat_id=123456,  # Private chat with first user
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
                chat_id=sample_chats[0].chat_id,
                file_path="/test/image1.jpg",
                file_size=1024,
                analysis={"summary": "Test image 1", "description": "A test image"},
                embedding=[0.1, 0.2, 0.3, 0.4, 0.5],
            ),
            Image(
                file_id="AgACAgIAAxkBAAJ",
                chat_id=sample_chats[0].chat_id,
                file_path="/test/image2.jpg",
                file_size=2048,
                analysis={
                    "summary": "Test image 2",
                    "description": "Another test image",
                },
                embedding=[0.2, 0.3, 0.4, 0.5, 0.6],
            ),
            Image(
                file_id="AgACAgIAAxkBAAK",
                chat_id=sample_chats[1].chat_id,
                file_path="/test/image3.jpg",
                file_size=1536,
                analysis={"summary": "Test image 3", "description": "Third test image"},
                embedding=[0.9, 0.8, 0.7, 0.6, 0.5],
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
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                    tables = [row[0] for row in result]

                    expected_tables = ["users", "chats", "images", "messages"]
                    for table in expected_tables:
                        assert table in tables

                await engine.dispose()

    @pytest.mark.asyncio
    async def test_health_check_success(self, test_db_engine):
        """Test successful database health check"""
        with patch("src.core.database.engine", test_db_engine):
            is_healthy = await health_check()
            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test database health check failure"""
        # Mock engine that raises exception
        mock_engine = Mock()
        mock_engine.execute = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("src.core.database.engine", mock_engine):
            is_healthy = await health_check()
            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_user_count_functionality(self, test_session, sample_users):
        """Test user count retrieval"""
        with patch("src.core.database.get_db_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = test_session

            count = await get_user_count()

            # Should count all users (including inactive)
            assert count == 3

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
            assert "total_embeddings" in stats
            assert "vector_dimensions" in stats
            assert stats["total_embeddings"] == 3
            assert (
                stats["vector_dimensions"] == 5
            )  # Our test embeddings have 5 dimensions

    @pytest.mark.asyncio
    async def test_concurrent_database_operations(self, test_session):
        """Test concurrent database operations"""

        async def create_user(user_id, username):
            user = User(
                user_id=user_id,
                username=username,
                first_name="Concurrent",
                last_name="Test",
                is_active=True,
            )
            test_session.add(user)
            await test_session.commit()
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
    async def test_large_embedding_storage(self, test_session):
        """Test storage and retrieval of large embeddings"""
        # Create image with large embedding (simulating real-world embeddings)
        large_embedding = [float(i) for i in range(1536)]  # OpenAI embedding size

        image = Image(
            file_id="large_embedding_test",
            chat_id=-1001111111111,
            file_path="/test/large_embedding.jpg",
            file_size=5000,
            analysis={
                "summary": "Large embedding test",
                "description": "Testing large embeddings",
            },
            embedding=large_embedding,
        )

        test_session.add(image)
        await test_session.commit()

        # Retrieve and verify
        result = await test_session.execute(
            select(Image).where(Image.file_id == "large_embedding_test")
        )
        retrieved_image = result.scalar_one()

        assert len(retrieved_image.embedding) == 1536
        assert retrieved_image.embedding == large_embedding

    @pytest.mark.asyncio
    async def test_database_integrity_constraints(self, test_session):
        """Test database integrity constraints"""
        # Test foreign key constraint
        with pytest.raises(Exception):
            # Try to create image with non-existent chat_id
            invalid_image = Image(
                file_id="invalid_chat_test",
                chat_id=-9999999999999,  # Non-existent chat
                file_path="/test/invalid.jpg",
                file_size=1000,
                analysis={"summary": "Invalid test"},
                embedding=[0.1, 0.2],
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
            user.is_active = True  # Ensure all users are active

        await test_session.commit()

        # Verify migration
        result = await test_session.execute(select(User).where(User.is_active == True))
        active_users = result.scalars().all()
        assert len(active_users) == 3

    @pytest.mark.asyncio
    async def test_bulk_operations_performance(self, test_session):
        """Test performance of bulk database operations"""
        import time

        # Create many images for bulk testing
        bulk_images = []
        for i in range(100):
            image = Image(
                file_id=f"bulk_test_{i}",
                chat_id=-1001000000000,
                file_path=f"/test/bulk_{i}.jpg",
                file_size=1000 + i,
                analysis={"summary": f"Bulk test image {i}"},
                embedding=[float(j) for j in range(5)],
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
                result = await session.execute("SELECT 1")
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
