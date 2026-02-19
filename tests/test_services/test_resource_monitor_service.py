"""Tests for ResourceMonitorService."""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.resource_monitor_service import ResourceMonitor, _get_chat_ids

# ---------------------------------------------------------------------------
# ResourceMonitor — cooldown logic
# ---------------------------------------------------------------------------


class TestResourceMonitorCooldown:
    def test_should_alert_first_time(self):
        """First alert for a resource should always fire."""
        monitor = ResourceMonitor(cooldown_minutes=30)
        assert monitor._should_alert("memory") is True

    def test_should_not_alert_within_cooldown(self):
        """Alert within cooldown period should be suppressed."""
        monitor = ResourceMonitor(cooldown_minutes=30)
        monitor._last_alert["memory"] = datetime.utcnow()
        assert monitor._should_alert("memory") is False

    def test_should_alert_after_cooldown_expires(self):
        """Alert after cooldown period should fire."""
        monitor = ResourceMonitor(cooldown_minutes=30)
        monitor._last_alert["memory"] = datetime.utcnow() - timedelta(minutes=31)
        assert monitor._should_alert("memory") is True

    def test_cooldown_is_per_resource(self):
        """Each resource has an independent cooldown."""
        monitor = ResourceMonitor(cooldown_minutes=30)
        monitor._last_alert["memory"] = datetime.utcnow()
        assert monitor._should_alert("memory") is False
        assert monitor._should_alert("cpu") is True  # never alerted

    def test_record_alert_sets_timestamp(self):
        """_record_alert stores the current UTC time."""
        monitor = ResourceMonitor(cooldown_minutes=30)
        before = datetime.utcnow()
        monitor._record_alert("disk_space")
        after = datetime.utcnow()
        ts = monitor._last_alert["disk_space"]
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# ResourceMonitor — formatting
# ---------------------------------------------------------------------------


class TestResourceMonitorFormatting:
    def test_format_alert_contains_resource_names(self):
        """Alert message includes all alerted resource names."""
        from src.services.heartbeat_service import CheckResult

        alerts = [
            CheckResult("memory", "warning", "85% used"),
            CheckResult("cpu", "critical", "98% usage"),
        ]
        msg = ResourceMonitor._format_alert(alerts)

        assert "<b>Resource Alert</b>" in msg
        assert "<b>memory</b>" in msg
        assert "<b>cpu</b>" in msg
        assert "85% used" in msg
        assert "98% usage" in msg

    def test_format_alert_uses_correct_emojis(self):
        """Warning uses ⚠️ and critical uses ❌."""
        from src.services.heartbeat_service import CheckResult

        alerts = [
            CheckResult("memory", "warning", "85%"),
            CheckResult("cpu", "critical", "98%"),
        ]
        msg = ResourceMonitor._format_alert(alerts)
        assert "\u26a0\ufe0f" in msg  # warning
        assert "\u274c" in msg  # critical


# ---------------------------------------------------------------------------
# _get_chat_ids
# ---------------------------------------------------------------------------


class TestGetChatIds:
    def test_dedicated_env_var(self):
        """RESOURCE_MONITOR_CHAT_IDS is used when set."""
        with patch.dict(
            os.environ,
            {"RESOURCE_MONITOR_CHAT_IDS": "111,222", "HEARTBEAT_CHAT_IDS": "999"},
        ):
            ids = _get_chat_ids()
        assert ids == [111, 222]

    def test_falls_back_to_heartbeat_chat_ids(self):
        """Falls back to HEARTBEAT_CHAT_IDS when dedicated var is absent."""
        env = {"HEARTBEAT_CHAT_IDS": "333"}
        with patch.dict(os.environ, env, clear=True):
            ids = _get_chat_ids()
        assert ids == [333]

    def test_empty_when_no_vars_set(self):
        """Returns empty list when neither env var is set."""
        with patch.dict(os.environ, {}, clear=True):
            ids = _get_chat_ids()
        assert ids == []

    def test_strips_whitespace(self):
        """Handles whitespace around chat ID values."""
        with patch.dict(
            os.environ, {"RESOURCE_MONITOR_CHAT_IDS": " 100 , 200 "}, clear=True
        ):
            ids = _get_chat_ids()
        assert ids == [100, 200]


# ---------------------------------------------------------------------------
# ResourceMonitor.check_and_alert — integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_and_alert_sends_on_threshold_breach():
    """Alert is sent when a resource check reports warning/critical."""
    from src.services.heartbeat_service import CheckResult

    monitor = ResourceMonitor(cooldown_minutes=30)

    mock_service = MagicMock()
    mock_service.check_memory = AsyncMock(
        return_value=CheckResult("memory", "warning", "85% used", value=85.0)
    )
    mock_service.check_cpu = AsyncMock(
        return_value=CheckResult("cpu", "ok", "30% usage", value=30.0)
    )
    mock_service.check_disk_space = AsyncMock(
        return_value=CheckResult("disk_space", "ok", "50% used", value=50.0)
    )
    mock_service.check_database_size = AsyncMock(
        return_value=CheckResult("database_size", "ok", "50MB", value=50.0)
    )

    with patch(
        "src.services.resource_monitor_service.get_heartbeat_service",
        return_value=mock_service,
    ):
        with patch(
            "src.services.resource_monitor_service.send_message_sync"
        ) as mock_send:
            await monitor.check_and_alert([123])

    mock_send.assert_called_once()
    call_text = mock_send.call_args[0][1]
    assert "memory" in call_text


