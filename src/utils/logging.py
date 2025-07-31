import logging
import logging.handlers
import structlog
import sys
import os
from pathlib import Path
from typing import Any, Dict
import json
from datetime import datetime


def setup_logging(log_level: str = "INFO", log_to_file: bool = True) -> None:
    """Set up comprehensive logging configuration for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to files in addition to console
    """

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

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)

    # Root logger setup
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Clear any existing handlers
    root_logger.addHandler(console_handler)

    if log_to_file:
        # General application log file
        app_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
        )
        app_handler.setLevel(logging.INFO)
        app_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        )
        app_handler.setFormatter(app_formatter)
        root_logger.addHandler(app_handler)

        # Image processing specific log file
        image_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "image_processing.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,
        )
        image_handler.setLevel(logging.DEBUG)
        image_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        )
        image_handler.setFormatter(image_formatter)

        # Create image processing logger
        image_logger = logging.getLogger("image_processing")
        image_logger.addHandler(image_handler)
        image_logger.propagate = True  # Also send to root logger

        # Error-only log file for critical issues
        error_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "errors.log", maxBytes=5 * 1024 * 1024, backupCount=10  # 5MB
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s - %(exc_info)s"
        )
        error_handler.setFormatter(error_formatter)
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
