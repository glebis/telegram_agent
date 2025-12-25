import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# Explicitly load .env files at startup
# Load order (later files override earlier):
# 1. ~/.env (global user API keys)
# 2. project .env (project defaults)
# 3. project .env.local (local overrides)
project_root = Path(__file__).parent.parent
home_env = Path.home() / ".env"
env_file = project_root / ".env"
env_local = project_root / ".env.local"

# Load ~/.env first (base layer for global API keys like GROQ, etc.)
if home_env.exists():
    load_dotenv(home_env, override=False)
    print(f"📁 Loaded global environment from {home_env}")

# Load project .env (project defaults)
if env_file.exists():
    load_dotenv(env_file, override=True)
    print(f"📁 Loaded environment from {env_file}")

# Load .env.local last (highest priority overrides)
if env_local.exists():
    load_dotenv(env_local, override=True)
    print(f"📁 Loaded environment from {env_local}")

from .bot.bot import initialize_bot, shutdown_bot, get_bot
from .core.database import init_database, close_database
from .utils.logging import setup_logging
from .utils.task_tracker import cancel_all_tasks, get_active_task_count

# Set up comprehensive logging
log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(log_level=log_level, log_to_file=True)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Telegram Agent starting up...")

    # Initialize database
    try:
        logger.info("📣 LIFESPAN: Starting database initialization")
        await init_database()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

    # Initialize Telegram bot
    bot_initialized = False
    try:
        logger.info("📣 LIFESPAN: Starting bot initialization")
        await initialize_bot()
        logger.info("✅ Telegram bot initialized")
        bot_initialized = True
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        logger.info(
            "📣 LIFESPAN: Continuing with webhook setup despite bot initialization failure"
        )

    # Set up webhook based on environment
    try:
        logger.info("📣 LIFESPAN: Starting webhook setup")
        environment = os.getenv("ENVIRONMENT", "development").lower()
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")

        # Log environment detection prominently
        logger.info(f"🔍 ENVIRONMENT DETECTION: Current environment is '{environment}'")
        logger.info(
            f"🔍 ENVIRONMENT VARIABLES: ENVIRONMENT={environment}, WEBHOOK_SECRET={'***' if webhook_secret else 'None'}"
        )

        if environment == "production":
            logger.info(
                "📣 LIFESPAN: Production environment detected, importing setup_production_webhook"
            )
            from .utils.ngrok_utils import setup_production_webhook
            from .utils.ip_utils import get_webhook_base_url

            # Get base URL (either from env var or auto-detected)
            base_url, is_auto_detected = get_webhook_base_url()

            if is_auto_detected:
                logger.info(
                    f"🌐 LIFESPAN: Auto-detected external IP for webhook base URL: {base_url}"
                )
            else:
                logger.info(f"🌐 LIFESPAN: Using provided webhook base URL: {base_url}")

            if base_url:
                success, message, webhook_url = await setup_production_webhook(
                    bot_token=bot_token,
                    base_url=base_url,
                    webhook_path="/webhook",
                    secret_token=webhook_secret,
                )

                if success:
                    # Log the full webhook URL prominently
                    logger.info("✅ Production webhook set up successfully")
                    print("\n" + "=" * 80)
                    print("🚀 PRODUCTION WEBHOOK CONFIGURED SUCCESSFULLY")
                    print(f"📡 WEBHOOK URL: {webhook_url}")
                    print(
                        f"🔒 SECRET TOKEN: {'Configured' if webhook_secret else 'Not configured'}"
                    )
                    print(
                        f"🔍 IP DETECTION: {'Auto-detected' if is_auto_detected else 'Manually configured'}"
                    )
                    print("=" * 80 + "\n")
                else:
                    logger.error(f"❌ Failed to set up production webhook: {message}")
            else:
                logger.warning(
                    "⚠️ Webhook base URL not available, skipping webhook setup"
                )
        else:
            # For development, webhook will be managed separately via the API
            logger.info(
                f"Development environment detected (ENVIRONMENT={environment}), webhook will be managed via API"
            )
    except Exception as e:
        logger.error(f"❌ Webhook setup failed: {e}")
        # Continue without webhook setup

    yield

    # Cleanup
    logger.info("🛑 Telegram Agent shutting down...")

    # Cancel all tracked background tasks first
    active_count = get_active_task_count()
    if active_count > 0:
        logger.info(f"Cancelling {active_count} active background tasks...")
        await cancel_all_tasks(timeout=5.0)

    if bot_initialized:
        await shutdown_bot()
    await close_database()
    logger.info("✅ Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Telegram Agent",
    description="Telegram bot with image processing, vision AI, and MCP integration",
    version="0.3.0",
    lifespan=lifespan,
)

