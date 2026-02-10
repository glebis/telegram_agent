import asyncio
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# Explicitly load .env files at startup
# Load order (later files override earlier):
# 1. ~/.env (global user API keys)
# 2. project .env (project defaults)
# 3. ENV_FILE override or .env.local (highest priority)
project_root = Path(__file__).parent.parent
home_env = Path.home() / ".env"
env_file = project_root / ".env"
env_override = (
    Path(os.environ["ENV_FILE"])
    if "ENV_FILE" in os.environ
    else project_root / ".env.local"
)

# Load ~/.env first (base layer for global API keys like GROQ, etc.)
if home_env.exists():
    load_dotenv(home_env, override=False)
    print(f"📁 Loaded global environment from {home_env}")

# Load project .env (project defaults)
if env_file.exists():
    load_dotenv(env_file, override=True)
    print(f"📁 Loaded environment from {env_file}")

# Load override env file last (highest priority)
if env_override.exists():
    load_dotenv(env_override, override=True)
    print(f"📁 Loaded environment from {env_override}")

from .api.webhook import get_admin_api_key, verify_admin_key  # noqa: E402
from .bot.bot import get_bot, initialize_bot, shutdown_bot  # noqa: E402
from .core.config import get_settings  # noqa: E402
from .core.config_validator import log_config_summary, validate_config  # noqa: E402
from .core.database import close_database, init_database  # noqa: E402
from .core.services import setup_services  # noqa: E402
from .middleware.body_size import BodySizeLimitMiddleware  # noqa: E402
from .middleware.error_handler import ErrorHandlerMiddleware  # noqa: E402
from .middleware.rate_limit import RateLimitMiddleware  # noqa: E402
from .middleware.user_rate_limit import UserRateLimitMiddleware  # noqa: E402
from .plugins import get_plugin_manager  # noqa: E402
from .utils.cleanup import cleanup_all_temp_files, run_periodic_cleanup  # noqa: E402
from .utils.logging import setup_logging  # noqa: E402
from .utils.retry import async_retry  # noqa: E402
from .utils.task_tracker import (  # noqa: E402
    cancel_all_tasks,
    create_tracked_task,
    get_active_task_count,
    get_active_tasks,
)
from .version import __version__  # noqa: E402

# Track if bot lifespan has fully completed
_bot_fully_initialized = False


def is_bot_initialized() -> bool:
    """Check if bot lifespan startup completed."""
    return _bot_fully_initialized


# Set up comprehensive logging
log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(log_level=log_level, log_to_file=True)
logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

