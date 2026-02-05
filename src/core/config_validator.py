"""
Startup configuration validation and redacted summary logging.

Called early in the FastAPI lifespan to fail fast on misconfiguration.
"""

import logging
import re
from typing import List
from urllib.parse import urlparse

from .config import Settings

logger = logging.getLogger(__name__)

# Secrets that must be non-empty for the bot to function.
_REQUIRED_SECRETS = [
    ("telegram_bot_token", "TELEGRAM_BOT_TOKEN"),
    ("telegram_webhook_secret", "TELEGRAM_WEBHOOK_SECRET"),
]

# Minimal pattern: scheme://... or scheme:///...
_SQLALCHEMY_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://")


def validate_config(settings: Settings) -> List[str]:
    """
    Validate application configuration and return a list of error strings.

    An empty list means the configuration is valid.
    """
    errors: List[str] = []

    # -- Required secrets --------------------------------------------------
    for attr, env_name in _REQUIRED_SECRETS:
        value = getattr(settings, attr, "")
        if not value or not value.strip():
            errors.append(f"{env_name} is required but missing or empty")

    # -- DATABASE_URL format -----------------------------------------------
    db_url = (settings.database_url or "").strip()
    if not db_url:
        errors.append("DATABASE_URL is required but missing or empty")
    elif not _SQLALCHEMY_URL_RE.match(db_url):
        errors.append(
            f"DATABASE_URL format is invalid (expected SQLAlchemy URL like "
            f"'sqlite+aiosqlite:///...' or 'postgresql+asyncpg://...'): "
            f"'{db_url}'"
        )

    # -- Production DB enforcement -----------------------------------------
    if settings.environment.lower() == "production" and db_url:
        if db_url.lower().startswith("sqlite"):
            errors.append(
                "SQLite is not allowed in production. "
                "DATABASE_URL must use PostgreSQL (e.g. postgresql+asyncpg://...)"
            )

    # -- TELEGRAM_WEBHOOK_URL format (optional) ----------------------------
    webhook_url = getattr(settings, "telegram_webhook_url", None)
    if webhook_url is not None and webhook_url.strip():
        parsed = urlparse(webhook_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(
                f"TELEGRAM_WEBHOOK_URL format is invalid "
                f"(expected http(s)://...): '{webhook_url}'"
            )

    return errors


def _redact(secret: str) -> str:
    """Return first 4 characters followed by '***', or '<empty>' if blank."""
    if not secret:
        return "<empty>"
    return secret[:4] + "***"


def _db_type(database_url: str) -> str:
    """Extract the database backend name from a SQLAlchemy URL."""
    if not database_url:
        return "none"
    scheme = database_url.split("://")[0] if "://" in database_url else database_url
    # e.g. "sqlite+aiosqlite" -> "sqlite", "postgresql+asyncpg" -> "postgresql"
    return scheme.split("+")[0].lower()


def log_config_summary(settings: Settings) -> None:
    """
    Log an INFO-level summary of loaded configuration with secrets redacted.

    Includes: environment, database type, tunnel provider, and enabled features.
    """
    features = []
    if settings.groq_api_key:
        features.append("groq_stt")
    if settings.anthropic_api_key:
        features.append("anthropic")
    if settings.openai_api_key:
        features.append("openai")
    if settings.heartbeat_chat_ids:
        features.append("heartbeat")

    tunnel = settings.tunnel_provider or "none"

    summary_lines = [
        f"environment={settings.environment}",
        f"database={_db_type(settings.database_url)}",
        f"tunnel={tunnel}",
        f"features=[{', '.join(features) if features else 'none'}]",
        f"bot_token={_redact(settings.telegram_bot_token)}",
        f"webhook_secret={_redact(settings.telegram_webhook_secret)}",
    ]

    # Include optional API keys only if set
    if settings.anthropic_api_key:
        summary_lines.append(f"anthropic_key={_redact(settings.anthropic_api_key)}")
    if settings.groq_api_key:
        summary_lines.append(f"groq_key={_redact(settings.groq_api_key)}")

    logger.info("Config loaded: %s", " | ".join(summary_lines))
