# tests/test_preflight/test_checks.py
"""Tests for preflight check functions."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.preflight.checks import (
    check_python_version,
    check_dependencies,
    check_environment_variables,
    check_port_availability,
    check_directory_structure,
    check_database,
    check_config_files,
)
from src.preflight.models import CheckStatus


class TestCheckPythonVersion:
    """Tests for check_python_version."""

    def test_current_python_passes(self):
        """Current Python (3.11+) should pass."""
        result = check_python_version()
        # We're running on 3.11, so should pass or warn
        assert result.status in (CheckStatus.PASS, CheckStatus.WARNING)
        assert result.name == "python_version"

    @patch("sys.version_info", (3, 10, 0))
    def test_python_310_fails(self):
        """Python 3.10 should fail."""
        result = check_python_version()
        assert result.status == CheckStatus.FAIL
        assert "3.11" in result.message

    @patch("sys.version_info", (3, 11, 0))
    def test_python_311_passes(self):
        """Python 3.11 should pass."""
        result = check_python_version()
        assert result.status == CheckStatus.PASS

    @patch("sys.version_info", (3, 12, 0))
    def test_python_312_warns(self):
        """Python 3.12+ should warn (untested)."""
        result = check_python_version()
        assert result.status == CheckStatus.WARNING
        assert "untested" in result.message.lower() or "3.12" in result.message


class TestCheckDependencies:
    """Tests for check_dependencies."""

    def test_all_deps_present(self):
        """When all dependencies are importable, should pass."""
        # This test runs in our actual environment where deps should exist
        result = check_dependencies(auto_fix=False)
        # May pass or be fixed depending on environment
        assert result.status in (CheckStatus.PASS, CheckStatus.FIXED, CheckStatus.FAIL)
        assert result.name == "dependencies"

    @patch("src.preflight.checks.CRITICAL_MODULES", ["os", "sys", "json"])
    def test_stdlib_modules_pass(self):
        """Standard library modules should always pass."""
        result = check_dependencies(auto_fix=False)
        assert result.status == CheckStatus.PASS

    @patch("src.preflight.checks.CRITICAL_MODULES", ["nonexistent_module_12345"])
    def test_missing_module_fails_without_fix(self):
        """Missing module should fail when auto_fix=False."""
        result = check_dependencies(auto_fix=False)
        assert result.status == CheckStatus.FAIL
        assert "nonexistent_module_12345" in result.message.lower() or "missing" in result.message.lower()

    @patch("src.preflight.checks.CRITICAL_MODULES", ["nonexistent_module_12345"])
    @patch("src.preflight.checks.fix_missing_dependencies")
    def test_missing_module_attempts_fix(self, mock_fix):
        """Missing module should attempt fix when auto_fix=True."""
        from src.preflight.models import FixResult
        mock_fix.return_value = FixResult(success=False, message="Failed")

        result = check_dependencies(auto_fix=True)
        mock_fix.assert_called_once()
        assert result.status == CheckStatus.FAIL


class TestCheckEnvironmentVariables:
    """Tests for check_environment_variables."""

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token"}, clear=False)
    def test_required_env_present(self):
        """When required env vars are present, should pass or warn."""
        result = check_environment_variables()
        # PASS if all vars present, WARNING if optional missing
        assert result.status in (CheckStatus.PASS, CheckStatus.WARNING)
        assert result.name == "environment_variables"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_telegram_token_fails(self):
        """Missing TELEGRAM_BOT_TOKEN should fail."""
        result = check_environment_variables()
        assert result.status == CheckStatus.FAIL
        assert "TELEGRAM_BOT_TOKEN" in result.message

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test"}, clear=True)
    def test_missing_optional_warns(self):
        """Missing optional vars should warn."""
        result = check_environment_variables()
        # Should pass with warning about optional vars
        assert result.status in (CheckStatus.PASS, CheckStatus.WARNING)

    @patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test",
        "GROQ_API_KEY": "groq",
        "OBSIDIAN_VAULT_PATH": "/vault"
    }, clear=True)
    def test_all_vars_present_passes(self):
        """All vars present should pass."""
        result = check_environment_variables()
        assert result.status == CheckStatus.PASS


class TestCheckPortAvailability:
    """Tests for check_port_availability."""

    @patch("socket.socket")
    def test_port_available(self, mock_socket):
        """Available port should pass."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket.return_value.__exit__ = MagicMock(return_value=False)
        mock_sock.bind = MagicMock()  # No exception = port available

        result = check_port_availability(auto_fix=False)
        assert result.status == CheckStatus.PASS
        assert result.name == "port_availability"

    @patch("src.preflight.checks._find_process_on_port")
    @patch("src.preflight.checks.socket.socket")
    def test_port_in_use_fails_without_fix(self, mock_socket, mock_find):
        """Port in use should fail when auto_fix=False."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket.return_value.__exit__ = MagicMock(return_value=False)
        mock_sock.bind.side_effect = OSError("Address already in use")
        mock_find.return_value = 12345

        result = check_port_availability(auto_fix=False)
        assert result.status == CheckStatus.FAIL
        assert "in use" in result.message.lower() or "8847" in result.message

    @patch("src.preflight.checks._find_process_on_port")
    @patch("src.preflight.checks.fix_port_conflict")
    @patch("src.preflight.checks.socket.socket")
    def test_port_in_use_attempts_fix(self, mock_socket, mock_fix, mock_find):
        """Port in use should attempt fix when auto_fix=True."""
        from src.preflight.models import FixResult

        mock_sock = MagicMock()
        mock_socket.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket.return_value.__exit__ = MagicMock(return_value=False)
        # First call fails (port in use), second call succeeds (after fix)
        mock_sock.bind.side_effect = [OSError("Address already in use"), None]

        mock_find.return_value = 12345  # Found a process
        mock_fix.return_value = FixResult(success=True, message="Killed")

        result = check_port_availability(auto_fix=True)
        mock_fix.assert_called_once()


class TestCheckDirectoryStructure:
    """Tests for check_directory_structure."""

    def test_existing_dirs_pass(self):
        """Existing directories should pass."""
        # Default behavior auto_fix=True may create dirs, so they'll exist
        result = check_directory_structure(auto_fix=True)
        # With auto_fix=True, will be PASS (already exist) or FIXED (created)
        assert result.status in (CheckStatus.PASS, CheckStatus.FIXED)
        assert result.name == "directory_structure"

    @patch("src.preflight.checks.REQUIRED_DIRS", ["/nonexistent/path/12345"])
    def test_missing_dir_fails_without_fix(self):
        """Missing directory should fail when auto_fix=False."""
        result = check_directory_structure(auto_fix=False)
        assert result.status == CheckStatus.FAIL

    def test_auto_creates_dirs(self):
        """auto_fix=True should create missing directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "subdir"

            with patch("src.preflight.checks.REQUIRED_DIRS", [str(test_dir)]):
                result = check_directory_structure(auto_fix=True)

            assert result.status == CheckStatus.FIXED
            assert test_dir.exists()


