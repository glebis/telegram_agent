"""
Tests for src/utils/tool_check.py — CLI tool and Python package detection.

Tests cover:
- check_tool() for present and missing CLI executables
- check_python_package() for importable and missing packages
- get_missing_tools() and get_missing_python_packages() filtering
- format_install_hint() platform-specific output
- format_missing_tools_error() multi-tool formatting
- Worker queue graceful failure on missing tools
"""

from unittest.mock import patch

import pytest

from src.utils.tool_check import (
    JOB_TOOL_REQUIREMENTS,
    _get_platform_key,
    check_python_package,
    check_tool,
    format_install_hint,
    format_missing_tools_error,
    get_missing_python_packages,
    get_missing_tools,
)


# =============================================================================
# check_tool
# =============================================================================


class TestCheckTool:
    """Tests for check_tool()."""

    def test_finds_tool_on_path(self):
        """check_tool returns True for a tool known to exist (python3)."""
        # python3 is guaranteed to be on PATH in this project's test env
        assert check_tool("python3") is True

    def test_missing_tool_returns_false(self):
        """check_tool returns False for a clearly non-existent tool."""
        assert check_tool("nonexistent_tool_xyz_999") is False

    @patch("src.utils.tool_check.shutil.which", return_value="/usr/bin/fake")
    def test_delegates_to_shutil_which(self, mock_which):
        """check_tool delegates to shutil.which and respects its result."""
        assert check_tool("fake_tool") is True
        mock_which.assert_called_once_with("fake_tool")

    @patch("src.utils.tool_check.shutil.which", return_value=None)
    def test_returns_false_when_which_returns_none(self, mock_which):
        """check_tool returns False when shutil.which returns None."""
        assert check_tool("missing") is False


# =============================================================================
# check_python_package
# =============================================================================


class TestCheckPythonPackage:
    """Tests for check_python_package()."""

    def test_finds_importable_package(self):
        """check_python_package returns True for a package in the environment."""
        assert check_python_package("os") is True
        assert check_python_package("sys") is True

    def test_missing_package_returns_false(self):
        """check_python_package returns False for a non-existent package."""
        assert check_python_package("nonexistent_pkg_xyz_999") is False

    def test_finds_third_party_package(self):
        """check_python_package finds installed third-party packages."""
        # pytest is guaranteed to be installed since we are running it
        assert check_python_package("pytest") is True

    @patch("src.utils.tool_check.importlib.import_module", side_effect=ImportError)
    def test_import_error_returns_false(self, mock_import):
        """check_python_package returns False when import raises ImportError."""
        assert check_python_package("broken_pkg") is False


# =============================================================================
# get_missing_tools / get_missing_python_packages
# =============================================================================


