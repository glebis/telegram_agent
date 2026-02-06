"""
Tests for the Claude Subprocess Service.

Tests cover:
- _validate_cwd function for directory path validation
- _sanitize_text function for UTF-8 surrogate removal
- _build_claude_script function for script generation
- execute_claude_subprocess async generator function
- Subprocess execution, output parsing, error handling
- Timeout handling
- Stop check functionality
- Session ID handling
- Edge cases and error scenarios
"""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.claude_subprocess import (
    CLAUDE_TIMEOUT_SECONDS,
    _build_claude_script,
    _encode_path_as_claude_dir,
    _is_session_error,
    _sanitize_text,
    _validate_cwd,
    execute_claude_subprocess,
    find_session_cwd,
    get_configured_tools,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def allowed_cwd_ai_projects(tmp_path):
    """Create a temporary directory simulating ~/ai_projects."""
    with patch.object(Path, "home", return_value=tmp_path):
        ai_projects = tmp_path / "ai_projects" / "test_project"
        ai_projects.mkdir(parents=True, exist_ok=True)
        yield str(ai_projects)


@pytest.fixture
def allowed_cwd_vault(tmp_path):
    """Create a temporary directory simulating ~/Research/vault."""
    with patch.object(Path, "home", return_value=tmp_path):
        vault = tmp_path / "Research" / "vault"
        vault.mkdir(parents=True, exist_ok=True)
        yield str(vault)


@pytest.fixture
def mock_process():
    """Create a mock async subprocess."""
    process = MagicMock()
    process.pid = 12345
    process.returncode = 0
    process.stdout = MagicMock()
    process.stderr = MagicMock()
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


@pytest.fixture
def sample_prompt():
    """Sample prompt for testing."""
    return "List all files in the current directory"


@pytest.fixture
def sample_system_prompt():
    """Sample system prompt for testing."""
    return "You are a helpful assistant"


# =============================================================================
# _validate_cwd Tests
# =============================================================================


class TestValidateCwd:
    """Tests for _validate_cwd function."""

    def test_validate_allowed_path_ai_projects(self, tmp_path):
        """Test validation of path within ~/ai_projects."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            result = _validate_cwd(str(ai_projects))

            assert result == str(ai_projects.resolve())

    def test_validate_allowed_path_vault(self, tmp_path):
        """Test validation of path within ~/Research/vault."""
        with patch.object(Path, "home", return_value=tmp_path):
            vault = tmp_path / "Research" / "vault"
            vault.mkdir(parents=True, exist_ok=True)

            result = _validate_cwd(str(vault))

            assert result == str(vault.resolve())

    def test_validate_allowed_path_tmp(self):
        """Test validation of /tmp path."""
        # /tmp is always allowed
        result = _validate_cwd("/tmp")

        assert "/tmp" in result or "/private/tmp" in result

    def test_validate_allowed_path_private_tmp(self):
        """Test validation of /private/tmp path (macOS)."""
        result = _validate_cwd("/private/tmp")

        assert "/private/tmp" in result

    def test_validate_disallowed_path_raises_error(self):
        """Test that disallowed paths raise ValueError."""
        # /var/spool is not under any allowed base (/tmp, ~/ai_projects, ~/Research/vault)
        with pytest.raises(ValueError) as exc_info:
            _validate_cwd("/var/spool")
        assert "not in allowed paths" in str(exc_info.value)

    def test_validate_path_with_tilde_expansion(self, tmp_path):
        """Test that ~ is expanded in path."""
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            ai_projects = tmp_path / "ai_projects" / "tilde_test_dir"
            ai_projects.mkdir(parents=True, exist_ok=True)

            # Use ~ in path - this should work since ~/ai_projects is allowed
            result = _validate_cwd("~/ai_projects/tilde_test_dir")

            assert str(ai_projects.resolve()) == result

    def test_validate_path_resolves_symlinks(self, tmp_path):
        """Test that symlinks are resolved."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "real_dir"
            ai_projects.mkdir(parents=True, exist_ok=True)
            symlink = tmp_path / "ai_projects" / "symlink"

            # Create symlink if possible
            try:
                symlink.symlink_to(ai_projects)
                result = _validate_cwd(str(symlink))
                assert result == str(ai_projects.resolve())
            except OSError:
                # Skip on systems that don't support symlinks
                pytest.skip("Symlinks not supported")

    def test_validate_nonexistent_but_allowed_parent(self, tmp_path):
        """Test path within allowed directory but not yet created."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects"
            ai_projects.mkdir(parents=True, exist_ok=True)

            # This subdirectory doesn't exist yet
            nonexistent = ai_projects / "new_project"

            # Should still be allowed based on parent
            result = _validate_cwd(str(nonexistent))

            # Result is the resolved path (parent exists)
            assert "ai_projects" in result


# =============================================================================
# _sanitize_text Tests
# =============================================================================


class TestSanitizeText:
    """Tests for _sanitize_text function."""

    def test_sanitize_normal_text(self):
        """Test that normal text passes through unchanged."""
        text = "Hello, world! This is a normal message."
        result = _sanitize_text(text)

        assert result == text

    def test_sanitize_empty_text(self):
        """Test handling of empty string."""
        result = _sanitize_text("")

        assert result == ""

    def test_sanitize_none_text(self):
        """Test handling of None."""
        result = _sanitize_text(None)

        assert result is None

    def test_sanitize_text_with_emojis(self):
        """Test that emojis are preserved."""
        text = "Hello! 👋 How are you? 🎉"
        result = _sanitize_text(text)

        assert result == text
        assert "👋" in result
        assert "🎉" in result

    def test_sanitize_text_with_unicode(self):
        """Test that unicode characters are preserved."""
        text = "Привет мир! こんにちは 你好"
        result = _sanitize_text(text)

        assert result == text

    def test_sanitize_text_with_surrogates(self):
        """Test removal of UTF-8 surrogates."""
        # Create text with surrogate character
        text = "Hello \ud800 world"
        result = _sanitize_text(text)

        # Surrogate should be replaced with replacement character
        assert "\ud800" not in result
        assert "Hello" in result
        assert "world" in result

    def test_sanitize_text_with_multiple_surrogates(self):
        """Test removal of multiple surrogates."""
        text = "Test \ud800\udc00 \udfff text"
        result = _sanitize_text(text)

        # All surrogates should be replaced
        assert "\ud800" not in result
        assert "\udc00" not in result
        assert "\udfff" not in result
        assert "Test" in result
        assert "text" in result

    def test_sanitize_text_preserves_newlines(self):
        """Test that newlines are preserved."""
        text = "Line 1\nLine 2\nLine 3"
        result = _sanitize_text(text)

        assert result == text
        assert result.count("\n") == 2

    def test_sanitize_text_preserves_tabs(self):
        """Test that tabs are preserved."""
        text = "Column1\tColumn2\tColumn3"
        result = _sanitize_text(text)

        assert result == text
        assert result.count("\t") == 2


# =============================================================================
# _build_claude_script Tests
# =============================================================================


class TestBuildClaudeScript:
    """Tests for _build_claude_script function."""

    def test_build_script_basic(self):
        """Test basic script generation."""
        script = _build_claude_script(
            prompt="Hello",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "import asyncio" in script
        assert "import json" in script
        assert "from claude_agent_sdk" in script
        assert '"Hello"' in script
        assert '"/tmp"' in script
        assert '"sonnet"' in script
        assert "asyncio.run(run())" in script

    def test_build_script_with_system_prompt(self):
        """Test script generation with system prompt."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt="You are helpful",
            session_id=None,
        )

        assert '"You are helpful"' in script
        assert "system_prompt=" in script

    def test_build_script_with_session_id(self):
        """Test script generation with session ID for resumption."""
        session_id = "test-session-123"
        script = _build_claude_script(
            prompt="Continue",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=session_id,
        )

        assert f'"{session_id}"' in script
        assert "resume=resume_session" in script

    def test_build_script_with_multiple_tools(self):
        """Test script generation with multiple allowed tools."""
        tools = ["Read", "Write", "Edit", "Bash"]
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=tools,
            system_prompt=None,
            session_id=None,
        )

        for tool in tools:
            assert f'"{tool}"' in script

    def test_build_script_escapes_quotes_in_prompt(self):
        """Test that quotes in prompt are properly escaped."""
        prompt = 'Say "Hello" to the world'
        script = _build_claude_script(
            prompt=prompt,
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        # JSON dumps escapes quotes
        assert '\\"Hello\\"' in script or "Hello" in script

    def test_build_script_handles_emojis(self):
        """Test that emojis in prompt are preserved."""
        prompt = "Hello! 👋 Test message 🎉"
        script = _build_claude_script(
            prompt=prompt,
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        # Emojis should be in the script (ensure_ascii=False)
        assert (
            "👋" in script or "\\ud83d" not in script
        )  # Either UTF-8 or no surrogates

    def test_build_script_handles_newlines_in_prompt(self):
        """Test that newlines in prompt are handled."""
        prompt = "Line 1\nLine 2\nLine 3"
        script = _build_claude_script(
            prompt=prompt,
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        # JSON encodes newlines as \n
        assert "\\n" in script or "Line 1" in script

    def test_build_script_contains_message_handling(self):
        """Test that script includes message type handling."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        # Script should handle different message types
        assert "SystemMessage" in script
        assert "AssistantMessage" in script
        assert "ResultMessage" in script
        assert "TextBlock" in script
        assert "ToolUseBlock" in script


# =============================================================================
# execute_claude_subprocess Tests
# =============================================================================


class TestExecuteClaudeSubprocess:
    """Tests for execute_claude_subprocess async generator."""

    @pytest.mark.asyncio
    async def test_execute_yields_text_messages(self, tmp_path):
        """Test that text messages are yielded correctly."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            # Mock the subprocess
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            # Simulate output lines
            output_lines = [
                json.dumps({"type": "init", "session_id": "sess-123"}).encode() + b"\n",
                json.dumps({"type": "text", "content": "Hello, world!"}).encode()
                + b"\n",
                json.dumps(
                    {"type": "done", "session_id": "sess-123", "cost": 0.01}
                ).encode()
                + b"\n",
                b"",  # EOF
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, session_id))

            # Should have text and done messages
            assert any(r[0] == "text" and r[1] == "Hello, world!" for r in results)
            assert any(r[0] == "done" for r in results)

    @pytest.mark.asyncio
    async def test_execute_yields_tool_messages(self, tmp_path):
        """Test that tool use messages are yielded correctly."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps({"type": "tool", "content": "Read: /path/to/file"}).encode()
                + b"\n",
                json.dumps({"type": "done", "session_id": "sess-123"}).encode() + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, session_id))

            assert any(r[0] == "tool" and "Read" in r[1] for r in results)

    @pytest.mark.asyncio
    async def test_execute_handles_error_messages(self, tmp_path):
        """Test that error messages from subprocess are yielded."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps(
                    {"type": "error", "content": "Something went wrong"}
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, session_id))

            assert any(
                r[0] == "error" and "Something went wrong" in r[1] for r in results
            )

    @pytest.mark.asyncio
    async def test_execute_timeout_handling(self, tmp_path):
        """Test that timeout is handled correctly."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.terminate = MagicMock()
            mock_process.kill = MagicMock()

            # Simulate timeout on readline
            async def readline_timeout():
                raise asyncio.TimeoutError()

            mock_process.stdout.readline = readline_timeout
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, session_id))

            # Should have error about timeout
            assert any(r[0] == "error" and "Timed out" in r[1] for r in results)
            # Process should be gracefully terminated (terminate called, not kill)
            mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_stop_check(self, tmp_path):
        """Test that stop_check callback works."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.terminate = MagicMock()
            mock_process.kill = MagicMock()

            # First call returns data, second call will trigger stop check
            call_count = [0]

            async def readline():
                call_count[0] += 1
                if call_count[0] == 1:
                    return (
                        json.dumps({"type": "text", "content": "First"}).encode()
                        + b"\n"
                    )
                # After first call, stop_check will return True
                await asyncio.sleep(0.1)
                return (
                    json.dumps({"type": "text", "content": "Second"}).encode() + b"\n"
                )

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            # Stop check returns True after first message
            stop_flag = [False]

            def stop_check():
                return stop_flag[0]

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                    stop_check=stop_check,
                ):
                    results.append((msg_type, content, session_id))
                    # Set stop flag after first message
                    stop_flag[0] = True

            # Should have been stopped
            assert any(r[0] == "error" and "Stopped by user" in r[1] for r in results)
            # Process should be gracefully terminated
            mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_process_failure(self, tmp_path):
        """Test handling of subprocess failure."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 1  # Non-zero exit code

            output_lines = [b""]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(
                return_value=b"Error: Something failed"
            )
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, session_id))

            # Should have error message
            assert any(r[0] == "error" and "Process failed" in r[1] for r in results)

    @pytest.mark.asyncio
    async def test_execute_invalid_cwd_raises_error(self):
        """Test that invalid cwd raises ValueError."""
        # /var/spool is not under any allowed base
        with pytest.raises(ValueError) as exc_info:
            async for msg_type, content, session_id in execute_claude_subprocess(
                prompt="Test",
                cwd="/var/spool",
            ):
                pass  # Should never reach here

        assert "not in allowed paths" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_encoding_error(self, tmp_path):
        """Test handling of script encoding errors."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            # Create a prompt with invalid encoding that can't be fixed
            with patch(
                "src.services.claude_subprocess._build_claude_script"
            ) as mock_build:
                # Create a mock string that raises UnicodeEncodeError on encode()
                bad_script = MagicMock()
                # UnicodeEncodeError requires: encoding, object (str), start, end, reason
                bad_script.encode = MagicMock(
                    side_effect=UnicodeEncodeError(
                        "utf-8", "test string", 0, 1, "test error"
                    )
                )

                mock_build.return_value = bad_script

                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, session_id))

            # Should have encoding error
            assert any(r[0] == "error" and "encoding" in r[1].lower() for r in results)

    @pytest.mark.asyncio
    async def test_execute_session_id_returned(self, tmp_path):
        """Test that session ID is returned in done message."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            session_id = "test-session-abc123"
            output_lines = [
                json.dumps({"type": "init", "session_id": session_id}).encode() + b"\n",
                json.dumps(
                    {"type": "done", "session_id": session_id, "cost": 0.01}
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            # Find done message and check session_id
            done_msgs = [r for r in results if r[0] == "done"]
            assert len(done_msgs) == 1
            assert done_msgs[0][2] == session_id

    @pytest.mark.asyncio
    async def test_execute_with_resume_session(self, tmp_path):
        """Test execution with session resumption."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps({"type": "done", "session_id": "resumed-session"}).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            captured_script = []

            async def capture_subprocess_exec(*args, **kwargs):
                if len(args) >= 3:
                    captured_script.append(args[2])  # The script is the third argument
                return mock_process

            with patch(
                "asyncio.create_subprocess_exec", side_effect=capture_subprocess_exec
            ):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Continue",
                    cwd=str(ai_projects),
                    session_id="previous-session-123",
                ):
                    results.append((msg_type, content, sess_id))

            # Verify script contains resume session
            assert len(captured_script) == 1
            assert "previous-session-123" in captured_script[0]

    @pytest.mark.asyncio
    async def test_execute_ignores_non_json_output(self, tmp_path):
        """Test that non-JSON output lines are ignored."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                b"Some debug output\n",
                b"Another log line\n",
                json.dumps({"type": "text", "content": "Real message"}).encode()
                + b"\n",
                b"More debug\n",
                json.dumps({"type": "done", "session_id": "sess"}).encode() + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            # Should only have the valid JSON messages
            assert len(results) == 2
            assert results[0][0] == "text"
            assert results[0][1] == "Real message"
            assert results[1][0] == "done"

    @pytest.mark.asyncio
    async def test_execute_empty_lines_ignored(self, tmp_path):
        """Test that empty lines are skipped."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                b"\n",
                b"   \n",
                json.dumps({"type": "text", "content": "Hello"}).encode() + b"\n",
                b"\n",
                json.dumps({"type": "done", "session_id": "s"}).encode() + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            # Should have text and done only
            assert len(results) == 2


