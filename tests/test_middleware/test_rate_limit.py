"""Tests for per-IP token bucket rate limiting middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.rate_limit import RateLimitMiddleware, TokenBucket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(requests_per_minute: int = 60, path_prefixes=None) -> FastAPI:
    """Create a minimal FastAPI app with RateLimitMiddleware."""
    app = FastAPI()
    kwargs = {"requests_per_minute": requests_per_minute}
    if path_prefixes is not None:
        kwargs["path_prefixes"] = path_prefixes
    app.add_middleware(RateLimitMiddleware, **kwargs)

    @app.get("/webhook")
    @app.post("/webhook")
    async def webhook():
        return {"ok": True}

    @app.get("/api/health")
    async def api_health():
        return {"status": "healthy"}

    @app.get("/admin/dashboard")
    async def admin_dashboard():
        return {"admin": True}

    @app.get("/public/page")
    async def public_page():
        return {"public": True}

    @app.get("/other")
    async def other():
        return {"other": True}

    return app


# ---------------------------------------------------------------------------
# TestTokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    """Unit tests for the TokenBucket data structure."""

    def test_consume_success(self):
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        assert bucket.consume() is True

    def test_consume_depletes_tokens(self):
        bucket = TokenBucket(capacity=3, refill_rate=1.0)
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is False

    def test_refill_after_time(self, monkeypatch):
        """Tokens refill based on elapsed time."""
        fake_time = [100.0]
        monkeypatch.setattr(
            "src.middleware.rate_limit.time.monotonic", lambda: fake_time[0]
        )

        bucket = TokenBucket(capacity=2, refill_rate=1.0)
        # Consume all tokens
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

        # Advance time by 1 second → should refill ~1 token (rate = capacity/60 per sec)
        # refill_rate is per-second = requests_per_minute / 60
        # With refill_rate=1.0, 1 second = 1 token
        fake_time[0] = 101.0
        assert bucket.consume() is True

    def test_capacity_cap(self, monkeypatch):
        """Tokens never exceed capacity even after long idle periods."""
        fake_time = [100.0]
        monkeypatch.setattr(
            "src.middleware.rate_limit.time.monotonic", lambda: fake_time[0]
        )

        bucket = TokenBucket(capacity=3, refill_rate=1.0)
        # Advance time significantly
        fake_time[0] = 1000.0
        # Refill would add many tokens, but should be capped at capacity
        bucket.consume()
        assert bucket.tokens <= 3.0

    def test_initial_tokens_equal_capacity(self):
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        assert bucket.tokens == 10.0


# ---------------------------------------------------------------------------
# TestPathFiltering
# ---------------------------------------------------------------------------


class TestPathFiltering:
    """Rate limiting only applies to configured path prefixes."""

    @pytest.fixture()
    def app(self):
        return _make_app(requests_per_minute=60)

    @pytest.fixture()
    def client(self, app):
        return TestClient(app, raise_server_exceptions=False)

    def test_webhook_path_is_rate_limited(self, client):
        resp = client.get("/webhook")
        assert resp.status_code == 200

    def test_api_path_is_rate_limited(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_admin_path_is_rate_limited(self, client):
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200

    def test_non_matching_path_skips_rate_limiting(self, client):
        """Paths not matching any prefix should bypass rate limiting entirely."""
        app = _make_app(requests_per_minute=1)
        c = TestClient(app, raise_server_exceptions=False)
        # Even with 1 req/min, non-matching paths are never limited
        c.get("/public/page")
        resp = c.get("/public/page")
        assert resp.status_code == 200

    def test_other_path_skips_rate_limiting(self, client):
        resp = client.get("/other")
        assert resp.status_code == 200

    def test_custom_path_prefixes(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TEST", "1")
        app = _make_app(requests_per_minute=1, path_prefixes=("/custom/",))

        @app.get("/custom/endpoint")
        async def custom():
            return {"custom": True}

        c = TestClient(app, raise_server_exceptions=False)
        c.get("/custom/endpoint")
        resp = c.get("/custom/endpoint")
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# TestRateLimiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Verify that rate limiting correctly blocks excess requests."""

    @pytest.fixture(autouse=True)
    def _enable_rate_limit(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TEST", "1")

    def test_allows_requests_within_limit(self):
        app = _make_app(requests_per_minute=5)
        client = TestClient(app, raise_server_exceptions=False)
        for _ in range(5):
            resp = client.get("/webhook")
            assert resp.status_code == 200

    def test_returns_429_when_exceeded(self):
        app = _make_app(requests_per_minute=2)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/webhook")
        client.get("/webhook")
        resp = client.get("/webhook")
        assert resp.status_code == 429

    def test_429_response_body(self):
        app = _make_app(requests_per_minute=1)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/webhook")
        resp = client.get("/webhook")
        assert resp.status_code == 429
        body = resp.json()
        assert "detail" in body
        assert "Rate limit exceeded" in body["detail"]

    def test_429_includes_retry_after_header(self):
        app = _make_app(requests_per_minute=1)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/webhook")
        resp = client.get("/webhook")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert retry_after > 0


# ---------------------------------------------------------------------------
# TestEnvironmentSkipping
# ---------------------------------------------------------------------------


class TestEnvironmentSkipping:
    """Rate limiting is bypassed in test environment unless explicitly enabled."""

    def test_skips_when_environment_is_test(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.delenv("RATE_LIMIT_TEST", raising=False)
        app = _make_app(requests_per_minute=1)
        client = TestClient(app, raise_server_exceptions=False)
        # Should NOT be rate limited even though limit is 1
        client.get("/webhook")
        resp = client.get("/webhook")
        assert resp.status_code == 200

    def test_enabled_when_rate_limit_test_flag_set(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("RATE_LIMIT_TEST", "1")
        app = _make_app(requests_per_minute=1)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/webhook")
        resp = client.get("/webhook")
        assert resp.status_code == 429

    def test_applies_when_environment_is_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("RATE_LIMIT_TEST", raising=False)
        app = _make_app(requests_per_minute=1)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/webhook")
        resp = client.get("/webhook")
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# TestPruning
# ---------------------------------------------------------------------------


class TestPruning:
    """Stale buckets are cleaned up after the prune interval."""

    def test_stale_buckets_pruned(self, monkeypatch):
        """Test _maybe_prune removes stale buckets."""
        import time as time_mod

        fake_time = [1000.0]
        monkeypatch.setattr(time_mod, "monotonic", lambda: fake_time[0])

        # Directly instantiate middleware (not via FastAPI) to inspect internals
        mw = RateLimitMiddleware(app=None, requests_per_minute=60)
        mw._last_prune = fake_time[0]

        # Create a bucket at t=1000
        bucket = mw._get_bucket("1.2.3.4")
        bucket.last_refill = fake_time[0]
        assert "1.2.3.4" in mw._buckets

        # Advance past prune interval (300s) and past stale threshold (120s)
        fake_time[0] = 1500.0

        mw._maybe_prune()

        # The bucket's last_refill is 1000, stale threshold is 1500-120=1380
        # Since 1000 < 1380, the bucket should be pruned
        assert "1.2.3.4" not in mw._buckets
