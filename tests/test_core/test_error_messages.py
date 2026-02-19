"""
Tests for error message sanitization.

Ensures raw exception details never leak to Telegram users.
"""

import pytest


class TestSanitizeError:
    """Test that sanitize_error() maps exceptions to friendly messages."""

    def test_returns_string(self):
        """sanitize_error should always return a string."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(ValueError("anything"))
        assert isinstance(result, str)

    def test_never_leaks_raw_exception_message(self):
        """Raw exception text like file paths must not appear in output."""
        from src.core.error_messages import sanitize_error

        secret = "/etc/secrets/api_key.json"
        result = sanitize_error(ValueError(secret))
        assert secret not in result

    def test_never_leaks_traceback_info(self):
        """Stack trace fragments must not appear in output."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(
            RuntimeError("Traceback (most recent call last): File /app/main.py")
        )
        assert "/app/main.py" not in result
        assert "Traceback" not in result

    def test_maps_connection_error(self):
        """ConnectionError should produce a connectivity-related message."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(ConnectionError("Failed to connect to 10.0.0.1:5432"))
        assert "10.0.0.1" not in result
        assert "connection" in result.lower() or "service" in result.lower()

    def test_maps_timeout_error(self):
        """TimeoutError should produce a timeout-related message."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(TimeoutError("Read timed out after 30s"))
        assert "30s" not in result
        assert "timeout" in result.lower() or "too long" in result.lower()

    def test_maps_permission_error(self):
        """PermissionError should produce a generic message, not expose paths."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(
            PermissionError("[Errno 13] Permission denied: '/var/data/db.sqlite'")
        )
        assert "/var/data" not in result
        assert "Errno 13" not in result

    def test_maps_file_not_found_error(self):
        """FileNotFoundError should produce a generic not-found message."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(
            FileNotFoundError("[Errno 2] No such file: '/secret/path/data.json'")
        )
        assert "/secret/path" not in result

    def test_maps_value_error(self):
        """ValueError should produce a generic message."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(ValueError("invalid literal for int(): 'abc'"))
        assert "invalid literal" not in result

    def test_maps_key_error(self):
        """KeyError should produce a generic message, not the key name."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(KeyError("secret_api_token"))
        assert "secret_api_token" not in result

    def test_maps_generic_exception(self):
        """Unknown exception types should produce a safe fallback message."""
        from src.core.error_messages import sanitize_error

        class CustomInternalError(Exception):
            pass

        result = sanitize_error(
            CustomInternalError("internal detail: database schema mismatch v3->v4")
        )
        assert "schema mismatch" not in result
        assert "v3->v4" not in result

    def test_default_message_is_user_friendly(self):
        """The fallback message should be polite and actionable."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(Exception("anything"))
        assert "sorry" in result.lower() or "try again" in result.lower()

    def test_none_exception_returns_fallback(self):
        """Passing None should not crash, returns fallback."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_rate_limit_detection(self):
        """Exceptions with 'rate limit' in message get appropriate response."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(Exception("rate limit exceeded for user 12345"))
        assert "12345" not in result
        assert "rate" in result.lower() or "wait" in result.lower() or "try again" in result.lower()

    def test_authentication_error_detection(self):
        """Exceptions mentioning auth/api_key get appropriate response."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(
            Exception("AuthenticationError: invalid api_key sk-abc123xyz")
        )
        assert "sk-abc123xyz" not in result
        assert "api_key" not in result.lower() or "configuration" in result.lower()

    def test_database_error_detection(self):
        """Database-related errors get a service message."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(
            Exception("(sqlite3.OperationalError) database is locked")
        )
        assert "database is locked" not in result.lower()


class TestSanitizeErrorForContext:
    """Test context-specific error message formatting."""

    def test_with_context_prefix(self):
        """sanitize_error with context should include the context description."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(
            TimeoutError("connection timed out"),
            context="processing your image",
        )
        assert "image" in result.lower()

    def test_context_does_not_leak_exception(self):
        """Even with context, raw exception must not leak."""
        from src.core.error_messages import sanitize_error

        result = sanitize_error(
            ValueError("/Users/admin/.ssh/id_rsa"),
            context="reading file",
        )
        assert "/Users/admin" not in result
        assert "id_rsa" not in result
