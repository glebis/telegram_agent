"""
Tests for the JSON log formatter and RequestContext contextvar propagation.

Tests cover:
- JSONFormatter output shape (required fields)
- Context ID injection via RequestContextFilter
- RequestContext contextvar get/set/clear
- Console formatter still used in development
- JSON formatter used in production
"""

import json
import logging
import os
import tempfile
from io import StringIO

import pytest

from src.utils.logging import (
    JSONFormatter,
    RequestContext,
    RequestContextFilter,
    setup_logging,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def json_formatter():
    """Create a JSONFormatter instance."""
    return JSONFormatter()


@pytest.fixture
def logger_with_json(json_formatter):
    """Create a logger with JSONFormatter attached to a StringIO handler."""
    logger = logging.getLogger("test.json_formatter")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(json_formatter)
    handler.addFilter(RequestContextFilter())
    logger.addHandler(handler)

    yield logger, stream

    logger.handlers.clear()


@pytest.fixture(autouse=True)
def clear_request_context():
    """Clear RequestContext before and after each test."""
    RequestContext.clear()
    yield
    RequestContext.clear()


# =============================================================================
# JSONFormatter Output Shape Tests
# =============================================================================


class TestJSONFormatterShape:
    """Tests for JSONFormatter output fields."""

    def test_output_is_valid_json(self, logger_with_json):
        """Test that output is valid JSON."""
        logger, stream = logger_with_json
        logger.info("test message")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_contains_level(self, logger_with_json):
        """Test that output contains level field."""
        logger, stream = logger_with_json
        logger.info("test message")
        parsed = json.loads(stream.getvalue().strip())
        assert "level" in parsed
        assert parsed["level"] == "INFO"

    def test_contains_timestamp(self, logger_with_json):
        """Test that output contains timestamp field."""
        logger, stream = logger_with_json
        logger.info("test message")
        parsed = json.loads(stream.getvalue().strip())
        assert "timestamp" in parsed
        # Should be ISO format
        assert "T" in parsed["timestamp"]

    def test_contains_logger_name(self, logger_with_json):
        """Test that output contains logger name."""
        logger, stream = logger_with_json
        logger.info("test message")
        parsed = json.loads(stream.getvalue().strip())
        assert "logger" in parsed
        assert parsed["logger"] == "test.json_formatter"

    def test_contains_message(self, logger_with_json):
        """Test that output contains message field."""
        logger, stream = logger_with_json
        logger.info("hello world")
        parsed = json.loads(stream.getvalue().strip())
        assert "message" in parsed
        assert parsed["message"] == "hello world"

    def test_different_log_levels(self, logger_with_json):
        """Test output for different log levels."""
        logger, stream = logger_with_json

        for level_name in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            stream.truncate(0)
            stream.seek(0)
            getattr(logger, level_name.lower())("test")
            parsed = json.loads(stream.getvalue().strip())
            assert parsed["level"] == level_name

    def test_exception_info_included(self, logger_with_json):
        """Test that exception info is included when present."""
        logger, stream = logger_with_json
        try:
            raise ValueError("test error")
        except ValueError:
            logger.exception("caught error")

        parsed = json.loads(stream.getvalue().strip())
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "test error" in parsed["exception"]


# =============================================================================
# RequestContext Tests
# =============================================================================


class TestRequestContext:
    """Tests for RequestContext contextvar management."""

    def test_set_and_get_request_id(self):
        """Test setting and getting request_id."""
        RequestContext.set(request_id="req-123")
        ctx = RequestContext.get()
        assert ctx["request_id"] == "req-123"

    def test_set_and_get_chat_id(self):
        """Test setting and getting chat_id."""
        RequestContext.set(chat_id="chat-456")
        ctx = RequestContext.get()
        assert ctx["chat_id"] == "chat-456"

    def test_set_and_get_task_id(self):
        """Test setting and getting task_id."""
        RequestContext.set(task_id="task-789")
        ctx = RequestContext.get()
        assert ctx["task_id"] == "task-789"

    def test_set_multiple_fields(self):
        """Test setting multiple context fields at once."""
        RequestContext.set(request_id="req-1", chat_id="chat-2", task_id="task-3")
        ctx = RequestContext.get()
        assert ctx["request_id"] == "req-1"
        assert ctx["chat_id"] == "chat-2"
        assert ctx["task_id"] == "task-3"

    def test_clear_resets_all_fields(self):
        """Test that clear resets all context fields."""
        RequestContext.set(request_id="req-1", chat_id="chat-2", task_id="task-3")
        RequestContext.clear()
        ctx = RequestContext.get()
        assert ctx["request_id"] is None
        assert ctx["chat_id"] is None
        assert ctx["task_id"] is None

    def test_get_returns_none_by_default(self):
        """Test that get returns None values by default."""
        ctx = RequestContext.get()
        assert ctx["request_id"] is None
        assert ctx["chat_id"] is None
        assert ctx["task_id"] is None

    def test_partial_set_preserves_other_fields(self):
        """Test that setting one field preserves others."""
        RequestContext.set(request_id="req-1", chat_id="chat-2")
        RequestContext.set(task_id="task-3")
        ctx = RequestContext.get()
        # request_id and chat_id should still be set from first call
        assert ctx["request_id"] == "req-1"
        assert ctx["chat_id"] == "chat-2"
        assert ctx["task_id"] == "task-3"


# =============================================================================
# RequestContextFilter Tests
# =============================================================================


class TestRequestContextFilter:
    """Tests for RequestContextFilter injecting context into log records."""

    def test_injects_request_id(self, logger_with_json):
        """Test that request_id is injected into log output."""
        logger, stream = logger_with_json
        RequestContext.set(request_id="req-abc")
        logger.info("test")
        parsed = json.loads(stream.getvalue().strip())
        assert parsed.get("request_id") == "req-abc"

    def test_injects_chat_id(self, logger_with_json):
        """Test that chat_id is injected into log output."""
        logger, stream = logger_with_json
        RequestContext.set(chat_id="chat-def")
        logger.info("test")
        parsed = json.loads(stream.getvalue().strip())
        assert parsed.get("chat_id") == "chat-def"

    def test_injects_task_id(self, logger_with_json):
        """Test that task_id is injected into log output."""
        logger, stream = logger_with_json
        RequestContext.set(task_id="task-ghi")
        logger.info("test")
        parsed = json.loads(stream.getvalue().strip())
        assert parsed.get("task_id") == "task-ghi"

    def test_no_context_fields_when_unset(self, logger_with_json):
        """Test that context fields are absent when not set."""
        logger, stream = logger_with_json
        logger.info("test")
        parsed = json.loads(stream.getvalue().strip())
        # None fields should not appear in JSON output
        assert "request_id" not in parsed or parsed["request_id"] is None
        assert "chat_id" not in parsed or parsed["chat_id"] is None
        assert "task_id" not in parsed or parsed["task_id"] is None

    def test_all_context_fields_injected(self, logger_with_json):
        """Test that all context fields are injected together."""
        logger, stream = logger_with_json
        RequestContext.set(request_id="r1", chat_id="c2", task_id="t3")
        logger.info("test")
        parsed = json.loads(stream.getvalue().strip())
        assert parsed.get("request_id") == "r1"
        assert parsed.get("chat_id") == "c2"
        assert parsed.get("task_id") == "t3"


# =============================================================================
# Setup Logging Mode Tests
# =============================================================================


class TestSetupLoggingModes:
    """Tests for JSON vs console formatter selection."""

    def test_json_formatter_in_production(self):
        """Test that JSON formatter is used when ENVIRONMENT=production."""
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        original_level = root_logger.level
        original_env = os.environ.get("ENVIRONMENT")

        try:
            root_logger.handlers.clear()
            os.environ["ENVIRONMENT"] = "production"

            with tempfile.TemporaryDirectory() as temp_dir:
                original_cwd = os.getcwd()
                os.chdir(temp_dir)
                try:
                    setup_logging(log_level="INFO", log_to_file=False)
                    root_logger = logging.getLogger()

                    # Find console handler
                    console_handlers = [
                        h
                        for h in root_logger.handlers
                        if isinstance(h, logging.StreamHandler)
                        and not isinstance(h, logging.FileHandler)
                    ]
                    assert len(console_handlers) >= 1
                    # Should use JSONFormatter
                    assert isinstance(console_handlers[0].formatter, JSONFormatter)
                finally:
                    os.chdir(original_cwd)
        finally:
            root_logger.handlers.clear()
            for h in original_handlers:
                root_logger.addHandler(h)
            root_logger.setLevel(original_level)
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
            else:
                os.environ.pop("ENVIRONMENT", None)

    def test_console_formatter_in_development(self):
        """Test that standard formatter is used when ENVIRONMENT=development."""
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        original_level = root_logger.level
        original_env = os.environ.get("ENVIRONMENT")

        try:
            root_logger.handlers.clear()
            os.environ["ENVIRONMENT"] = "development"

            with tempfile.TemporaryDirectory() as temp_dir:
                original_cwd = os.getcwd()
                os.chdir(temp_dir)
                try:
                    setup_logging(log_level="INFO", log_to_file=False)
                    root_logger = logging.getLogger()

                    console_handlers = [
                        h
                        for h in root_logger.handlers
                        if isinstance(h, logging.StreamHandler)
                        and not isinstance(h, logging.FileHandler)
                    ]
                    assert len(console_handlers) >= 1
                    # Should NOT use JSONFormatter
                    assert not isinstance(console_handlers[0].formatter, JSONFormatter)
                finally:
                    os.chdir(original_cwd)
        finally:
            root_logger.handlers.clear()
            for h in original_handlers:
                root_logger.addHandler(h)
            root_logger.setLevel(original_level)
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
            else:
                os.environ.pop("ENVIRONMENT", None)
