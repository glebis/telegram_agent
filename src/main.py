import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .bot.bot import initialize_bot, shutdown_bot, get_bot
from .core.database import init_database, close_database

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Telegram Agent starting up...")
    
    # Initialize database
    try:
        await init_database()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    
    # Initialize bot
    try:
        await initialize_bot()
        logger.info("✅ Telegram bot initialized")
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        # Continue without bot for webhook management API
    
    yield
    
    # Cleanup
    logger.info("🛑 Telegram Agent shutting down...")
    await shutdown_bot()
    await close_database()


# Create FastAPI application
app = FastAPI(
    title="Telegram Agent",
    description="Telegram bot with image processing, vision AI, and MCP integration",
    version="0.3.0",
    lifespan=lifespan
)

# Add CORS middleware
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint"""
    return {
        "message": "Telegram Agent API",
        "version": "0.3.0",
        "status": "running"
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint"""
    try:
        from .core.database import health_check, get_user_count, get_chat_count, get_image_count, get_embedding_stats
        
        # Check database health
        db_healthy = await health_check()
        
        # If database is healthy, get stats
        stats = {}
        embedding_stats = {}
        if db_healthy:
            try:
                stats = {
                    "users": await get_user_count(),
                    "chats": await get_chat_count(), 
                    "images": await get_image_count()
                }
                embedding_stats = await get_embedding_stats()
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                stats = {"error": "Failed to get stats"}
                embedding_stats = {"error": "Failed to get embedding stats"}
        
        return {
            "status": "healthy" if db_healthy else "degraded",
            "service": "telegram-agent",
            "database": "connected" if db_healthy else "disconnected",
            "stats": stats,
            "embedding_stats": embedding_stats
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "service": "telegram-agent",
            "database": "unknown",
            "error": str(e),
            "stats": {}
        }


@app.post("/webhook")
async def webhook_endpoint(request: Request) -> Dict[str, str]:
    """Telegram webhook endpoint"""
    try:
        # Verify webhook secret if configured
        webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if webhook_secret:
            # Check X-Telegram-Bot-Api-Secret-Token header
            received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if received_secret != webhook_secret:
                logger.warning("Invalid webhook secret token")
                raise HTTPException(status_code=401, detail="Unauthorized")
        
        # Get the update data
        update_data = await request.json()
        update_id = update_data.get('update_id', 'unknown')
        
        logger.info(f"Received webhook update: {update_id}")
        
        # Process the update with the bot
        bot = get_bot()
        success = await bot.process_update(update_data)
        
        if success:
            return {"status": "ok"}
        else:
            logger.error(f"Failed to process update {update_id}")
            raise HTTPException(status_code=500, detail="Update processing failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Include webhook management API
try:
    from .api.webhook import router as webhook_router
    
    # We'll need to pass bot_token as dependency later
    # For now, just include the router without the dependency
    app.include_router(webhook_router)
    logger.info("✅ Webhook management API loaded")
except ImportError as e:
    logger.warning(f"⚠️  Webhook management API not available: {e}")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )