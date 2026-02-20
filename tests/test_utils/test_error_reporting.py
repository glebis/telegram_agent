"""Tests for standardized error reporting.

TDD: RED → GREEN → REFACTOR for error categories, counters,
message formatting, and the handle_errors decorator.
"""

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest


class TestErrorCategories:
    """Slice 1: Classify exceptions into error categories."""

    def test_connection_error_is_network(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(ConnectionError("refused")) == ErrorCategory.NETWORK

    def test_timeout_error_is_network(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(TimeoutError("timed out")) == ErrorCategory.NETWORK

    def test_os_error_is_network(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(OSError("network down")) == ErrorCategory.NETWORK

    def test_sqlalchemy_error_is_database(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        # Simulate a SQLAlchemy-like error by using a class with the right module
        class FakeSAError(Exception):
            pass

        FakeSAError.__module__ = "sqlalchemy.exc"
        assert classify_error(FakeSAError("db error")) == ErrorCategory.DATABASE

    def test_value_error_is_validation(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(ValueError("bad input")) == ErrorCategory.VALIDATION

    def test_type_error_is_validation(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(TypeError("wrong type")) == ErrorCategory.VALIDATION

    def test_key_error_is_validation(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(KeyError("missing")) == ErrorCategory.VALIDATION

    def test_permission_error_is_auth(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(PermissionError("denied")) == ErrorCategory.AUTH

    def test_generic_exception_is_internal(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        assert classify_error(RuntimeError("oops")) == ErrorCategory.INTERNAL

    def test_unknown_exception_is_internal(self):
        from src.utils.error_reporting import ErrorCategory, classify_error

        class CustomError(Exception):
            pass

        assert classify_error(CustomError("wat")) == ErrorCategory.INTERNAL


class TestErrorCounter:
    """Slice 2: In-memory error counter by category."""

    def test_initial_counts_are_zero(self):
        from src.utils.error_reporting import ErrorCounter

        counter = ErrorCounter()
        counts = counter.get_counts()
        assert all(v == 0 for v in counts.values())

    def test_increment_tracks_category(self):
        from src.utils.error_reporting import ErrorCategory, ErrorCounter

        counter = ErrorCounter()
        counter.increment(ErrorCategory.NETWORK)
        counter.increment(ErrorCategory.NETWORK)
        counter.increment(ErrorCategory.DATABASE)
        counts = counter.get_counts()
        assert counts[ErrorCategory.NETWORK] == 2
        assert counts[ErrorCategory.DATABASE] == 1

    def test_reset_clears_all(self):
        from src.utils.error_reporting import ErrorCategory, ErrorCounter

        counter = ErrorCounter()
        counter.increment(ErrorCategory.NETWORK)
        counter.reset()
        counts = counter.get_counts()
        assert counts[ErrorCategory.NETWORK] == 0

    def test_get_total(self):
        from src.utils.error_reporting import ErrorCategory, ErrorCounter

        counter = ErrorCounter()
        counter.increment(ErrorCategory.NETWORK)
        counter.increment(ErrorCategory.DATABASE)
        counter.increment(ErrorCategory.INTERNAL)
        assert counter.get_total() == 3

    def test_global_counter_is_singleton(self):
        from src.utils.error_reporting import get_error_counter

        c1 = get_error_counter()
        c2 = get_error_counter()
        assert c1 is c2


class TestUserErrorMessages:
    """Slice 3: User-friendly error messages (no tracebacks)."""

    def test_network_message(self):
        from src.utils.error_reporting import ErrorCategory, format_user_error_message

        msg = format_user_error_message(ErrorCategory.NETWORK, "upload_photo")
        assert "network" in msg.lower() or "connection" in msg.lower()
        assert "traceback" not in msg.lower()
        assert "Traceback" not in msg

    def test_database_message(self):
        from src.utils.error_reporting import ErrorCategory, format_user_error_message

        msg = format_user_error_message(ErrorCategory.DATABASE, "save_note")
        assert "database" in msg.lower() or "storage" in msg.lower()

    def test_validation_message(self):
        from src.utils.error_reporting import ErrorCategory, format_user_error_message

        msg = format_user_error_message(ErrorCategory.VALIDATION, "set_timer")
        assert "invalid" in msg.lower() or "input" in msg.lower()

    def test_internal_message_is_generic(self):
        from src.utils.error_reporting import ErrorCategory, format_user_error_message

        msg = format_user_error_message(ErrorCategory.INTERNAL, "process")
        assert "error" in msg.lower()
        # Should NOT contain the handler name in user message
        assert "process" not in msg.lower() or "processing" in msg.lower()


class TestHandleErrorsDecorator:
    """Slice 4: @handle_errors decorator wraps async handlers."""

    @pytest.fixture(autouse=True)
    def reset_counter(self):
        from src.utils.error_reporting import get_error_counter

        get_error_counter().reset()

    def test_successful_handler_runs_normally(self):
        from src.utils.error_reporting import handle_errors

        @handle_errors("test_handler")
        async def my_handler(update, context):
            return "ok"

        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        result = asyncio.get_event_loop().run_until_complete(
            my_handler(update, context)
        )
        assert result == "ok"

    def test_failing_handler_catches_exception(self):
        from src.utils.error_reporting import handle_errors

        @handle_errors("test_handler")
        async def bad_handler(update, context):
            raise ConnectionError("network down")

        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        # Should not raise
        asyncio.get_event_loop().run_until_complete(bad_handler(update, context))

    def test_failing_handler_increments_counter(self):
        from src.utils.error_reporting import (
            ErrorCategory,
            get_error_counter,
            handle_errors,
        )

        @handle_errors("test_handler")
        async def bad_handler(update, context):
            raise ConnectionError("network down")

        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        asyncio.get_event_loop().run_until_complete(bad_handler(update, context))
        counts = get_error_counter().get_counts()
        assert counts[ErrorCategory.NETWORK] == 1

    def test_failing_handler_logs_structured_context(self, caplog):
        from src.utils.error_reporting import handle_errors

        @handle_errors("test_handler")
        async def bad_handler(update, context):
            raise RuntimeError("oops")

        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 123
        update.effective_user = MagicMock()
        update.effective_user.id = 456
        context = MagicMock()

        with caplog.at_level(logging.ERROR):
            asyncio.get_event_loop().run_until_complete(bad_handler(update, context))

        assert any("test_handler" in r.message for r in caplog.records)
        assert any("internal" in r.message.lower() for r in caplog.records)

    def test_failing_handler_sends_user_message(self):
        from src.utils.error_reporting import handle_errors

        @handle_errors("test_handler")
        async def bad_handler(update, context):
            raise ConnectionError("network down")

        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()

        with patch("src.utils.error_reporting.send_message_sync") as mock_send:
            asyncio.get_event_loop().run_until_complete(bad_handler(update, context))
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["chat_id"] == 123 or call_args[0][0] == 123
