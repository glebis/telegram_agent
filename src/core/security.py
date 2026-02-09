"""
Centralized API key derivation for the Telegram Agent.

Supports two modes:
1. **Dedicated secret** (recommended): When API_SECRET_KEY is set, keys are
   derived via HMAC-SHA256 using that secret as the HMAC key and a
   purpose-specific label as the message.
2. **Legacy fallback**: When API_SECRET_KEY is *not* set, keys are derived
   from TELEGRAM_WEBHOOK_SECRET using the old salted-SHA256 scheme. A
   deprecation warning is emitted on each derivation.

All callers should use ``derive_api_key(purpose)`` instead of rolling their
own hash.  The *purpose* string (e.g. ``"admin_api"``, ``"messaging_api"``)
ensures that each endpoint gets a distinct key even though they share the
same root secret.
"""

import hashlib
import hmac
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Flag to ensure the deprecation warning is logged only once per process.
_legacy_warning_emitted = False


def _get_api_secret_key() -> Optional[str]:
    """Return the dedicated API secret if configured, else None.

    Checks the environment variable first (matches production behavior
    where load_dotenv may update os.environ), then falls back to the
    Settings object (useful when env var is unset but .env has it).
    """
    env_val = os.getenv("API_SECRET_KEY")
    if env_val:
        return env_val

    try:
        from .config import get_settings

        settings = get_settings()
        val = getattr(settings, "api_secret_key", None)
        if val:
            return val
    except Exception:
        pass

    return None


def _get_webhook_secret() -> Optional[str]:
    """Return the webhook secret (legacy source for key derivation).

    Checks the environment variable first (matches the original
    get_admin_api_key behavior where env has final say), then falls
    back to the Settings object.
    """
    env_val = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if env_val:
        return env_val

    try:
        from .config import get_settings

        settings = get_settings()
        val = getattr(settings, "telegram_webhook_secret", None)
        if val:
            return val
    except Exception:
        pass

    return None


def derive_api_key(purpose: str) -> str:
    """Derive a hex API key for the given *purpose* label.

    Args:
        purpose: A short identifier such as ``"admin_api"`` or
            ``"messaging_api"``.  Must be non-empty.

    Returns:
        A 64-character lowercase hex string (256 bits).

    Raises:
        ValueError: If neither API_SECRET_KEY nor TELEGRAM_WEBHOOK_SECRET
            is configured.
    """
    if not purpose:
        raise ValueError("purpose must be a non-empty string")

    # ---- preferred path: dedicated secret + HMAC-SHA256 ----
    api_secret = _get_api_secret_key()
    if api_secret:
        return hmac.new(
            api_secret.encode(),
            purpose.encode(),
            hashlib.sha256,
        ).hexdigest()

    # ---- legacy fallback: webhook secret + plain SHA-256 ----
    webhook_secret = _get_webhook_secret()
    if not webhook_secret:
        raise ValueError(
            "Neither API_SECRET_KEY nor TELEGRAM_WEBHOOK_SECRET is configured"
        )

    global _legacy_warning_emitted
    if not _legacy_warning_emitted:
        logger.warning(
            "API_SECRET_KEY is not set — falling back to TELEGRAM_WEBHOOK_SECRET "
            "for API key derivation. Set API_SECRET_KEY for stronger isolation."
        )
        _legacy_warning_emitted = True

    return hashlib.sha256(f"{webhook_secret}:{purpose}".encode()).hexdigest()


def reset_legacy_warning() -> None:
    """Reset the one-shot deprecation flag (for tests only)."""
    global _legacy_warning_emitted
    _legacy_warning_emitted = False
