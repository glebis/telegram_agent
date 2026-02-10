"""Tests for per-user (Telegram user_id) rate limiting (GitHub issue #181).

Covers:
- Per-user rate limit triggers after threshold
- OWNER/ADMIN users get higher limits
- Per-IP limiting still works for non-webhook endpoints
- Rate limit resets after the window expires
- Updates without a user_id are not rate-limited
- Extraction from various Telegram update types
"""

import json
import os
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.user_rate_limit import (
    UserRateLimitMiddleware,
    UserTokenBucket,
    _extract_user_id,
)

# ---------------------------------------------------------------------------
# Unit tests: UserTokenBucket
# ---------------------------------------------------------------------------


class TestUserTokenBucket:
    """UserTokenBucket allows burst up to capacity and then denies."""

    def test_allows_burst(self):
        bucket = UserTokenBucket(capacity=3, refill_rate=1.0)
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is False

    def test_refills_over_time(self):
        bucket = UserTokenBucket(capacity=1, refill_rate=100.0)  # fast refill
        assert bucket.consume() is True
        assert bucket.consume() is False
        # Simulate time passing
        bucket.last_refill -= 1.0  # pretend 1 second passed
        assert bucket.consume() is True


# ---------------------------------------------------------------------------
# Unit tests: _extract_user_id
# ---------------------------------------------------------------------------


class TestExtractUserId:
    """_extract_user_id correctly finds user_id from various update types."""

    def test_message(self):
        body = {"update_id": 1, "message": {"from": {"id": 12345}, "text": "hi"}}
        assert _extract_user_id(body) == 12345

    def test_callback_query(self):
        body = {
            "update_id": 2,
            "callback_query": {"from": {"id": 67890}, "data": "btn"},
        }
        assert _extract_user_id(body) == 67890

    def test_edited_message(self):
        body = {
            "update_id": 3,
            "edited_message": {"from": {"id": 11111}, "text": "edited"},
        }
        assert _extract_user_id(body) == 11111

    def test_inline_query(self):
        body = {
            "update_id": 4,
            "inline_query": {"from": {"id": 22222}, "query": "search"},
        }
        assert _extract_user_id(body) == 22222

    def test_no_user_id(self):
        body = {"update_id": 5}
        assert _extract_user_id(body) is None

    def test_malformed_from(self):
        body = {"update_id": 6, "message": {"from": "not-a-dict"}}
        assert _extract_user_id(body) is None


# ---------------------------------------------------------------------------
# Integration tests: UserRateLimitMiddleware
# ---------------------------------------------------------------------------


def _make_app(user_rpm=2, privileged_rpm=5, privileged_user_ids=None):
    """Create a minimal FastAPI app with UserRateLimitMiddleware."""
    app = FastAPI()
    app.add_middleware(
        UserRateLimitMiddleware,
        user_rpm=user_rpm,
        privileged_rpm=privileged_rpm,
        privileged_user_ids=privileged_user_ids or set(),
    )

    @app.post("/webhook")
    async def webhook():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


def _webhook_payload(update_id: int, user_id: int) -> dict:
    """Build a minimal Telegram webhook update payload."""
    return {
        "update_id": update_id,
        "message": {"from": {"id": user_id}, "text": "hello"},
    }


