"""Tunnel health monitoring and auto-recovery service.

This service monitors Cloudflare tunnel health and attempts automatic recovery
without requiring a full bot restart.
"""

import asyncio
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class TunnelMonitorService:
    """Monitors tunnel health and performs automatic recovery."""

    def __init__(
        self,
        bot_token: str,
        webhook_secret: Optional[str] = None,
        restart_cooldown: int = 300,  # 5 minutes
        max_restarts_per_hour: int = 3,
    ):
        """Initialize tunnel monitor.

        Args:
            bot_token: Telegram bot token for webhook operations
            webhook_secret: Webhook secret token
            restart_cooldown: Minimum seconds between restarts
            max_restarts_per_hour: Maximum restarts allowed per hour
        """
        self._bot_token = bot_token
        self._webhook_secret = webhook_secret
        self._restart_cooldown = restart_cooldown
        self._max_restarts_per_hour = max_restarts_per_hour
        self._restart_times: list[float] = []
        self._last_restart_time: float = 0.0
        self._consecutive_failures: int = 0

    async def check_tunnel_health(self) -> Tuple[bool, str]:
        """Check if tunnel is healthy.

        Returns:
            Tuple of (is_healthy, status_message)
        """
        from ..tunnel.factory import get_tunnel_provider_instance

        provider = get_tunnel_provider_instance()

        if not provider:
            return True, "No tunnel provider configured"

        # Skip monitoring for non-Cloudflare providers
        if provider.name != "cloudflare":
            return True, f"Tunnel provider {provider.name} doesn't require monitoring"

        # Use provider's health check method
        try:
            is_healthy, message = await provider.health_check()
            if is_healthy:
                self._consecutive_failures = 0
            return is_healthy, message
        except Exception as e:
            logger.error(f"Error checking tunnel health: {e}", exc_info=True)
            return False, f"Health check error: {e}"

    def _can_restart(self) -> Tuple[bool, str]:
        """Check if restart is allowed (rate limiting).

        Returns:
            Tuple of (can_restart, reason)
        """
        now = time.time()

        # Cooldown check: at least N minutes since last restart
        if self._last_restart_time > 0:
            elapsed = now - self._last_restart_time
            if elapsed < self._restart_cooldown:
                remaining = int(self._restart_cooldown - elapsed)
                return False, f"Cooldown active ({remaining}s remaining)"

        # Sliding window: max N restarts per hour
        self._restart_times = [t for t in self._restart_times if now - t < 3600]
        if len(self._restart_times) >= self._max_restarts_per_hour:
            return False, f"Rate limit exceeded ({self._max_restarts_per_hour}/hour)"

        return True, "OK"

    async def _restart_tunnel(self) -> bool:
        """Restart the tunnel without restarting the bot.

        Returns:
            True if restart successful, False otherwise
        """
        from ..tunnel.factory import get_tunnel_provider_instance

        provider = get_tunnel_provider_instance()

        if not provider:
            logger.error("No tunnel provider available to restart")
            return False

        try:
            logger.info(f"Attempting to restart {provider.name} tunnel...")

            # Stop current tunnel
            await provider.stop()
            await asyncio.sleep(2)  # Brief pause

            # Start new tunnel
            tunnel_url = await provider.start()

            if not tunnel_url:
                logger.error("Tunnel restart failed: no URL returned")
                return False

            # Re-register webhook with new/same URL
            webhook_url = f"{tunnel_url}/webhook"
            success = await self._reregister_webhook(webhook_url)

            if success:
                logger.info(f"✅ Tunnel restarted successfully: {tunnel_url}")
                # Update restart tracking
                now = time.time()
                self._restart_times.append(now)
                self._last_restart_time = now
                self._consecutive_failures = 0
                return True
            else:
                logger.error("Tunnel restarted but webhook registration failed")
                return False

        except Exception as e:
            logger.error(f"Error restarting tunnel: {e}", exc_info=True)
            return False

    async def _reregister_webhook(self, webhook_url: str) -> bool:
        """Re-register webhook after tunnel restart.

        Args:
            webhook_url: New webhook URL

        Returns:
            True if registration successful
        """
        try:
            from ..utils.ngrok_utils import WebhookManager

            manager = WebhookManager(self._bot_token)
            success, message = await manager.set_webhook(
                webhook_url, self._webhook_secret
            )

            if success:
                logger.info(f"Webhook re-registered: {webhook_url}")
            else:
                logger.error(f"Webhook registration failed: {message}")

            return success

        except Exception as e:
            logger.error(f"Error re-registering webhook: {e}", exc_info=True)
            return False

    async def recover_from_failure(self) -> bool:
        """Attempt recovery from tunnel failure.

        Uses progressive fallback strategy:
        1. Check if restart is rate-limited
        2. Attempt tunnel restart
        3. Return failure if recovery impossible (triggers bot restart)

        Returns:
            True if recovery successful, False if bot restart needed
        """
        self._consecutive_failures += 1

        # Check rate limiting
        can_restart, reason = self._can_restart()
        if not can_restart:
            logger.warning(
                f"Cannot restart tunnel: {reason}. "
                f"Consecutive failures: {self._consecutive_failures}"
            )
            # If we've had 3+ consecutive failures and can't restart,
            # return False to trigger bot restart
            if self._consecutive_failures >= 3:
                logger.error(
                    "Multiple consecutive failures and rate limit hit - "
                    "bot restart required"
                )
                return False
            # Otherwise, wait for cooldown
            return True  # Don't trigger bot restart yet

        # Attempt tunnel restart
        logger.info(
            f"Attempting tunnel recovery (consecutive failures: "
            f"{self._consecutive_failures})"
        )

        success = await self._restart_tunnel()

        if not success:
            logger.error("Tunnel restart failed")
            # If restart failed and we've had multiple failures, give up
            if self._consecutive_failures >= 2:
                logger.error(
                    f"Tunnel restart failed after {self._consecutive_failures} "
                    "consecutive failures - bot restart required"
                )
                return False

        return success


async def run_periodic_tunnel_monitor(
    bot_token: str,
    webhook_secret: Optional[str] = None,
    interval_minutes: float = 2.0,
) -> None:
    """Run periodic tunnel health monitoring and auto-recovery.

    This background task checks tunnel health every N minutes and attempts
    automatic recovery if issues are detected.

    Args:
        bot_token: Telegram bot token
        webhook_secret: Webhook secret token
        interval_minutes: Check interval in minutes
    """
    logger.info(f"Starting periodic tunnel monitoring (every {interval_minutes} min)")

    monitor = TunnelMonitorService(bot_token, webhook_secret)

    # Wait before first check to allow tunnel to initialize
    await asyncio.sleep(interval_minutes * 60)

    while True:
        try:
            is_healthy, message = await monitor.check_tunnel_health()

            if not is_healthy:
                logger.warning(f"Tunnel unhealthy: {message}")
                recovered = await monitor.recover_from_failure()

                if recovered:
                    logger.info("✅ Tunnel recovery successful")
                else:
                    logger.error(
                        "❌ Tunnel recovery failed - bot restart may be needed"
                    )
            else:
                logger.debug(f"Tunnel check: {message}")

            # Wait for next check
            await asyncio.sleep(interval_minutes * 60)

        except asyncio.CancelledError:
            logger.info("Tunnel monitor task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic tunnel monitoring: {e}", exc_info=True)
            # Continue despite errors
            await asyncio.sleep(interval_minutes * 60)
