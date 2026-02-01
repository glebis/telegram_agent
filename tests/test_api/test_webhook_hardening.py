import importlib
import json
import os
from types import ModuleType

import pytest
from fastapi.testclient import TestClient


def load_app(monkeypatch) -> tuple[ModuleType, TestClient]:
    """Reload src.main with current env and return app + client."""
    if "src.main" in list(importlib.sys.modules):
        importlib.invalidate_caches()
        importlib.sys.modules.pop("src.main")
    module = importlib.import_module("src.main")
    client = TestClient(module.app)
    return module, client


@pytest.mark.parametrize("max_bytes", [120])
def test_webhook_rejects_oversize_body(monkeypatch, max_bytes):
    monkeypatch.setenv("WEBHOOK_MAX_BODY_BYTES", str(max_bytes))
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    module, client = load_app(monkeypatch)

    big_payload = {"update_id": 1, "data": "x" * (max_bytes + 50)}
    response = client.post("/webhook", content=json.dumps(big_payload))

    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_webhook_rate_limits_per_ip(monkeypatch):
    # allow only 2 requests per window
    monkeypatch.setenv("WEBHOOK_RATE_LIMIT", "2")
    monkeypatch.setenv("WEBHOOK_RATE_WINDOW_SECONDS", "60")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    module, client = load_app(monkeypatch)

    payload = {"update_id": 1}

    # first two should pass
    for i in range(2):
        res = client.post("/webhook", json={**payload, "update_id": i + 1})
        assert res.status_code == 200

    # third should be rate limited
    res = client.post("/webhook", json={**payload, "update_id": 99})
    assert res.status_code == 429
    assert "rate" in res.json()["detail"].lower()


def test_webhook_concurrency_cap(monkeypatch):
    # set max concurrency to 1 and simulate a pending task by not releasing semaphore
    monkeypatch.setenv("WEBHOOK_MAX_CONCURRENCY", "1")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    module, client = load_app(monkeypatch)

    # occupy semaphore by directly acquiring
    assert module._webhook_semaphore is not None
    module.asyncio.get_event_loop().run_until_complete(module._webhook_semaphore.acquire())

    res = client.post("/webhook", json={"update_id": 123})
    assert res.status_code in (429, 503)

    module._webhook_semaphore.release()
