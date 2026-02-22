"""
Telegram Agent — FastAPI application entry point.

This module creates the FastAPI app, configures middleware, and wires up
all routes. Business logic lives in dedicated modules:
- src.lifecycle — startup/shutdown lifespan management
- src.api.webhook_handler — webhook endpoint + dedup logic
- src.api.health — health check endpoints (lightweight)
- src.api.webhook — webhook management admin API
- src.api.messaging — messaging API

Refactored as part of #152 (break apart god objects).
"""

import asyncio
import hmac
import logging
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware

# ── Environment loading ──
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

if home_env.exists():
    load_dotenv(home_env, override=False)
    print(f"📁 Loaded global environment from {home_env}")

if env_file.exists():
    load_dotenv(env_file, override=True)
    print(f"📁 Loaded environment from {env_file}")

if env_override.exists():
    load_dotenv(env_override, override=True)
    print(f"📁 Loaded environment from {env_override}")

# ── Imports (after env is loaded) ──
from .api.webhook import get_admin_api_key, verify_admin_key  # noqa: E402
from .api.webhook_handler import (  # noqa: E402, F401
    MAX_TRACKED_UPDATES,
    UPDATE_EXPIRY_SECONDS,
    _check_user_rate_limit,
    _cleanup_old_updates,
    _processed_updates,
    _processing_updates,
    _updates_lock,
    handle_webhook,
)

# Re-exports for backward compatibility (tests import these from src.main)
from .bot.bot import get_bot, initialize_bot, shutdown_bot  # noqa: E402, F401
from .core.config import get_settings  # noqa: E402, F401
from .core.config_validator import validate_config  # noqa: E402, F401
from .core.database import close_database, init_database  # noqa: E402, F401
from .core.services import setup_services  # noqa: E402, F401
from .lifecycle import is_bot_initialized, lifespan  # noqa: E402, F401
from .middleware.body_size import BodySizeLimitMiddleware  # noqa: E402
from .middleware.error_handler import ErrorHandlerMiddleware  # noqa: E402
from .middleware.metrics import MetricsMiddleware  # noqa: E402
from .middleware.rate_limit import RateLimitMiddleware  # noqa: E402
from .middleware.user_rate_limit import UserRateLimitMiddleware  # noqa: E402
from .plugins import get_plugin_manager  # noqa: E402, F401
from .utils.cleanup import cleanup_all_temp_files  # noqa: E402
from .utils.logging import setup_logging  # noqa: E402
from .utils.task_tracker import (  # noqa: E402, F401
    create_tracked_task,
    get_active_tasks,
)
from .version import __version__  # noqa: E402

# ── Logging ──
log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(log_level=log_level, log_to_file=True)
logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

if ENVIRONMENT == "production" and not WEBHOOK_SECRET:
    raise RuntimeError(
        "TELEGRAM_WEBHOOK_SECRET is required in production for webhook authentication"
    )

# ── FastAPI application ──
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

# ── Middleware ──
cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:8000"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Api-Key", "Authorization"],
)

app.add_middleware(ErrorHandlerMiddleware)

# Add Prometheus metrics recording middleware
app.add_middleware(MetricsMiddleware)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    if (
        request.url.scheme == "https"
        or request.headers.get("X-Forwarded-Proto") == "https"
    ):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# Hardening settings from config
_hardening_rpm = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
_hardening_body = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
_hardening_concurrency = int(os.getenv("WEBHOOK_MAX_CONCURRENT", "20"))

app.add_middleware(BodySizeLimitMiddleware, max_bytes=_hardening_body)
app.add_middleware(RateLimitMiddleware, requests_per_minute=_hardening_rpm)

# Per-user rate limiting for webhook requests
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

# ── Concurrency guard ──
_webhook_semaphore: asyncio.Semaphore = asyncio.Semaphore(_hardening_concurrency)