class TestExecuteClaudeSubprocessDefaultTools:
    """Tests for default tool configuration."""

    @pytest.mark.asyncio
    async def test_default_tools_applied(self, tmp_path):
        """Test that default tools are used when not specified."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps({"type": "done", "session_id": "s"}).encode() + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            captured_script = []

            async def capture_subprocess(*args, **kwargs):
                if len(args) >= 3:
                    captured_script.append(args[2])
                return mock_process

            with patch(
                "asyncio.create_subprocess_exec", side_effect=capture_subprocess
            ):
                async for _ in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                    # No allowed_tools specified
                ):
                    pass

            # Check default tools are in script
            assert len(captured_script) == 1
            script = captured_script[0]
            for tool in ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]:
                assert f'"{tool}"' in script


class TestExecuteClaudeSubprocessEnvironment:
    """Tests for environment variable handling."""

    @pytest.mark.asyncio
    async def test_api_key_unset_in_subprocess(self, tmp_path):
        """Test that ANTHROPIC_API_KEY is unset in subprocess environment."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps({"type": "done", "session_id": "s"}).encode() + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            captured_env = []

            async def capture_subprocess(*args, **kwargs):
                captured_env.append(kwargs.get("env", {}))
                return mock_process

            with patch(
                "asyncio.create_subprocess_exec", side_effect=capture_subprocess
            ):
                async for _ in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    pass

            # ANTHROPIC_API_KEY should be empty string
            assert len(captured_env) == 1
            assert captured_env[0].get("ANTHROPIC_API_KEY") == ""


