"""Tests for per-user Telegram rate limiting middleware."""

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.middleware.user_rate_limit import (
    UserRateLimitMiddleware,
    _extract_user_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(
    user_rpm: int = 30,
    privileged_rpm: int = 120,
    privileged_user_ids: list[int] | None = None,
    webhook_path: str = "/webhook",
) -> FastAPI:
    """Create a minimal FastAPI app with UserRateLimitMiddleware."""
    app = FastAPI()
    app.add_middleware(
        UserRateLimitMiddleware,
        user_rpm=user_rpm,
        privileged_rpm=privileged_rpm,
        privileged_user_ids=privileged_user_ids or [],
        webhook_path=webhook_path,
    )

    @app.post("/webhook")
    async def webhook(request: Request):
        body = await request.body()
        return JSONResponse({"ok": True, "body_length": len(body)})

    @app.get("/webhook")
    async def webhook_get():
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.post("/other")
    async def other(request: Request):
        body = await request.body()
        return {"ok": True, "body_length": len(body)}

    return app


def _webhook_body(user_id: int, text: str = "hello") -> dict:
    """Build a minimal Telegram update body with message.from.id."""
    return {
        "update_id": 123456,
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": user_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }


def _post_webhook(client: TestClient, body: dict):
    """POST a JSON body to /webhook."""
    return client.post(
        "/webhook",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )


# ---------------------------------------------------------------------------
# TestExtractUserId
# ---------------------------------------------------------------------------


class TestExtractUserId:
    """Unit tests for _extract_user_id helper."""

    def test_extract_from_message(self):
        body = {"message": {"from": {"id": 111}}}
        assert _extract_user_id(body) == 111

    def test_extract_from_callback_query(self):
        body = {"callback_query": {"from": {"id": 222}}}
        assert _extract_user_id(body) == 222

    def test_extract_from_edited_message(self):
        body = {"edited_message": {"from": {"id": 333}}}
        assert _extract_user_id(body) == 333

    def test_extract_from_inline_query(self):
        body = {"inline_query": {"from": {"id": 444}}}
        assert _extract_user_id(body) == 444

    def test_empty_body_returns_none(self):
        assert _extract_user_id({}) is None

    def test_malformed_body_returns_none(self):
        assert _extract_user_id({"message": "not a dict"}) is None

    def test_missing_from_field_returns_none(self):
        body = {"message": {"text": "hello"}}
        assert _extract_user_id(body) is None

    def test_missing_id_in_from_returns_none(self):
        body = {"message": {"from": {"first_name": "Test"}}}
        assert _extract_user_id(body) is None


# ---------------------------------------------------------------------------
# TestWebhookFiltering
# ---------------------------------------------------------------------------


class TestWebhookFiltering:
    """Middleware only applies to POST requests to the webhook path."""

    @pytest.fixture(autouse=True)
    def _enable_rate_limit(self, monkeypatch):
        monkeypatch.setenv("USER_RATE_LIMIT_TEST", "1")

    @pytest.fixture()
    def app(self):
        return _make_app(user_rpm=1)

    @pytest.fixture()
    def client(self, app):
        return TestClient(app, raise_server_exceptions=False)

    def test_post_webhook_applies_rate_limiting(self, client):
        body = _webhook_body(user_id=100)
        _post_webhook(client, body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 429

    def test_get_webhook_skips_rate_limiting(self, client):
        # GET requests should pass through without rate limiting
        client.get("/webhook")
        resp = client.get("/webhook")
        assert resp.status_code == 200

    def test_non_webhook_path_skips_rate_limiting(self, client):
        # POST to /other should not be rate limited
        body = json.dumps({"data": "test"})
        client.post(
            "/other", content=body, headers={"Content-Type": "application/json"}
        )
        resp = client.post(
            "/other", content=body, headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestRateLimiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Verify per-user rate limiting behavior."""

    @pytest.fixture(autouse=True)
    def _enable_rate_limit(self, monkeypatch):
        monkeypatch.setenv("USER_RATE_LIMIT_TEST", "1")

    def test_allows_requests_within_limit(self):
        app = _make_app(user_rpm=5)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        for _ in range(5):
            resp = _post_webhook(client, body)
            assert resp.status_code == 200

    def test_blocks_excess_requests(self):
        app = _make_app(user_rpm=2)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        _post_webhook(client, body)
        _post_webhook(client, body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 429

    def test_separate_buckets_per_user(self):
        app = _make_app(user_rpm=1)
        client = TestClient(app, raise_server_exceptions=False)

        body_user_a = _webhook_body(user_id=100)
        body_user_b = _webhook_body(user_id=200)

        # User A exhausts their limit
        resp_a = _post_webhook(client, body_user_a)
        assert resp_a.status_code == 200

        # User B should still be allowed (separate bucket)
        resp_b = _post_webhook(client, body_user_b)
        assert resp_b.status_code == 200

    def test_privileged_user_gets_higher_limit(self):
        app = _make_app(user_rpm=2, privileged_rpm=10, privileged_user_ids=[999])
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=999)

        # Privileged user should be able to make more requests than user_rpm
        for _ in range(5):
            resp = _post_webhook(client, body)
            assert resp.status_code == 200

    def test_non_privileged_user_limited_at_user_rpm(self):
        app = _make_app(user_rpm=2, privileged_rpm=10, privileged_user_ids=[999])
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)

        _post_webhook(client, body)
        _post_webhook(client, body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 429

    def test_429_response_body(self):
        app = _make_app(user_rpm=1)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        _post_webhook(client, body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 429
        data = resp.json()
        assert "detail" in data


# ---------------------------------------------------------------------------
# TestBodyReinjection
# ---------------------------------------------------------------------------


class TestBodyReinjection:
    """Middleware reads body for user ID extraction; downstream must still read it."""

    @pytest.fixture(autouse=True)
    def _enable_rate_limit(self, monkeypatch):
        monkeypatch.setenv("USER_RATE_LIMIT_TEST", "1")

    def test_downstream_receives_full_body(self):
        app = _make_app(user_rpm=60)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        raw = json.dumps(body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["body_length"] == len(raw.encode("utf-8"))

    def test_body_content_preserved_after_rate_limit_check(self):
        """The exact bytes are available to the endpoint handler."""
        app = _make_app(user_rpm=60)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        body["message"]["text"] = "specific payload content"
        raw = json.dumps(body)
        resp = client.post(
            "/webhook",
            content=raw,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["body_length"] == len(raw.encode("utf-8"))


# ---------------------------------------------------------------------------
# TestEnvironmentSkipping
# ---------------------------------------------------------------------------


class TestEnvironmentSkipping:
    """Rate limiting is bypassed in test environment unless explicitly enabled."""

    def test_skips_when_environment_is_test(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.delenv("USER_RATE_LIMIT_TEST", raising=False)
        app = _make_app(user_rpm=1)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        _post_webhook(client, body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 200

    def test_enabled_when_user_rate_limit_test_flag_set(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("USER_RATE_LIMIT_TEST", "1")
        app = _make_app(user_rpm=1)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        _post_webhook(client, body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 429

    def test_applies_when_environment_is_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("USER_RATE_LIMIT_TEST", raising=False)
        app = _make_app(user_rpm=1)
        client = TestClient(app, raise_server_exceptions=False)
        body = _webhook_body(user_id=100)
        _post_webhook(client, body)
        resp = _post_webhook(client, body)
        assert resp.status_code == 429
