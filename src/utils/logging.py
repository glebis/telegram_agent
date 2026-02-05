import json
import logging
import logging.handlers
import os
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

# Patterns to redact sensitive tokens/keys from logs
SECRET_PATTERNS = [
    # Telegram bot tokens: 6+ digits:alphanum
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"), "[TELEGRAM_TOKEN]"),
    # OpenAI / Anthropic / generic sk- style keys
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "[API_KEY]"),
    # Groq keys often start with gk_ or groq_
    (re.compile(r"\b(?:gk|groq)_[A-Za-z0-9]{16,}\b"), "[API_KEY]"),
    # Bearer tokens / JWT-like strings (base64-ish with dots)
    (
        re.compile(r"\b[A-Za-z0-9-_]{20,}\.[A-Za-z0-9-_]{10,}\.[A-Za-z0-9-_]{10,}\b"),
        "[TOKEN]",
    ),
]


# ---------------------------------------------------------------------------
# RequestContext: contextvar-based context propagation
# ---------------------------------------------------------------------------

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_chat_id_var: ContextVar[Optional[str]] = ContextVar("chat_id", default=None)
_task_id_var: ContextVar[Optional[str]] = ContextVar("task_id", default=None)


class RequestContext:
    """Contextvar-based request context for propagating IDs across log calls.

    Usage:
        RequestContext.set(request_id="abc-123", chat_id="456")
        ctx = RequestContext.get()  # {"request_id": "abc-123", ...}
        RequestContext.clear()
    """

    @staticmethod
    def set(
        request_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Set context fields. Only non-None values are updated."""
        if request_id is not None:
            _request_id_var.set(request_id)
        if chat_id is not None:
            _chat_id_var.set(chat_id)
        if task_id is not None:
            _task_id_var.set(task_id)

    @staticmethod
    def get() -> Dict[str, Optional[str]]:
        """Return current context as a dict."""
        return {
            "request_id": _request_id_var.get(),
            "chat_id": _chat_id_var.get(),
            "task_id": _task_id_var.get(),
        }

    @staticmethod
    def clear() -> None:
        """Reset all context fields to None."""
        _request_id_var.set(None)
        _chat_id_var.set(None)
        _task_id_var.set(None)


# ---------------------------------------------------------------------------
# RequestContextFilter: injects context IDs into log records
# ---------------------------------------------------------------------------


class RequestContextFilter(logging.Filter):
    """Logging filter that copies RequestContext values onto each LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = RequestContext.get()
        record.request_id = ctx["request_id"]  # type: ignore[attr-defined]
        record.chat_id = ctx["chat_id"]  # type: ignore[attr-defined]
        record.task_id = ctx["task_id"]  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# JSONFormatter: structured JSON output for production logs
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """Logging formatter that outputs one JSON object per line.

    Fields: level, timestamp, logger, message.
    Optional context fields (request_id, chat_id, task_id) are included when set.
    Exception info is captured in an 'exception' field.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "level": record.levelname,
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context fields if present and not None
        for field in ("request_id", "chat_id", "task_id"):
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def redact_sensitive_data(logger, method_name, event_dict):
    """Structlog processor to scrub secrets from event dict values."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            for pattern, replacement in SECRET_PATTERNS:
                value = pattern.sub(replacement, value)
            event_dict[key] = value
    if "event" in event_dict and isinstance(event_dict["event"], str):
        text = event_dict["event"]
        for pattern, replacement in SECRET_PATTERNS:
            text = pattern.sub(replacement, text)
        event_dict["event"] = text
    return event_dict


class PIISanitizingFilter(logging.Filter):
    """Filter that redacts PII from log records before they are written to files.

    Redacts: phone numbers, Telegram user/chat IDs in certain contexts,
    and transcription text content.
    """

    PATTERNS = [
        # Phone numbers (international formats)
        (
            re.compile(r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"),
            "[PHONE_REDACTED]",
        ),
        # Transcription content after common prefixes
        (
            re.compile(r"(Transcription result:)\s*.+", re.IGNORECASE),
            r"\1 [TRANSCRIPTION_REDACTED]",
        ),
        (
            re.compile(r"(Corrected transcript:)\s*.+", re.IGNORECASE),
            r"\1 [TRANSCRIPTION_REDACTED]",
        ),
        # Tokens / API keys
        *SECRET_PATTERNS,
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        return True


def setup_logging(log_level: str = "INFO", log_to_file: bool = True) -> None:
    """Set up comprehensive logging configuration for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to files in addition to console
    """
    # Never write log files during tests
    if os.environ.get("ENVIRONMENT") == "test":
        log_to_file = False

    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Configure structlog
    structlog.configure(
        processors=[
            # Add extra context
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_sensitive_data,
            # Add caller info for debugging
            structlog.dev.set_exc_info,
            # JSON formatting for file logs
            (
                structlog.processors.JSONRenderer()
                if log_to_file
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[],  # We'll add handlers manually
    )

    # Determine if we should use JSON formatting for console
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    use_json_console = environment == "production"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    if use_json_console:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

    # Add RequestContextFilter to console handler so context IDs are available
    console_handler.addFilter(RequestContextFilter())

    # Root logger setup
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Clear any existing handlers
    root_logger.addHandler(console_handler)

    # PII sanitizing filter for file handlers
    pii_filter = PIISanitizingFilter()

    if log_to_file:
        # General application log file (time-based rotation, 30-day retention)
        app_handler = logging.handlers.TimedRotatingFileHandler(
            logs_dir / "app.log",
            when="midnight",
            interval=1,
            backupCount=30,
        )
        app_handler.setLevel(logging.INFO)
        app_fmt = (
            "%(asctime)s - %(name)s - %(levelname)s"
            " - %(funcName)s:%(lineno)d - %(message)s"
        )
        app_formatter = logging.Formatter(app_fmt)
        app_handler.setFormatter(app_formatter)
        app_handler.addFilter(pii_filter)
        root_logger.addHandler(app_handler)

        # Image processing specific log file
        image_handler = logging.handlers.TimedRotatingFileHandler(
            logs_dir / "image_processing.log",
            when="midnight",
            interval=1,
            backupCount=30,
        )
        image_handler.setLevel(logging.DEBUG)
        image_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        )
        image_handler.setFormatter(image_formatter)
        image_handler.addFilter(pii_filter)

        # Create image processing logger
        image_logger = logging.getLogger("image_processing")
        image_logger.addHandler(image_handler)
        image_logger.propagate = True  # Also send to root logger

        # Error-only log file for critical issues
        error_handler = logging.handlers.TimedRotatingFileHandler(
            logs_dir / "errors.log",
            when="midnight",
            interval=1,
            backupCount=30,
        )
        error_handler.setLevel(logging.ERROR)
        err_fmt = (
            "%(asctime)s - %(name)s - %(levelname)s"
            " - %(funcName)s:%(lineno)d"
            " - %(message)s - %(exc_info)s"
        )
        error_formatter = logging.Formatter(err_fmt)
        error_handler.setFormatter(error_formatter)
        error_handler.addFilter(pii_filter)
        root_logger.addHandler(error_handler)


def get_image_logger(name: str = None) -> structlog.BoundLogger:
    """Get a structured logger specifically for image processing.

    Args:
        name: Logger name (defaults to calling module)

    Returns:
        Structured logger with image processing context
    """
    if name is None:
        name = "image_processing"

    logger = structlog.get_logger(name)
    return logger


def log_image_processing_error(
    error: Exception, context: Dict[str, Any], logger: structlog.BoundLogger = None
) -> None:
    """Log image processing errors with comprehensive context.

    Args:
        error: The exception that occurred
        context: Additional context about the error
        logger: Logger to use (creates one if not provided)
    """
    if logger is None:
        logger = get_image_logger()

    error_context = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "timestamp": datetime.now().isoformat(),
        **context,
    }

    logger.error("Image processing error occurred", **error_context, exc_info=True)


def log_image_processing_step(
    step: str, details: Dict[str, Any], logger: structlog.BoundLogger = None
) -> None:
    """Log image processing steps for debugging and monitoring.

    Args:
        step: Name of the processing step
        details: Step-specific details
        logger: Logger to use (creates one if not provided)
    """
    if logger is None:
        logger = get_image_logger()

    logger.info(
        f"Image processing step: {step}",
        step=step,
        timestamp=datetime.now().isoformat(),
        **details,
    )


def log_image_processing_success(
    processing_time: float,
    details: Dict[str, Any],
    logger: structlog.BoundLogger = None,
) -> None:
    """Log successful image processing with metrics.

    Args:
        processing_time: Time taken to process the image
        details: Processing details and results
        logger: Logger to use (creates one if not provided)
    """
    if logger is None:
        logger = get_image_logger()

    logger.info(
        "Image processing completed successfully",
        processing_time_seconds=processing_time,
        timestamp=datetime.now().isoformat(),
        **details,
    )


class ImageProcessingLogContext:
    """Context manager for image processing logging."""

    def __init__(self, operation: str, **context):
        self.operation = operation
        self.context = context
        self.logger = get_image_logger()
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        log_image_processing_step(
            f"{self.operation} - START",
            {"start_time": self.start_time.isoformat(), **self.context},
            self.logger,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.now()
        processing_time = (end_time - self.start_time).total_seconds()

        if exc_type is not None:
            # An exception occurred
            log_image_processing_error(
                exc_val,
                {
                    "operation": self.operation,
                    "processing_time_seconds": processing_time,
                    "end_time": end_time.isoformat(),
                    **self.context,
                },
                self.logger,
            )
        else:
            # Success
            log_image_processing_success(
                processing_time,
                {
                    "operation": self.operation,
                    "end_time": end_time.isoformat(),
                    **self.context,
                },
                self.logger,
            )
