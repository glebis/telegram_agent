"""Tests for HeartbeatService."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.heartbeat_service import (
    CheckResult,
    HeartbeatResult,
    HeartbeatService,
)


@pytest.fixture
def service():
    return HeartbeatService()


# ------------------------------------------------------------------
# Phase 1: Individual checks
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_db_ok(service):
    """DB check returns ok when connected."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "src.core.database.get_db_session",
        return_value=mock_session,
    ):
        result = await service.check_db()

    assert result.status == "ok"
    assert result.name == "database"


@pytest.mark.asyncio
async def test_check_db_failure(service):
    """DB check returns critical when unreachable."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "src.core.database.get_db_session",
        return_value=mock_session,
    ):
        result = await service.check_db()

    assert result.status == "critical"


@pytest.mark.asyncio
async def test_check_api_keys_all_present(service):
    """API key check returns ok when all keys present."""
    env = {
        "TELEGRAM_BOT_TOKEN": "test:token",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "sk-test",
    }
    with patch.dict(os.environ, env):
        result = await service.check_api_keys()

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_check_api_keys_missing_critical(service):
    """API key check returns critical when bot token missing."""
    env = os.environ.copy()
    env.pop("TELEGRAM_BOT_TOKEN", None)

    with patch.dict(os.environ, env, clear=True):
        result = await service.check_api_keys()

    assert result.status == "critical"
    assert "TELEGRAM_BOT_TOKEN" in result.message


@pytest.mark.asyncio
async def test_check_api_keys_missing_optional(service):
    """API key check returns warning when optional keys missing."""
    env = {
        "TELEGRAM_BOT_TOKEN": "test:token",
    }
    with patch.dict(os.environ, env, clear=True):
        result = await service.check_api_keys()

    assert result.status == "warning"


@pytest.mark.asyncio
async def test_check_disk_space(service):
    """Disk space check returns ok for normal usage."""
    mock_usage = MagicMock()
    mock_usage.total = 100 * (1024**3)
    mock_usage.used = 50 * (1024**3)
    mock_usage.free = 50 * (1024**3)

    with patch("shutil.disk_usage", return_value=mock_usage):
        result = await service.check_disk_space()

    assert result.status == "ok"
    assert result.value == 50.0


@pytest.mark.asyncio
async def test_check_disk_space_critical(service):
    """Disk space check returns critical for high usage."""
    mock_usage = MagicMock()
    mock_usage.total = 100 * (1024**3)
    mock_usage.used = 96 * (1024**3)
    mock_usage.free = 4 * (1024**3)

    with patch("shutil.disk_usage", return_value=mock_usage):
        result = await service.check_disk_space()

    assert result.status == "critical"


@pytest.mark.asyncio
async def test_check_uptime(service):
    """Uptime check always returns ok."""
    result = await service.check_uptime()
    assert result.status == "ok"
    assert "Up " in result.message


@pytest.mark.asyncio
async def test_check_webhook_no_token(service):
    """Webhook check returns critical without bot token."""
    with patch.dict(os.environ, {}, clear=True):
        result = await service.check_webhook()

    assert result.status == "critical"


@pytest.mark.asyncio
async def test_check_webhook_ok(service):
    """Webhook check returns ok with valid webhook."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ok": True,
        "result": {
            "url": "https://example.com/webhook",
            "pending_update_count": 0,
            "last_error_message": "",
        },
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test:token"}):
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await service.check_webhook()

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_check_recent_errors_no_log(service):
    """Recent errors check returns ok when log file missing."""
    with patch(
        "src.services.heartbeat_service.Path.cwd",
        return_value=Path("/nonexistent"),
    ):
        result = await service.check_recent_errors()

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_check_task_queue_ok(service):
    """Task queue check returns ok with no failures."""
    mock_service = MagicMock()
    mock_service.get_queue_status.return_value = {
        "pending": 0,
        "failed": 0,
        "completed": 5,
        "in_progress": 0,
    }

    with patch(
        "src.services.job_queue_service.get_job_queue_service",
        return_value=mock_service,
    ):
        result = await service.check_task_queue()

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_check_task_queue_warning(service):
    """Task queue check returns warning with failed jobs."""
    mock_service = MagicMock()
    mock_service.get_queue_status.return_value = {
        "pending": 2,
        "failed": 3,
        "completed": 10,
        "in_progress": 0,
    }

    with patch(
        "src.services.job_queue_service.get_job_queue_service",
        return_value=mock_service,
    ):
        result = await service.check_task_queue()

    assert result.status == "warning"


# ------------------------------------------------------------------
# Full run
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_all_ok_skips_llm(service):
    """When all checks pass, LLM triage is not called."""
    ok_result = CheckResult("test", "ok", "fine")

    with patch.object(
        service, "run_phase1", new_callable=AsyncMock, return_value=[ok_result]
    ):
        with patch.object(service, "run_triage", new_callable=AsyncMock) as mock_triage:
            result = await service.run(chat_id=123)

    assert result.status == "ok"
    mock_triage.assert_not_called()


@pytest.mark.asyncio
async def test_run_with_issues_triggers_llm(service):
    """When issues found, LLM triage runs."""
    checks = [
        CheckResult("db", "ok", "connected"),
        CheckResult("disk", "warning", "85% used"),
    ]

    with patch.object(
        service, "run_phase1", new_callable=AsyncMock, return_value=checks
    ):
        with patch.object(
            service,
            "run_triage",
            new_callable=AsyncMock,
            return_value="Check disk space",
        ):
            result = await service.run(chat_id=123)

    assert result.status == "warning"
    assert result.summary == "Check disk space"


@pytest.mark.asyncio
async def test_run_llm_failure_graceful(service):
    """LLM triage failure doesn't crash the heartbeat."""
    checks = [CheckResult("db", "critical", "down")]

    with patch.object(
        service, "run_phase1", new_callable=AsyncMock, return_value=checks
    ):
        with patch.object(
            service, "run_triage", new_callable=AsyncMock, return_value=None
        ):
            result = await service.run(chat_id=123)

    assert result.status == "critical"
    assert result.summary is None


# ------------------------------------------------------------------
# Delivery
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_and_deliver_skips_ok(service):
    """run_and_deliver skips message when all ok and show_ok=false."""
    ok_result = HeartbeatResult(status="ok", checks=[])

    with patch.object(service, "run", new_callable=AsyncMock, return_value=ok_result):
        with patch(
            "src.services.heartbeat_service.get_config_value",
            side_effect=lambda k, d=None: False if k == "heartbeat.show_ok" else d,
        ):
            with patch("src.bot.handlers.base.send_message_sync") as mock_send:
                result = await service.run_and_deliver(chat_id=123)

    assert result.status == "skipped"
    mock_send.assert_not_called()


# ------------------------------------------------------------------
# Formatting
# ------------------------------------------------------------------


def test_format_message(service):
    """Format produces valid HTML structure."""
    result = HeartbeatResult(
        status="warning",
        checks=[
            CheckResult("database", "ok", "Connected"),
            CheckResult("disk_space", "warning", "87% used"),
        ],
        summary="Disk usage is high",
        duration_seconds=1.23,
    )
    msg = service._format_message(result)
    assert "<b>Heartbeat: WARNING</b>" in msg
    assert "<b>database</b>" in msg
    assert "<b>disk_space</b>" in msg
    assert "Triage:" in msg
    assert "1.23s" in msg
