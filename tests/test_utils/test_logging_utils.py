"""
Tests for the Logging Utilities module.

Tests cover:
- Logger configuration with setup_logging()
- Log level settings
- File handler setup
- Format configuration
- Structured logging with structlog
- Image processing logging helpers
- ImageProcessingLogContext context manager
"""

import logging
import logging.handlers
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import structlog

from src.utils.logging import (
    setup_logging,
    get_image_logger,
    log_image_processing_error,
    log_image_processing_step,
    log_image_processing_success,
    ImageProcessingLogContext,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_logs_dir():
    """Create a temporary logs directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        logs_dir = Path(temp_dir) / "logs"
        logs_dir.mkdir(exist_ok=True)
        yield logs_dir


@pytest.fixture
def clean_logging_state():
    """Clean up logging state before and after each test."""
    # Store original state
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers.copy()
    original_level = root_logger.level

    # Clear handlers before test
    root_logger.handlers.clear()
    # Reset level to NOTSET so setup_logging can set it properly
    root_logger.setLevel(logging.NOTSET)

    yield

    # Restore original state after test
    root_logger.handlers.clear()
    for handler in original_handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(original_level)

    # Clear image_processing logger handlers
    image_logger = logging.getLogger("image_processing")
    image_logger.handlers.clear()


@pytest.fixture
def mock_structlog():
    """Mock structlog configuration."""
    with patch("src.utils.logging.structlog") as mock:
        yield mock


# =============================================================================
# Setup Logging Tests
# =============================================================================


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_creates_logs_directory(self, clean_logging_state):
        """Test that setup_logging creates logs directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Change to temp directory so 'logs' is created there
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=True)
                logs_dir = Path(temp_dir) / "logs"
                assert logs_dir.exists()
                assert logs_dir.is_dir()
            finally:
                os.chdir(original_cwd)

    def test_default_log_level_is_info(self, clean_logging_state):
        """Test that default log level is INFO.

        Note: We check the console handler level since logging.basicConfig
        may be a no-op if the root logger already has handlers (e.g., from pytest).
        The implementation sets the level on the console handler explicitly.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=False)
                root_logger = logging.getLogger()

                # Find the console handler added by setup_logging
                console_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)
                ]
                assert len(console_handlers) >= 1
                # The console handler should be set to INFO level
                assert console_handlers[0].level == logging.INFO
            finally:
                os.chdir(original_cwd)

    @pytest.mark.parametrize("log_level,expected", [
        ("DEBUG", logging.DEBUG),
        ("INFO", logging.INFO),
        ("WARNING", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
        ("debug", logging.DEBUG),  # Test case insensitivity
        ("Info", logging.INFO),
    ])
    def test_log_level_settings(self, clean_logging_state, log_level, expected):
        """Test that log level is correctly set on console handler.

        Note: We check the console handler level since logging.basicConfig
        may be a no-op if the root logger already has handlers (e.g., from pytest).
        The implementation sets the level on the console handler explicitly.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_level=log_level, log_to_file=False)
                root_logger = logging.getLogger()

                # Find the console handler added by setup_logging
                console_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)
                ]
                assert len(console_handlers) >= 1
                # The console handler should be set to the expected level
                assert console_handlers[0].level == expected
            finally:
                os.chdir(original_cwd)

    def test_console_handler_added(self, clean_logging_state):
        """Test that console handler is added to root logger."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=False)
                root_logger = logging.getLogger()

                console_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)
                ]
                assert len(console_handlers) >= 1
            finally:
                os.chdir(original_cwd)

    def test_console_handler_format(self, clean_logging_state):
        """Test that console handler has correct format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=False)
                root_logger = logging.getLogger()

                console_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)
                ]
                assert len(console_handlers) >= 1
                handler = console_handlers[0]

                # Check format contains expected fields
                format_str = handler.formatter._fmt
                assert "%(asctime)s" in format_str
                assert "%(name)s" in format_str
                assert "%(levelname)s" in format_str
                assert "%(message)s" in format_str
            finally:
                os.chdir(original_cwd)

    def test_clears_existing_handlers(self, clean_logging_state):
        """Test that existing handlers are cleared."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                root_logger = logging.getLogger()

                # Add a dummy handler
                dummy_handler = logging.StreamHandler()
                root_logger.addHandler(dummy_handler)

                setup_logging(log_to_file=False)

                # Dummy handler should be removed
                assert dummy_handler not in root_logger.handlers
            finally:
                os.chdir(original_cwd)


class TestSetupLoggingWithFileHandlers:
    """Tests for setup_logging with file handlers."""

    def test_file_handlers_created(self, clean_logging_state):
        """Test that file handlers are created when log_to_file is True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=True)
                root_logger = logging.getLogger()

                file_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.handlers.RotatingFileHandler)
                ]
                # Should have app.log and errors.log handlers
                assert len(file_handlers) >= 2
            finally:
                os.chdir(original_cwd)

    def test_no_file_handlers_when_disabled(self, clean_logging_state):
        """Test that no file handlers are created when log_to_file is False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=False)
                root_logger = logging.getLogger()

                file_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.FileHandler)
                ]
                assert len(file_handlers) == 0
            finally:
                os.chdir(original_cwd)

    def test_app_log_handler_configuration(self, clean_logging_state):
        """Test app.log handler configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=True)
                root_logger = logging.getLogger()

                # Find app.log handler
                app_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.handlers.RotatingFileHandler)
                    and "app.log" in str(h.baseFilename)
                ]
                assert len(app_handlers) == 1

                handler = app_handlers[0]
                assert handler.level == logging.INFO
                assert handler.maxBytes == 10 * 1024 * 1024  # 10MB
                assert handler.backupCount == 5
            finally:
                os.chdir(original_cwd)

    def test_error_log_handler_configuration(self, clean_logging_state):
        """Test errors.log handler configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=True)
                root_logger = logging.getLogger()

                # Find errors.log handler
                error_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.handlers.RotatingFileHandler)
                    and "errors.log" in str(h.baseFilename)
                ]
                assert len(error_handlers) == 1

                handler = error_handlers[0]
                assert handler.level == logging.ERROR
                assert handler.maxBytes == 5 * 1024 * 1024  # 5MB
                assert handler.backupCount == 10
            finally:
                os.chdir(original_cwd)

    def test_image_processing_logger_configuration(self, clean_logging_state):
        """Test image_processing logger is configured."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=True)

                image_logger = logging.getLogger("image_processing")

                # Should have image_processing.log handler
                image_handlers = [
                    h for h in image_logger.handlers
                    if isinstance(h, logging.handlers.RotatingFileHandler)
                    and "image_processing.log" in str(h.baseFilename)
                ]
                assert len(image_handlers) == 1

                handler = image_handlers[0]
                assert handler.level == logging.DEBUG
                assert handler.maxBytes == 10 * 1024 * 1024  # 10MB
                assert handler.backupCount == 10

                # Should propagate to root logger
                assert image_logger.propagate is True
            finally:
                os.chdir(original_cwd)

    def test_app_log_format_includes_function_info(self, clean_logging_state):
        """Test app.log format includes function and line number."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=True)
                root_logger = logging.getLogger()

                app_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.handlers.RotatingFileHandler)
                    and "app.log" in str(h.baseFilename)
                ]
                handler = app_handlers[0]
                format_str = handler.formatter._fmt

                assert "%(funcName)s" in format_str
                assert "%(lineno)d" in format_str
            finally:
                os.chdir(original_cwd)


class TestStructlogConfiguration:
    """Tests for structlog configuration."""

    def test_structlog_configured(self, clean_logging_state):
        """Test that structlog is configured by setup_logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                with patch("src.utils.logging.structlog.configure") as mock_configure:
                    setup_logging(log_to_file=False)
                    mock_configure.assert_called_once()
            finally:
                os.chdir(original_cwd)

    def test_structlog_uses_json_renderer_for_file(self, clean_logging_state):
        """Test structlog uses JSONRenderer when log_to_file is True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                with patch("src.utils.logging.structlog.configure") as mock_configure:
                    setup_logging(log_to_file=True)

                    call_kwargs = mock_configure.call_args[1]
                    processors = call_kwargs["processors"]

                    # Last processor should be JSONRenderer
                    has_json_renderer = any(
                        isinstance(p, structlog.processors.JSONRenderer)
                        for p in processors
                    )
                    assert has_json_renderer
            finally:
                os.chdir(original_cwd)

    def test_structlog_uses_console_renderer_for_no_file(self, clean_logging_state):
        """Test structlog uses ConsoleRenderer when log_to_file is False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                with patch("src.utils.logging.structlog.configure") as mock_configure:
                    setup_logging(log_to_file=False)

                    call_kwargs = mock_configure.call_args[1]
                    processors = call_kwargs["processors"]

                    # Last processor should be ConsoleRenderer
                    has_console_renderer = any(
                        isinstance(p, structlog.dev.ConsoleRenderer)
                        for p in processors
                    )
                    assert has_console_renderer
            finally:
                os.chdir(original_cwd)


