"""Tests for webhook/admin ingress hardening (GitHub issue #26).

Covers:
- Per-IP rate limiting (429)
- Request body size rejection (413)
- Webhook concurrency cap (503)
- Structured auth failure logging (IP + User-Agent, no secrets)
- Settings integration for all config knobs
"""

import asyncio
import json
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def _clean_main_state():
    """Reset mutable module-level state in src.main between tests."""
    from src import main

    main._processed_updates.clear()
    main._processing_updates.clear()
    yield
    main._processed_updates.clear()
    main._processing_updates.clear()


def _make_client():
    """Return a TestClient wired to the real FastAPI app with mocked externals."""
    from src.main import app

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Rate Limit Middleware
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """RateLimitMiddleware returns 429 when per-IP limit is exceeded."""

    def test_token_bucket_allows_burst(self):
        """A fresh bucket should allow `capacity` requests."""
        from src.middleware.rate_limit import TokenBucket

        bucket = TokenBucket(capacity=3, refill_rate=1.0)
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True
        # 4th should be denied
        assert bucket.consume() is False

    def test_token_bucket_refills_over_time(self):
        """After waiting, tokens should refill."""
        from src.middleware.rate_limit import TokenBucket

        bucket = TokenBucket(capacity=1, refill_rate=100.0)  # fast refill
        assert bucket.consume() is True
        assert bucket.consume() is False
        # Simulate time passing
        bucket.last_refill -= 1.0  # 1 second ago
        assert bucket.consume() is True

    def test_rate_limit_middleware_returns_429(self):
        """Middleware returns 429 after exceeding the per-IP limit."""
        from src.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=2,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            # First 2 should succeed
            for _ in range(2):
                res = client.post("/test")
                assert res.status_code == 200, res.text

            # 3rd should be rate-limited
            res = client.post("/test")
            assert res.status_code == 429
            body = res.json()
            assert "rate limit" in body.get("detail", "").lower()

    def test_rate_limit_skips_non_matching_paths(self):
        """Requests to non-matching paths are not rate-limited."""
        from src.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=1,
            path_prefixes=("/webhook",),
        )

        @app.get("/health")
        async def health():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)
            # Even many requests should not be rate-limited
            for _ in range(5):
                res = client.get("/health")
                assert res.status_code == 200

    def test_rate_limit_skips_in_test_env(self):
        """Rate limiting is skipped when ENVIRONMENT=test and RATE_LIMIT_TEST!=1."""
        from src.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=1,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(os.environ, {"ENVIRONMENT": "test"}, clear=False):
            # Remove RATE_LIMIT_TEST if set
            os.environ.pop("RATE_LIMIT_TEST", None)
            client = TestClient(app, raise_server_exceptions=False)
            for _ in range(5):
                res = client.post("/test")
                assert res.status_code == 200

    def test_rate_limit_has_retry_after_header(self):
        """429 responses include a Retry-After header."""
        from src.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=1,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)
            client.post("/test")  # consume the 1 token
            res = client.post("/test")
            assert res.status_code == 429
            assert "retry-after" in res.headers


# ---------------------------------------------------------------------------
# 2. Body Size Limit Middleware
# ---------------------------------------------------------------------------


class TestBodySizeLimitMiddleware:
    """BodySizeLimitMiddleware returns 413 for oversized payloads."""

    def test_rejects_large_content_length(self):
        """Requests with Content-Length exceeding the limit get 413."""
        from src.middleware.body_size import BodySizeLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_bytes=100,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "BODY_SIZE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)
            big_payload = "x" * 200
            res = client.post(
                "/test",
                content=big_payload,
                headers={"content-length": str(len(big_payload))},
            )
            assert res.status_code == 413
            assert "too large" in res.json().get("detail", "").lower()

    def test_rejects_large_body_without_content_length(self):
        """When Content-Length is absent, the body is read and checked."""
        from src.middleware.body_size import BodySizeLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_bytes=50,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "BODY_SIZE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)
            big_payload = json.dumps({"data": "x" * 100})
            res = client.post("/test", content=big_payload)
            assert res.status_code == 413

    def test_allows_small_payload(self):
        """Payloads under the limit pass through."""
        from src.middleware.body_size import BodySizeLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_bytes=10000,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "BODY_SIZE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)
            res = client.post("/test", json={"data": "ok"})
            assert res.status_code == 200

    def test_rejects_invalid_content_length(self):
        """Malformed Content-Length returns 400."""
        from src.middleware.body_size import BodySizeLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_bytes=100,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "BODY_SIZE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)
            res = client.post(
                "/test",
                content="hello",
                headers={"content-length": "not-a-number"},
            )
            assert res.status_code == 400

    def test_skips_non_matching_paths(self):
        """Paths not in path_prefixes are not checked."""
        from src.middleware.body_size import BodySizeLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_bytes=10,
            path_prefixes=("/webhook",),
        )

        @app.post("/other")
        async def other_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "BODY_SIZE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)
            res = client.post("/other", content="x" * 100)
            assert res.status_code == 200

    def test_skips_in_test_env(self):
        """Body size check is skipped when ENVIRONMENT=test and BODY_SIZE_LIMIT_TEST!=1."""
        from src.middleware.body_size import BodySizeLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_bytes=10,
            path_prefixes=("/test",),
        )

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.dict(os.environ, {"ENVIRONMENT": "test"}, clear=False):
            os.environ.pop("BODY_SIZE_LIMIT_TEST", None)
            client = TestClient(app, raise_server_exceptions=False)
            res = client.post("/test", content="x" * 100)
            assert res.status_code == 200


# ---------------------------------------------------------------------------
# 3. Webhook Concurrency Cap
# ---------------------------------------------------------------------------


