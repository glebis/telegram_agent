"""
Comprehensive pytest tests for plugin database model support.

This module tests the plugin models functionality including:
- Plugin model registration and table creation
- Table existence checking
- Table creation and dropping
- PluginModelMixin class
- Error handling scenarios
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, String, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.plugins.models import (
    PluginModelMixin,
    _create_table,
    _table_exists,
    drop_plugin_tables,
    register_plugin_models,
)


# Test model that properly inherits from Base
# Note: Prefix with underscore to avoid pytest collection warning
class _TestPluginModel(Base):
    """Test model for plugin system testing."""

    __tablename__ = "test_plugin_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=True)


# Alias for use in tests
TestPluginModel = _TestPluginModel


# Test model that does NOT inherit from Base (for testing validation)
class InvalidPluginModel:
    """Invalid model that does not inherit from Base."""

    __tablename__ = "invalid_model"


# Test model with mixin
# Note: Prefix with underscore to avoid pytest collection warning
class _TestMixinModel(Base, PluginModelMixin):
    """Test model that uses PluginModelMixin."""

    __tablename__ = "test_mixin_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data: Mapped[str] = mapped_column(String(255), nullable=True)


# Alias for use in tests
TestMixinModel = _TestMixinModel


class TestPluginModelMixin:
    """Tests for PluginModelMixin class."""

    def test_mixin_exists(self):
        """Test that PluginModelMixin class exists and can be instantiated."""
        # The mixin is currently a pass-through, but should be importable
        assert PluginModelMixin is not None

    def test_model_with_mixin_inherits_correctly(self):
        """Test that a model with PluginModelMixin properly inherits from Base."""
        assert issubclass(TestMixinModel, Base)
        assert issubclass(TestMixinModel, PluginModelMixin)

    def test_model_with_mixin_has_tablename(self):
        """Test that model with mixin has __tablename__ attribute."""
        assert hasattr(TestMixinModel, "__tablename__")
        assert TestMixinModel.__tablename__ == "test_mixin_data"


class TestTableExists:
    """Tests for the _table_exists helper function."""

    @pytest.fixture
    async def test_db(self):
        """Create a test database with tables."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield {
            "engine": engine,
            "db_path": db_path,
            "database_url": database_url,
        }

        # Cleanup
        await engine.dispose()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_table_exists_returns_true_for_existing_table(self, test_db):
        """Test _table_exists returns True for tables that exist."""
        with patch("src.plugins.models.get_db_session") as mock_get_session:
            # Create a real session
            async_session = async_sessionmaker(
                test_db["engine"], class_=AsyncSession, expire_on_commit=False
            )

            # Create the table first
            async with test_db["engine"].begin() as conn:
                await conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS existing_test_table "
                        "(id INTEGER PRIMARY KEY)"
                    )
                )

            # Mock get_db_session to return our test session
            mock_context = AsyncMock()
            async_session_instance = async_session()
            mock_context.__aenter__.return_value = async_session_instance
            mock_context.__aexit__.return_value = None
            mock_get_session.return_value = mock_context

            result = await _table_exists("existing_test_table")

            await async_session_instance.close()
            assert result is True

    @pytest.mark.asyncio
    async def test_table_exists_returns_false_for_nonexistent_table(self, test_db):
        """Test _table_exists returns False for tables that don't exist."""
        with patch("src.plugins.models.get_db_session") as mock_get_session:
            async_session = async_sessionmaker(
                test_db["engine"], class_=AsyncSession, expire_on_commit=False
            )

            mock_context = AsyncMock()
            async_session_instance = async_session()
            mock_context.__aenter__.return_value = async_session_instance
            mock_context.__aexit__.return_value = None
            mock_get_session.return_value = mock_context

            result = await _table_exists("nonexistent_table_xyz")

            await async_session_instance.close()
            assert result is False

    @pytest.mark.asyncio
    async def test_table_exists_handles_exception(self):
        """Test _table_exists returns False when exception occurs."""
        with patch("src.plugins.models.get_db_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=Exception("Database error"))

            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_session
            mock_context.__aexit__.return_value = None
            mock_get_session.return_value = mock_context

            result = await _table_exists("any_table")

            assert result is False


class TestCreateTable:
    """Tests for the _create_table helper function."""

    @pytest.fixture
    async def test_db(self):
        """Create a test database."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        yield {
            "engine": engine,
            "db_path": db_path,
            "database_url": database_url,
        }

        # Cleanup
        await engine.dispose()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_create_table_creates_new_table(self, test_db):
        """Test _create_table creates a new table successfully."""
        with patch("src.plugins.models.get_engine", return_value=test_db["engine"]):
            # Ensure table doesn't exist yet
            async with test_db["engine"].begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='test_plugin_data'"
                    )
                )
                assert result.scalar() is None

            # Create the table
            await _create_table(TestPluginModel)

            # Verify table was created
            async with test_db["engine"].begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='test_plugin_data'"
                    )
                )
                assert result.scalar() == "test_plugin_data"

    @pytest.mark.asyncio
    async def test_create_table_raises_on_error(self):
        """Test _create_table raises exception on database error."""
        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock(side_effect=Exception("Create failed"))

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_conn
        mock_context.__aexit__.return_value = None
        mock_engine.begin.return_value = mock_context

        with patch("src.plugins.models.get_engine", return_value=mock_engine):
            with pytest.raises(Exception, match="Create failed"):
                await _create_table(TestPluginModel)


class TestRegisterPluginModels:
    """Tests for the register_plugin_models function."""

    @pytest.fixture
    async def test_db(self):
        """Create a test database."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        yield {
            "engine": engine,
            "db_path": db_path,
            "database_url": database_url,
        }

        # Cleanup
        await engine.dispose()
        os.unlink(db_path)

    @pytest.fixture
    def mock_plugin(self):
        """Create a mock plugin instance."""
        plugin = MagicMock()
        plugin.metadata.name = "test-plugin"
        return plugin

    @pytest.mark.asyncio
    async def test_register_empty_models_list(self, mock_plugin):
        """Test register_plugin_models handles empty models list."""
        # Should not raise and return early
        await register_plugin_models(mock_plugin, [])
        # No assertion needed - just verifying no exception

    @pytest.mark.asyncio
    async def test_register_none_models_list(self, mock_plugin):
        """Test register_plugin_models handles None models list."""
        # Should not raise and return early
        await register_plugin_models(mock_plugin, None)
        # No assertion needed - just verifying no exception

    @pytest.mark.asyncio
    async def test_register_skips_invalid_model(self, mock_plugin):
        """Test register_plugin_models skips models that don't inherit from Base."""
        with patch("src.plugins.models._table_exists") as mock_exists:
            # _table_exists should not be called for invalid models
            await register_plugin_models(mock_plugin, [InvalidPluginModel])

            # Verify _table_exists was never called since the model was skipped
            mock_exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_creates_table_if_not_exists(self, mock_plugin, test_db):
        """Test register_plugin_models creates table when it doesn't exist."""
        with (
            patch("src.plugins.models._table_exists", return_value=False) as mock_exists,
            patch("src.plugins.models._create_table") as mock_create,
        ):
            await register_plugin_models(mock_plugin, [TestPluginModel])

            mock_exists.assert_called_once_with("test_plugin_data")
            mock_create.assert_called_once_with(TestPluginModel)

    @pytest.mark.asyncio
    async def test_register_skips_existing_table(self, mock_plugin):
        """Test register_plugin_models skips table creation if table exists."""
        with (
            patch("src.plugins.models._table_exists", return_value=True) as mock_exists,
            patch("src.plugins.models._create_table") as mock_create,
        ):
            await register_plugin_models(mock_plugin, [TestPluginModel])

            mock_exists.assert_called_once_with("test_plugin_data")
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_multiple_models(self, mock_plugin):
        """Test register_plugin_models handles multiple models."""
        # Create a second test model dynamically
        class AnotherTestModel(Base):
            __tablename__ = "another_test_table"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        with (
            patch("src.plugins.models._table_exists", return_value=False) as mock_exists,
            patch("src.plugins.models._create_table") as mock_create,
        ):
            await register_plugin_models(
                mock_plugin, [TestPluginModel, AnotherTestModel]
            )

            assert mock_exists.call_count == 2
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_register_mixed_valid_invalid_models(self, mock_plugin):
        """Test register_plugin_models processes valid models and skips invalid."""
        with (
            patch("src.plugins.models._table_exists", return_value=False) as mock_exists,
            patch("src.plugins.models._create_table") as mock_create,
        ):
            await register_plugin_models(
                mock_plugin, [InvalidPluginModel, TestPluginModel]
            )

            # Only valid model should be processed
            mock_exists.assert_called_once_with("test_plugin_data")
            mock_create.assert_called_once_with(TestPluginModel)


