import logging
import os
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    yield
    logger.info("🛑 Telegram Agent shutting down...")


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
async def health() -> Dict[str, str]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "telegram-agent"
    }


@app.post("/webhook")
async def webhook_endpoint(update: Dict) -> Dict[str, str]:
    """Telegram webhook endpoint (placeholder)"""
    logger.info(f"Received webhook update: {update.get('update_id', 'unknown')}")
    return {"status": "ok"}


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