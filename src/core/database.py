import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import text
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
    
    # Initialize vector database support
    try:
        from ..core.vector_db import get_vector_db
        vector_db = get_vector_db()
        await vector_db.initialize_vector_support()
        logger.info("Vector database support initialized")
    except Exception as e:
        logger.warning(f"Vector database initialization failed (continuing without vector search): {e}")


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
    logger.info("Performing database health check")
    try:
        if not _session_factory:
            logger.warning("No session factory available, attempting to initialize database")
            await init_database()
            if not _session_factory:
                logger.error("Failed to initialize database session factory")
                return False
            logger.info("Database initialized during health check")
        
        logger.debug("Opening database session for health check")
        async with get_db_session() as session:
            # Simple query to test connection
            logger.debug("Executing test query")
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            logger.debug(f"Test query result: {value}")
            is_healthy = value == 1
            
            if is_healthy:
                logger.info("Database health check successful")
            else:
                logger.warning(f"Database health check query returned unexpected value: {value}")
                
            return is_healthy
    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        # Log more specific error types for better diagnostics
        if "connection" in str(e).lower():
            logger.error("Connection error detected - database may be unreachable")
        elif "timeout" in str(e).lower():
            logger.error("Timeout error detected - database may be overloaded")
        elif "authentication" in str(e).lower() or "permission" in str(e).lower():
            logger.error("Authentication error detected - check credentials")
        return False


async def get_user_count() -> int:
    """Get total number of users"""
    try:
        async with get_db_session() as session:
            from ..models.user import User
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        return 0


async def get_chat_count() -> int:
    """Get total number of chats"""
    try:
        async with get_db_session() as session:
            from ..models.chat import Chat
            result = await session.execute(text("SELECT COUNT(*) FROM chats"))
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"Error getting chat count: {e}")
        return 0


async def get_image_count() -> int:
    """Get total number of processed images"""
    try:
        async with get_db_session() as session:
            from ..models.image import Image
            result = await session.execute(text("SELECT COUNT(*) FROM images"))
            return result.scalar() or 0
    except Exception as e:
        logger.error(f"Error getting image count: {e}")
        return 0


async def get_embedding_stats() -> dict:
    """Get statistics about embeddings in the database"""
    try:
        async with get_db_session() as session:
            from sqlalchemy import func, select
            from ..models.image import Image
            
            # Total completed images
            total_result = await session.execute(
                select(func.count(Image.id)).where(Image.processing_status == "completed")
            )
            total_images = total_result.scalar() or 0
            
            # Images with embeddings
            with_embeddings_result = await session.execute(
                select(func.count(Image.id)).where(
                    Image.processing_status == "completed",
                    Image.embedding.isnot(None)
                )
            )
            with_embeddings = with_embeddings_result.scalar() or 0
            
            # Images without embeddings
            without_embeddings = total_images - with_embeddings
            
            # Coverage percentage
            coverage = (with_embeddings / total_images * 100) if total_images > 0 else 0
            
            return {
                "total_images": total_images,
                "with_embeddings": with_embeddings,
                "without_embeddings": without_embeddings,
                "coverage_percentage": coverage
            }
            
    except Exception as e:
        logger.error(f"Error getting embedding stats: {e}")
        return {
            "total_images": 0,
            "with_embeddings": 0,
            "without_embeddings": 0,
            "coverage_percentage": 0
        }


async def get_images_without_embeddings_count(user_id: Optional[int] = None) -> int:
    """Get count of images without embeddings that have accessible files"""
    try:
        async with get_db_session() as session:
            from sqlalchemy import select
            from ..models.image import Image
            from ..models.chat import Chat
            
            query = select(func.count(Image.id)).where(
                Image.embedding.is_(None),
                Image.processing_status == "completed"
            )
            
            if user_id:
                query = query.join(Image.chat).where(Chat.user_id == user_id)
            
            result = await session.execute(query)
            return result.scalar() or 0
            
    except Exception as e:
        logger.error(f"Error getting images without embeddings count: {e}")
        return 0