class TestDropPluginTables:
    """Tests for the drop_plugin_tables function."""

    @pytest.fixture
    async def test_db(self):
        """Create a test database."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        yield {
            "engine": engine,
            "db_path": db_path,
            "database_url": database_url,
        }

        # Cleanup
        await engine.dispose()
        os.unlink(db_path)

    @pytest.fixture
    def mock_plugin_with_models(self):
        """Create a mock plugin with database models."""
        plugin = MagicMock()
        plugin.metadata.name = "test-plugin"
        plugin.get_database_models.return_value = [TestPluginModel]
        return plugin

    @pytest.fixture
    def mock_plugin_no_models(self):
        """Create a mock plugin without database models."""
        plugin = MagicMock()
        plugin.metadata.name = "no-models-plugin"
        plugin.get_database_models.return_value = []
        return plugin

    @pytest.mark.asyncio
    async def test_drop_plugin_tables_no_models(self, mock_plugin_no_models):
        """Test drop_plugin_tables handles plugins with no models."""
        # Should not raise and return early
        await drop_plugin_tables(mock_plugin_no_models)

        # Verify get_database_models was called
        mock_plugin_no_models.get_database_models.assert_called_once()

    @pytest.mark.asyncio
    async def test_drop_plugin_tables_none_models(self):
        """Test drop_plugin_tables handles plugins returning None."""
        plugin = MagicMock()
        plugin.get_database_models.return_value = None

        # Should not raise and return early
        await drop_plugin_tables(plugin)

    @pytest.mark.asyncio
    async def test_drop_plugin_tables_drops_existing_table(
        self, mock_plugin_with_models, test_db
    ):
        """Test drop_plugin_tables successfully drops a table."""
        with patch("src.plugins.models.get_engine", return_value=test_db["engine"]):
            # Create the table first
            async with test_db["engine"].begin() as conn:
                await conn.run_sync(
                    lambda sync_conn: TestPluginModel.__table__.create(
                        sync_conn, checkfirst=True
                    )
                )

            # Verify table exists
            async with test_db["engine"].begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='test_plugin_data'"
                    )
                )
                assert result.scalar() == "test_plugin_data"

            # Drop the table
            await drop_plugin_tables(mock_plugin_with_models)

            # Verify table was dropped
            async with test_db["engine"].begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='test_plugin_data'"
                    )
                )
                assert result.scalar() is None

    @pytest.mark.asyncio
    async def test_drop_plugin_tables_handles_nonexistent_table(
        self, mock_plugin_with_models, test_db
    ):
        """Test drop_plugin_tables handles dropping non-existent table gracefully."""
        with patch("src.plugins.models.get_engine", return_value=test_db["engine"]):
            # Table doesn't exist - should not raise due to checkfirst=True
            await drop_plugin_tables(mock_plugin_with_models)
            # No exception means success

    @pytest.mark.asyncio
    async def test_drop_plugin_tables_continues_on_error(self):
        """Test drop_plugin_tables continues with other tables after error."""

        class Model1(Base):
            __tablename__ = "model1_table"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        class Model2(Base):
            __tablename__ = "model2_table"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        plugin = MagicMock()
        plugin.get_database_models.return_value = [Model1, Model2]

        # Track calls
        call_count = [0]

        # Create a mock engine that returns proper async context managers
        mock_engine = MagicMock()

        # Create async context manager class for begin()
        class MockBeginContext:
            def __init__(self, should_fail):
                self.should_fail = should_fail

            async def __aenter__(self):
                mock_conn = MagicMock()
                if self.should_fail:
                    mock_conn.run_sync = MagicMock(
                        side_effect=Exception("Drop failed")
                    )
                else:
                    mock_conn.run_sync = MagicMock()
                return mock_conn

            async def __aexit__(self, *args):
                pass

        def mock_begin():
            call_count[0] += 1
            # First call fails, second succeeds
            return MockBeginContext(should_fail=(call_count[0] == 1))

        mock_engine.begin = mock_begin

        with patch("src.plugins.models.get_engine", return_value=mock_engine):
            # Should not raise - continues after first error
            await drop_plugin_tables(plugin)

            # Both tables should have been attempted
            assert call_count[0] == 2


class TestIntegration:
    """Integration tests for plugin model registration workflow."""

    @pytest.fixture
    async def test_db(self):
        """Create a test database."""
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(db_fd)

        database_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(database_url, echo=False, future=True)

        yield {
            "engine": engine,
            "db_path": db_path,
            "database_url": database_url,
        }

        # Cleanup
        await engine.dispose()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_full_lifecycle_register_and_drop(self, test_db):
        """Test complete lifecycle: register models, verify, then drop."""
        # Create a fresh model for this test
        class LifecycleTestModel(Base):
            __tablename__ = "lifecycle_test_table"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)
            data: Mapped[str] = mapped_column(String(100), nullable=True)

        mock_plugin = MagicMock()
        mock_plugin.metadata.name = "lifecycle-plugin"
        mock_plugin.get_database_models.return_value = [LifecycleTestModel]

        # Setup session factory for _table_exists
        async_session_factory = async_sessionmaker(
            test_db["engine"], class_=AsyncSession, expire_on_commit=False
        )

        # Create a proper async context manager class for get_db_session
        class MockSessionContext:
            def __init__(self):
                self.session = None

            async def __aenter__(self):
                self.session = async_session_factory()
                return self.session

            async def __aexit__(self, *args):
                if self.session:
                    await self.session.close()

        with (
            patch("src.plugins.models.get_engine", return_value=test_db["engine"]),
            patch(
                "src.plugins.models.get_db_session",
                side_effect=lambda: MockSessionContext(),
            ),
        ):
            # Step 1: Register models (creates table)
            await register_plugin_models(mock_plugin, [LifecycleTestModel])

            # Step 2: Verify table exists
            async with test_db["engine"].begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='lifecycle_test_table'"
                    )
                )
                assert result.scalar() == "lifecycle_test_table"

            # Step 3: Insert some data
            async with test_db["engine"].begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO lifecycle_test_table (data) VALUES ('test_data')"
                    )
                )

            # Step 4: Verify data exists
            async with test_db["engine"].begin() as conn:
                result = await conn.execute(
                    text("SELECT data FROM lifecycle_test_table")
                )
                assert result.scalar() == "test_data"

            # Step 5: Drop table
            await drop_plugin_tables(mock_plugin)

            # Step 6: Verify table is dropped
            async with test_db["engine"].begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='lifecycle_test_table'"
                    )
                )
                assert result.scalar() is None


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def mock_plugin(self):
        """Create a mock plugin instance."""
        plugin = MagicMock()
        plugin.metadata.name = "edge-case-plugin"
        return plugin

    @pytest.mark.asyncio
    async def test_register_model_with_special_table_name(self, mock_plugin):
        """Test registering model with special characters in table name."""

        class SpecialNameModel(Base):
            __tablename__ = "special_table_123"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        with (
            patch("src.plugins.models._table_exists", return_value=False) as mock_exists,
            patch("src.plugins.models._create_table") as mock_create,
        ):
            await register_plugin_models(mock_plugin, [SpecialNameModel])

            mock_exists.assert_called_once_with("special_table_123")
            mock_create.assert_called_once_with(SpecialNameModel)

    @pytest.mark.asyncio
    async def test_register_model_with_long_table_name(self, mock_plugin):
        """Test registering model with a long table name."""

        class LongNameModel(Base):
            __tablename__ = "a" * 64  # Max typical table name length
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        with (
            patch("src.plugins.models._table_exists", return_value=False) as mock_exists,
            patch("src.plugins.models._create_table") as mock_create,
        ):
            await register_plugin_models(mock_plugin, [LongNameModel])

            mock_exists.assert_called_once_with("a" * 64)
            mock_create.assert_called_once_with(LongNameModel)

    @pytest.mark.asyncio
    async def test_table_exists_empty_table_name(self):
        """Test _table_exists with empty table name."""
        with patch("src.plugins.models.get_db_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=MagicMock(scalar=lambda: None))

            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_session
            mock_context.__aexit__.return_value = None
            mock_get_session.return_value = mock_context

            result = await _table_exists("")

            assert result is False

    @pytest.mark.asyncio
    async def test_plugin_name_used_in_logging(self, mock_plugin):
        """Test that plugin name is used in logging messages."""
        mock_plugin.metadata.name = "logging-test-plugin"

        with (
            patch("src.plugins.models._table_exists", return_value=False),
            patch("src.plugins.models._create_table"),
            patch("src.plugins.models.logger") as mock_logger,
        ):
            await register_plugin_models(mock_plugin, [TestPluginModel])

            # Verify logging was called with plugin name
            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "logging-test-plugin" in call_args

    @pytest.mark.asyncio
    async def test_model_without_tablename_attribute(self, mock_plugin):
        """Test handling model class without __tablename__."""

        # Create a class that technically inherits from Base but has issues
        class NoTableNameModel(Base):
            __abstract__ = True  # Abstract models don't need tablename
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        # Abstract models should be handled gracefully
        # This tests robustness of the system
        with (
            patch("src.plugins.models._table_exists") as mock_exists,
            patch("src.plugins.models._create_table") as mock_create,
        ):
            # Should not crash, but behavior depends on implementation
            try:
                await register_plugin_models(mock_plugin, [NoTableNameModel])
            except AttributeError:
                # Expected if __tablename__ is accessed on abstract model
                pass

    @pytest.mark.asyncio
    async def test_concurrent_table_creation(self, mock_plugin):
        """Test behavior when multiple registrations happen concurrently."""
        import asyncio

        call_count = {"exists": 0, "create": 0}

        async def mock_table_exists(name):
            call_count["exists"] += 1
            await asyncio.sleep(0.01)  # Simulate database latency
            return False

        async def mock_create_table(model):
            call_count["create"] += 1
            await asyncio.sleep(0.01)

        with (
            patch("src.plugins.models._table_exists", side_effect=mock_table_exists),
            patch("src.plugins.models._create_table", side_effect=mock_create_table),
        ):
            # Run multiple registrations concurrently
            tasks = [
                register_plugin_models(mock_plugin, [TestPluginModel]),
                register_plugin_models(mock_plugin, [TestPluginModel]),
                register_plugin_models(mock_plugin, [TestPluginModel]),
            ]
            await asyncio.gather(*tasks)

            # All should have attempted to check/create
            assert call_count["exists"] == 3
            assert call_count["create"] == 3
