import importlib
import json
from types import ModuleType

import pytest
from fastapi.testclient import TestClient


def load_app(monkeypatch) -> tuple[ModuleType, TestClient]:
    """Reload src.main with current env and return app + client."""
    if "src.main" in list(importlib.sys.modules):
        importlib.invalidate_caches()
        importlib.sys.modules.pop("src.main")
    module = importlib.import_module("src.main")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    client = TestClient(module.app)
    return module, client


@pytest.mark.parametrize("path", ["/api/health", "/admin/webhook/status", "/webhook"])
def test_body_limit_blocks_large_payloads(monkeypatch, path):
    monkeypatch.setenv("API_MAX_BODY_BYTES", "100")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("API_BODY_LIMIT_TEST", "1")

    module, client = load_app(monkeypatch)
    monkeypatch.setattr(module, "API_MAX_BODY_BYTES", 100, raising=False)

    big_payload = {"data": "x" * 120}
    response = client.post(path, content=json.dumps(big_payload))

    # /webhook returns detail, others return error key
    assert response.status_code == 413
    body = response.json()
    assert any("large" in str(v).lower() for v in body.values())


def test_body_limit_allows_small_payload(monkeypatch):
    monkeypatch.setenv("API_MAX_BODY_BYTES", "100")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("API_BODY_LIMIT_TEST", "1")

    module, client = load_app(monkeypatch)
    monkeypatch.setattr(module, "API_MAX_BODY_BYTES", 100, raising=False)

    small_payload = {"data": "ok"}
    res = client.post("/api/health", json=small_payload)
    assert res.status_code in (200, 404)  # route may not exist but not 413
