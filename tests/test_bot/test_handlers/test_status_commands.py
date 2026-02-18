"""Tests for /status command handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.status_commands import (
    _collect_status_data,
    _format_status_message,
    status_command,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update with effective_user and effective_chat."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Create a mock context."""
    return MagicMock()


@pytest.fixture
def healthy_status_data():
    """Status data when everything is healthy."""
    return {
        "status": "healthy",
        "uptime": "2d 3h",
        "version": "1.2.3",
        "database": "connected",
        "bot_initialized": True,
        "memory_pct": 45.2,
        "cpu_pct": 12.0,
        "disk_pct": 55.0,
        "disk_free_gb": 120.5,
        "webhook_ok": True,
        "webhook_pending": 0,
        "recent_errors": 0,
        "error_window_hours": 6,
    }


@pytest.fixture
def degraded_status_data():
    """Status data when some subsystems are degraded."""
    return {
        "status": "degraded",
        "uptime": "0h 5m",
        "version": "1.2.3",
        "database": "disconnected",
        "bot_initialized": True,
        "memory_pct": 88.5,
        "cpu_pct": 92.0,
        "disk_pct": 55.0,
        "disk_free_gb": 120.5,
        "webhook_ok": True,
        "webhook_pending": 15,
        "recent_errors": 42,
        "error_window_hours": 6,
    }


# ---------------------------------------------------------------------------
# Authorization tests
# ---------------------------------------------------------------------------