class TestUserRateLimitMiddleware:
    """UserRateLimitMiddleware rate-limits webhook requests per Telegram user_id."""

    def test_regular_user_rate_limited_after_threshold(self):
        """A regular user is rate-limited after exceeding user_rpm."""
        app = _make_app(user_rpm=2)
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            user_id = 100
            # First 2 requests should pass
            for i in range(2):
                res = client.post(
                    "/webhook",
                    content=json.dumps(_webhook_payload(i + 1, user_id)),
                    headers={"Content-Type": "application/json"},
                )
                assert res.status_code == 200, f"Request {i+1} failed: {res.text}"

            # 3rd request should be rate-limited
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(99, user_id)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 429
            assert "rate limit" in res.json()["detail"].lower()

    def test_different_users_have_separate_limits(self):
        """Different user_ids have independent rate limits."""
        app = _make_app(user_rpm=1)
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            # User A: 1 request (should pass)
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(1, 100)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 200

            # User A: 2nd request (should be rate-limited)
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(2, 100)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 429

            # User B: 1st request (should pass — different user)
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(3, 200)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 200

    def test_privileged_user_gets_higher_limit(self):
        """OWNER/ADMIN users get privileged_rpm instead of user_rpm."""
        owner_id = 999
        app = _make_app(
            user_rpm=1,
            privileged_rpm=3,
            privileged_user_ids={owner_id},
        )
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            # Owner should be able to send 3 requests
            for i in range(3):
                res = client.post(
                    "/webhook",
                    content=json.dumps(_webhook_payload(i + 1, owner_id)),
                    headers={"Content-Type": "application/json"},
                )
                assert res.status_code == 200, f"Owner request {i+1} failed"

            # 4th request should be rate-limited even for owner
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(99, owner_id)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 429

    def test_regular_user_limited_while_privileged_passes(self):
        """Regular user is limited at user_rpm while privileged user continues."""
        owner_id = 999
        app = _make_app(
            user_rpm=1,
            privileged_rpm=5,
            privileged_user_ids={owner_id},
        )
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            # Regular user exhausts their limit
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(1, 100)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 200

            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(2, 100)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 429

            # Owner still has capacity
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(3, owner_id)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 200

    def test_non_webhook_paths_not_affected(self):
        """Non-webhook endpoints are not subject to per-user rate limiting."""
        app = _make_app(user_rpm=1)
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            # GET /health should always pass regardless of rate limit
            for _ in range(10):
                res = client.get("/health")
                assert res.status_code == 200

    def test_updates_without_user_id_pass_through(self):
        """Webhook updates without a user_id (e.g., bare update) are not limited."""
        app = _make_app(user_rpm=1)
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            # Payloads without "from" should pass through
            for i in range(5):
                res = client.post(
                    "/webhook",
                    content=json.dumps({"update_id": i + 1}),
                    headers={"Content-Type": "application/json"},
                )
                assert res.status_code == 200

    def test_rate_limit_resets_after_window(self):
        """Rate limit resets once the token bucket refills."""
        app = _make_app(user_rpm=1)
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            user_id = 100

            # Exhaust the limit
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(1, user_id)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 200

            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(2, user_id)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 429

            # Simulate time passing by manipulating the bucket directly.
            # Walk the Starlette middleware stack to find our instance.
            from src.middleware.user_rate_limit import UserRateLimitMiddleware as URLM

            stack = app.middleware_stack
            while stack is not None:
                if isinstance(stack, URLM):
                    bucket = stack._buckets.get(user_id)
                    if bucket:
                        # Simulate 60 seconds passing (enough for full refill)
                        bucket.last_refill -= 60.0
                    break
                stack = getattr(stack, "app", None)

            # Now the next request should succeed
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(3, user_id)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 200

    def test_skips_in_test_env_by_default(self):
        """Rate limiting skipped in test env without USER_RATE_LIMIT_TEST."""
        app = _make_app(user_rpm=1)
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}, clear=False):
            os.environ.pop("USER_RATE_LIMIT_TEST", None)
            client = TestClient(app, raise_server_exceptions=False)

            user_id = 100
            # Even many requests should pass in test env
            for i in range(5):
                res = client.post(
                    "/webhook",
                    content=json.dumps(_webhook_payload(i + 1, user_id)),
                    headers={"Content-Type": "application/json"},
                )
                assert res.status_code == 200

    def test_429_includes_retry_after_header(self):
        """429 responses include a Retry-After header."""
        app = _make_app(user_rpm=1)
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            user_id = 100
            client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(1, user_id)),
                headers={"Content-Type": "application/json"},
            )
            res = client.post(
                "/webhook",
                content=json.dumps(_webhook_payload(2, user_id)),
                headers={"Content-Type": "application/json"},
            )
            assert res.status_code == 429
            assert "retry-after" in res.headers

    def test_invalid_json_passes_through(self):
        """Invalid JSON bodies are passed through to downstream handlers."""
        app = _make_app(user_rpm=1)
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "USER_RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            res = client.post(
                "/webhook",
                content="not-json{{{",
                headers={"Content-Type": "application/json"},
            )
            # Should not be 429 — middleware lets it through
            assert res.status_code != 429


# ---------------------------------------------------------------------------
# Integration: per-IP limiting still works for non-webhook endpoints
# ---------------------------------------------------------------------------


class TestPerIpStillWorks:
    """Per-IP rate limiting (existing middleware) still functions."""

    def test_per_ip_rate_limit_on_api_endpoint(self):
        """Per-IP rate limiting applies to non-webhook paths like /api/."""
        from src.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=2,
            path_prefixes=("/api/",),
        )

        @app.get("/api/test")
        async def api_endpoint():
            return {"ok": True}

        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "RATE_LIMIT_TEST": "1"}
        ):
            client = TestClient(app, raise_server_exceptions=False)

            # First 2 should pass
            for _ in range(2):
                res = client.get("/api/test")
                assert res.status_code == 200

            # 3rd should be rate-limited
            res = client.get("/api/test")
            assert res.status_code == 429


# ---------------------------------------------------------------------------
# Settings integration
# ---------------------------------------------------------------------------


class TestUserRateLimitSettings:
    """Settings class includes per-user rate limit config knobs."""

    def test_settings_has_user_rpm(self):
        from src.core.config import Settings

        s = Settings()
        assert hasattr(s, "user_rate_limit_rpm")
        assert s.user_rate_limit_rpm == 30

    def test_settings_has_privileged_rpm(self):
        from src.core.config import Settings

        s = Settings()
        assert hasattr(s, "user_rate_limit_privileged_rpm")
        assert s.user_rate_limit_privileged_rpm == 120

    def test_settings_overridable_via_env(self):
        with patch.dict(
            os.environ,
            {
                "USER_RATE_LIMIT_RPM": "50",
                "USER_RATE_LIMIT_PRIVILEGED_RPM": "200",
            },
        ):
            from src.core.config import Settings

            s = Settings()
            assert s.user_rate_limit_rpm == 50
            assert s.user_rate_limit_privileged_rpm == 200