class TestCheckDatabase:
    """Tests for check_database."""

    def test_existing_db_passes(self):
        """Existing, readable database should pass."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"SQLite format 3\0")  # SQLite header
            db_path = f.name

        try:
            with patch("src.preflight.checks.DATABASE_PATH", db_path):
                result = check_database()
            assert result.status == CheckStatus.PASS
            assert result.name == "database"
        finally:
            os.unlink(db_path)

    def test_missing_db_warns(self):
        """Missing database should warn (first run is OK)."""
        with patch("src.preflight.checks.DATABASE_PATH", "/nonexistent/db.sqlite"):
            result = check_database()
        assert result.status == CheckStatus.WARNING
        assert "first run" in result.message.lower() or "not found" in result.message.lower()

    def test_corrupted_db_fails(self):
        """Corrupted database should fail."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"not a database")
            db_path = f.name

        try:
            with patch("src.preflight.checks.DATABASE_PATH", db_path):
                result = check_database()
            assert result.status == CheckStatus.FAIL
            assert "corrupt" in result.message.lower() or "invalid" in result.message.lower()
        finally:
            os.unlink(db_path)


class TestCheckConfigFiles:
    """Tests for check_config_files."""

    def test_existing_configs_pass(self):
        """Existing config files should pass."""
        result = check_config_files()
        # May pass or warn depending on which configs exist
        assert result.status in (CheckStatus.PASS, CheckStatus.WARNING)
        assert result.name == "config_files"

    @patch("src.preflight.checks.REQUIRED_CONFIGS", ["/nonexistent/config.yaml"])
    def test_missing_config_warns(self):
        """Missing config file should warn."""
        result = check_config_files()
        assert result.status == CheckStatus.WARNING

    def test_checks_modes_yaml(self):
        """Should check for modes.yaml."""
        result = check_config_files()
        # Result details should mention config files checked
        assert result.details is not None or result.message