class TestWebhookConcurrencyCap:
    """Webhook endpoint returns 503 when the concurrency semaphore is exhausted."""

    @pytest.fixture
    def client(self, _clean_main_state):
        """Create test client with mocked dependencies."""
        with (
            patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": ""}),
            patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
            patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
            patch("src.lifecycle.init_database", new_callable=AsyncMock),
            patch("src.lifecycle.close_database", new_callable=AsyncMock),
            patch("src.lifecycle.setup_services"),
            patch("src.lifecycle.get_plugin_manager") as mock_pm,
            patch("src.main.get_bot") as mock_get_bot,
            patch("src.main.create_tracked_task") as mock_create_task,
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

            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    def test_503_when_semaphore_exhausted(self, client):
        """When all semaphore slots are taken, new requests get 503."""
        from src import main

        # Replace semaphore with one that has 0 capacity effectively
        original = main._webhook_semaphore
        main._webhook_semaphore = asyncio.Semaphore(1)
        # Acquire the only slot
        asyncio.get_event_loop().run_until_complete(main._webhook_semaphore.acquire())

        try:
            res = client.post("/webhook", json={"update_id": 999})
            assert res.status_code == 503
            assert "busy" in res.json().get("detail", "").lower()
        finally:
            main._webhook_semaphore.release()
            main._webhook_semaphore = original

    def test_normal_request_succeeds(self, client):
        """Normal requests go through when semaphore has capacity."""
        res = client.post("/webhook", json={"update_id": 501})
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# 4. Structured Auth Failure Logging
# ---------------------------------------------------------------------------


class TestAuthFailureLogging:
    """Auth failures log IP and User-Agent at WARNING, never log secret values."""

    @pytest.fixture
    def client(self, _clean_main_state):
        """Create test client with mocked dependencies."""
        with (
            patch.dict(
                os.environ,
                {"TELEGRAM_WEBHOOK_SECRET": "super-secret-value-12345"},
            ),
            patch("src.lifecycle.initialize_bot", new_callable=AsyncMock),
            patch("src.lifecycle.shutdown_bot", new_callable=AsyncMock),
            patch("src.lifecycle.init_database", new_callable=AsyncMock),
            patch("src.lifecycle.close_database", new_callable=AsyncMock),
            patch("src.lifecycle.setup_services"),
            patch("src.lifecycle.get_plugin_manager") as mock_pm,
            patch("src.main.get_bot") as mock_get_bot,
            patch("src.main.create_tracked_task") as mock_create_task,
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

            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    def test_webhook_auth_failure_logs_ip_and_ua(self, client, caplog):
        """Invalid webhook secret logs IP + User-Agent at WARNING."""
        with caplog.at_level(logging.WARNING, logger="src.main"):
            res = client.post(
                "/webhook",
                json={"update_id": 1},
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": "wrong-token",
                    "User-Agent": "EvilBot/1.0",
                },
            )
        assert res.status_code == 401

        # Check log output
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        auth_log = [r for r in warning_records if "Auth failure" in r.message]
        assert (
            len(auth_log) >= 1
        ), f"Expected auth failure log, got: {[r.message for r in warning_records]}"

        log_msg = auth_log[0].message
        assert "ip=" in log_msg
        assert "user_agent=" in log_msg
        assert "EvilBot/1.0" in log_msg
        # CRITICAL: the actual secret must NEVER appear in logs
        assert "super-secret-value-12345" not in log_msg
        assert "wrong-token" not in log_msg

    def test_admin_auth_failure_logs_ip_and_ua(self, client, caplog):
        """Invalid admin API key logs IP + User-Agent at WARNING."""
        with caplog.at_level(logging.WARNING, logger="src.api.webhook"):
            res = client.get(
                "/admin/webhook/status",
                headers={
                    "X-Api-Key": "bad-key-value",
                    "User-Agent": "TestAgent/2.0",
                },
            )
        assert res.status_code == 401

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        auth_log = [r for r in warning_records if "Auth failure" in r.message]
        assert (
            len(auth_log) >= 1
        ), f"Expected auth failure log, got: {[r.message for r in warning_records]}"

        log_msg = auth_log[0].message
        assert "ip=" in log_msg
        assert "user_agent=" in log_msg
        assert "TestAgent/2.0" in log_msg
        # Secrets must NEVER appear
        assert "super-secret-value-12345" not in log_msg
        assert "bad-key-value" not in log_msg

    def test_missing_api_key_logs_structured(self, client, caplog):
        """Missing API key produces structured log (not just 'Missing...')."""
        with caplog.at_level(logging.WARNING, logger="src.api.webhook"):
            res = client.get("/admin/webhook/status")
        assert res.status_code == 401

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        auth_log = [r for r in warning_records if "Auth failure" in r.message]
        assert len(auth_log) >= 1


# ---------------------------------------------------------------------------
# 5. Settings Integration
# ---------------------------------------------------------------------------


class TestHardeningSettings:
    """Settings class includes all hardening config knobs."""

    def test_settings_has_rate_limit(self):
        from src.core.config import Settings

        s = Settings()
        assert hasattr(s, "rate_limit_requests_per_minute")
        assert s.rate_limit_requests_per_minute == 60

    def test_settings_has_body_limit(self):
        from src.core.config import Settings

        s = Settings()
        assert hasattr(s, "max_request_body_bytes")
        assert s.max_request_body_bytes == 1048576

    def test_settings_has_concurrency(self):
        from src.core.config import Settings

        s = Settings()
        assert hasattr(s, "webhook_max_concurrent")
        assert s.webhook_max_concurrent == 20

    def test_settings_overridable_via_env(self):
        """Env vars override defaults."""
        with patch.dict(
            os.environ,
            {
                "RATE_LIMIT_REQUESTS_PER_MINUTE": "120",
                "MAX_REQUEST_BODY_BYTES": "2097152",
                "WEBHOOK_MAX_CONCURRENT": "50",
            },
        ):
            from src.core.config import Settings

            s = Settings()
            assert s.rate_limit_requests_per_minute == 120
            assert s.max_request_body_bytes == 2097152
            assert s.webhook_max_concurrent == 50