# =============================================================================
# Get Image Logger Tests
# =============================================================================


class TestGetImageLogger:
    """Tests for get_image_logger function."""

    def test_returns_bound_logger(self):
        """Test that get_image_logger returns a BoundLogger."""
        logger = get_image_logger()

        # structlog.get_logger returns a bound logger
        assert logger is not None

    def test_default_name_is_image_processing(self):
        """Test that default logger name is 'image_processing'."""
        with patch("src.utils.logging.structlog.get_logger") as mock_get_logger:
            get_image_logger()
            mock_get_logger.assert_called_once_with("image_processing")

    def test_custom_name(self):
        """Test that custom name is used when provided."""
        with patch("src.utils.logging.structlog.get_logger") as mock_get_logger:
            get_image_logger("custom_logger")
            mock_get_logger.assert_called_once_with("custom_logger")

    def test_none_name_uses_default(self):
        """Test that None name defaults to 'image_processing'."""
        with patch("src.utils.logging.structlog.get_logger") as mock_get_logger:
            get_image_logger(None)
            mock_get_logger.assert_called_once_with("image_processing")


# =============================================================================
# Log Image Processing Error Tests
# =============================================================================


class TestLogImageProcessingError:
    """Tests for log_image_processing_error function."""

    def test_logs_error_with_context(self):
        """Test that error is logged with context."""
        mock_logger = MagicMock()
        error = ValueError("Test error")
        context = {"file_path": "/test/image.jpg", "step": "download"}

        log_image_processing_error(error, context, mock_logger)

        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args[1]

        assert call_kwargs["error_type"] == "ValueError"
        assert call_kwargs["error_message"] == "Test error"
        assert call_kwargs["file_path"] == "/test/image.jpg"
        assert call_kwargs["step"] == "download"
        assert "timestamp" in call_kwargs
        assert call_kwargs["exc_info"] is True

    def test_creates_logger_if_not_provided(self):
        """Test that logger is created if not provided."""
        with patch("src.utils.logging.get_image_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            error = ValueError("Test error")
            log_image_processing_error(error, {})

            mock_get_logger.assert_called_once()
            mock_logger.error.assert_called_once()

    def test_error_message_format(self):
        """Test that error message format is correct."""
        mock_logger = MagicMock()
        error = RuntimeError("Something went wrong")

        log_image_processing_error(error, {}, mock_logger)

        call_args = mock_logger.error.call_args[0]
        assert "Image processing error occurred" in call_args[0]

    def test_timestamp_is_iso_format(self):
        """Test that timestamp is in ISO format."""
        mock_logger = MagicMock()
        error = ValueError("Test error")

        log_image_processing_error(error, {}, mock_logger)

        call_kwargs = mock_logger.error.call_args[1]
        timestamp = call_kwargs["timestamp"]

        # Should be valid ISO format
        datetime.fromisoformat(timestamp)

    def test_preserves_context_values(self):
        """Test that all context values are preserved."""
        mock_logger = MagicMock()
        error = ValueError("Test error")
        context = {
            "file_path": "/path/to/image.jpg",
            "chat_id": 12345,
            "user_id": 67890,
            "processing_stage": "compression",
            "extra_data": {"key": "value"},
        }

        log_image_processing_error(error, context, mock_logger)

        call_kwargs = mock_logger.error.call_args[1]
        assert call_kwargs["file_path"] == "/path/to/image.jpg"
        assert call_kwargs["chat_id"] == 12345
        assert call_kwargs["user_id"] == 67890
        assert call_kwargs["processing_stage"] == "compression"
        assert call_kwargs["extra_data"] == {"key": "value"}


# =============================================================================
# Log Image Processing Step Tests
# =============================================================================


class TestLogImageProcessingStep:
    """Tests for log_image_processing_step function."""

    def test_logs_step_with_details(self):
        """Test that step is logged with details."""
        mock_logger = MagicMock()
        step = "compress"
        details = {"original_size": 1024, "compressed_size": 512}

        log_image_processing_step(step, details, mock_logger)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        call_kwargs = mock_logger.info.call_args[1]

        assert f"Image processing step: {step}" in call_args[0]
        assert call_kwargs["step"] == step
        assert call_kwargs["original_size"] == 1024
        assert call_kwargs["compressed_size"] == 512
        assert "timestamp" in call_kwargs

    def test_creates_logger_if_not_provided(self):
        """Test that logger is created if not provided."""
        with patch("src.utils.logging.get_image_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            log_image_processing_step("test_step", {})

            mock_get_logger.assert_called_once()
            mock_logger.info.assert_called_once()

    def test_empty_details(self):
        """Test logging step with empty details."""
        mock_logger = MagicMock()

        log_image_processing_step("empty_step", {}, mock_logger)

        mock_logger.info.assert_called_once()
        call_kwargs = mock_logger.info.call_args[1]
        assert call_kwargs["step"] == "empty_step"
        assert "timestamp" in call_kwargs


# =============================================================================
# Log Image Processing Success Tests
# =============================================================================


class TestLogImageProcessingSuccess:
    """Tests for log_image_processing_success function."""

    def test_logs_success_with_time(self):
        """Test that success is logged with processing time."""
        mock_logger = MagicMock()
        processing_time = 1.5
        details = {"file_path": "/test/image.jpg", "output_path": "/test/output.jpg"}

        log_image_processing_success(processing_time, details, mock_logger)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        call_kwargs = mock_logger.info.call_args[1]

        assert "Image processing completed successfully" in call_args[0]
        assert call_kwargs["processing_time_seconds"] == 1.5
        assert call_kwargs["file_path"] == "/test/image.jpg"
        assert call_kwargs["output_path"] == "/test/output.jpg"
        assert "timestamp" in call_kwargs

    def test_creates_logger_if_not_provided(self):
        """Test that logger is created if not provided."""
        with patch("src.utils.logging.get_image_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            log_image_processing_success(1.0, {})

            mock_get_logger.assert_called_once()
            mock_logger.info.assert_called_once()

    def test_zero_processing_time(self):
        """Test logging with zero processing time."""
        mock_logger = MagicMock()

        log_image_processing_success(0.0, {}, mock_logger)

        call_kwargs = mock_logger.info.call_args[1]
        assert call_kwargs["processing_time_seconds"] == 0.0

    def test_large_processing_time(self):
        """Test logging with large processing time."""
        mock_logger = MagicMock()

        log_image_processing_success(3600.5, {}, mock_logger)

        call_kwargs = mock_logger.info.call_args[1]
        assert call_kwargs["processing_time_seconds"] == 3600.5


# =============================================================================
# ImageProcessingLogContext Tests
# =============================================================================


class TestImageProcessingLogContext:
    """Tests for ImageProcessingLogContext context manager."""

    def test_context_manager_basic_usage(self):
        """Test basic context manager usage."""
        with patch("src.utils.logging.log_image_processing_step") as mock_step, \
             patch("src.utils.logging.log_image_processing_success") as mock_success:

            with ImageProcessingLogContext("test_operation", file_path="/test.jpg"):
                pass

            # Should log start
            mock_step.assert_called()
            start_call = mock_step.call_args_list[0]
            assert "test_operation - START" in start_call[0][0]

            # Should log success
            mock_success.assert_called_once()

    def test_context_manager_stores_operation(self):
        """Test that context manager stores operation name."""
        ctx = ImageProcessingLogContext("my_operation")
        assert ctx.operation == "my_operation"

    def test_context_manager_stores_context(self):
        """Test that context manager stores additional context."""
        ctx = ImageProcessingLogContext("operation", key1="value1", key2="value2")
        assert ctx.context == {"key1": "value1", "key2": "value2"}

    def test_enter_sets_start_time(self):
        """Test that __enter__ sets start time."""
        ctx = ImageProcessingLogContext("operation")

        with patch("src.utils.logging.log_image_processing_step"):
            result = ctx.__enter__()

        assert ctx.start_time is not None
        assert isinstance(ctx.start_time, datetime)
        assert result is ctx

    def test_enter_logs_start_step(self):
        """Test that __enter__ logs start step."""
        with patch("src.utils.logging.log_image_processing_step") as mock_step:
            ctx = ImageProcessingLogContext("download", url="http://example.com")
            ctx.__enter__()

            mock_step.assert_called_once()
            call_args = mock_step.call_args[0]
            call_kwargs = mock_step.call_args[1] if len(mock_step.call_args) > 1 else {}

            assert "download - START" in call_args[0]

    def test_exit_logs_success_on_normal_exit(self):
        """Test that __exit__ logs success on normal exit."""
        with patch("src.utils.logging.log_image_processing_step"), \
             patch("src.utils.logging.log_image_processing_success") as mock_success:

            ctx = ImageProcessingLogContext("compress")
            ctx.__enter__()
            ctx.__exit__(None, None, None)

            mock_success.assert_called_once()
            call_kwargs = mock_success.call_args[1] if len(mock_success.call_args) > 1 else {}

    def test_exit_logs_error_on_exception(self):
        """Test that __exit__ logs error on exception."""
        with patch("src.utils.logging.log_image_processing_step"), \
             patch("src.utils.logging.log_image_processing_error") as mock_error:

            ctx = ImageProcessingLogContext("process")
            ctx.__enter__()

            exc = ValueError("Test error")
            ctx.__exit__(ValueError, exc, None)

            mock_error.assert_called_once()
            call_args = mock_error.call_args[0]
            assert call_args[0] is exc

    def test_processing_time_calculation(self):
        """Test that processing time is calculated correctly."""
        import time

        with patch("src.utils.logging.log_image_processing_step"), \
             patch("src.utils.logging.log_image_processing_success") as mock_success:

            with ImageProcessingLogContext("slow_operation"):
                time.sleep(0.1)

            call_args = mock_success.call_args[0]
            processing_time = call_args[0]

            # Should be at least 0.1 seconds
            assert processing_time >= 0.1
            # But not much more
            assert processing_time < 0.5

    def test_context_preserved_in_error_log(self):
        """Test that context is preserved in error log."""
        with patch("src.utils.logging.log_image_processing_step"), \
             patch("src.utils.logging.log_image_processing_error") as mock_error:

            try:
                with ImageProcessingLogContext("fail_op", custom_key="custom_value"):
                    raise RuntimeError("Intentional failure")
            except RuntimeError:
                pass

            mock_error.assert_called_once()
            call_args = mock_error.call_args[0]
            error_context = call_args[1]

            assert error_context["operation"] == "fail_op"
            assert error_context["custom_key"] == "custom_value"
            assert "processing_time_seconds" in error_context
            assert "end_time" in error_context

    def test_context_preserved_in_success_log(self):
        """Test that context is preserved in success log."""
        with patch("src.utils.logging.log_image_processing_step"), \
             patch("src.utils.logging.log_image_processing_success") as mock_success:

            with ImageProcessingLogContext("success_op", file_id="12345"):
                pass

            mock_success.assert_called_once()
            call_args = mock_success.call_args[0]
            success_details = call_args[1]

            assert success_details["operation"] == "success_op"
            assert success_details["file_id"] == "12345"
            assert "end_time" in success_details

    def test_exception_not_suppressed(self):
        """Test that exceptions are not suppressed by context manager."""
        with pytest.raises(ValueError, match="Test exception"):
            with patch("src.utils.logging.log_image_processing_step"), \
                 patch("src.utils.logging.log_image_processing_error"):

                with ImageProcessingLogContext("failing_op"):
                    raise ValueError("Test exception")

    def test_logger_created_on_init(self):
        """Test that logger is created during initialization."""
        with patch("src.utils.logging.get_image_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = ImageProcessingLogContext("operation")

            mock_get_logger.assert_called_once()
            assert ctx.logger is mock_logger


# =============================================================================
# Integration Tests
# =============================================================================


class TestLoggingIntegration:
    """Integration tests for logging utilities."""

    def test_full_logging_setup_and_usage(self, clean_logging_state):
        """Test complete logging setup and usage flow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                # Setup logging
                setup_logging(log_level="DEBUG", log_to_file=True)

                # Get image logger
                logger = get_image_logger()
                assert logger is not None

                # Log a step
                log_image_processing_step(
                    "download",
                    {"url": "http://example.com/image.jpg"},
                    logger
                )

                # Log success
                log_image_processing_success(
                    1.5,
                    {"output_path": "/tmp/output.jpg"},
                    logger
                )

                # Log error
                error = ValueError("Test error")
                log_image_processing_error(
                    error,
                    {"step": "compression"},
                    logger
                )

            finally:
                os.chdir(original_cwd)

    def test_context_manager_integration(self, clean_logging_state):
        """Test context manager with actual logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_level="DEBUG", log_to_file=False)

                # Successful operation
                with ImageProcessingLogContext("test_compress", input_size=1024):
                    pass  # Simulate processing

                # Failed operation
                try:
                    with ImageProcessingLogContext("test_analyze", model="vision"):
                        raise ValueError("Analysis failed")
                except ValueError:
                    pass  # Expected

            finally:
                os.chdir(original_cwd)

    def test_multiple_loggers_coexist(self, clean_logging_state):
        """Test that multiple loggers can coexist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                setup_logging(log_to_file=True)

                # Get multiple loggers
                logger1 = get_image_logger("logger1")
                logger2 = get_image_logger("logger2")
                logger3 = get_image_logger()  # Default

                # All should be usable
                assert logger1 is not None
                assert logger2 is not None
                assert logger3 is not None

            finally:
                os.chdir(original_cwd)


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_context_dict(self):
        """Test logging with empty context dictionary."""
        mock_logger = MagicMock()
        error = ValueError("Error")

        # Should not raise
        log_image_processing_error(error, {}, mock_logger)
        log_image_processing_step("step", {}, mock_logger)
        log_image_processing_success(1.0, {}, mock_logger)

    def test_special_characters_in_context(self):
        """Test logging with special characters in context."""
        mock_logger = MagicMock()

        context = {
            "path": "/path/with spaces/and\ttabs",
            "unicode": "Hello \u4e16\u754c",
            "newlines": "line1\nline2\r\nline3",
        }

        # Should not raise
        log_image_processing_step("special_chars", context, mock_logger)
        mock_logger.info.assert_called_once()

    def test_none_values_in_context(self):
        """Test logging with None values in context."""
        mock_logger = MagicMock()

        context = {
            "valid_key": "valid_value",
            "none_key": None,
        }

        # Should not raise
        log_image_processing_step("none_test", context, mock_logger)

    def test_nested_context_values(self):
        """Test logging with nested context values."""
        mock_logger = MagicMock()

        context = {
            "nested": {
                "level1": {
                    "level2": "deep_value"
                }
            },
            "list_value": [1, 2, 3],
        }

        # Should not raise
        log_image_processing_step("nested_test", context, mock_logger)

    def test_very_long_error_message(self):
        """Test logging with very long error message."""
        mock_logger = MagicMock()

        long_message = "A" * 10000
        error = ValueError(long_message)

        # Should not raise
        log_image_processing_error(error, {}, mock_logger)

        call_kwargs = mock_logger.error.call_args[1]
        assert call_kwargs["error_message"] == long_message

    def test_context_manager_with_no_context(self):
        """Test context manager with no additional context."""
        with patch("src.utils.logging.log_image_processing_step"), \
             patch("src.utils.logging.log_image_processing_success"):

            # Should work without any context kwargs
            with ImageProcessingLogContext("bare_operation"):
                pass

    def test_rapid_logging(self):
        """Test rapid successive logging calls."""
        mock_logger = MagicMock()

        for i in range(100):
            log_image_processing_step(
                f"step_{i}",
                {"iteration": i},
                mock_logger
            )

        assert mock_logger.info.call_count == 100

    def test_invalid_log_level_raises(self, clean_logging_state):
        """Test that invalid log level raises an error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                with pytest.raises(AttributeError):
                    setup_logging(log_level="INVALID_LEVEL", log_to_file=False)
            finally:
                os.chdir(original_cwd)
