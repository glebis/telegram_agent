"""Tests for centralized API key derivation (src/core/security.py).

Covers:
- HMAC-SHA256 derivation with dedicated API_SECRET_KEY
- Legacy fallback to TELEGRAM_WEBHOOK_SECRET with deprecation warning
- ValueError when neither secret is configured
- Key isolation: different purposes produce different keys
"""

import hashlib
import hmac
import logging
import os
from unittest.mock import patch

import pytest

# Ensure minimal env for test imports
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test_webhook_secret_12345")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:bot_token")


class TestDeriveApiKeyWithDedicatedSecret:
    """Tests for the preferred HMAC-SHA256 path (API_SECRET_KEY set)."""

    def setup_method(self):
        from src.core.security import reset_legacy_warning

        reset_legacy_warning()

    def test_hmac_sha256_derivation(self):
        """derive_api_key uses HMAC-SHA256 when API_SECRET_KEY is set."""
        from src.core.security import derive_api_key

        secret = "my_dedicated_secret"
        with patch.dict(os.environ, {"API_SECRET_KEY": secret}):
            key = derive_api_key("admin_api")

        expected = hmac.new(secret.encode(), b"admin_api", hashlib.sha256).hexdigest()
        assert key == expected
        assert len(key) == 64  # SHA-256 hex digest length

    def test_different_purposes_produce_different_keys(self):
        """Different purpose labels produce distinct keys."""
        from src.core.security import derive_api_key

        secret = "my_dedicated_secret"
        with patch.dict(os.environ, {"API_SECRET_KEY": secret}):
            admin_key = derive_api_key("admin_api")
            messaging_key = derive_api_key("messaging_api")

        assert admin_key != messaging_key

    def test_no_deprecation_warning_with_dedicated_secret(self, caplog):
        """No deprecation warning when API_SECRET_KEY is set."""
        from src.core.security import derive_api_key

        with patch.dict(os.environ, {"API_SECRET_KEY": "some_secret"}):
            with caplog.at_level(logging.WARNING, logger="src.core.security"):
                derive_api_key("admin_api")

        assert "falling back" not in caplog.text.lower()

    def test_dedicated_secret_differs_from_legacy_output(self):
        """HMAC path produces a different key than legacy SHA-256 path."""
        from src.core.security import derive_api_key

        webhook_secret = "shared_secret"
        api_secret = "shared_secret"  # same value, different algorithm

        # Legacy output
        legacy_key = hashlib.sha256(f"{webhook_secret}:admin_api".encode()).hexdigest()

        # HMAC output
        with patch.dict(
            os.environ,
            {"API_SECRET_KEY": api_secret, "TELEGRAM_WEBHOOK_SECRET": webhook_secret},
        ):
            hmac_key = derive_api_key("admin_api")

        assert hmac_key != legacy_key


class TestDeriveApiKeyLegacyFallback:
    """Tests for the legacy fallback path (no API_SECRET_KEY)."""

    def setup_method(self):
        from src.core.security import reset_legacy_warning

        reset_legacy_warning()

    def test_legacy_sha256_derivation(self):
        """Falls back to salted SHA-256 when API_SECRET_KEY is absent."""
        from src.core.security import derive_api_key

        webhook_secret = "test_webhook_secret_12345"
        with patch.dict(
            os.environ, {"TELEGRAM_WEBHOOK_SECRET": webhook_secret}, clear=False
        ):
            os.environ.pop("API_SECRET_KEY", None)
            key = derive_api_key("admin_api")

        expected = hashlib.sha256(f"{webhook_secret}:admin_api".encode()).hexdigest()
        assert key == expected
        assert len(key) == 64

    def test_backward_compat_admin_key(self):
        """Legacy admin key matches the old derivation exactly."""
        from src.core.security import derive_api_key

        secret = "test_secret"
        old_key = hashlib.sha256(f"{secret}:admin_api".encode()).hexdigest()

        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": secret}, clear=False):
            os.environ.pop("API_SECRET_KEY", None)
            new_key = derive_api_key("admin_api")

        assert new_key == old_key

    def test_backward_compat_messaging_key(self):
        """Legacy messaging key matches the old derivation exactly."""
        from src.core.security import derive_api_key

        secret = "test_secret"
        old_key = hashlib.sha256(f"{secret}:messaging_api".encode()).hexdigest()

        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": secret}, clear=False):
            os.environ.pop("API_SECRET_KEY", None)
            new_key = derive_api_key("messaging_api")

        assert new_key == old_key

    def test_deprecation_warning_logged_on_fallback(self, caplog):
        """A deprecation warning is logged once when using the legacy path."""
        from src.core.security import derive_api_key

        with patch.dict(
            os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test_secret"}, clear=False
        ):
            os.environ.pop("API_SECRET_KEY", None)
            with caplog.at_level(logging.WARNING, logger="src.core.security"):
                derive_api_key("admin_api")

        assert "API_SECRET_KEY is not set" in caplog.text
        assert "falling back" in caplog.text.lower()

    def test_deprecation_warning_logged_only_once(self, caplog):
        """The fallback warning fires only once, not on every call."""
        from src.core.security import derive_api_key, reset_legacy_warning

        reset_legacy_warning()

        with patch.dict(
            os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test_secret"}, clear=False
        ):
            os.environ.pop("API_SECRET_KEY", None)
            with caplog.at_level(logging.WARNING, logger="src.core.security"):
                derive_api_key("admin_api")
                derive_api_key("messaging_api")

        # Should appear exactly once
        count = caplog.text.count("API_SECRET_KEY is not set")
        assert count == 1


class TestDeriveApiKeyNoSecret:
    """Tests for the error case when no secret is configured at all."""

    def setup_method(self):
        from src.core.security import reset_legacy_warning

        reset_legacy_warning()

    def test_raises_when_no_secrets_configured(self):
        """ValueError raised when neither secret is available."""
        from src.core.security import derive_api_key

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("API_SECRET_KEY", None)
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            # Patch get_settings to return empty secrets (fallback path)
            with patch("src.core.config.get_settings") as mock_settings:
                mock_settings.return_value.api_secret_key = None
                mock_settings.return_value.telegram_webhook_secret = None
                with pytest.raises(ValueError):
                    derive_api_key("admin_api")

    def test_raises_with_empty_purpose(self):
        """ValueError raised for empty purpose string."""
        from src.core.security import derive_api_key

        with pytest.raises(ValueError, match="purpose must be a non-empty"):
            derive_api_key("")


class TestResetLegacyWarning:
    """Tests for the test helper reset_legacy_warning()."""

    def test_reset_allows_warning_again(self, caplog):
        """After reset, the deprecation warning fires again."""
        from src.core.security import derive_api_key, reset_legacy_warning

        reset_legacy_warning()
        with patch.dict(
            os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test_secret"}, clear=False
        ):
            os.environ.pop("API_SECRET_KEY", None)
            with caplog.at_level(logging.WARNING, logger="src.core.security"):
                derive_api_key("admin_api")
            first_count = caplog.text.count("API_SECRET_KEY is not set")

        reset_legacy_warning()
        with patch.dict(
            os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test_secret"}, clear=False
        ):
            os.environ.pop("API_SECRET_KEY", None)
            with caplog.at_level(logging.WARNING, logger="src.core.security"):
                derive_api_key("admin_api")
            second_count = caplog.text.count("API_SECRET_KEY is not set")

        assert first_count == 1
        assert second_count == 2  # One more after reset
