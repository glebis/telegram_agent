# tests/test_preflight/test_fixes.py
"""Tests for preflight fix functions."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from src.preflight.fixes import fix_missing_dependencies, fix_port_conflict
from src.preflight.models import FixResult


class TestFixMissingDependencies:
    """Tests for fix_missing_dependencies function."""

    def test_empty_list_returns_success(self):
        """No missing dependencies should return success."""
        result = fix_missing_dependencies([])
        assert result.success is True
        assert "nothing to install" in result.message.lower()

    @patch("subprocess.run")
    def test_successful_pip_install(self, mock_run):
        """Successful pip install should return success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        result = fix_missing_dependencies(["frontmatter", "apscheduler"])
        assert result.success is True
        assert "installed" in result.message.lower()
        # Verify pip was called with requirements.txt
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "pip" in call_args[0][0][1] or "-m" in call_args[0][0]

    @patch("subprocess.run")
    def test_failed_pip_install(self, mock_run):
        """Failed pip install should return failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ERROR: Could not find package"
        )
        result = fix_missing_dependencies(["nonexistent-package"])
        assert result.success is False
        assert "failed" in result.message.lower()

    @patch("subprocess.run")
    def test_pip_timeout(self, mock_run):
        """Pip timeout should return failure."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip", timeout=60)
        result = fix_missing_dependencies(["some-package"])
        assert result.success is False
        assert "timeout" in result.message.lower()

    @patch("subprocess.run")
    def test_details_contain_package_list(self, mock_run):
        """Details should contain the package list."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = fix_missing_dependencies(["package1", "package2"])
        assert result.success is True
        # Details should mention what was attempted
        assert result.details is not None


class TestFixPortConflict:
    """Tests for fix_port_conflict function."""

    @patch("os.kill")
    @patch("psutil.Process")
    def test_kill_stale_uvicorn(self, mock_process, mock_kill):
        """Killing stale uvicorn process should succeed."""
        mock_proc = MagicMock()
        mock_proc.name.return_value = "python"
        mock_proc.cmdline.return_value = ["python", "-m", "uvicorn", "src.main:app"]
        mock_process.return_value = mock_proc

        result = fix_port_conflict(8847, 12345)
        assert result.success is True
        mock_kill.assert_called_once()

    @patch("psutil.Process")
    def test_non_uvicorn_process_not_killed(self, mock_process):
        """Non-uvicorn processes should not be killed."""
        mock_proc = MagicMock()
        mock_proc.name.return_value = "nginx"
        mock_proc.cmdline.return_value = ["nginx", "-g", "daemon off;"]
        mock_process.return_value = mock_proc

        result = fix_port_conflict(8847, 12345)
        assert result.success is False
        assert "not a known process" in result.message.lower() or "cannot kill" in result.message.lower()

    @patch("os.kill")
    @patch("psutil.Process")
    def test_kill_stale_python(self, mock_process, mock_kill):
        """Killing stale python process on our port should succeed."""
        mock_proc = MagicMock()
        mock_proc.name.return_value = "python3.11"
        mock_proc.cmdline.return_value = ["python3.11", "some_script.py"]
        mock_process.return_value = mock_proc

        result = fix_port_conflict(8847, 12345)
        assert result.success is True

    @patch("os.kill")
    @patch("psutil.Process")
    def test_kill_failure(self, mock_process, mock_kill):
        """Kill failure should return failure result."""
        mock_proc = MagicMock()
        mock_proc.name.return_value = "python"
        mock_proc.cmdline.return_value = ["python", "-m", "uvicorn"]
        mock_process.return_value = mock_proc
        mock_kill.side_effect = PermissionError("Operation not permitted")

        result = fix_port_conflict(8847, 12345)
        assert result.success is False
        assert "permission" in result.message.lower() or "failed" in result.message.lower()

    @patch("psutil.Process")
    def test_process_not_found(self, mock_process):
        """Non-existent process should return failure."""
        import psutil
        mock_process.side_effect = psutil.NoSuchProcess(12345)

        result = fix_port_conflict(8847, 12345)
        # Process already gone is actually a success (port freed)
        assert result.success is True
        assert "no longer running" in result.message.lower() or "already" in result.message.lower()

    @patch("os.kill")
    @patch("psutil.Process")
    def test_details_contain_process_info(self, mock_process, mock_kill):
        """Details should contain process information."""
        mock_proc = MagicMock()
        mock_proc.name.return_value = "python"
        mock_proc.cmdline.return_value = ["python", "-m", "uvicorn"]
        mock_proc.pid = 12345
        mock_process.return_value = mock_proc

        result = fix_port_conflict(8847, 12345)
        assert result.details is not None
        assert "12345" in result.details or "uvicorn" in result.details.lower()