# Add CORS middleware
cors_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:8000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint for health checks and API info"""
    return {"message": "Telegram Agent API", "version": "0.3.0", "status": "running"}


async def check_telegram_webhook() -> Dict[str, Any]:
    """Check Telegram webhook status and bot responsiveness."""
    import httpx

    result = {
        "webhook_url": None,
        "webhook_configured": False,
        "bot_responsive": False,
        "bot_username": None,
        "pending_updates": 0,
        "last_error": None,
        "ngrok_active": False,
        "ngrok_url": None,
    }

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        result["error"] = "TELEGRAM_BOT_TOKEN not configured"
        return result

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Check webhook info
            webhook_resp = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
            )
            if webhook_resp.status_code == 200:
                webhook_data = webhook_resp.json().get("result", {})
                result["webhook_url"] = webhook_data.get("url") or None
                result["webhook_configured"] = bool(result["webhook_url"])
                result["pending_updates"] = webhook_data.get("pending_update_count", 0)
                result["last_error"] = webhook_data.get("last_error_message")

            # Check bot responsiveness with getMe
            me_resp = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getMe"
            )
            if me_resp.status_code == 200:
                me_data = me_resp.json().get("result", {})
                result["bot_responsive"] = True
                result["bot_username"] = me_data.get("username")
    except Exception as e:
        result["error"] = f"Telegram API error: {str(e)}"

    # Check ngrok status
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            ngrok_resp = await client.get("http://localhost:4040/api/tunnels")
            if ngrok_resp.status_code == 200:
                tunnels = ngrok_resp.json().get("tunnels", [])
                if tunnels:
                    result["ngrok_active"] = True
                    result["ngrok_url"] = tunnels[0].get("public_url")
    except Exception:
        pass  # ngrok not running is not an error

    return result


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint"""
    logger.info("Health check started")
    error_details = {}
    db_connection_info = {}

    try:
        # Get database connection info
        try:
            logger.debug("Getting database connection info")
            from .core.database import get_database_url

            db_url = get_database_url()
            # Mask password in connection string if present
            masked_url = db_url
            if "://" in db_url and "@" in db_url:
                parts = db_url.split("@")
                auth_part = parts[0].split("://")[1]
                if ":" in auth_part:
                    user = auth_part.split(":")[0]
                    masked_url = f"{db_url.split('://')[0]}://{user}:****@{parts[1]}"
            db_connection_info = {"connection_string": masked_url}
            logger.debug(f"Database connection info retrieved: {masked_url}")
        except Exception as conn_err:
            db_connection_info = {
                "error": f"Failed to get database URL: {str(conn_err)}"
            }
            logger.error(f"Database URL error: {conn_err}", exc_info=True)

        # Import database functions
        try:
            logger.debug("Importing database health check functions")
            from .core.database import (
                health_check,
                get_user_count,
                get_chat_count,
                get_image_count,
                get_embedding_stats,
            )

            logger.debug("Database functions imported successfully")
        except ImportError as imp_err:
            error_details["import_error"] = str(imp_err)
            logger.error(f"Import error in health check: {imp_err}", exc_info=True)
            logger.warning("Health check failed at import stage")
            return {
                "status": "error",
                "service": "telegram-agent",
                "database": "unknown",
                "error": f"Failed to import database modules: {str(imp_err)}",
                "error_details": error_details,
                "db_connection_info": db_connection_info,
            }

        # Check database health
        try:
            logger.info("Checking database connection health")
            db_healthy = await health_check()
            if db_healthy:
                logger.info("✅ Database health check passed")
            else:
                logger.warning(
                    "⚠️ Database health check failed but did not raise an exception"
                )
        except Exception as db_err:
            error_details["db_health_check_error"] = str(db_err)
            logger.error(f"Database health check error: {db_err}", exc_info=True)
            logger.warning("Health check failed at database connection stage")
            return {
                "status": "error",
                "service": "telegram-agent",
                "database": "disconnected",
                "error": f"Database health check failed: {str(db_err)}",
                "error_details": error_details,
                "db_connection_info": db_connection_info,
            }

        # If database is healthy, get stats
        stats = {}
        embedding_stats = {}
        if db_healthy:
            try:
                logger.info("Database is healthy, retrieving statistics")
                logger.debug("Getting user count")
                user_count = await get_user_count()
                logger.debug("Getting chat count")
                chat_count = await get_chat_count()
                logger.debug("Getting image count")
                image_count = await get_image_count()

                stats = {
                    "users": user_count,
                    "chats": chat_count,
                    "images": image_count,
                }
                logger.debug(f"Retrieved stats: {stats}")

                logger.debug("Getting embedding stats")
                embedding_stats = await get_embedding_stats()
                logger.debug(f"Retrieved embedding stats: {embedding_stats}")
            except Exception as stats_err:
                logger.error(f"Error getting stats: {stats_err}", exc_info=True)
                error_details["stats_error"] = str(stats_err)
                stats = {"error": f"Failed to get stats: {str(stats_err)}"}
                embedding_stats = {
                    "error": f"Failed to get embedding stats: {str(stats_err)}"
                }

        # Check Telegram webhook and bot status
        telegram_status = await check_telegram_webhook()

        # Determine overall health status
        # - healthy: db connected AND webhook configured AND bot responsive
        # - degraded: db connected but webhook/bot issues
        # - error: db disconnected
        if not db_healthy:
            status = "error"
        elif not telegram_status.get("webhook_configured"):
            status = "degraded"
            error_details["webhook"] = "Webhook URL not configured"
        elif not telegram_status.get("bot_responsive"):
            status = "degraded"
            error_details["bot"] = "Bot not responding to Telegram API"
        else:
            status = "healthy"

        logger.info(f"Health check completed with status: {status}")
        return {
            "status": status,
            "service": "telegram-agent",
            "database": "connected" if db_healthy else "disconnected",
            "telegram": telegram_status,
            "stats": stats,
            "embedding_stats": embedding_stats,
            "db_connection_info": db_connection_info,
            "error_details": error_details if error_details else None,
        }
    except Exception as e:
        logger.error(f"Health check failed with unexpected error: {e}", exc_info=True)
        error_details["general_error"] = str(e)
        return {
            "status": "error",
            "service": "telegram-agent",
            "database": "unknown",
            "error": str(e),
            "error_details": error_details,
            "db_connection_info": db_connection_info,
            "stats": {},
        }


