"""
Audit logging for security-relevant events.

Logs to a separate audit.log file with 90-day retention.
Events: data exports, data deletions, admin API access, failed auth attempts.
"""

import logging
import logging.handlers
from pathlib import Path


def get_audit_logger() -> logging.Logger:
    """Get or create the audit logger with dedicated file handler."""
    logger = logging.getLogger("audit")

    if not logger.handlers:
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        handler = logging.handlers.TimedRotatingFileHandler(
            logs_dir / "audit.log",
            when="midnight",
            interval=1,
            backupCount=90,
        )
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - AUDIT - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Don't send to root logger

    return logger


def audit_log(event: str, user_id: int = None, details: str = None) -> None:
    """Log a security-relevant event.

    Args:
        event: Event type (e.g., "data_export", "data_deletion", "auth_failure")
        user_id: Telegram user ID (optional)
        details: Additional context
    """
    logger = get_audit_logger()
    parts = [f"event={event}"]
    if user_id is not None:
        parts.append(f"user_id={user_id}")
    if details:
        parts.append(f"details={details}")
    logger.info(" | ".join(parts))