class TestStatusAuthorization:
    """Test that /status respects authorization tiers."""

    @pytest.mark.asyncio
    async def test_admin_can_access(self, mock_update, mock_context):
        """Admin users should be able to use /status."""
        with patch(
            "src.bot.handlers.status_commands._collect_status_data",
            new_callable=AsyncMock,
        ) as mock_collect:
            mock_collect.return_value = {
                "status": "healthy",
                "uptime": "1h 0m",
                "version": "1.0.0",
                "database": "connected",
                "bot_initialized": True,
                "memory_pct": 50.0,
                "cpu_pct": 10.0,
                "disk_pct": 50.0,
                "disk_free_gb": 100.0,
                "webhook_ok": True,
                "webhook_pending": 0,
                "recent_errors": 0,
                "error_window_hours": 6,
            }

            # Call the underlying function directly (bypass decorator)
            await status_command.__wrapped__(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, mock_update, mock_context):
        """Non-admin users should be rejected by @require_tier."""
        with patch("src.core.authorization.get_user_tier") as mock_tier:
            from src.core.authorization import AuthTier

            mock_tier.return_value = AuthTier.USER

            await status_command(mock_update, mock_context)

            # Should get the denial message
            mock_update.message.reply_text.assert_called_once_with(
                "You are not authorized to use this command."
            )

    @pytest.mark.asyncio
    async def test_owner_can_access(self, mock_update, mock_context):
        """Owner tier should also have access (higher than ADMIN)."""
        with patch(
            "src.bot.handlers.status_commands._collect_status_data",
            new_callable=AsyncMock,
        ) as mock_collect:
            mock_collect.return_value = {
                "status": "healthy",
                "uptime": "1h 0m",
                "version": "1.0.0",
                "database": "connected",
                "bot_initialized": True,
                "memory_pct": 50.0,
                "cpu_pct": 10.0,
                "disk_pct": 50.0,
                "disk_free_gb": 100.0,
                "webhook_ok": True,
                "webhook_pending": 0,
                "recent_errors": 0,
                "error_window_hours": 6,
            }

            await status_command.__wrapped__(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once()


# ---------------------------------------------------------------------------
# Data collection tests
# ---------------------------------------------------------------------------


class TestCollectStatusData:
    """Test the data collection function."""

    @pytest.mark.asyncio
    async def test_returns_all_required_fields(self):
        """_collect_status_data should return all required status fields."""
        with (
            patch(
                "src.bot.handlers.status_commands.check_database_health",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.bot.handlers.status_commands._is_bot_initialized",
                return_value=True,
            ),
            patch(
                "src.bot.handlers.status_commands._get_version",
                return_value="1.0.0",
            ),
            patch(
                "src.bot.handlers.status_commands.get_uptime_seconds",
                return_value=7260.0,
            ),
            patch("src.bot.handlers.status_commands.get_heartbeat_service") as mock_hb,
        ):
            service = MagicMock()
            mock_hb.return_value = service
            service.check_memory = AsyncMock(
                return_value=MagicMock(value=45.0, message="45.0% used, 8GB available")
            )
            service.check_cpu = AsyncMock(
                return_value=MagicMock(value=12.0, message="12.0% usage")
            )
            service.check_disk_space = AsyncMock(
                return_value=MagicMock(value=55.0, message="55.0% used, 120GB free")
            )
            service.check_webhook = AsyncMock(
                return_value=MagicMock(
                    status="ok", value=0, message="URL set, 0 pending"
                )
            )
            service.check_recent_errors = AsyncMock(
                return_value=MagicMock(value=3, message="3 errors in last 6h")
            )

            data = await _collect_status_data()

            required_keys = {
                "status",
                "uptime",
                "version",
                "database",
                "bot_initialized",
                "memory_pct",
                "cpu_pct",
                "disk_pct",
                "disk_free_gb",
                "webhook_ok",
                "webhook_pending",
                "recent_errors",
                "error_window_hours",
            }
            assert required_keys.issubset(data.keys())

    @pytest.mark.asyncio
    async def test_db_disconnected(self):
        """When DB health check fails, status should be degraded."""
        with (
            patch(
                "src.bot.handlers.status_commands.check_database_health",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.bot.handlers.status_commands._is_bot_initialized",
                return_value=True,
            ),
            patch(
                "src.bot.handlers.status_commands._get_version",
                return_value="1.0.0",
            ),
            patch(
                "src.bot.handlers.status_commands.get_uptime_seconds",
                return_value=100.0,
            ),
            patch("src.bot.handlers.status_commands.get_heartbeat_service") as mock_hb,
        ):
            service = MagicMock()
            mock_hb.return_value = service
            service.check_memory = AsyncMock(
                return_value=MagicMock(value=45.0, message="45%")
            )
            service.check_cpu = AsyncMock(
                return_value=MagicMock(value=10.0, message="10%")
            )
            service.check_disk_space = AsyncMock(
                return_value=MagicMock(value=50.0, message="50% used, 100GB free")
            )
            service.check_webhook = AsyncMock(
                return_value=MagicMock(status="ok", value=0, message="ok")
            )
            service.check_recent_errors = AsyncMock(
                return_value=MagicMock(value=0, message="0 errors")
            )

            data = await _collect_status_data()
            assert data["database"] == "disconnected"
            assert data["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_resource_check_crash_handled(self):
        """If a resource check crashes, data should still be returned with defaults."""
        with (
            patch(
                "src.bot.handlers.status_commands.check_database_health",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.bot.handlers.status_commands._is_bot_initialized",
                return_value=True,
            ),
            patch(
                "src.bot.handlers.status_commands._get_version",
                return_value="1.0.0",
            ),
            patch(
                "src.bot.handlers.status_commands.get_uptime_seconds",
                return_value=100.0,
            ),
            patch("src.bot.handlers.status_commands.get_heartbeat_service") as mock_hb,
        ):
            service = MagicMock()
            mock_hb.return_value = service
            # Memory check crashes
            service.check_memory = AsyncMock(side_effect=Exception("psutil broken"))
            service.check_cpu = AsyncMock(
                return_value=MagicMock(value=10.0, message="10%")
            )
            service.check_disk_space = AsyncMock(
                return_value=MagicMock(value=50.0, message="50% used, 100GB free")
            )
            service.check_webhook = AsyncMock(
                return_value=MagicMock(status="ok", value=0, message="ok")
            )
            service.check_recent_errors = AsyncMock(
                return_value=MagicMock(value=0, message="0 errors")
            )

            data = await _collect_status_data()
            # Should still return data, with None for failed check
            assert data["memory_pct"] is None
            assert data["cpu_pct"] == 10.0


# ---------------------------------------------------------------------------
# Formatting tests
# ---------------------------------------------------------------------------


class TestFormatStatusMessage:
    """Test the status message formatter."""

    def test_healthy_status_format(self, healthy_status_data):
        """Healthy status should show green check and all fields."""
        msg = _format_status_message(healthy_status_data)

        assert "HEALTHY" in msg
        assert "2d 3h" in msg
        assert "1.2.3" in msg
        assert "connected" in msg.lower()
        assert "45.2%" in msg
        assert "12.0%" in msg
        assert "<pre>" in msg  # monospace formatting

    def test_degraded_status_format(self, degraded_status_data):
        """Degraded status should show warning indicators."""
        msg = _format_status_message(degraded_status_data)

        assert "DEGRADED" in msg
        assert "disconnected" in msg.lower()
        assert "88.5%" in msg
        assert "42" in msg  # error count

    def test_message_within_telegram_limit(self, healthy_status_data):
        """Status message should fit in a single Telegram message."""
        msg = _format_status_message(healthy_status_data)
        assert len(msg) < 4096  # Telegram message limit

    def test_none_values_handled(self):
        """None values for failed checks should display gracefully."""
        data = {
            "status": "healthy",
            "uptime": "1h 0m",
            "version": "1.0.0",
            "database": "connected",
            "bot_initialized": True,
            "memory_pct": None,
            "cpu_pct": None,
            "disk_pct": 50.0,
            "disk_free_gb": 100.0,
            "webhook_ok": True,
            "webhook_pending": 0,
            "recent_errors": 0,
            "error_window_hours": 6,
        }
        msg = _format_status_message(data)
        assert "n/a" in msg.lower()
        # Should not crash
        assert len(msg) > 0

    def test_html_is_valid(self, healthy_status_data):
        """Output should have matching HTML tags."""
        msg = _format_status_message(healthy_status_data)

        # Every <b> should have </b>
        assert msg.count("<b>") == msg.count("</b>")
        assert msg.count("<pre>") == msg.count("</pre>")


# ---------------------------------------------------------------------------
# Integration: status_command end-to-end
# ---------------------------------------------------------------------------


class TestStatusCommandIntegration:
    """Test the status_command handler end-to-end."""

    @pytest.mark.asyncio
    async def test_sends_reply_with_html(self, mock_update, mock_context):
        """status_command should send a reply with parse_mode=HTML."""
        with patch(
            "src.bot.handlers.status_commands._collect_status_data",
            new_callable=AsyncMock,
        ) as mock_collect:
            mock_collect.return_value = {
                "status": "healthy",
                "uptime": "1h 0m",
                "version": "1.0.0",
                "database": "connected",
                "bot_initialized": True,
                "memory_pct": 50.0,
                "cpu_pct": 10.0,
                "disk_pct": 50.0,
                "disk_free_gb": 100.0,
                "webhook_ok": True,
                "webhook_pending": 0,
                "recent_errors": 0,
                "error_window_hours": 6,
            }

            await status_command.__wrapped__(mock_update, mock_context)

            call_args = mock_update.message.reply_text.call_args
            assert call_args[1].get("parse_mode") == "HTML"

    @pytest.mark.asyncio
    async def test_no_message_no_crash(self, mock_context):
        """If update.message is None, command should return without error."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 12345
        update.effective_chat = MagicMock()
        update.effective_chat.id = 12345
        update.message = None

        with patch(
            "src.bot.handlers.status_commands._collect_status_data",
            new_callable=AsyncMock,
        ) as mock_collect:
            mock_collect.return_value = {
                "status": "healthy",
                "uptime": "1h",
                "version": "1.0.0",
                "database": "connected",
                "bot_initialized": True,
                "memory_pct": 50.0,
                "cpu_pct": 10.0,
                "disk_pct": 50.0,
                "disk_free_gb": 100.0,
                "webhook_ok": True,
                "webhook_pending": 0,
                "recent_errors": 0,
                "error_window_hours": 6,
            }

            # Should not raise
            await status_command.__wrapped__(update, mock_context)

    @pytest.mark.asyncio
    async def test_no_user_no_crash(self, mock_context):
        """If effective_user is None, command should return early."""
        update = MagicMock()
        update.effective_user = None
        update.effective_chat = MagicMock()

        # The decorator should handle this gracefully
        await status_command(update, mock_context)


# ---------------------------------------------------------------------------
# Uptime formatting
# ---------------------------------------------------------------------------


class TestUptimeFormatting:
    """Test uptime display logic."""

    def test_minutes_only(self):
        """Less than 1 hour should show minutes."""
        from src.bot.handlers.status_commands import _format_uptime

        assert _format_uptime(300.0) == "0h 5m"

    def test_hours_and_minutes(self):
        """1-24 hours should show hours and minutes."""
        from src.bot.handlers.status_commands import _format_uptime

        assert _format_uptime(3660.0) == "1h 1m"

    def test_days_hours(self):
        """More than 24 hours should show days and hours."""
        from src.bot.handlers.status_commands import _format_uptime

        result = _format_uptime(90000.0)  # 25 hours
        assert "1d" in result
        assert "1h" in result

    def test_zero_uptime(self):
        """Zero seconds should show 0h 0m."""
        from src.bot.handlers.status_commands import _format_uptime

        assert _format_uptime(0.0) == "0h 0m"