if ENVIRONMENT == "production" and not WEBHOOK_SECRET:
    raise RuntimeError(
        "TELEGRAM_WEBHOOK_SECRET is required in production for webhook authentication"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Telegram Agent starting up...")

    # Validate configuration before anything else
    settings = get_settings()
    config_errors = validate_config(settings)
    if config_errors:
        for err in config_errors:
            logger.error(f"Config validation error: {err}")
        logger.critical(
            "Aborting startup due to %d configuration error(s)", len(config_errors)
        )
        import sys

        sys.exit(1)
    log_config_summary(settings)

    # Initialize database
    try:
        logger.info("📣 LIFESPAN: Starting database initialization")
        await init_database()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

    # Register all services in the DI container
    try:
        logger.info("📣 LIFESPAN: Setting up service container")
        setup_services()
        logger.info("✅ Service container initialized")
    except Exception as e:
        logger.error(f"❌ Service container setup failed: {e}")
        raise

    # Load plugins
    plugin_manager = get_plugin_manager()
    try:
        logger.info("📣 LIFESPAN: Loading plugins")
        from .core.container import get_container

        plugin_results = await plugin_manager.load_plugins(get_container())
        loaded_count = sum(plugin_results.values())
        total_count = len(plugin_results)
        if total_count > 0:
            logger.info(f"✅ Plugins loaded: {loaded_count}/{total_count}")
        else:
            logger.info("📦 No plugins found")
    except Exception as e:
        logger.warning(f"⚠️ Plugin loading failed: {e}")

    # Pre-load collect sessions from database
    # Must be done before message processing to avoid SQLite deadlocks
    try:
        from .services.collect_service import get_collect_service

        collect_service = get_collect_service()
        await collect_service.initialize()
        logger.info("✅ Collect service initialized")
    except Exception as e:
        logger.warning(f"⚠️ Collect service initialization failed: {e}")

    # Hydrate callback data from database so inline buttons survive restarts
    try:
        from .bot.callback_data_manager import get_callback_data_manager

        callback_manager = get_callback_data_manager()
        await callback_manager.load_from_db()
        logger.info("✅ Callback data loaded from database")

        # Start periodic flush of pending callback data writes (every 60s)
        async def _periodic_callback_flush():
            import asyncio

            while True:
                await asyncio.sleep(60)
                try:
                    mgr = get_callback_data_manager()
                    await mgr.flush_pending_writes()
                except Exception as exc:
                    logger.error(f"Periodic callback data flush failed: {exc}")

        create_tracked_task(_periodic_callback_flush(), name="callback_data_flush")
    except Exception as e:
        logger.warning(f"⚠️ Callback data hydration failed: {e}")

    # Initialize Telegram bot with retry logic
    bot_initialized = False

    @async_retry(
        max_attempts=3, base_delay=2.0, exponential_base=2.0, exceptions=(Exception,)
    )
    async def _initialize_bot_with_retry():
        logger.info("📣 LIFESPAN: Starting bot initialization")
        await initialize_bot()
        logger.info("✅ Telegram bot initialized")

        # Activate plugins (register handlers)
        try:
            bot = get_bot()
            if bot and bot.application:
                await plugin_manager.activate_plugins(bot.application)
                logger.info("✅ Plugins activated")
        except Exception as e:
            logger.warning(f"⚠️ Plugin activation failed: {e}")

    try:
        await _initialize_bot_with_retry()
        bot_initialized = True
    except Exception as e:
        logger.error(
            f"❌ All bot initialization attempts failed - running in degraded mode: {e}"
        )

    # Set up webhook based on environment
    tunnel_provider = None
    try:
        logger.info("📣 LIFESPAN: Starting webhook setup")
        environment = os.getenv("ENVIRONMENT", "development").lower()
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        port = int(os.getenv("TUNNEL_PORT", os.getenv("NGROK_PORT", "8000")))

        # Log environment detection prominently
        logger.info(f"🔍 ENVIRONMENT DETECTION: Current environment is '{environment}'")
        logger.info(
            f"🔍 ENVIRONMENT VARIABLES: ENVIRONMENT={environment}, WEBHOOK_SECRET={'***' if webhook_secret else 'None'}"
        )

        from .tunnel import get_tunnel_provider
        from .utils.ngrok_utils import WebhookManager

        tunnel_provider = get_tunnel_provider(port=port)

        if tunnel_provider:
            logger.info(f"📣 LIFESPAN: Using tunnel provider '{tunnel_provider.name}'")

            tunnel_url = await tunnel_provider.start()
            webhook_url = f"{tunnel_url}/webhook"

            webhook_manager = WebhookManager(bot_token)

            # Retry webhook registration — quick tunnels need DNS propagation
            max_attempts = 6 if not tunnel_provider.provides_stable_url else 1
            success = False
            message = ""
            for attempt in range(1, max_attempts + 1):
                success, message = await webhook_manager.set_webhook(
                    webhook_url, webhook_secret
                )
                if success:
                    break
                if attempt < max_attempts:
                    logger.warning(
                        f"Webhook attempt {attempt}/{max_attempts} failed "
                        f"(DNS propagating?): {message}"
                    )
                    await asyncio.sleep(5)

            if success:
                logger.info("✅ Webhook set up successfully via tunnel provider")
                print("\n" + "=" * 80)
                print(f"🚀 WEBHOOK CONFIGURED ({tunnel_provider.name.upper()})")
                print(f"📡 WEBHOOK URL: {webhook_url}")
                print(
                    f"🔒 SECRET TOKEN: {'Configured' if webhook_secret else 'Not configured'}"
                )
                print(
                    f"🔗 STABLE URL: {'Yes' if tunnel_provider.provides_stable_url else 'No'}"
                )
                print("=" * 80 + "\n")
            else:
                logger.error(f"❌ Failed to set webhook: {message}")

            # Only start periodic recovery for unstable-URL providers
            if not tunnel_provider.provides_stable_url:
                from .utils.ngrok_utils import run_periodic_webhook_check

                create_tracked_task(
                    run_periodic_webhook_check(
                        bot_token=bot_token,
                        port=port,
                        webhook_path="/webhook",
                        secret_token=webhook_secret,
                        interval_minutes=5.0,
                    ),
                    name="webhook_health_check",
                )
                logger.info("✅ Started periodic webhook health check (every 5 min)")
            else:
                logger.info(
                    f"ℹ️ Skipping periodic webhook recovery — "
                    f"{tunnel_provider.name} provides stable URLs"
                )
        else:
            # No tunnel provider — auto-detect URL (Railway, external IP, env var)
            from .utils.ip_utils import get_webhook_base_url

            base_url, is_auto_detected = get_webhook_base_url()
            if is_auto_detected:
                logger.info(f"🌐 Auto-detected webhook base URL: {base_url}")
            if base_url:
                from .utils.ngrok_utils import setup_production_webhook

                success, message, webhook_url = await setup_production_webhook(
                    bot_token=bot_token,
                    base_url=base_url,
                    webhook_path="/webhook",
                    secret_token=webhook_secret,
                )
                if success:
                    logger.info(f"✅ Webhook set to {webhook_url}")
                else:
                    logger.error(f"❌ Failed to set webhook: {message}")
            else:
                logger.warning(
                    "⚠️ No tunnel provider and no WEBHOOK_BASE_URL — skipping webhook setup"
                )
    except Exception as e:
        logger.error(f"❌ Webhook setup failed: {e}")
        # Continue without webhook setup

    # Start periodic cleanup task (every hour, delete files older than 1 hour)
    create_tracked_task(
        run_periodic_cleanup(interval_hours=1.0, max_age_hours=1.0),
        name="periodic_cleanup",
    )
    logger.info("✅ Started periodic cleanup task")

    # Start periodic zombie Claude process reaper (every hour)
    from .services.claude_code_service import run_periodic_process_reaper

    create_tracked_task(
        run_periodic_process_reaper(interval_hours=1.0), name="claude_process_reaper"
    )
    logger.info("✅ Started periodic Claude process reaper")

    # Start periodic data retention enforcement (every 24 hours)
    from .services.data_retention_service import run_periodic_retention

    create_tracked_task(
        run_periodic_retention(interval_hours=24.0), name="data_retention"
    )
    logger.info("✅ Started periodic data retention task")

    # Start periodic stale Claude session cleanup (every hour, deactivate after 7 days)
    from .services.session_cleanup_service import run_periodic_session_cleanup

    create_tracked_task(
        run_periodic_session_cleanup(interval_hours=1.0, max_age_days=7),
        name="session_cleanup",
    )
    logger.info("✅ Started periodic stale session cleanup")

    # Start periodic reply context cleanup (every hour)
    async def _run_reply_context_cleanup():
        """Periodically clean up expired reply contexts."""
        import asyncio

        while True:
            try:
                await asyncio.sleep(3600)  # 1 hour
                from .services.reply_context import get_reply_context_service

                service = get_reply_context_service()
                if service:
                    removed = service.cleanup_expired()
                    if removed:
                        logger.info(
                            f"Reply context cleanup: removed {removed} expired entries"
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reply context cleanup error: {e}")

    create_tracked_task(_run_reply_context_cleanup(), name="reply_context_cleanup")
    logger.info("✅ Started periodic reply context cleanup")

    # Mark bot as fully initialized ONLY if bot actually initialized
    global _bot_fully_initialized
    if bot_initialized:
        _bot_fully_initialized = True
        logger.info("✅ Bot fully initialized and ready")
    else:
        logger.warning("⚠️ Bot NOT fully initialized - running in degraded mode")

    yield

    # Cleanup
    _bot_fully_initialized = False
    logger.info("🛑 Telegram Agent shutting down...")

    # Stop tunnel provider
    if tunnel_provider:
        try:
            await tunnel_provider.stop()
            logger.info(f"✅ Tunnel provider ({tunnel_provider.name}) stopped")
        except Exception as e:
            logger.error(f"❌ Tunnel provider stop error: {e}")

    # Shutdown plugins first (reverse order)
    try:
        await plugin_manager.shutdown()
        logger.info("✅ Plugins shutdown complete")
    except Exception as e:
        logger.error(f"❌ Plugin shutdown error: {e}")

    # Flush any pending callback data writes before shutdown
    try:
        from .bot.callback_data_manager import get_callback_data_manager

        callback_manager = get_callback_data_manager()
        await callback_manager.flush_pending_writes()
        logger.info("✅ Callback data flushed to database")
    except Exception as e:
        logger.error(f"❌ Callback data flush on shutdown failed: {e}")

    # Cancel all tracked background tasks
    active_count = get_active_task_count()
    if active_count > 0:
        logger.info(f"Cancelling {active_count} active background tasks...")
        await cancel_all_tasks(timeout=5.0)

    if bot_initialized:
        await shutdown_bot()
    await close_database()
    logger.info("✅ Shutdown complete")


# Create FastAPI application
# Disable docs endpoints in production to prevent API schema disclosure
_is_production = os.getenv("ENVIRONMENT", "").lower() == "production"
app = FastAPI(
    title="Telegram Agent",
    description="Telegram bot with image processing, vision AI, and MCP integration",
    version=__version__,
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# Add CORS middleware
cors_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:8000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Api-Key", "Authorization"],
)

# Add error handling middleware (catches unhandled exceptions)
app.add_middleware(ErrorHandlerMiddleware)


# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    # HSTS only when behind HTTPS
    if (
        request.url.scheme == "https"
        or request.headers.get("X-Forwarded-Proto") == "https"
    ):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# Load hardening settings from config (with env-var fallback for module-level access)
_hardening_rpm = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
_hardening_body = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
_hardening_concurrency = int(os.getenv("WEBHOOK_MAX_CONCURRENT", "20"))

# Add body size limit middleware (applied before rate limiting)
app.add_middleware(
    BodySizeLimitMiddleware,
    max_bytes=_hardening_body,
)

# Add per-IP rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=_hardening_rpm,
)

# Add per-user (Telegram user_id) rate limiting for webhook requests.
# Telegram webhook traffic arrives from shared IPs, so per-IP limiting alone
# is insufficient to throttle individual abusive users.
_user_rpm = int(os.getenv("USER_RATE_LIMIT_RPM", "30"))
_privileged_rpm = int(os.getenv("USER_RATE_LIMIT_PRIVILEGED_RPM", "120"))
_privileged_ids: set[int] = set()
_owner_id = os.getenv("OWNER_USER_ID", "")
if _owner_id.strip().isdigit():
    _privileged_ids.add(int(_owner_id.strip()))
for _part in os.getenv("ADMIN_USER_IDS", "").split(","):
    _part = _part.strip()
    if _part.isdigit():
        _privileged_ids.add(int(_part))

app.add_middleware(
    UserRateLimitMiddleware,
    user_rpm=_user_rpm,
    privileged_rpm=_privileged_rpm,
    privileged_user_ids=_privileged_ids,
)


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint for health checks and API info"""
    return {
        "message": "Telegram Agent API",
        "status": "running",
    }


@app.post("/cleanup")
async def trigger_cleanup(
    max_age_hours: float = 1.0,
    dry_run: bool = False,
    _: bool = Depends(verify_admin_key),
) -> Dict[str, Any]:
    """
    Trigger manual cleanup of temp files.

    Requires admin API key authentication via X-Api-Key header.

    Args:
        max_age_hours: Delete files older than this (default: 1 hour)
        dry_run: If true, don't actually delete files
    """
    logger.info(
        f"Manual cleanup triggered: max_age={max_age_hours}h, dry_run={dry_run}"
    )
    result = cleanup_all_temp_files(max_age_hours=max_age_hours, dry_run=dry_run)
    return result


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
            me_resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            if me_resp.status_code == 200:
                me_data = me_resp.json().get("result", {})
                result["bot_responsive"] = True
                result["bot_username"] = me_data.get("username")
    except Exception as e:
        result["error"] = f"Telegram API error: {str(e)}"

    # Check tunnel provider status
    try:
        from .tunnel import get_tunnel_provider

        provider = get_tunnel_provider()
        if provider:
            status = provider.get_status()
            result["ngrok_active"] = status.get("active", False)
            result["ngrok_url"] = status.get("url")
            result["tunnel_provider"] = status.get("provider")
        else:
            # Fallback: check ngrok API directly for backward compat
            async with httpx.AsyncClient(timeout=5) as client:
                ngrok_resp = await client.get("http://localhost:4040/api/tunnels")
                if ngrok_resp.status_code == 200:
                    tunnels = ngrok_resp.json().get("tunnels", [])
                    if tunnels:
                        result["ngrok_active"] = True
                        result["ngrok_url"] = tunnels[0].get("public_url")
    except Exception:
        pass  # tunnel not running is not an error

    return result


def _verify_admin_key_optional(x_api_key: str) -> bool:
    """Verify admin API key without raising exception (for optional auth)."""
    if not x_api_key:
        return False
    try:
        expected_key = get_admin_api_key()
        return hmac.compare_digest(x_api_key, expected_key)
    except Exception:
        return False


@app.get("/health")
async def health(
    x_api_key: str = Header(
        None, description="Optional API key for detailed health info"
    )
) -> Dict[str, Any]:
    """
    Health check endpoint.

    Without authentication: Returns basic status only (status, uptime, service name)
    With valid X-Api-Key header: Returns full detailed health information
    """
    # Check if authenticated for detailed info
    show_details = _verify_admin_key_optional(x_api_key)

    logger.info(f"Health check started (detailed={show_details})")

    # Always return basic info
    basic_response = {
        "status": "healthy",
        "service": "telegram-agent",
        "bot_initialized": _bot_fully_initialized,
    }

    # If not authenticated, return basic info only
    if not show_details:
        if not _bot_fully_initialized:
            basic_response["status"] = "degraded"
        return basic_response

    # === Detailed health check (requires auth) ===
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
                get_chat_count,
                get_embedding_stats,
                get_image_count,
                get_user_count,
                health_check,
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
        # - healthy: db connected AND webhook configured AND bot responsive AND fully initialized
        # - degraded: db connected but webhook/bot issues
        # - error: db disconnected OR not fully initialized
        if not _bot_fully_initialized:
            status = "error"
            error_details["initialization"] = "Bot lifespan startup not completed"
        elif not db_healthy:
            status = "error"
        elif not telegram_status.get("webhook_configured"):
            status = "degraded"
            error_details["webhook"] = "Webhook URL not configured"
        elif not telegram_status.get("bot_responsive"):
            status = "degraded"
            error_details["bot"] = "Bot not responding to Telegram API"
        else:
            status = "healthy"

        # Get background task stats
        active_tasks = get_active_tasks()
        task_stats = {
            "active_count": len(active_tasks),
            "task_names": [t.get_name() for t in active_tasks if not t.done()],
        }

        logger.info(f"Health check completed with status: {status}")
        return {
            "status": status,
            "service": "telegram-agent",
            "bot_initialized": _bot_fully_initialized,
            "database": "connected" if db_healthy else "disconnected",
            "telegram": telegram_status,
            "background_tasks": task_stats,
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
from collections import OrderedDict  # noqa: E402

_processed_updates: OrderedDict[int, float] = OrderedDict()
_processing_updates: set[int] = set()  # Currently being processed
_updates_lock = asyncio.Lock()


def _get_update_limits():
    """Load update dedup limits from config (lazy, avoids import-time YAML reads)."""
    try:
        from src.core.config import get_nested, load_defaults

        cfg = load_defaults()
        return (
            get_nested(cfg, "limits.max_tracked_updates", 1000),
            get_nested(cfg, "limits.update_expiry_seconds", 600),
        )
    except Exception:
        return 1000, 600


MAX_TRACKED_UPDATES, UPDATE_EXPIRY_SECONDS = _get_update_limits()

# Concurrency guard — configured via WEBHOOK_MAX_CONCURRENT env var (default: 20)
_webhook_semaphore: asyncio.Semaphore = asyncio.Semaphore(_hardening_concurrency)


# Per-user rate limiting for webhook (complements per-IP middleware)
_USER_RATE_LIMIT = 30  # messages per minute per user
_user_rate_buckets: dict[int, tuple[float, float]] = (
    {}
)  # user_id -> (tokens, last_refill)
_USER_RATE_REFILL = _USER_RATE_LIMIT / 60.0


def _check_user_rate_limit(user_id: int) -> bool:
    """Check per-user rate limit. Returns True if allowed."""
    now = time.monotonic()
    tokens, last = _user_rate_buckets.get(user_id, (float(_USER_RATE_LIMIT), now))
    tokens = min(_USER_RATE_LIMIT, tokens + (now - last) * _USER_RATE_REFILL)
    if tokens >= 1.0:
        _user_rate_buckets[user_id] = (tokens - 1.0, now)
        return True
    _user_rate_buckets[user_id] = (tokens, now)
    return False


def _log_auth_failure(request: Request, reason: str) -> None:
    """Log structured auth failure with IP and User-Agent. Never logs secrets."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    logger.warning(
        "Auth failure on %s %s: reason=%s, ip=%s, user_agent=%s",
        request.method,
        request.url.path,
        reason,
        client_ip,
        user_agent,
    )


