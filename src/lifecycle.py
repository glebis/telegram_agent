"""
Application lifespan management.

Handles startup and shutdown of all subsystems:
- Configuration validation
- Database initialization
- Service container setup
- Plugin loading
- Telegram bot initialization
- Webhook setup (tunnel or production)
- Background tasks (cleanup, monitoring, etc.)

Extracted from main.py as part of #152.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .bot.bot import get_bot, initialize_bot, shutdown_bot
from .core.config import get_config_value, get_settings
from .core.config_validator import log_config_summary, validate_config
from .core.database import close_database, init_database
from .core.services import setup_services
from .plugins import get_plugin_manager
from .utils.cleanup import run_periodic_cleanup
from .utils.retry import async_retry
from .utils.task_tracker import (
    cancel_all_tasks,
    create_tracked_task,
    get_active_task_count,
)

logger = logging.getLogger(__name__)

# Track if bot lifespan has fully completed
_bot_fully_initialized = False


def is_bot_initialized() -> bool:
    """Check if bot lifespan startup completed."""
    return _bot_fully_initialized


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
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
    tunnel_provider = await _setup_webhook()

    # Start background tasks
    _start_background_tasks()

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
    await _shutdown(tunnel_provider, plugin_manager, bot_initialized)


async def _setup_webhook():
    """Set up webhook based on environment. Returns tunnel_provider or None."""
    tunnel_provider = None
    try:
        logger.info("📣 LIFESPAN: Starting webhook setup")
        environment = os.getenv("ENVIRONMENT", "development").lower()
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        port = int(os.getenv("TUNNEL_PORT", os.getenv("NGROK_PORT", "8000")))

        logger.info(f"🔍 ENVIRONMENT DETECTION: Current environment is '{environment}'")
        logger.info(
            f"🔍 ENVIRONMENT VARIABLES: ENVIRONMENT={environment}, "
            f"WEBHOOK_SECRET={'***' if webhook_secret else 'None'}"
        )

        from .tunnel import get_tunnel_provider
        from .tunnel.factory import set_tunnel_provider_instance
        from .utils.ngrok_utils import WebhookManager

        tunnel_provider = get_tunnel_provider(port=port)

        # Register tunnel provider singleton for monitoring
        set_tunnel_provider_instance(tunnel_provider)

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

                # But DO monitor Cloudflare tunnel health proactively
                if tunnel_provider.name == "cloudflare":
                    from .services.tunnel_monitor_service import (
                        run_periodic_tunnel_monitor,
                    )

                    create_tracked_task(
                        run_periodic_tunnel_monitor(
                            bot_token=bot_token,
                            webhook_secret=webhook_secret,
                            interval_minutes=2.0,
                        ),
                        name="tunnel_health_monitor",
                    )
                    logger.info(
                        "✅ Started periodic tunnel health monitoring (every 2 min)"
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

    return tunnel_provider


def _start_background_tasks():
    """Start all periodic background tasks."""
    # Periodic cleanup (every hour, delete files older than 1 hour)
    create_tracked_task(
        run_periodic_cleanup(interval_hours=1.0, max_age_hours=1.0),
        name="periodic_cleanup",
    )
    logger.info("✅ Started periodic cleanup task")

    # Periodic zombie Claude process reaper (every hour)
    from .services.claude_code_service import run_periodic_process_reaper

    create_tracked_task(
        run_periodic_process_reaper(interval_hours=1.0), name="claude_process_reaper"
    )
    logger.info("✅ Started periodic Claude process reaper")

    # Periodic data retention enforcement (every 24 hours)
    from .services.data_retention_service import run_periodic_retention

    create_tracked_task(
        run_periodic_retention(interval_hours=24.0), name="data_retention"
    )
    logger.info("✅ Started periodic data retention task")

    # Periodic stale Claude session cleanup (every hour, deactivate after 7 days)
    from .services.session_cleanup_service import run_periodic_session_cleanup

    create_tracked_task(
        run_periodic_session_cleanup(interval_hours=1.0, max_age_days=7),
        name="session_cleanup",
    )
    logger.info("✅ Started periodic stale session cleanup")

    # Periodic reply context cleanup (every hour)
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

    # Resource monitor (opt-in via RESOURCE_MONITOR_CHAT_IDS or HEARTBEAT_CHAT_IDS)
    resource_monitor_enabled = get_config_value("resource_monitor.enabled", True)
    if resource_monitor_enabled:
        from .services.resource_monitor_service import run_periodic_resource_monitor

        rm_interval = get_config_value("resource_monitor.interval_minutes", 5.0)
        rm_cooldown = get_config_value("resource_monitor.cooldown_minutes", 30)
        create_tracked_task(
            run_periodic_resource_monitor(
                interval_minutes=rm_interval,
                cooldown_minutes=rm_cooldown,
            ),
            name="resource_monitor",
        )
        logger.info("✅ Started resource monitor (every %.0f min)", rm_interval)


async def _shutdown(tunnel_provider, plugin_manager, bot_initialized):
    """Shutdown all subsystems in order."""
    logger.info("🛑 Telegram Agent shutting down...")

    # Stop tunnel provider
    if tunnel_provider:
        try:
            from .tunnel.factory import set_tunnel_provider_instance

            await tunnel_provider.stop()
            set_tunnel_provider_instance(None)
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
