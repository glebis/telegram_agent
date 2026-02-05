"""
Database model support for plugins.

Plugins can define their own SQLAlchemy models. This module handles
registering those models with the database and creating tables.
"""

import logging
from typing import List, Type

from sqlalchemy import text

from ..core.database import get_db_session, get_engine
from ..models.base import Base

logger = logging.getLogger(__name__)


async def register_plugin_models(plugin, models: List[Type]) -> None:
    """
    Register plugin database models and create tables if needed.

    Args:
        plugin: The plugin instance
        models: List of SQLAlchemy model classes
    """
    if not models:
        return

    plugin_name = plugin.metadata.name

    # Ensure all models inherit from our Base
    for model in models:
        if not issubclass(model, Base):
            logger.warning(
                f"Plugin {plugin_name} model {model.__name__} "
                "does not inherit from Base, skipping"
            )
            continue

        # Check if table exists
        table_name = model.__tablename__
        table_exists = await _table_exists(table_name)

        if not table_exists:
            logger.info(f"Creating table {table_name} for plugin {plugin_name}")
            await _create_table(model)
        else:
            logger.debug(f"Table {table_name} already exists")


async def _table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    async with get_db_session() as session:
        try:
            # SQLite-specific check
            result = await session.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name=:name"
                ),
                {"name": table_name},
            )
            return result.scalar() is not None
        except Exception as e:
            logger.error(f"Error checking table existence: {e}")
            return False


async def _create_table(model: Type) -> None:
    """Create a table for a model."""
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: model.__table__.create(sync_conn))
        logger.info(f"Created table: {model.__tablename__}")
    except Exception as e:
        logger.error(f"Error creating table {model.__tablename__}: {e}")
        raise


async def drop_plugin_tables(plugin) -> None:
    """
    Drop all tables for a plugin.

    Use with caution - this deletes data!

    Args:
        plugin: The plugin instance
    """
    models = plugin.get_database_models()
    if not models:
        return

    engine = get_engine()
    for model in models:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(
                    lambda sync_conn: model.__table__.drop(sync_conn, checkfirst=True)
                )
            logger.info(f"Dropped table: {model.__tablename__}")
        except Exception as e:
            logger.error(f"Error dropping table {model.__tablename__}: {e}")


class PluginModelMixin:
    """
    Mixin for plugin models that adds common fields.

    Usage:
        class MyPluginModel(Base, PluginModelMixin):
            __tablename__ = "my_plugin_data"
            # ... your columns
    """

    pass  # Can add common columns like created_at, updated_at if needed
