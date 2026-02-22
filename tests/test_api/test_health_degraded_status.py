"""Tests for enriched bot_status in health endpoints when bot is degraded.

These tests verify that the health endpoint and build_enriched_health()
report granular bot initialization state (retrying, initializing, ok)
instead of just a boolean bot_initialized flag.

TDD RED phase: all tests should FAIL until src/api/health.py is updated
to read from _bot_init_state and include bot_status / last_error fields.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lifecycle import BotInitState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_init_state(state: str, last_error: str | None = None) -> BotInitState:
    """Create a BotInitState in the given state."""
    obj = BotInitState()
    if state == "initializing":
        obj.set_initializing()
    elif state == "initialized":
        obj.set_initialized()
    elif state == "failed":
        obj.set_failed(last_error or "something broke")
    return obj


# ---------------------------------------------------------------------------
# Unit tests: build_enriched_health()
# ---------------------------------------------------------------------------


class TestEnrichedHealthBotStatus:
    """build_enriched_health() should include bot_status from _bot_init_state."""

    async def test_enriched_health_includes_bot_status(self):
        """build_enriched_health() result must contain a 'bot_status' key."""
        from src.api.health import build_enriched_health

        state = _make_init_state("initialized")

        with (
            patch(
                "src.api.health.check_database_health",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.health._is_bot_initialized", return_value=True),
            patch("src.lifecycle._bot_init_state", state),
        ):
            result = await build_enriched_health()

        assert (
            "bot_status" in result
        ), "build_enriched_health() must include 'bot_status' field"

    async def test_enriched_health_bot_status_ok_when_initialized(self):
        """When bot is fully initialized, bot_status should be 'ok'."""
        from src.api.health import build_enriched_health

        state = _make_init_state("initialized")

        with (
            patch(
                "src.api.health.check_database_health",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.health._is_bot_initialized", return_value=True),
            patch("src.lifecycle._bot_init_state", state),
        ):
            result = await build_enriched_health()

        assert result["bot_status"] == "ok"
        assert result.get("last_error") is None

    async def test_enriched_health_bot_status_retrying_when_failed(self):
        """When bot init failed (retry active), bot_status should be 'retrying'."""
        from src.api.health import build_enriched_health

        state = _make_init_state("failed", last_error="Connection refused")

        with (
            patch(
                "src.api.health.check_database_health",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.health._is_bot_initialized", return_value=False),
            patch("src.lifecycle._bot_init_state", state),
        ):
            result = await build_enriched_health()

        assert result["bot_status"] == "retrying"

    async def test_enriched_health_bot_status_initializing(self):
        """When bot init is in progress, bot_status should be 'initializing'."""
        from src.api.health import build_enriched_health

        state = _make_init_state("initializing")

        with (
            patch(
                "src.api.health.check_database_health",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.health._is_bot_initialized", return_value=False),
            patch("src.lifecycle._bot_init_state", state),
        ):
            result = await build_enriched_health()

        assert result["bot_status"] == "initializing"

    async def test_enriched_health_includes_last_error_when_failed(self):
        """When state is 'failed', the payload must include 'last_error'."""
        from src.api.health import build_enriched_health

        state = _make_init_state("failed", last_error="Telegram API 502")

        with (
            patch(
                "src.api.health.check_database_health",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.health._is_bot_initialized", return_value=False),
            patch("src.lifecycle._bot_init_state", state),
        ):
            result = await build_enriched_health()

        assert result.get("last_error") == "Telegram API 502"


# ---------------------------------------------------------------------------
# Integration tests: /health HTTP endpoint (from main.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def _app_client():
    """Create a TestClient against the real FastAPI app with mocked lifecycle."""
    with (
        patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": ""}),
        patch("src.lifecycle.validate_config", return_value=[]),
        patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
        patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
        patch("src.lifecycle.init_database", new_callable=AsyncMock),
        patch("src.lifecycle.close_database", new_callable=AsyncMock),
        patch("src.lifecycle.setup_services"),
        patch("src.lifecycle.get_plugin_manager") as mock_pm,
        patch("src.api.webhook_handler.get_bot") as mock_get_bot,
        patch("src.lifecycle.create_tracked_task") as mock_task,
        patch(
            "src.utils.ngrok_utils.check_and_recover_webhook",
            new_callable=AsyncMock,
        ),
        patch(
            "src.utils.ngrok_utils.run_periodic_webhook_check",
            new_callable=AsyncMock,
        ),
        patch("src.utils.cleanup.run_periodic_cleanup", new_callable=AsyncMock),
    ):
        mock_pm_instance = MagicMock()
        mock_pm_instance.load_plugins = AsyncMock(return_value={})
        mock_pm_instance.activate_plugins = AsyncMock()
        mock_pm_instance.shutdown = AsyncMock()
        mock_pm.return_value = mock_pm_instance

        mock_bot = MagicMock()
        mock_bot.process_update = AsyncMock(return_value=True)
        mock_get_bot.return_value = mock_bot

        def close_coro(coro, name=None):
            coro.close()
            return None

        mock_task.side_effect = close_coro

        from fastapi.testclient import TestClient

        from src.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestHealthEndpointBotStatus:
    """The /health endpoint should expose bot_status from _bot_init_state."""

    def test_health_endpoint_returns_bot_status_retrying(self, _app_client):
        """When bot init failed with retry active, response has bot_status='retrying'."""
        state = _make_init_state("failed", last_error="Connection refused")

        with (
            patch("src.lifecycle._bot_init_state", state),
            patch("src.lifecycle._bot_fully_initialized", False),
        ):
            response = _app_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert (
            data.get("bot_status") == "retrying"
        ), f"Expected bot_status='retrying', got {data}"

    def test_health_endpoint_returns_last_error(self, _app_client):
        """When state is 'failed', response includes last_error with the message."""
        state = _make_init_state("failed", last_error="Telegram API timeout")

        with (
            patch("src.lifecycle._bot_init_state", state),
            patch("src.lifecycle._bot_fully_initialized", False),
        ):
            response = _app_client.get("/health")

        data = response.json()
        assert (
            data.get("last_error") == "Telegram API timeout"
        ), f"Expected last_error in response, got {data}"

    def test_health_endpoint_returns_bot_status_initializing(self, _app_client):
        """When bot init is in progress, response has bot_status='initializing'."""
        state = _make_init_state("initializing")

        with (
            patch("src.lifecycle._bot_init_state", state),
            patch("src.lifecycle._bot_fully_initialized", False),
        ):
            response = _app_client.get("/health")

        data = response.json()
        assert (
            data.get("bot_status") == "initializing"
        ), f"Expected bot_status='initializing', got {data}"

    def test_health_endpoint_returns_bot_status_ok_when_initialized(self, _app_client):
        """When bot is fully initialized, bot_status='ok' and no last_error."""
        state = _make_init_state("initialized")

        with (
            patch("src.lifecycle._bot_init_state", state),
            patch("src.lifecycle._bot_fully_initialized", True),
        ):
            response = _app_client.get("/health")

        data = response.json()
        assert data.get("bot_status") == "ok", f"Expected bot_status='ok', got {data}"
        assert "last_error" not in data or data["last_error"] is None

    def test_health_endpoint_still_returns_200_when_degraded(self, _app_client):
        """Health endpoint must return HTTP 200 even in degraded mode.

        Monitoring tools typically treat 5xx as 'down'. A degraded bot
        should still report 200 so alerting is based on the JSON payload,
        not the HTTP status code.
        """
        state = _make_init_state("failed", last_error="init exploded")

        with (
            patch("src.lifecycle._bot_init_state", state),
            patch("src.lifecycle._bot_fully_initialized", False),
        ):
            response = _app_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