# ── Endpoints ──


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint for health checks and API info."""
    return {"message": "Telegram Agent API", "status": "running"}


@app.post("/cleanup")
async def trigger_cleanup(
    max_age_hours: float = 1.0,
    dry_run: bool = False,
    _: bool = Depends(verify_admin_key),
) -> Dict[str, Any]:
    """Trigger manual cleanup of temp files (requires admin API key)."""
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
            webhook_resp = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
            )
            if webhook_resp.status_code == 200:
                webhook_data = webhook_resp.json().get("result", {})
                result["webhook_url"] = webhook_data.get("url") or None
                result["webhook_configured"] = bool(result["webhook_url"])
                result["pending_updates"] = webhook_data.get("pending_update_count", 0)
                result["last_error"] = webhook_data.get("last_error_message")

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
            async with httpx.AsyncClient(timeout=5) as client:
                ngrok_resp = await client.get("http://localhost:4040/api/tunnels")
                if ngrok_resp.status_code == 200:
                    tunnels = ngrok_resp.json().get("tunnels", [])
                    if tunnels:
                        result["ngrok_active"] = True
                        result["ngrok_url"] = tunnels[0].get("public_url")
    except Exception:
        pass

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
    ),
) -> Dict[str, Any]:
    """Health check endpoint.

    Without auth: basic status. With valid X-Api-Key: full details.
    """
    from .lifecycle import _bot_fully_initialized, _bot_init_state

    show_details = _verify_admin_key_optional(x_api_key)
    logger.info(f"Health check started (detailed={show_details})")

    # Map BotInitState to bot_status
    _status_map = {
        "initialized": "ok",
        "failed": "retrying",
        "initializing": "initializing",
        "not_started": "not_started",
    }
    bot_status = _status_map.get(_bot_init_state.state, _bot_init_state.state)

    basic_response: Dict[str, Any] = {
        "status": "healthy",
        "service": "telegram-agent",
        "bot_initialized": _bot_fully_initialized,
        "bot_status": bot_status,
    }

    if _bot_init_state.last_error:
        basic_response["last_error"] = _bot_init_state.last_error

    if not show_details:
        if not _bot_fully_initialized:
            basic_response["status"] = "degraded"
        return basic_response

    # === Detailed health check (requires auth) ===
    error_details = {}
    db_connection_info = {}

    try:
        try:
            from .core.database import get_database_url

            db_url = get_database_url()
            masked_url = db_url
            if "://" in db_url and "@" in db_url:
                parts = db_url.split("@")
                auth_part = parts[0].split("://")[1]
                if ":" in auth_part:
                    user = auth_part.split(":")[0]
                    masked_url = f"{db_url.split('://')[0]}://{user}:****@{parts[1]}"
            db_connection_info = {"connection_string": masked_url}
        except Exception as conn_err:
            db_connection_info = {
                "error": f"Failed to get database URL: {str(conn_err)}"
            }

        try:
            from .core.database import (
                get_chat_count,
                get_embedding_stats,
                get_image_count,
                get_user_count,
                health_check,
            )
        except ImportError as imp_err:
            error_details["import_error"] = str(imp_err)
            return {
                "status": "error",
                "service": "telegram-agent",
                "database": "unknown",
                "error": f"Failed to import database modules: {str(imp_err)}",
                "error_details": error_details,
                "db_connection_info": db_connection_info,
            }

        try:
            db_healthy = await health_check()
        except Exception as db_err:
            error_details["db_health_check_error"] = str(db_err)
            return {
                "status": "error",
                "service": "telegram-agent",
                "database": "disconnected",
                "error": f"Database health check failed: {str(db_err)}",
                "error_details": error_details,
                "db_connection_info": db_connection_info,
            }

        stats = {}
        embedding_stats = {}
        if db_healthy:
            try:
                user_count = await get_user_count()
                chat_count = await get_chat_count()
                image_count = await get_image_count()
                stats = {
                    "users": user_count,
                    "chats": chat_count,
                    "images": image_count,
                }
                embedding_stats = await get_embedding_stats()
            except Exception as stats_err:
                error_details["stats_error"] = str(stats_err)
                stats = {"error": f"Failed to get stats: {str(stats_err)}"}
                embedding_stats = {
                    "error": f"Failed to get embedding stats: {str(stats_err)}"
                }

        telegram_status = await check_telegram_webhook()

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

        active_tasks = get_active_tasks()
        task_stats = {
            "active_count": len(active_tasks),
            "task_names": [t.get_name() for t in active_tasks if not t.done()],
        }

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
        logger.error(f"Health check failed: {e}", exc_info=True)
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


@app.post("/webhook")
async def webhook_endpoint(request: Request) -> Dict[str, str]:
    """Telegram webhook endpoint — delegates to webhook handler."""
    return await handle_webhook(request, _webhook_semaphore)


# ── Include routers ──
try:
    from .api.webhook import router as webhook_router

    app.include_router(webhook_router)
    logger.info("✅ Webhook management API loaded (with authentication)")
except ImportError as e:
    logger.warning(f"⚠️  Webhook management API not available: {e}")

try:
    from .api.messaging import router as messaging_router

    app.include_router(messaging_router)
    logger.info("✅ Messaging API loaded")
except ImportError as e:
    logger.warning(f"⚠️  Messaging API not available: {e}")

try:
    from .api.metrics import create_metrics_router

    app.include_router(create_metrics_router())
    logger.info("✅ Metrics API loaded (with authentication)")
except ImportError as e:
    logger.warning(f"⚠️  Metrics API not available: {e}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("src.main:app", host=host, port=port, reload=True, log_level="info")