@pytest.mark.asyncio
async def test_check_and_alert_suppressed_by_cooldown():
    """Alert is suppressed when the resource is still on cooldown."""
    from src.services.heartbeat_service import CheckResult

    monitor = ResourceMonitor(cooldown_minutes=30)
    monitor._last_alert["memory"] = datetime.utcnow()  # just alerted

    mock_service = MagicMock()
    mock_service.check_memory = AsyncMock(
        return_value=CheckResult("memory", "warning", "85% used", value=85.0)
    )
    mock_service.check_cpu = AsyncMock(
        return_value=CheckResult("cpu", "ok", "30%", value=30.0)
    )
    mock_service.check_disk_space = AsyncMock(
        return_value=CheckResult("disk_space", "ok", "50%", value=50.0)
    )
    mock_service.check_database_size = AsyncMock(
        return_value=CheckResult("database_size", "ok", "50MB", value=50.0)
    )

    with patch(
        "src.services.resource_monitor_service.get_heartbeat_service",
        return_value=mock_service,
    ):
        with patch(
            "src.services.resource_monitor_service.send_message_sync"
        ) as mock_send:
            await monitor.check_and_alert([123])

    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_alert_no_message_when_all_ok():
    """No alert sent when all checks are ok."""
    from src.services.heartbeat_service import CheckResult

    monitor = ResourceMonitor(cooldown_minutes=30)

    mock_service = MagicMock()
    mock_service.check_memory = AsyncMock(
        return_value=CheckResult("memory", "ok", "60%", value=60.0)
    )
    mock_service.check_cpu = AsyncMock(
        return_value=CheckResult("cpu", "ok", "20%", value=20.0)
    )
    mock_service.check_disk_space = AsyncMock(
        return_value=CheckResult("disk_space", "ok", "40%", value=40.0)
    )
    mock_service.check_database_size = AsyncMock(
        return_value=CheckResult("database_size", "ok", "100MB", value=100.0)
    )

    with patch(
        "src.services.resource_monitor_service.get_heartbeat_service",
        return_value=mock_service,
    ):
        with patch(
            "src.services.resource_monitor_service.send_message_sync"
        ) as mock_send:
            await monitor.check_and_alert([123])

    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_alert_records_cooldown_after_send():
    """Cooldown timestamp is updated for each alerted resource."""
    from src.services.heartbeat_service import CheckResult

    monitor = ResourceMonitor(cooldown_minutes=30)

    mock_service = MagicMock()
    mock_service.check_memory = AsyncMock(
        return_value=CheckResult("memory", "critical", "95%", value=95.0)
    )
    mock_service.check_cpu = AsyncMock(
        return_value=CheckResult("cpu", "ok", "10%", value=10.0)
    )
    mock_service.check_disk_space = AsyncMock(
        return_value=CheckResult("disk_space", "ok", "30%", value=30.0)
    )
    mock_service.check_database_size = AsyncMock(
        return_value=CheckResult("database_size", "ok", "50MB", value=50.0)
    )

    with patch(
        "src.services.resource_monitor_service.get_heartbeat_service",
        return_value=mock_service,
    ):
        with patch("src.services.resource_monitor_service.send_message_sync"):
            await monitor.check_and_alert([123])

    assert "memory" in monitor._last_alert
    assert "cpu" not in monitor._last_alert  # ok checks don't record cooldown


@pytest.mark.asyncio
async def test_check_and_alert_handles_check_exception_gracefully():
    """A crashed check does not prevent other checks from being evaluated."""
    from src.services.heartbeat_service import CheckResult

    monitor = ResourceMonitor(cooldown_minutes=30)

    mock_service = MagicMock()
    mock_service.check_memory = AsyncMock(side_effect=RuntimeError("psutil broken"))
    mock_service.check_cpu = AsyncMock(
        return_value=CheckResult("cpu", "critical", "99%", value=99.0)
    )
    mock_service.check_disk_space = AsyncMock(
        return_value=CheckResult("disk_space", "ok", "30%", value=30.0)
    )
    mock_service.check_database_size = AsyncMock(
        return_value=CheckResult("database_size", "ok", "50MB", value=50.0)
    )

    with patch(
        "src.services.resource_monitor_service.get_heartbeat_service",
        return_value=mock_service,
    ):
        with patch(
            "src.services.resource_monitor_service.send_message_sync"
        ) as mock_send:
            await monitor.check_and_alert([123])

    # cpu critical should still fire despite memory check crashing
    mock_send.assert_called_once()
    assert "cpu" in mock_send.call_args[0][1]
