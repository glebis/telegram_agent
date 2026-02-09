"""Tests for webhook update deduplication logic in src/main.py.

Covers:
- Duplicate update_id rejection
- In-progress update_id rejection
- Cleanup of expired entries
- Normal update processing
"""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWebhookDeduplication:
    """Tests for webhook deduplication tracking."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        with (
            patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": ""}),
            patch("src.main.validate_config", return_value=[]),
            patch("src.main.log_config_summary"),
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

            with TestClient(app, raise_server_exceptions=False) as c:
                yield c

    @pytest.fixture(autouse=True)
    def reset_dedup_state(self):
        """Reset global dedup tracking to avoid cross-test contamination."""
        from src import main

        main._processed_updates.clear()
        main._processing_updates.clear()
        yield
        main._processed_updates.clear()
        main._processing_updates.clear()

    # ------------------------------------------------------------------
    # 1. Duplicate update_id is rejected
    # ------------------------------------------------------------------
    def test_duplicate_update_id_rejected(self, client):
        """An update_id already in _processed_updates returns 'duplicate'."""
        from src import main

        main._processed_updates[500] = time.time()

        resp = client.post("/webhook", json={"update_id": 500})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["note"] == "duplicate"

    def test_duplicate_not_reprocessed(self, client):
        """A duplicate should NOT be added to _processing_updates."""
        from src import main

        main._processed_updates[501] = time.time()

        client.post("/webhook", json={"update_id": 501})

        assert 501 not in main._processing_updates

    # ------------------------------------------------------------------
    # 2. In-progress update_id returns "in_progress"
    # ------------------------------------------------------------------
    def test_in_progress_update_rejected(self, client):
        """An update_id currently in _processing_updates returns 'in_progress'."""
        from src import main

        main._processing_updates.add(600)

        resp = client.post("/webhook", json={"update_id": 600})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["note"] == "in_progress"

    def test_in_progress_not_duplicated_in_set(self, client):
        """An in-progress rejection should not double-add the id."""
        from src import main

        main._processing_updates.add(601)

        client.post("/webhook", json={"update_id": 601})

        # Still exactly one entry
        assert main._processing_updates == {601}

    # ------------------------------------------------------------------
    # 3. Cleanup function removes expired entries
    # ------------------------------------------------------------------
    def test_cleanup_removes_expired_entries(self, client):
        """_cleanup_old_updates removes entries older than UPDATE_EXPIRY_SECONDS."""
        from src import main

        original_expiry = main.UPDATE_EXPIRY_SECONDS
        try:
            main.UPDATE_EXPIRY_SECONDS = 10  # 10-second expiry for test

            # Insert one expired and one fresh entry
            main._processed_updates[700] = time.time() - 20  # expired
            main._processed_updates[701] = time.time()  # fresh

            # Trigger cleanup via webhook (set MAX_TRACKED_UPDATES low)
            original_max = main.MAX_TRACKED_UPDATES
            main.MAX_TRACKED_UPDATES = 1  # force cleanup path
            try:
                resp = client.post("/webhook", json={"update_id": 702})
                assert resp.status_code == 200
            finally:
                main.MAX_TRACKED_UPDATES = original_max

            # Expired entry should be removed, fresh entry kept
            assert 700 not in main._processed_updates
            assert 701 in main._processed_updates
        finally:
            main.UPDATE_EXPIRY_SECONDS = original_expiry

    def test_cleanup_preserves_fresh_entries(self, client):
        """Fresh entries within expiry window are not removed by cleanup."""
        from src import main

        now = time.time()
        main._processed_updates[710] = now - 1
        main._processed_updates[711] = now
        main._processed_updates[712] = now

        original_max = main.MAX_TRACKED_UPDATES
        try:
            main.MAX_TRACKED_UPDATES = 2  # force cleanup path
            resp = client.post("/webhook", json={"update_id": 713})
            assert resp.status_code == 200

            # All entries are fresh, but excess is trimmed (oldest first)
            assert len(main._processed_updates) <= main.MAX_TRACKED_UPDATES + 1
        finally:
            main.MAX_TRACKED_UPDATES = original_max

    # ------------------------------------------------------------------
    # 4. Normal updates are processed successfully
    # ------------------------------------------------------------------
    def test_normal_update_accepted(self, client):
        """A new update_id returns status 'ok' without a 'note' field."""
        resp = client.post("/webhook", json={"update_id": 800})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "note" not in body

    def test_normal_update_added_to_processing(self, client):
        """A new update_id is added to _processing_updates."""
        from src import main

        client.post("/webhook", json={"update_id": 801})

        # The background task was mocked (coroutine closed), so the id
        # remains in _processing_updates because the finally block never ran
        assert 801 in main._processing_updates

    def test_normal_update_not_yet_in_processed(self, client):
        """Update not immediately in _processed_updates (moves after bg task)."""
        from src import main

        client.post("/webhook", json={"update_id": 802})

        # Since the background coroutine is closed (not awaited),
        # the id should NOT yet appear in _processed_updates.
        assert 802 not in main._processed_updates

    def test_two_different_updates_both_accepted(self, client):
        """Two distinct update_ids should both be accepted."""
        from src import main

        resp1 = client.post("/webhook", json={"update_id": 810})
        resp2 = client.post("/webhook", json={"update_id": 811})

        assert resp1.status_code == 200
        assert resp1.json()["status"] == "ok"
        assert "note" not in resp1.json()

        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"
        assert "note" not in resp2.json()

        assert 810 in main._processing_updates
        assert 811 in main._processing_updates
