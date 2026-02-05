"""
Tests for subprocess_sandbox.py -- sandboxed subprocess execution with
timeout enforcement and output capping.
"""

import sys

from src.services.subprocess_sandbox import SubprocessResult, run_sandboxed


class TestRunSandboxed:
    """Basic subprocess sandbox tests."""

    def test_simple_command_succeeds(self):
        result = run_sandboxed(["echo", "hello"])
        assert result.success
        assert "hello" in result.stdout

    def test_return_code_captured(self):
        result = run_sandboxed(["false"])
        assert not result.success
        assert result.return_code != 0

    def test_stderr_captured(self):
        result = run_sandboxed(
            [sys.executable, "-c", "import sys; print('err', file=sys.stderr)"]
        )
        assert "err" in result.stderr


class TestTimeout:
    """Timeout enforcement."""

    def test_timeout_kills_process(self):
        """A command that exceeds the timeout should be killed."""
        result = run_sandboxed(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout_seconds=1,
        )
        assert not result.success
        assert result.timed_out
        assert "timeout" in (result.error or "").lower()

    def test_fast_command_not_timed_out(self):
        result = run_sandboxed(["echo", "fast"], timeout_seconds=10)
        assert result.success
        assert not result.timed_out


class TestOutputCapping:
    """Output size limits."""

    def test_stdout_capped(self):
        """Output exceeding max_output_bytes should be truncated."""
        # Generate ~10KB of output, cap at 100 bytes
        result = run_sandboxed(
            [sys.executable, "-c", "print('x' * 10000)"],
            max_output_bytes=100,
        )
        # The result's stdout should be at most max_output_bytes
        assert (
            len(result.stdout.encode("utf-8")) <= 200
        )  # some tolerance for OS buffering

    def test_stderr_capped(self):
        """Stderr exceeding max_output_bytes should be truncated."""
        result = run_sandboxed(
            [sys.executable, "-c", "import sys; print('x' * 10000, file=sys.stderr)"],
            max_output_bytes=100,
        )
        assert len(result.stderr.encode("utf-8")) <= 200


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_nonexistent_command(self):
        result = run_sandboxed(["nonexistent_binary_xyz123"])
        assert not result.success
        assert result.error is not None

    def test_empty_command_list(self):
        result = run_sandboxed([])
        assert not result.success

    def test_result_dataclass_fields(self):
        result = run_sandboxed(["echo", "test"])
        assert isinstance(result, SubprocessResult)
        assert hasattr(result, "success")
        assert hasattr(result, "stdout")
        assert hasattr(result, "stderr")
        assert hasattr(result, "return_code")
        assert hasattr(result, "error")
        assert hasattr(result, "timed_out")
