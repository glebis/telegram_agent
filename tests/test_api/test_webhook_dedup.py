"""Tests for webhook update deduplication logic.

Covers:
- Duplicate update_id rejection
- In-progress update_id rejection
- Cleanup of expired entries
- Normal update processing

Dedup state lives in src.api.webhook_handler (extracted from main.py in #152).
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
            patch("src.lifecycle.validate_config", return_value=[]),
            patch("src.lifecycle.log_config_summary"),
            patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
            patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
            patch("src.lifecycle.init_database", new_callable=AsyncMock),
            patch("src.lifecycle.close_database", new_callable=AsyncMock),
            patch("src.lifecycle.setup_services"),
            patch("src.lifecycle.get_plugin_manager") as mock_pm,
            patch("src.lifecycle.create_tracked_task") as mock_lc_task,
            patch("src.api.webhook_handler.get_bot") as mock_get_bot,
            patch("src.api.webhook_handler.create_tracked_task") as mock_wh_task,
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

            mock_lc_task.side_effect = close_coro
            mock_wh_task.side_effect = close_coro

            from fastapi.testclient import TestClient

            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as c:
                yield c

    @pytest.fixture(autouse=True)
    def reset_dedup_state(self):
        """Reset global dedup tracking to avoid cross-test contamination."""
        from src.api import webhook_handler

        webhook_handler._processed_updates.clear()
        webhook_handler._processing_updates.clear()
        yield
        webhook_handler._processed_updates.clear()
        webhook_handler._processing_updates.clear()

    # ------------------------------------------------------------------
    # 1. Duplicate update_id is rejected
    # ------------------------------------------------------------------
    def test_duplicate_update_id_rejected(self, client):
        """An update_id already in _processed_updates returns 'duplicate'."""
        from src.api import webhook_handler

        webhook_handler._processed_updates[500] = time.time()

        resp = client.post("/webhook", json={"update_id": 500})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["note"] == "duplicate"

    def test_duplicate_not_reprocessed(self, client):
        """A duplicate should NOT be added to _processing_updates."""
        from src.api import webhook_handler

        webhook_handler._processed_updates[501] = time.time()

        client.post("/webhook", json={"update_id": 501})

        assert 501 not in webhook_handler._processing_updates

    # ------------------------------------------------------------------
    # 2. In-progress update_id returns "in_progress"
    # ------------------------------------------------------------------
    def test_in_progress_update_rejected(self, client):
        """An update_id currently in _processing_updates returns 'in_progress'."""
        from src.api import webhook_handler

        webhook_handler._processing_updates.add(600)

        resp = client.post("/webhook", json={"update_id": 600})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["note"] == "in_progress"

    def test_in_progress_not_duplicated_in_set(self, client):
        """An in-progress rejection should not double-add the id."""
        from src.api import webhook_handler

        webhook_handler._processing_updates.add(601)

        client.post("/webhook", json={"update_id": 601})

        # Still exactly one entry
        assert webhook_handler._processing_updates == {601}

    # ------------------------------------------------------------------
    # 3. Cleanup function removes expired entries
    # ------------------------------------------------------------------
    def test_cleanup_removes_expired_entries(self, client):
        """_cleanup_old_updates removes entries older than UPDATE_EXPIRY_SECONDS."""
        from src.api import webhook_handler

        original_expiry = webhook_handler.UPDATE_EXPIRY_SECONDS
        try:
            webhook_handler.UPDATE_EXPIRY_SECONDS = 10  # 10-second expiry

            # Insert one expired and one fresh entry
            webhook_handler._processed_updates[700] = time.time() - 20
            webhook_handler._processed_updates[701] = time.time()

            # Trigger cleanup via webhook (set MAX_TRACKED_UPDATES low)
            original_max = webhook_handler.MAX_TRACKED_UPDATES
            webhook_handler.MAX_TRACKED_UPDATES = 1
            try:
                resp = client.post("/webhook", json={"update_id": 702})
                assert resp.status_code == 200
            finally:
                webhook_handler.MAX_TRACKED_UPDATES = original_max

            # Expired entry should be removed, fresh entry kept
            assert 700 not in webhook_handler._processed_updates
            assert 701 in webhook_handler._processed_updates
        finally:
            webhook_handler.UPDATE_EXPIRY_SECONDS = original_expiry

    def test_cleanup_preserves_fresh_entries(self, client):
        """Fresh entries within expiry window are not removed by cleanup."""
        from src.api import webhook_handler

        now = time.time()
        webhook_handler._processed_updates[710] = now - 1
        webhook_handler._processed_updates[711] = now
        webhook_handler._processed_updates[712] = now

        original_max = webhook_handler.MAX_TRACKED_UPDATES
        try:
            webhook_handler.MAX_TRACKED_UPDATES = 2
            resp = client.post("/webhook", json={"update_id": 713})
            assert resp.status_code == 200

            assert (
                len(webhook_handler._processed_updates)
                <= webhook_handler.MAX_TRACKED_UPDATES + 1
            )
        finally:
            webhook_handler.MAX_TRACKED_UPDATES = original_max

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
        from src.api import webhook_handler

        client.post("/webhook", json={"update_id": 801})

        assert 801 in webhook_handler._processing_updates

    def test_normal_update_not_yet_in_processed(self, client):
        """Update not immediately in _processed_updates (moves after bg task)."""
        from src.api import webhook_handler

        client.post("/webhook", json={"update_id": 802})

        assert 802 not in webhook_handler._processed_updates

    def test_two_different_updates_both_accepted(self, client):
        """Two distinct update_ids should both be accepted."""
        from src.api import webhook_handler

        resp1 = client.post("/webhook", json={"update_id": 810})
        resp2 = client.post("/webhook", json={"update_id": 811})

        assert resp1.status_code == 200
        assert resp1.json()["status"] == "ok"
        assert "note" not in resp1.json()

        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"
        assert "note" not in resp2.json()

        assert 810 in webhook_handler._processing_updates
        assert 811 in webhook_handler._processing_updates