class TestGetMissing:
    """Tests for get_missing_tools() and get_missing_python_packages()."""

    @patch("src.utils.tool_check.shutil.which")
    def test_get_missing_tools_all_present(self, mock_which):
        """Returns empty list when all tools are present."""
        mock_which.return_value = "/usr/bin/tool"
        assert get_missing_tools(["curl", "git"]) == []

    @patch("src.utils.tool_check.shutil.which")
    def test_get_missing_tools_some_missing(self, mock_which):
        """Returns only the missing tools."""
        mock_which.side_effect = lambda name: "/usr/bin/curl" if name == "curl" else None
        result = get_missing_tools(["curl", "marker_single"])
        assert result == ["marker_single"]

    @patch("src.utils.tool_check.shutil.which", return_value=None)
    def test_get_missing_tools_all_missing(self, mock_which):
        """Returns all tools when none are present."""
        result = get_missing_tools(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_get_missing_tools_empty_input(self):
        """Returns empty list for empty input."""
        assert get_missing_tools([]) == []

    def test_get_missing_python_packages_all_present(self):
        """Returns empty list when all packages are importable."""
        assert get_missing_python_packages(["os", "sys"]) == []

    def test_get_missing_python_packages_some_missing(self):
        """Returns only the missing packages."""
        result = get_missing_python_packages(["os", "nonexistent_pkg_xyz"])
        assert result == ["nonexistent_pkg_xyz"]

    def test_get_missing_python_packages_empty_input(self):
        """Returns empty list for empty input."""
        assert get_missing_python_packages([]) == []


# =============================================================================
# _get_platform_key
# =============================================================================


class TestGetPlatformKey:
    """Tests for _get_platform_key()."""

    @patch("src.utils.tool_check.platform.system", return_value="Darwin")
    def test_macos(self, _mock):
        assert _get_platform_key() == "darwin"

    @patch("src.utils.tool_check.platform.system", return_value="Linux")
    def test_linux(self, _mock):
        assert _get_platform_key() == "linux"

    @patch("src.utils.tool_check.platform.system", return_value="Windows")
    def test_windows(self, _mock):
        assert _get_platform_key() == "windows"

    @patch("src.utils.tool_check.platform.system", return_value="FreeBSD")
    def test_unknown_defaults_to_linux(self, _mock):
        assert _get_platform_key() == "linux"


# =============================================================================
# format_install_hint
# =============================================================================


class TestFormatInstallHint:
    """Tests for format_install_hint()."""

    @patch("src.utils.tool_check.platform.system", return_value="Darwin")
    def test_known_tool_macos(self, _mock):
        """Returns brew/pip hint on macOS for a known tool."""
        hint = format_install_hint("curl")
        assert "brew install curl" in hint

    @patch("src.utils.tool_check.platform.system", return_value="Linux")
    def test_known_tool_linux(self, _mock):
        """Returns apt hint on Linux for a known tool."""
        hint = format_install_hint("curl")
        assert "apt-get install curl" in hint

    @patch("src.utils.tool_check.platform.system", return_value="Darwin")
    def test_pip_tool_macos(self, _mock):
        """Returns pip hint for a pip-installable tool on macOS."""
        hint = format_install_hint("marker_single")
        assert "pip install marker-pdf" in hint

    @patch("src.utils.tool_check.platform.system", return_value="Linux")
    def test_pip_tool_linux(self, _mock):
        """Returns pip hint for a pip-installable tool on Linux."""
        hint = format_install_hint("marker_single")
        assert "pip install marker-pdf" in hint

    @patch("src.utils.tool_check.platform.system", return_value="Darwin")
    def test_unknown_tool_macos(self, _mock):
        """Returns generic macOS hint for an unknown tool."""
        hint = format_install_hint("completely_unknown_tool")
        assert "macOS" in hint
        assert "completely_unknown_tool" in hint

    @patch("src.utils.tool_check.platform.system", return_value="Linux")
    def test_unknown_tool_linux(self, _mock):
        """Returns generic Linux hint for an unknown tool."""
        hint = format_install_hint("completely_unknown_tool")
        assert "Linux" in hint
        assert "completely_unknown_tool" in hint

    def test_hint_is_nonempty_string(self):
        """format_install_hint always returns a non-empty string."""
        for tool in ["curl", "marker_single", "unknown"]:
            hint = format_install_hint(tool)
            assert isinstance(hint, str)
            assert len(hint) > 0


# =============================================================================
# format_missing_tools_error
# =============================================================================


class TestFormatMissingToolsError:
    """Tests for format_missing_tools_error()."""

    def test_empty_list_returns_empty_string(self):
        """No missing tools produces an empty string."""
        assert format_missing_tools_error([]) == ""

    @patch("src.utils.tool_check.platform.system", return_value="Darwin")
    def test_single_missing_tool(self, _mock):
        """Single missing tool produces a readable error."""
        result = format_missing_tools_error(["curl"])
        assert "curl" in result
        assert "Missing required tool" in result

    @patch("src.utils.tool_check.platform.system", return_value="Linux")
    def test_multiple_missing_tools(self, _mock):
        """Multiple missing tools each get their own hint line."""
        result = format_missing_tools_error(["curl", "marker_single"])
        assert "curl" in result
        assert "marker_single" in result
        # Each tool should have its own hint line
        lines = result.strip().split("\n")
        assert len(lines) >= 3  # header + 2 hint lines


# =============================================================================
# JOB_TOOL_REQUIREMENTS constant
# =============================================================================


class TestJobToolRequirements:
    """Tests for the JOB_TOOL_REQUIREMENTS mapping."""

    def test_pdf_convert_requires_marker_and_curl(self):
        assert "marker_single" in JOB_TOOL_REQUIREMENTS["pdf_convert"]
        assert "curl" in JOB_TOOL_REQUIREMENTS["pdf_convert"]

    def test_pdf_save_requires_marker_and_curl(self):
        assert "marker_single" in JOB_TOOL_REQUIREMENTS["pdf_save"]
        assert "curl" in JOB_TOOL_REQUIREMENTS["pdf_save"]

    def test_custom_command_not_in_requirements(self):
        """custom_command is validated via allowlist, not tool requirements."""
        assert "custom_command" not in JOB_TOOL_REQUIREMENTS


# =============================================================================
# Worker queue integration — graceful failure on missing tools
# =============================================================================


class TestWorkerToolGating:
    """Tests that worker_queue.JobExecutor gates on missing tools."""

    def test_check_required_tools_raises_on_missing(self):
        """JobExecutor._check_required_tools raises RuntimeError for missing tools."""
        # Import inside test to avoid module-level side effects from worker_queue
        import sys
        import os

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
        try:
            from worker_queue import JobExecutor
        finally:
            sys.path.pop(0)

        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="marker_single"):
                JobExecutor._check_required_tools("pdf_convert")

    def test_check_required_tools_passes_when_present(self):
        """JobExecutor._check_required_tools does not raise when tools exist."""
        import sys
        import os

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
        try:
            from worker_queue import JobExecutor
        finally:
            sys.path.pop(0)

        with patch("shutil.which", return_value="/usr/bin/fake"):
            # Should not raise
            JobExecutor._check_required_tools("pdf_convert")

    def test_check_required_tools_no_requirements(self):
        """JobExecutor._check_required_tools is a no-op for types with no requirements."""
        import sys
        import os

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
        try:
            from worker_queue import JobExecutor
        finally:
            sys.path.pop(0)

        # Should not raise for unknown or requirement-free job types
        JobExecutor._check_required_tools("custom_command")
        JobExecutor._check_required_tools("research")