async def _cleanup_old_updates():
    """Remove expired update_ids from tracking."""
    current_time = time.time()
    expired = [
        uid
        for uid, ts in _processed_updates.items()
        if current_time - ts > UPDATE_EXPIRY_SECONDS
    ]
    for uid in expired:
        _processed_updates.pop(uid, None)


@app.post("/webhook")
async def webhook_endpoint(request: Request) -> Dict[str, str]:
    """Telegram webhook endpoint.

    Body size and rate limiting are enforced by BodySizeLimitMiddleware and
    RateLimitMiddleware respectively. This endpoint handles:
    - Concurrency cap (semaphore)
    - Webhook secret verification
    - Update deduplication
    - Background processing dispatch
    """
    # Concurrency cap (non-blocking check)
    if _webhook_semaphore.locked():
        raise HTTPException(status_code=503, detail="Busy")
    acquired = await _webhook_semaphore.acquire()
    task_started = False
    try:
        try:
            update_data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        # Verify webhook secret if configured
        webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if webhook_secret:
            # Check X-Telegram-Bot-Api-Secret-Token header
            received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            # Use timing-safe comparison to prevent timing attacks
            if not hmac.compare_digest(received_secret, webhook_secret):
                _log_auth_failure(request, "invalid_webhook_secret")
                raise HTTPException(status_code=401, detail="Unauthorized")

        update_id = update_data.get("update_id")

        if update_id is None:
            logger.warning("Webhook update missing update_id")
            raise HTTPException(status_code=400, detail="Missing update_id")

        logger.info(f"Received webhook update: {update_id}")

        # Populate RequestContext for structured logging
        from src.utils.logging import RequestContext

        chat_id = update_data.get("message", {}).get("chat", {}).get(
            "id"
        ) or update_data.get("callback_query", {}).get("message", {}).get(
            "chat", {}
        ).get(
            "id"
        )
        RequestContext.set(
            chat_id=str(chat_id) if chat_id else None,
        )

        # Per-user rate limiting (complements per-IP middleware)
        from_user = update_data.get("message", {}).get("from", {}) or update_data.get(
            "callback_query", {}
        ).get("from", {})
        tg_user_id = from_user.get("id") if from_user else None
        if tg_user_id and not _check_user_rate_limit(tg_user_id):
            logger.warning("Per-user rate limit exceeded for user %d", tg_user_id)
            return {"status": "ok", "note": "rate_limited"}

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
                logger.info(
                    f"Skipping duplicate update {update_id} (already processed)"
                )
                return {"status": "ok", "note": "duplicate"}

            if update_id in _processing_updates:
                logger.info(
                    f"Skipping duplicate update {update_id} (currently processing)"
                )
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
                _webhook_semaphore.release()

        # Start background task and return immediately
        create_tracked_task(process_in_background(), name=f"webhook_{update_id}")
        task_started = True
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        # If background task not started, release here
        if acquired and not task_started:
            try:
                _webhook_semaphore.release()
            except ValueError:
                pass


# Include webhook management API (now with proper authentication)
try:
    from .api.webhook import router as webhook_router

    app.include_router(webhook_router)
    logger.info("✅ Webhook management API loaded (with authentication)")
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