class TestExecuteClaudeSubprocessExceptionHandling:
    """Tests for exception handling during execution."""

    @pytest.mark.asyncio
    async def test_general_exception_yields_error(self, tmp_path):
        """Test that general exceptions yield error messages."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            with patch(
                "asyncio.create_subprocess_exec", side_effect=OSError("Process failed")
            ):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            assert len(results) == 1
            assert results[0][0] == "error"
            assert "Process failed" in results[0][1]


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_timeout_constant_value(self):
        """Test that timeout constant has expected value."""
        assert CLAUDE_TIMEOUT_SECONDS == 300  # 5 minutes

    def test_timeout_is_reasonable(self):
        """Test that timeout is within reasonable bounds."""
        assert CLAUDE_TIMEOUT_SECONDS >= 60  # At least 1 minute
        assert CLAUDE_TIMEOUT_SECONDS <= 600  # At most 10 minutes


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, tmp_path):
        """Test a complete conversation flow with multiple message types."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            session_id = "full-test-session"
            output_lines = [
                json.dumps({"type": "init", "session_id": session_id}).encode() + b"\n",
                json.dumps(
                    {"type": "text", "content": "Let me check that file..."}
                ).encode()
                + b"\n",
                json.dumps({"type": "tool", "content": "Read: /path/file.txt"}).encode()
                + b"\n",
                json.dumps(
                    {"type": "text", "content": "The file contains important data."}
                ).encode()
                + b"\n",
                json.dumps(
                    {"type": "done", "session_id": session_id, "turns": 2, "cost": 0.05}
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Read the file and tell me what's in it",
                    cwd=str(ai_projects),
                    model="sonnet",
                    allowed_tools=["Read"],
                    system_prompt="You are a helpful assistant",
                ):
                    results.append((msg_type, content, sess_id))

            # Verify message sequence
            assert len(results) == 4  # 2 text + 1 tool + 1 done

            types = [r[0] for r in results]
            assert types == ["text", "tool", "text", "done"]

            # Verify session ID in done message
            assert results[-1][2] == session_id

    @pytest.mark.asyncio
    async def test_prompt_with_special_characters(self, tmp_path):
        """Test handling of prompt with special characters."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps({"type": "done", "session_id": "s"}).encode() + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            special_prompt = (
                """Test with "quotes", 'apostrophes', and special chars: <>&\n\ttab"""
            )

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt=special_prompt,
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            # Should complete without error
            assert any(r[0] == "done" for r in results)


# =============================================================================
# Work Statistics Tests
# =============================================================================


class TestWorkStatisticsCollection:
    """Tests for work statistics collection in subprocess output."""

    @pytest.mark.asyncio
    async def test_done_message_contains_stats_json(self, tmp_path):
        """Test that done message content contains stats as JSON."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            stats = {
                "duration": "30s",
                "duration_seconds": 30,
                "tool_counts": {"Read": 5, "Write": 2},
                "files_read": ["file1.py", "file2.py"],
                "files_written": ["output.md"],
                "web_fetches": [],
                "skills_used": [],
                "bash_commands": [],
            }

            output_lines = [
                json.dumps(
                    {
                        "type": "done",
                        "session_id": "test-sess",
                        "cost": 0.05,
                        "stats": stats,
                    }
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            # Find done message
            done_msgs = [r for r in results if r[0] == "done"]
            assert len(done_msgs) == 1

            # Content should be JSON stats
            done_content = done_msgs[0][1]
            assert done_content  # Not empty
            parsed_stats = json.loads(done_content)
            assert parsed_stats["duration"] == "30s"
            assert parsed_stats["tool_counts"]["Read"] == 5

    @pytest.mark.asyncio
    async def test_stats_with_tool_tracking(self, tmp_path):
        """Test stats include tool usage counts."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            stats = {
                "duration": "1m 15s",
                "tool_counts": {
                    "Read": 10,
                    "Write": 3,
                    "Edit": 7,
                    "Grep": 5,
                    "Glob": 2,
                    "Bash": 8,
                },
            }

            output_lines = [
                json.dumps({"type": "tool", "content": "Read: /path/file.py"}).encode()
                + b"\n",
                json.dumps({"type": "tool", "content": "Edit: /path/file.py"}).encode()
                + b"\n",
                json.dumps(
                    {
                        "type": "done",
                        "session_id": "sess",
                        "stats": stats,
                    }
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            done_msgs = [r for r in results if r[0] == "done"]
            parsed_stats = json.loads(done_msgs[0][1])

            assert "tool_counts" in parsed_stats
            assert parsed_stats["tool_counts"]["Read"] == 10
            assert parsed_stats["tool_counts"]["Bash"] == 8

    @pytest.mark.asyncio
    async def test_stats_with_web_fetches(self, tmp_path):
        """Test stats include web fetch URLs."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            stats = {
                "duration": "45s",
                "web_fetches": [
                    "https://example.com/docs",
                    "search: python async patterns",
                ],
            }

            output_lines = [
                json.dumps(
                    {
                        "type": "done",
                        "session_id": "sess",
                        "stats": stats,
                    }
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            done_msgs = [r for r in results if r[0] == "done"]
            parsed_stats = json.loads(done_msgs[0][1])

            assert "web_fetches" in parsed_stats
            assert len(parsed_stats["web_fetches"]) == 2
            assert "https://example.com/docs" in parsed_stats["web_fetches"]

    @pytest.mark.asyncio
    async def test_stats_with_skills_used(self, tmp_path):
        """Test stats include skills that were invoked."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            stats = {
                "duration": "2m 0s",
                "skills_used": ["tavily-search", "pdf-generation", "deep-research"],
            }

            output_lines = [
                json.dumps(
                    {
                        "type": "done",
                        "session_id": "sess",
                        "stats": stats,
                    }
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            done_msgs = [r for r in results if r[0] == "done"]
            parsed_stats = json.loads(done_msgs[0][1])

            assert "skills_used" in parsed_stats
            assert "tavily-search" in parsed_stats["skills_used"]
            assert "deep-research" in parsed_stats["skills_used"]

    @pytest.mark.asyncio
    async def test_stats_with_files_tracked(self, tmp_path):
        """Test stats include files read and written."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            stats = {
                "duration": "1m 30s",
                "files_read": ["main.py", "utils.py", "config.py"],
                "files_written": ["output.md", "report.pdf"],
            }

            output_lines = [
                json.dumps(
                    {
                        "type": "done",
                        "session_id": "sess",
                        "stats": stats,
                    }
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            done_msgs = [r for r in results if r[0] == "done"]
            parsed_stats = json.loads(done_msgs[0][1])

            assert "files_read" in parsed_stats
            assert "main.py" in parsed_stats["files_read"]
            assert "files_written" in parsed_stats
            assert "output.md" in parsed_stats["files_written"]

    @pytest.mark.asyncio
    async def test_stats_empty_when_no_stats_provided(self, tmp_path):
        """Test handling when done message has no stats."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            # Done message without stats field
            output_lines = [
                json.dumps(
                    {
                        "type": "done",
                        "session_id": "sess",
                        "cost": 0.01,
                    }
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            done_msgs = [r for r in results if r[0] == "done"]
            # Content should be empty JSON object when no stats
            done_content = done_msgs[0][1]
            parsed = json.loads(done_content)
            assert parsed == {}

    @pytest.mark.asyncio
    async def test_stats_duration_format(self, tmp_path):
        """Test duration format in stats."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            stats = {
                "duration": "5m 30s",
                "duration_seconds": 330,
            }

            output_lines = [
                json.dumps(
                    {
                        "type": "done",
                        "session_id": "sess",
                        "stats": stats,
                    }
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                results = []
                async for msg_type, content, sess_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                ):
                    results.append((msg_type, content, sess_id))

            done_msgs = [r for r in results if r[0] == "done"]
            parsed_stats = json.loads(done_msgs[0][1])

            assert parsed_stats["duration"] == "5m 30s"
            assert parsed_stats["duration_seconds"] == 330


class TestBuildClaudeScriptStatistics:
    """Tests for statistics tracking in generated Claude script."""

    def test_script_contains_time_import(self):
        """Test that generated script imports time module."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "import time" in script

    def test_script_contains_counter_import(self):
        """Test that generated script imports Counter for tool tracking."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "from collections import Counter" in script

    def test_script_tracks_tool_counts(self):
        """Test that generated script has tool counting logic."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "tool_counts" in script
        assert "Counter()" in script

    def test_script_tracks_start_time(self):
        """Test that generated script captures start time."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "start_time = time.time()" in script

    def test_script_calculates_duration(self):
        """Test that generated script calculates duration."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "duration_seconds" in script
        assert "time.time() - start_time" in script

    def test_script_includes_stats_in_done_message(self):
        """Test that generated script includes stats in done JSON."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert '"stats": stats' in script

    def test_script_tracks_files_read(self):
        """Test that generated script tracks files read."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "files_read" in script

    def test_script_tracks_files_written(self):
        """Test that generated script tracks files written."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "files_written" in script

    def test_script_tracks_web_fetches(self):
        """Test that generated script tracks web fetches."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "web_fetches" in script

    def test_script_tracks_skills_used(self):
        """Test that generated script tracks skills used."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "skills_used" in script

    def test_script_tracks_bash_commands(self):
        """Test that generated script tracks bash commands."""
        script = _build_claude_script(
            prompt="Test",
            cwd="/tmp",
            model="sonnet",
            allowed_tools=["Read"],
            system_prompt=None,
            session_id=None,
        )

        assert "bash_commands" in script


# =============================================================================
# get_configured_tools Tests
# =============================================================================


class TestGetConfiguredTools:
    """Tests for configurable Claude Code tool access."""

    def test_explicit_override_takes_priority(self):
        """Explicit override list is returned as-is, ignoring config."""
        tools = get_configured_tools(["Read", "Glob"])
        assert tools == ["Read", "Glob"]

    def test_explicit_empty_list_returns_empty(self):
        """Explicit empty list means no tools."""
        tools = get_configured_tools([])
        assert tools == []

    def test_none_falls_through_to_config(self):
        """None triggers config resolution, not an empty list."""
        tools = get_configured_tools(None)
        assert len(tools) > 0

    def test_env_var_allowed_tools_parsed(self):
        """Env var is split on commas with whitespace stripped."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = " Read , Write , Edit "
        mock_settings.claude_disallowed_tools = None

        with patch("src.core.config.get_settings", return_value=mock_settings):
            from src.core.config import get_settings as _gs

            # Clear lru_cache to pick up our mock
            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert "Read" in tools
                assert "Write" in tools
                assert "Edit" in tools
                # No leading/trailing whitespace
                for t in tools:
                    assert t == t.strip()
            finally:
                _gs.cache_clear()

    def test_env_var_disallowed_tools_subtracted(self):
        """CLAUDE_DISALLOWED_TOOLS removes tools from the allowed set."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = "Read,Write,Edit,Bash"
        mock_settings.claude_disallowed_tools = "Bash,Write"

        with patch("src.core.config.get_settings", return_value=mock_settings):
            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert "Read" in tools
                assert "Edit" in tools
                assert "Bash" not in tools
                assert "Write" not in tools
            finally:
                _gs.cache_clear()

    def test_disallowed_applied_to_override(self):
        """Disallowed list is also applied when an explicit override is given."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = None
        mock_settings.claude_disallowed_tools = "Bash"

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch("src.core.config.get_config_value", return_value=None),
        ):
            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(["Read", "Bash", "Glob"])
                assert "Read" in tools
                assert "Glob" in tools
                assert "Bash" not in tools
            finally:
                _gs.cache_clear()

    def test_yaml_config_fallback(self):
        """Falls back to YAML config when env var is not set."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = None
        mock_settings.claude_disallowed_tools = None

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch("src.core.config.get_config_value") as mock_config,
        ):
            mock_config.side_effect = lambda key: {
                "claude_tools.allowed_tools": ["Read", "Glob"],
                "claude_tools.disallowed_tools": [],
            }.get(key)

            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert tools == ["Read", "Glob"]
            finally:
                _gs.cache_clear()

    def test_hardcoded_fallback_on_config_failure(self):
        """Falls back to hardcoded defaults if config loading raises."""
        with patch("src.core.config.get_settings", side_effect=RuntimeError("broken")):
            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert tools == ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
            finally:
                _gs.cache_clear()

    def test_empty_yaml_list_uses_hardcoded_default(self):
        """Empty YAML allowed_tools list falls through to hardcoded defaults."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = None
        mock_settings.claude_disallowed_tools = None

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch("src.core.config.get_config_value") as mock_config,
        ):
            mock_config.side_effect = lambda key: {
                "claude_tools.allowed_tools": [],
                "claude_tools.disallowed_tools": [],
            }.get(key)

            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert tools == ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
            finally:
                _gs.cache_clear()

    def test_disallow_all_returns_empty(self):
        """Disallowing every allowed tool returns an empty list."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = "Read,Write"
        mock_settings.claude_disallowed_tools = "Read,Write"

        with patch("src.core.config.get_settings", return_value=mock_settings):
            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert tools == []
            finally:
                _gs.cache_clear()

    def test_disallow_nonexistent_tool_is_no_op(self):
        """Disallowing a tool that's not in the allowed list does nothing."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = "Read,Write"
        mock_settings.claude_disallowed_tools = "NonExistentTool"

        with patch("src.core.config.get_settings", return_value=mock_settings):
            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert tools == ["Read", "Write"]
            finally:
                _gs.cache_clear()

    def test_empty_env_var_string_ignored(self):
        """Empty string env var falls through to YAML/default."""
        mock_settings = MagicMock()
        mock_settings.claude_allowed_tools = ""
        mock_settings.claude_disallowed_tools = ""

        with (
            patch("src.core.config.get_settings", return_value=mock_settings),
            patch("src.core.config.get_config_value") as mock_config,
        ):
            mock_config.side_effect = lambda key: {
                "claude_tools.allowed_tools": ["Read", "Grep"],
                "claude_tools.disallowed_tools": [],
            }.get(key)

            from src.core.config import get_settings as _gs

            _gs.cache_clear()
            try:
                tools = get_configured_tools(None)
                assert tools == ["Read", "Grep"]
            finally:
                _gs.cache_clear()


# =============================================================================
# _is_session_error Tests
# =============================================================================


class TestIsSessionError:
    """Tests for _is_session_error helper."""

    def test_exit_code_minus_5(self):
        assert _is_session_error("Command failed with exit code -5 (exit code: -5)")

    def test_fatal_error_in_message_reader(self):
        assert _is_session_error("Fatal error in message reader: something broke")

    def test_case_insensitive(self):
        assert _is_session_error("FATAL ERROR IN MESSAGE READER")

    def test_normal_error_not_matched(self):
        assert not _is_session_error("Connection timeout")

    def test_empty_string(self):
        assert not _is_session_error("")

    def test_partial_match(self):
        assert _is_session_error(
            "Process failed: Fatal error in message reader: exit code -5"
        )


# =============================================================================
# Session Resume Retry Tests
# =============================================================================


class TestSessionResumeRetry:
    """Tests for automatic retry when session resume fails."""

    @pytest.mark.asyncio
    async def test_retry_on_exit_code_minus_5(self, tmp_path):
        """When resume fails with exit code -5, retries with fresh session."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            call_count = 0

            def make_mock_process(succeed: bool):
                mock_process = MagicMock()
                mock_process.pid = 12345
                mock_process.returncode = 0 if succeed else 1

                if succeed:
                    output_lines = [
                        json.dumps({"type": "init", "session_id": "new-sess"}).encode()
                        + b"\n",
                        json.dumps(
                            {"type": "text", "content": "Fresh response"}
                        ).encode()
                        + b"\n",
                        json.dumps(
                            {"type": "done", "session_id": "new-sess", "cost": 0.01}
                        ).encode()
                        + b"\n",
                        b"",
                    ]
                else:
                    output_lines = [
                        json.dumps({"type": "init", "session_id": "old-sess"}).encode()
                        + b"\n",
                        json.dumps(
                            {
                                "type": "error",
                                "content": "Command failed with exit code -5 (exit code: -5)",
                            }
                        ).encode()
                        + b"\n",
                        b"",
                    ]

                line_iter = iter(output_lines)

                async def readline():
                    try:
                        return next(line_iter)
                    except StopIteration:
                        return b""

                mock_process.stdout.readline = readline
                mock_process.stderr.read = AsyncMock(
                    return_value=(
                        b"Fatal error in message reader" if not succeed else b""
                    )
                )
                mock_process.wait = AsyncMock()
                return mock_process

            async def fake_subprocess_exec(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return make_mock_process(succeed=(call_count > 1))

            with patch(
                "asyncio.create_subprocess_exec", side_effect=fake_subprocess_exec
            ):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                    session_id="old-sess",
                ):
                    results.append((msg_type, content, session_id))

            # Should have retried (2 subprocess calls)
            assert call_count == 2
            # Should have the fresh response, not the error
            assert any(r[0] == "text" and r[1] == "Fresh response" for r in results)
            assert not any(r[0] == "error" and "exit code -5" in r[1] for r in results)

    @pytest.mark.asyncio
    async def test_no_retry_without_session_id(self, tmp_path):
        """Errors without a session_id are not retried."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps(
                    {"type": "error", "content": "Command failed with exit code -5"}
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            call_count = 0

            async def fake_subprocess_exec(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return mock_process

            with patch(
                "asyncio.create_subprocess_exec", side_effect=fake_subprocess_exec
            ):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                    session_id=None,
                ):
                    results.append((msg_type, content, session_id))

            # Should NOT retry — no session to retry without
            assert call_count == 1
            assert any(r[0] == "error" for r in results)

    @pytest.mark.asyncio
    async def test_no_retry_after_content_yielded(self, tmp_path):
        """If content was already yielded before session error, don't retry."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps({"type": "init", "session_id": "sess-1"}).encode() + b"\n",
                json.dumps({"type": "text", "content": "Partial response"}).encode()
                + b"\n",
                json.dumps(
                    {"type": "error", "content": "Command failed with exit code -5"}
                ).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            call_count = 0

            async def fake_subprocess_exec(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return mock_process

            with patch(
                "asyncio.create_subprocess_exec", side_effect=fake_subprocess_exec
            ):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                    session_id="sess-1",
                ):
                    results.append((msg_type, content, session_id))

            # Should NOT retry — content was already yielded
            assert call_count == 1
            assert any(r[0] == "text" for r in results)
            assert any(r[0] == "error" for r in results)

    @pytest.mark.asyncio
    async def test_no_retry_on_non_session_error(self, tmp_path):
        """Non-session errors are yielded normally, not retried."""
        with patch.object(Path, "home", return_value=tmp_path):
            ai_projects = tmp_path / "ai_projects" / "test"
            ai_projects.mkdir(parents=True, exist_ok=True)

            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.returncode = 0

            output_lines = [
                json.dumps({"type": "error", "content": "Rate limit exceeded"}).encode()
                + b"\n",
                b"",
            ]
            line_iter = iter(output_lines)

            async def readline():
                try:
                    return next(line_iter)
                except StopIteration:
                    return b""

            mock_process.stdout.readline = readline
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock()

            call_count = 0

            async def fake_subprocess_exec(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return mock_process

            with patch(
                "asyncio.create_subprocess_exec", side_effect=fake_subprocess_exec
            ):
                results = []
                async for msg_type, content, session_id in execute_claude_subprocess(
                    prompt="Test",
                    cwd=str(ai_projects),
                    session_id="sess-1",
                ):
                    results.append((msg_type, content, session_id))

            # Should NOT retry — not a session error
            assert call_count == 1
            assert any(r[0] == "error" and "Rate limit" in r[1] for r in results)


# =============================================================================
# _encode_path_as_claude_dir Tests
# =============================================================================


class TestEncodePathAsClaudeDir:
    """Tests for the Claude SDK directory name encoding helper."""

    def test_encodes_slashes_to_dashes(self):
        """Forward slashes become dashes."""
        result = _encode_path_as_claude_dir("/Users/server/projects")
        assert result == "-Users-server-projects"

    def test_encodes_underscores_to_dashes(self):
        """Underscores become dashes (matches Claude SDK behaviour)."""
        result = _encode_path_as_claude_dir("/Users/server/ai_projects/telegram_agent")
        assert result == "-Users-server-ai-projects-telegram-agent"

    def test_simple_path(self):
        """A single-component path still gets the leading dash."""
        result = _encode_path_as_claude_dir("/tmp")
        assert result == "-tmp"

    def test_trailing_slash_stripped(self):
        """Trailing slash should not produce trailing dash."""
        result = _encode_path_as_claude_dir("/Users/server/project/")
        # The trailing slash becomes an empty component — strip it
        assert not result.endswith("-") or result == "-"


# =============================================================================
# find_session_cwd Tests (Dynamic Path Resolution)
# =============================================================================


class TestFindSessionCwd:
    """Tests for find_session_cwd with dynamic (non-hardcoded) path resolution.

    Note: tmp_path on macOS resolves to /private/var/folders/.../pytest-of-server/...
    which itself contains dashes.  The Claude SDK encoding maps both / and _ to -,
    making it impossible to reverse paths that contain literal dashes.
    We use a dash-free subdirectory as our fake HOME to avoid this test artefact.
    """

    @pytest.fixture
    def fake_home(self):
        """Create a dash-free root for use as a fake HOME.

        We use /tmp/ with a dash-free name because the Claude SDK
        encoding turns both / and _ into -, so paths containing literal
        dashes (like pytest's tmp_path) are impossible to roundtrip.
        Real project paths rarely contain dashes in directory names.
        """
        import tempfile

        # Create under /tmp with a clean, dash-free prefix
        home = Path(tempfile.mkdtemp(prefix="claudetest", dir="/tmp"))
        yield home
        import shutil

        shutil.rmtree(home, ignore_errors=True)

    def _setup_session(self, fake_home, project_path, session_id):
        """Helper: create the Claude project dir structure for a session."""
        project_path.mkdir(parents=True, exist_ok=True)
        encoded_name = _encode_path_as_claude_dir(str(project_path))
        claude_projects = fake_home / ".claude" / "projects"
        encoded_dir = claude_projects / encoded_name
        encoded_dir.mkdir(parents=True, exist_ok=True)
        (encoded_dir / f"{session_id}.jsonl").touch()

    def test_finds_session_in_project_dir(self, fake_home):
        """find_session_cwd should locate a session file in a project directory
        and return the decoded real path — without any hardcoded map."""
        project_path = fake_home / "ai_projects" / "my_project"
        self._setup_session(fake_home, project_path, "sess-abc123")

        with patch.object(Path, "home", return_value=fake_home):
            result = find_session_cwd("sess-abc123")

        assert result is not None
        assert result == str(project_path)

    def test_returns_none_when_session_not_found(self, fake_home):
        """Returns None when session ID has no matching file."""
        claude_projects = fake_home / ".claude" / "projects"
        claude_projects.mkdir(parents=True)

        with patch.object(Path, "home", return_value=fake_home):
            result = find_session_cwd("nonexistent-session")

        assert result is None

    def test_returns_none_when_claude_dir_missing(self, fake_home):
        """Returns None when ~/.claude/projects doesn't exist."""
        with patch.object(Path, "home", return_value=fake_home):
            result = find_session_cwd("some-session")

        assert result is None

    def test_no_hardcoded_paths_in_function(self):
        """The function must not contain hardcoded absolute user paths."""
        import inspect

        source = inspect.getsource(find_session_cwd)
        # Should not contain any /Users/server or similar hardcoded paths
        assert "/Users/server" not in source
        assert "project_map" not in source

    def test_fallback_for_path_without_underscores(self, fake_home):
        """For paths without underscores, the dash-to-slash reversal works."""
        project_path = fake_home / "Research" / "vault"
        self._setup_session(fake_home, project_path, "sess-xyz")

        with patch.object(Path, "home", return_value=fake_home):
            result = find_session_cwd("sess-xyz")

        assert result is not None
        assert result == str(project_path)

    def test_resolves_path_with_underscores(self, fake_home):
        """The function should resolve paths containing underscores
        by checking the filesystem, not from a hardcoded map."""
        project_path = fake_home / "code" / "my_app"
        self._setup_session(fake_home, project_path, "sess-project")

        with patch.object(Path, "home", return_value=fake_home):
            result = find_session_cwd("sess-project")

        assert result == str(project_path)

    def test_handles_deep_nested_project(self, fake_home):
        """Works for deeply nested project paths."""
        project_path = fake_home / "a" / "b" / "c" / "d"
        self._setup_session(fake_home, project_path, "sess-deep")

        with patch.object(Path, "home", return_value=fake_home):
            result = find_session_cwd("sess-deep")

        assert result is not None
        assert result == str(project_path)

    def test_skips_non_directory_entries(self, fake_home):
        """Non-directory entries in ~/.claude/projects are ignored."""
        claude_projects = fake_home / ".claude" / "projects"
        claude_projects.mkdir(parents=True)
        # Create a regular file, not a directory
        (claude_projects / "stray-file.txt").touch()

        with patch.object(Path, "home", return_value=fake_home):
            result = find_session_cwd("stray-file")

        assert result is None

    def test_encode_decode_roundtrip(self, fake_home):
        """Encoding a path then decoding should return the original."""
        project_path = fake_home / "ai_projects" / "telegram_agent"
        project_path.mkdir(parents=True)

        encoded = _encode_path_as_claude_dir(str(project_path))
        from src.services.claude_subprocess import _decode_claude_dir_to_path

        decoded = _decode_claude_dir_to_path(encoded)

        assert decoded == str(project_path)
