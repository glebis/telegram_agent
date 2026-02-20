"""Tests for beads Telegram command handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.handlers.beads_commands import bd_command


def _make_update_context(args=None):
    """Create mock Update and Context for command testing."""
    update = MagicMock()
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123

    context = MagicMock()
    context.args = args or []

    return update, context


@pytest.fixture(autouse=True)
def _mock_beads(monkeypatch):
    """Provide a mock BeadsService for all tests via monkeypatch."""
    mock_svc = AsyncMock()
    mock_svc.ready.return_value = []
    mock_svc.list_issues.return_value = []
    mock_svc.show.return_value = {}
    mock_svc.create_issue.return_value = {"id": "bd-test"}
    mock_svc.close.return_value = {}
    mock_svc.update.return_value = {}
    mock_svc.add_dependency.return_value = {}
    mock_svc.stats.return_value = {}

    import src.services.beads_service as mod

    monkeypatch.setattr(mod, "_beads_service", mock_svc)
    return mock_svc


class TestBdReady:
    """Tests for /bd (ready issues)."""

    async def test_bd_no_args_shows_ready(self, _mock_beads):
        """Verify /bd with no args calls ready() and formats output."""
        _mock_beads.ready.return_value = [
            {"id": "bd-a1b2", "title": "Fix bug", "priority": 1},
            {"id": "bd-c3d4", "title": "Add test", "priority": 2},
        ]
        update, context = _make_update_context([])
        await bd_command(update, context)

        _mock_beads.ready.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "bd-a1b2" in text
        assert "Fix bug" in text
        assert "bd-c3d4" in text

    async def test_bd_empty_ready(self, _mock_beads):
        """Verify /bd shows message when no ready issues."""
        _mock_beads.ready.return_value = []
        update, context = _make_update_context([])
        await bd_command(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "No unblocked" in text


class TestBdAdd:
    """Tests for /bd add."""

    async def test_bd_add_creates_issue(self, _mock_beads):
        """Verify /bd add <title> creates issue and replies with ID."""
        _mock_beads.create_issue.return_value = {
            "id": "bd-x1y2",
            "title": "Fix auth flow",
        }
        update, context = _make_update_context(["add", "Fix", "auth", "flow"])
        await bd_command(update, context)

        _mock_beads.create_issue.assert_called_once_with(
            "Fix auth flow", priority=2, issue_type="task"
        )
        text = update.message.reply_text.call_args[0][0]
        assert "bd-x1y2" in text

    async def test_bd_add_with_priority(self, _mock_beads):
        """Verify /bd add <title> p0 sets priority."""
        _mock_beads.create_issue.return_value = {"id": "bd-z9"}
        update, context = _make_update_context(["add", "Critical", "fix", "p0"])
        await bd_command(update, context)

        _mock_beads.create_issue.assert_called_once_with(
            "Critical fix", priority=0, issue_type="task"
        )

    async def test_bd_add_with_type(self, _mock_beads):
        """Verify /bd add <title> bug sets type."""
        _mock_beads.create_issue.return_value = {"id": "bd-z9"}
        update, context = _make_update_context(["add", "Memory", "leak", "bug"])
        await bd_command(update, context)

        _mock_beads.create_issue.assert_called_once_with(
            "Memory leak", priority=2, issue_type="bug"
        )

    async def test_bd_add_with_priority_and_type(self, _mock_beads):
        """Verify /bd add <title> p1 bug sets both."""
        _mock_beads.create_issue.return_value = {"id": "bd-z9"}
        update, context = _make_update_context(["add", "Auth", "issue", "bug", "p1"])
        await bd_command(update, context)

        _mock_beads.create_issue.assert_called_once_with(
            "Auth issue", priority=1, issue_type="bug"
        )

    async def test_bd_quick_add_unknown_subcommand(self, _mock_beads):
        """Verify /bd <title> (no subcommand) creates issue."""
        _mock_beads.create_issue.return_value = {"id": "bd-z9"}
        update, context = _make_update_context(["Buy", "groceries"])
        await bd_command(update, context)

        _mock_beads.create_issue.assert_called_once_with(
            "Buy groceries", priority=2, issue_type="task"
        )


class TestBdDone:
    """Tests for /bd done."""

    async def test_bd_done_closes_issue(self, _mock_beads):
        """Verify /bd done <id> closes the issue."""
        _mock_beads.close.return_value = {
            "id": "bd-a1b2",
            "status": "closed",
        }
        update, context = _make_update_context(["done", "bd-a1b2"])
        await bd_command(update, context)

        _mock_beads.close.assert_called_once_with("bd-a1b2", reason="Done")
        text = update.message.reply_text.call_args[0][0]
        assert "Closed" in text

    async def test_bd_done_with_reason(self, _mock_beads):
        """Verify /bd done <id> <reason> passes reason."""
        update, context = _make_update_context(
            ["done", "bd-a1b2", "Fixed", "in", "commit", "abc"]
        )
        await bd_command(update, context)

        _mock_beads.close.assert_called_once_with(
            "bd-a1b2", reason="Fixed in commit abc"
        )


class TestBdShow:
    """Tests for /bd show."""

    async def test_bd_show_displays_issue(self, _mock_beads):
        """Verify /bd show <id> formats issue details."""
        _mock_beads.show.return_value = {
            "id": "bd-a1b2",
            "title": "Fix bug",
            "status": "open",
            "priority": 1,
            "type": "bug",
            "description": "Something is broken",
        }
        update, context = _make_update_context(["show", "bd-a1b2"])
        await bd_command(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "bd-a1b2" in text
        assert "Fix bug" in text
        assert "P1" in text
        assert "Something is broken" in text


class TestBdBlock:
    """Tests for /bd block."""

    async def test_bd_block_adds_dependency(self, _mock_beads):
        """Verify /bd block <child> <parent> creates dependency."""
        update, context = _make_update_context(["block", "bd-c3d4", "bd-a1b2"])
        await bd_command(update, context)

        _mock_beads.add_dependency.assert_called_once_with("bd-c3d4", "bd-a1b2")
        text = update.message.reply_text.call_args[0][0]
        assert "blocked by" in text


class TestBdErrorHandling:
    """Tests for error handling in bd commands."""

    async def test_bd_handles_service_error(self, _mock_beads):
        """Verify bd commands show error message on failure."""
        _mock_beads.ready.side_effect = Exception("bd not initialized")
        update, context = _make_update_context([])
        await bd_command(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert "error" in text.lower() or "not initialized" in text