# Deduplication: Track processed update_ids to prevent duplicate processing
# when Telegram retries due to timeout (Claude Code can take >60s)
import asyncio
from collections import OrderedDict

_processed_updates: OrderedDict[int, float] = OrderedDict()
_processing_updates: set[int] = set()  # Currently being processed
_updates_lock = asyncio.Lock()
MAX_TRACKED_UPDATES = 1000  # Keep last N update_ids
UPDATE_EXPIRY_SECONDS = 600  # 10 minutes


async def _cleanup_old_updates():
    """Remove expired update_ids from tracking."""
    import time
    current_time = time.time()
    expired = [uid for uid, ts in _processed_updates.items()
               if current_time - ts > UPDATE_EXPIRY_SECONDS]
    for uid in expired:
        _processed_updates.pop(uid, None)


@app.post("/webhook")
async def webhook_endpoint(request: Request) -> Dict[str, str]:
    """Telegram webhook endpoint"""
    import time

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
        update_id = update_data.get("update_id")

        if update_id is None:
            logger.warning("Webhook update missing update_id")
            raise HTTPException(status_code=400, detail="Missing update_id")

        logger.info(f"Received webhook update: {update_id}")

        # Deduplication check
        async with _updates_lock:
            # Clean up old entries periodically
            if len(_processed_updates) > MAX_TRACKED_UPDATES:
                await _cleanup_old_updates()
                # Trim to max size
                while len(_processed_updates) > MAX_TRACKED_UPDATES:
                    _processed_updates.popitem(last=False)

            # Check if already processed or currently processing
            if update_id in _processed_updates:
                logger.info(f"Skipping duplicate update {update_id} (already processed)")
                return {"status": "ok", "note": "duplicate"}

            if update_id in _processing_updates:
                logger.info(f"Skipping duplicate update {update_id} (currently processing)")
                return {"status": "ok", "note": "in_progress"}

            # Mark as processing
            _processing_updates.add(update_id)

        # Process the update in background task to respond quickly to Telegram
        # This prevents Telegram from timing out and retrying the same update
        async def process_in_background():
            try:
                bot = get_bot()
                success = await bot.process_update(update_data)
                if not success:
                    logger.error(f"Failed to process update {update_id}")
            except Exception as e:
                logger.error(f"Error processing update {update_id}: {e}")
            finally:
                # Mark as processed (regardless of success/failure)
                async with _updates_lock:
                    _processing_updates.discard(update_id)
                    _processed_updates[update_id] = time.time()

        # Start background task and return immediately
        asyncio.create_task(process_in_background())
        return {"status": "ok"}

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

# Include messaging API
try:
    from .api.messaging import router as messaging_router

    app.include_router(messaging_router)
    logger.info("✅ Messaging API loaded")
except ImportError as e:
    logger.warning(f"⚠️  Messaging API not available: {e}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("src.main:app", host=host, port=port, reload=True, log_level="info")
