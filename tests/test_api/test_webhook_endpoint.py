"""Tests for Telegram webhook endpoint stability behavior."""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWebhookEndpoint:
    """Tests for /webhook endpoint behavior."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        with (
            patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": ""}),
            patch("src.main.initialize_bot", new_callable=AsyncMock),
            patch("src.main.shutdown_bot", new_callable=AsyncMock),
            patch("src.main.init_database", new_callable=AsyncMock),
            patch("src.main.close_database", new_callable=AsyncMock),
            patch("src.main.setup_services"),
            patch("src.main.get_plugin_manager") as mock_pm,
            patch("src.main.get_bot") as mock_get_bot,
            patch("src.main.create_tracked_task") as mock_create_task,
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

            mock_create_task.side_effect = close_coro

            from fastapi.testclient import TestClient

            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.fixture(autouse=True)
    def reset_webhook_state(self):
        """Reset global webhook tracking to avoid cross-test contamination."""
        from src import main

        main._processed_updates.clear()
        main._processing_updates.clear()
        yield
        main._processed_updates.clear()
        main._processing_updates.clear()

    def test_webhook_rejects_invalid_secret(self, client):
        """Invalid secret token should return 401."""
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "expected"}):
            response = client.post(
                "/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
                json={"update_id": 1},
            )

        assert response.status_code == 401

    def test_webhook_missing_update_id_returns_400(self, client):
        """Missing update_id should return 400."""
        response = client.post("/webhook", json={"message": {"text": "hi"}})

        assert response.status_code == 400
        assert "Missing update_id" in response.json().get("detail", "")

    def test_webhook_duplicate_returns_note(self, client):
        """Duplicate update_id should short-circuit with note."""
        from src import main

        main._processed_updates[123] = time.time()

        response = client.post("/webhook", json={"update_id": 123})

        assert response.status_code == 200
        assert response.json().get("note") == "duplicate"

    def test_webhook_in_progress_returns_note(self, client):
        """In-progress update_id should short-circuit with note."""
        from src import main

        main._processing_updates.add(124)

        response = client.post("/webhook", json={"update_id": 124})

        assert response.status_code == 200
        assert response.json().get("note") == "in_progress"

    def test_webhook_enqueues_background_task(self, client):
        """New update should enqueue background processing."""
        from src import main

        response = client.post("/webhook", json={"update_id": 125})

        assert response.status_code == 200
        assert 125 in main._processing_updates

    def test_webhook_cleanup_expired_updates(self, client):
        """Expired updates should be removed during dedupe checks."""
        from src import main

        original_max = main.MAX_TRACKED_UPDATES
        try:
            main.MAX_TRACKED_UPDATES = 1
            main._processed_updates[1] = 0.0
            main._processed_updates[2] = time.time()

            response = client.post("/webhook", json={"update_id": 126})

            assert response.status_code == 200
            assert 1 not in main._processed_updates
            assert 2 in main._processed_updates
        finally:
            main.MAX_TRACKED_UPDATES = original_max

    def test_webhook_trims_excess_updates(self, client):
        """Processed updates should be trimmed to MAX_TRACKED_UPDATES."""
        from src import main

        original_max = main.MAX_TRACKED_UPDATES
        try:
            main.MAX_TRACKED_UPDATES = 2
            main._processed_updates[1] = time.time()
            main._processed_updates[2] = time.time()
            main._processed_updates[3] = time.time()

            response = client.post("/webhook", json={"update_id": 127})

            assert response.status_code == 200
            assert len(main._processed_updates) <= 2
            assert 1 not in main._processed_updates
        finally:
            main.MAX_TRACKED_UPDATES = original_max
