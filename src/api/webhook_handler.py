"""
Telegram webhook endpoint handler.

Handles:
- Concurrency cap (semaphore)
- Webhook secret verification
- Update deduplication
- Per-user rate limiting
- Background processing dispatch

Extracted from main.py as part of #152.
"""

import asyncio
import hmac
import logging
import os
import time
from collections import OrderedDict
from typing import Dict

from fastapi import HTTPException, Request

from ..bot.bot import get_bot
from ..utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)

# ── Deduplication state ──
# Track processed update_ids to prevent duplicate processing
# when Telegram retries due to timeout (Claude Code can take >60s)
_processed_updates: OrderedDict[int, float] = OrderedDict()
_processing_updates: set[int] = set()
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


# ── Per-user rate limiting ──
_USER_RATE_LIMIT = 30  # messages per minute per user
_user_rate_buckets: dict[int, tuple[float, float]] = {}
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


async def handle_webhook(
    request: Request,
    webhook_semaphore: asyncio.Semaphore,
) -> Dict[str, str]:
    """Telegram webhook endpoint handler.

    Body size and rate limiting are enforced by middleware.
    This handler manages:
    - Concurrency cap (semaphore)
    - Webhook secret verification
    - Update deduplication
    - Background processing dispatch
    """
    # Concurrency cap (non-blocking check)
    if webhook_semaphore.locked():
        raise HTTPException(status_code=503, detail="Busy")
    acquired = await webhook_semaphore.acquire()
    task_started = False
    try:
        try:
            update_data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        # Verify webhook secret if configured
        webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if webhook_secret:
            received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
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

        # Per-user rate limiting
        from_user = update_data.get("message", {}).get("from", {}) or update_data.get(
            "callback_query", {}
        ).get("from", {})
        tg_user_id = from_user.get("id") if from_user else None
        if tg_user_id and not _check_user_rate_limit(tg_user_id):
            logger.warning("Per-user rate limit exceeded for user %d", tg_user_id)
            return {"status": "ok", "note": "rate_limited"}

        # Deduplication check
        async with _updates_lock:
            if len(_processed_updates) > MAX_TRACKED_UPDATES:
                await _cleanup_old_updates()
                while len(_processed_updates) > MAX_TRACKED_UPDATES:
                    _processed_updates.popitem(last=False)

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

            _processing_updates.add(update_id)

        # Process the update in background task
        async def process_in_background():
            try:
                bot = get_bot()
                success = await bot.process_update(update_data)
                if not success:
                    logger.error(f"Failed to process update {update_id}")
            except Exception as e:
                logger.error(f"Error processing update {update_id}: {e}")
            finally:
                async with _updates_lock:
                    _processing_updates.discard(update_id)
                    _processed_updates[update_id] = time.time()
                webhook_semaphore.release()

        create_tracked_task(process_in_background(), name=f"webhook_{update_id}")
        task_started = True
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if acquired and not task_started:
            try:
                webhook_semaphore.release()
            except ValueError:
                pass
