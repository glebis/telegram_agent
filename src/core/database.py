import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..models.base import Base

logger = logging.getLogger(__name__)

# Global variables for database connection
_engine = None
_session_factory = None


def get_database_url() -> str:
    """Get database URL from environment or use default"""
    import os
    return os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/telegram_agent.db")


async def init_database() -> None:
    """Initialize database connection and create tables"""
    global _engine, _session_factory
    
    database_url = get_database_url()
    logger.info(f"Initializing database: {database_url}")
    
    # Create async engine
    _engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL debugging
        poolclass=NullPool if "sqlite" in database_url else None,
        pool_pre_ping=True,
    )
    
    # Create session factory
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # Create all tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")


async def close_database() -> None:
    """Close database connection"""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("Database connection closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session context manager"""
    global _session_factory
    
    if not _session_factory:
        await init_database()
    
    async with _session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def get_db_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session"""
    async with get_db_session() as session:
        yield session


# Utility functions for common database operations
async def health_check() -> bool:
    """Check if database is accessible"""
    try:
        async with get_db_session() as session:
            # Simple query to test connection
            result = await session.execute("SELECT 1")
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def get_user_count() -> int:
    """Get total number of users"""
    try:
        async with get_db_session() as session:
            from ..models.user import User
            result = await session.execute("SELECT COUNT(*) FROM users")
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        return 0


async def get_chat_count() -> int:
    """Get total number of chats"""
    try:
        async with get_db_session() as session:
            from ..models.chat import Chat
            result = await session.execute("SELECT COUNT(*) FROM chats")
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"Error getting chat count: {e}")
        return 0


async def get_image_count() -> int:
    """Get total number of processed images"""
    try:
        async with get_db_session() as session:
            from ..models.image import Image
            result = await session.execute("SELECT COUNT(*) FROM images")
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"Error getting image count: {e}")
        return 0