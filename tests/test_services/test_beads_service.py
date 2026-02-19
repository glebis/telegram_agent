from unittest.mock import AsyncMock, patch

import pytest

from src.services.beads_service import (
    BeadsCommandError,
    BeadsNotInstalled,
    BeadsService,
)


class TestBeadsService:
    """Tests for BeadsService."""

    async def test_run_bd_raises_not_installed_when_binary_missing(self):
        """Verify _run_bd raises BeadsNotInstalled when bd binary not found."""
        service = BeadsService()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_subprocess.side_effect = FileNotFoundError(
                "[Errno 2] No such file or directory: 'bd'"
            )

            with pytest.raises(BeadsNotInstalled) as exc_info:
                await service._run_bd("ready")

            assert "install" in str(exc_info.value).lower()
            assert "bead" in str(exc_info.value).lower()

    async def test_run_bd_raises_command_error_on_nonzero_exit(self):
        """Verify _run_bd raises BeadsCommandError with stderr on failure."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b"",
            b"Error: not initialized",
        )
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(BeadsCommandError) as exc_info:
                await service._run_bd("ready")

            assert exc_info.value.returncode == 1
            assert exc_info.value.stderr == "Error: not initialized"
            assert "failed" in str(exc_info.value).lower()

    async def test_run_bd_parses_json_output(self):
        """Verify _run_bd returns parsed JSON from stdout."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"issues": [{"id": "bd-a1b2", "title": "Test"}]}',
            b"",
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service._run_bd("list")

        assert result == {"issues": [{"id": "bd-a1b2", "title": "Test"}]}

    async def test_run_bd_returns_empty_dict_on_empty_stdout(self):
        """Verify _run_bd returns {} when bd produces no output."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service._run_bd("init")

        assert result == {}

    async def test_run_bd_passes_json_flag_and_args(self):
        """Verify _run_bd appends --json and passes all args to bd."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"{}", b"")
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await service._run_bd("create", "Fix bug", "-p", "1")

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert call_args == ("bd", "create", "Fix bug", "-p", "1", "--json")


class TestBeadsInit:
    """Tests for BeadsService.init()."""

    async def test_init_calls_bd_init_stealth(self):
        """Verify init() runs bd init --stealth --quiet."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"initialized": true}',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.init()

        call_args = mock_exec.call_args[0]
        assert "init" in call_args
        assert "--stealth" in call_args
        assert "--quiet" in call_args
        assert result == {"initialized": True}

    async def test_init_handles_already_initialized(self):
        """Verify init() succeeds silently if already initialized."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"already_initialized": true}',
            b"",
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service.init()

        assert result is not None


class TestBeadsCreateIssue:
    """Tests for BeadsService.create_issue()."""

    async def test_create_issue_with_title_and_priority(self):
        """Verify create_issue passes title, priority, type to bd create."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"id": "bd-x1y2", "title": "Fix auth bug", "priority": 0}',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.create_issue(
                "Fix auth bug", priority=0, issue_type="bug"
            )

        call_args = mock_exec.call_args[0]
        assert "create" in call_args
        assert "Fix auth bug" in call_args
        assert "-p" in call_args
        assert "0" in call_args
        assert "-t" in call_args
        assert "bug" in call_args
        assert result["id"] == "bd-x1y2"

    async def test_create_issue_defaults(self):
        """Verify create_issue uses sensible defaults for priority and type."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"id": "bd-a1b2", "title": "Do thing"}',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.create_issue("Do thing")

        call_args = mock_exec.call_args[0]
        assert "-p" in call_args
        assert "-t" in call_args
        assert "task" in call_args  # default type
        assert result["id"] == "bd-a1b2"


class TestBeadsQueryIssues:
    """Tests for query operations: ready(), list_issues(), show()."""

    async def test_ready_returns_unblocked_issues(self):
        """Verify ready() calls bd ready and returns issue list."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'[{"id": "bd-a1b2", "title": "Fix bug", "status": "open"}]',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.ready()

        call_args = mock_exec.call_args[0]
        assert "ready" in call_args
        assert isinstance(result, list)
        assert result[0]["id"] == "bd-a1b2"

    async def test_list_issues_returns_all(self):
        """Verify list_issues() calls bd list and returns issues."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'[{"id": "bd-a1b2"}, {"id": "bd-c3d4"}]',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.list_issues()

        call_args = mock_exec.call_args[0]
        assert "list" in call_args
        assert isinstance(result, list)
        assert len(result) == 2

    async def test_show_returns_issue_details(self):
        """Verify show() calls bd show <id> and returns issue dict."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"id": "bd-a1b2", "title": "Fix bug", "description": "Details"}',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.show("bd-a1b2")

        call_args = mock_exec.call_args[0]
        assert "show" in call_args
        assert "bd-a1b2" in call_args
        assert result["id"] == "bd-a1b2"
        assert result["description"] == "Details"


class TestBeadsMutateIssues:
    """Tests for mutation operations: update(), close(), add_dependency()."""

    async def test_update_claims_issue(self):
        """Verify update() with claim passes --claim flag."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"id": "bd-a1b2", "status": "in_progress"}',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.update(
                "bd-a1b2", status="in_progress", claim=True
            )

        call_args = mock_exec.call_args[0]
        assert "update" in call_args
        assert "bd-a1b2" in call_args
        assert "--status" in call_args
        assert "in_progress" in call_args
        assert "--claim" in call_args
        assert result["status"] == "in_progress"

    async def test_update_without_claim(self):
        """Verify update() without claim omits --claim flag."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"id": "bd-a1b2", "status": "in_progress"}',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await service.update("bd-a1b2", status="in_progress")

        call_args = mock_exec.call_args[0]
        assert "--claim" not in call_args

    async def test_close_issue(self):
        """Verify close() passes issue ID and reason."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'{"id": "bd-a1b2", "status": "closed"}',
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            result = await service.close("bd-a1b2", reason="Completed")

        call_args = mock_exec.call_args[0]
        assert "close" in call_args
        assert "bd-a1b2" in call_args
        assert "--reason" in call_args
        assert "Completed" in call_args
        assert result["status"] == "closed"

    async def test_add_dependency(self):
        """Verify add_dependency() calls bd dep add child parent."""
        service = BeadsService()

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"{}", b"")
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await service.add_dependency("bd-c3d4", "bd-a1b2")

        call_args = mock_exec.call_args[0]
        assert "dep" in call_args
        assert "add" in call_args
        assert "bd-c3d4" in call_args
        assert "bd-a1b2" in call_args
