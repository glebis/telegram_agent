"""
Tests for config validation and production DB enforcement.

Covers:
- Required secret presence checks
- DATABASE_URL format validation
- WEBHOOK_BASE_URL format validation
- SQLite-in-production rejection
- Redacted config summary output
"""

import logging

from src.core.config import Settings

# ---------------------------------------------------------------------------
# Helper: build a Settings object with explicit overrides
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> Settings:
    """Create a Settings instance with sensible test defaults, applying overrides."""
    defaults = {
        "telegram_bot_token": "123456:ABC-DEF",
        "telegram_webhook_secret": "webhooksecret123",
        "database_url": "sqlite+aiosqlite:///./data/test.db",
        "environment": "development",
        "tunnel_provider": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)


# ===========================================================================
# Required secrets
# ===========================================================================


class TestRequiredSecrets:
    """validate_config must flag missing required secrets."""

    def test_missing_bot_token(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(telegram_bot_token="")
        errors = validate_config(settings)
        assert any("TELEGRAM_BOT_TOKEN" in e for e in errors)

    def test_missing_webhook_secret(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(telegram_webhook_secret="")
        errors = validate_config(settings)
        assert any("TELEGRAM_WEBHOOK_SECRET" in e for e in errors)

    def test_both_secrets_present(self):
        from src.core.config_validator import validate_config

        settings = _make_settings()
        errors = validate_config(settings)
        assert not any("TELEGRAM_BOT_TOKEN" in e for e in errors)
        assert not any("TELEGRAM_WEBHOOK_SECRET" in e for e in errors)


# ===========================================================================
# DATABASE_URL format
# ===========================================================================


class TestDatabaseUrlValidation:
    """DATABASE_URL must look like a valid SQLAlchemy connection string."""

    def test_valid_sqlite_url(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(database_url="sqlite+aiosqlite:///./data/app.db")
        errors = validate_config(settings)
        assert not any("DATABASE_URL" in e for e in errors)

    def test_valid_postgresql_url(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(
            database_url="postgresql+asyncpg://user:pass@host:5432/db"
        )
        errors = validate_config(settings)
        assert not any("DATABASE_URL" in e for e in errors)

    def test_invalid_database_url_no_scheme(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(database_url="just-a-string-no-colon-slash")
        errors = validate_config(settings)
        assert any("DATABASE_URL" in e for e in errors)

    def test_empty_database_url(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(database_url="")
        errors = validate_config(settings)
        assert any("DATABASE_URL" in e for e in errors)


# ===========================================================================
# WEBHOOK_BASE_URL format
# ===========================================================================


class TestWebhookBaseUrlValidation:
    """WEBHOOK_BASE_URL, when set, must be a valid http(s) URL."""

    def test_valid_https_url(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(telegram_webhook_url="https://example.com")
        errors = validate_config(settings)
        assert not any("WEBHOOK" in e and "URL format" in e for e in errors)

    def test_valid_http_url(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(telegram_webhook_url="http://localhost:8000")
        errors = validate_config(settings)
        assert not any("WEBHOOK" in e and "URL format" in e for e in errors)

    def test_invalid_webhook_url(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(telegram_webhook_url="not-a-url")
        errors = validate_config(settings)
        assert any("TELEGRAM_WEBHOOK_URL" in e for e in errors)

    def test_none_webhook_url_is_ok(self):
        """Not setting WEBHOOK_BASE_URL should produce no URL-format error."""
        from src.core.config_validator import validate_config

        settings = _make_settings(telegram_webhook_url=None)
        errors = validate_config(settings)
        assert not any("WEBHOOK" in e and "URL format" in e for e in errors)


# ===========================================================================
# Production DB enforcement (SQLite forbidden in prod)
# ===========================================================================


class TestProductionDbEnforcement:
    """In production, DATABASE_URL must start with 'postgresql'."""

    def test_sqlite_rejected_in_production(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(
            environment="production",
            database_url="sqlite+aiosqlite:///./data/prod.db",
        )
        errors = validate_config(settings)
        assert any("production" in e.lower() and "sqlite" in e.lower() for e in errors)

    def test_postgresql_accepted_in_production(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@host:5432/db",
        )
        errors = validate_config(settings)
        assert not any(
            "production" in e.lower() and "sqlite" in e.lower() for e in errors
        )

    def test_sqlite_allowed_in_development(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(
            environment="development",
            database_url="sqlite+aiosqlite:///./data/dev.db",
        )
        errors = validate_config(settings)
        assert not any(
            "production" in e.lower() and "sqlite" in e.lower() for e in errors
        )

    def test_sqlite_allowed_in_testing(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(
            environment="testing",
            database_url="sqlite+aiosqlite:///./data/test.db",
        )
        errors = validate_config(settings)
        assert not any(
            "production" in e.lower() and "sqlite" in e.lower() for e in errors
        )


# ===========================================================================
# Redacted config summary
# ===========================================================================


class TestRedactedConfigSummary:
    """log_config_summary must log a single INFO line with secrets redacted."""

    def test_secrets_are_redacted(self, caplog):
        from src.core.config_validator import log_config_summary

        settings = _make_settings(
            telegram_bot_token="123456:ABC-DEF1234567890",
            telegram_webhook_secret="supersecretvalue",
            anthropic_api_key="sk-ant-1234567890",
        )
        with caplog.at_level(logging.INFO, logger="src.core.config_validator"):
            log_config_summary(settings)

        log_text = caplog.text

        # Full secrets must NOT appear
        assert "123456:ABC-DEF1234567890" not in log_text
        assert "supersecretvalue" not in log_text
        assert "sk-ant-1234567890" not in log_text

        # Redacted prefixes (first 4 chars + ***) SHOULD appear
        assert "1234***" in log_text
        assert "supe***" in log_text
        assert "sk-a***" in log_text

    def test_summary_contains_environment(self, caplog):
        from src.core.config_validator import log_config_summary

        settings = _make_settings(environment="staging")
        with caplog.at_level(logging.INFO, logger="src.core.config_validator"):
            log_config_summary(settings)

        assert "staging" in caplog.text

    def test_summary_contains_database_type(self, caplog):
        from src.core.config_validator import log_config_summary

        settings = _make_settings(database_url="sqlite+aiosqlite:///./data/app.db")
        with caplog.at_level(logging.INFO, logger="src.core.config_validator"):
            log_config_summary(settings)

        assert "sqlite" in caplog.text.lower()

    def test_summary_contains_tunnel_provider(self, caplog):
        from src.core.config_validator import log_config_summary

        settings = _make_settings(tunnel_provider="cloudflare")
        with caplog.at_level(logging.INFO, logger="src.core.config_validator"):
            log_config_summary(settings)

        assert "cloudflare" in caplog.text

    def test_summary_none_tunnel_shows_none(self, caplog):
        from src.core.config_validator import log_config_summary

        settings = _make_settings(tunnel_provider=None)
        with caplog.at_level(logging.INFO, logger="src.core.config_validator"):
            log_config_summary(settings)

        # Should say "none" or similar for no tunnel
        assert "none" in caplog.text.lower()


# ===========================================================================
# validate_config returns empty list on fully valid config
# ===========================================================================


class TestValidConfigPassesClean:
    """A fully valid config should produce zero errors."""

    def test_valid_dev_config(self):
        from src.core.config_validator import validate_config

        settings = _make_settings()
        errors = validate_config(settings)
        assert errors == []

    def test_valid_prod_config(self):
        from src.core.config_validator import validate_config

        settings = _make_settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@host:5432/db",
        )
        errors = validate_config(settings)
        assert errors == []
