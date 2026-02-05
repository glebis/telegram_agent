"""
Tests for OpenCode integration: subprocess wrapper, service, and agent backend.

Tests cover:
- OpenCode subprocess wrapper (run_opencode_subprocess)
  - Basic prompt execution
  - Model selection flag
  - Session persistence (--session flag)
  - Custom working directory
  - Output parsing (stdout/stderr)
  - Error handling and timeouts
- OpenCode service (OpenCodeService)
  - run_opencode_query() basic flow
  - Session create/resume
  - is_available() with/without opencode installed
- Agent backend abstraction
  - Factory returns correct backend based on config
  - Fallback when opencode not installed
  - ClaudeCodeBackend delegation
  - OpenCodeBackend delegation
"""

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent_backend import (
    ClaudeCodeBackend,
    OpenCodeBackend,
    get_agent_backend,
)
from src.services.opencode_service import OpenCodeService
from src.services.opencode_subprocess import (
    OPENCODE_TIMEOUT_SECONDS,
    parse_opencode_output,
    run_opencode_subprocess,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_subprocess_success():
    """Mock a successful opencode subprocess call."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "This is the response from OpenCode.\n"
    mock_result.stderr = ""
    return mock_result


@pytest.fixture
def mock_subprocess_error():
    """Mock a failed opencode subprocess call."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Error: model not found\n"
    return mock_result


@pytest.fixture
def mock_subprocess_timeout():
    """Mock a subprocess that times out."""
    return subprocess.TimeoutExpired(cmd="opencode", timeout=300)


@pytest.fixture
def opencode_service(tmp_path):
    """Create an OpenCodeService instance with a temp work dir."""
    return OpenCodeService(work_dir=str(tmp_path))


# =============================================================================
# Tests: run_opencode_subprocess
# =============================================================================


class TestRunOpencodeSubprocess:
    """Tests for the OpenCode subprocess wrapper."""

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_basic_prompt_execution(
        self, mock_which, mock_run, mock_subprocess_success
    ):
        """Test basic prompt execution returns success with output."""
        mock_run.return_value = mock_subprocess_success

        result = run_opencode_subprocess("Write a hello world function")

        assert result["success"] is True
        assert "This is the response from OpenCode" in result["output"]
        assert result["error"] is None

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_model_selection_flag(self, mock_which, mock_run, mock_subprocess_success):
        """Test that --model flag is passed correctly."""
        mock_run.return_value = mock_subprocess_success

        run_opencode_subprocess("Write a function", model="openai:gpt-4o")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "openai:gpt-4o"

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_session_persistence(self, mock_which, mock_run, mock_subprocess_success):
        """Test that --session flag is passed for session persistence."""
        mock_run.return_value = mock_subprocess_success

        run_opencode_subprocess("Continue working", session_id="sess-abc-123")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--session" in cmd
        session_idx = cmd.index("--session")
        assert cmd[session_idx + 1] == "sess-abc-123"

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_custom_working_directory(
        self, mock_which, mock_run, mock_subprocess_success, tmp_path
    ):
        """Test that cwd is passed to subprocess."""
        mock_run.return_value = mock_subprocess_success
        work_dir = str(tmp_path)

        run_opencode_subprocess("List files", cwd=work_dir)

        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == work_dir

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_error_handling(self, mock_which, mock_run, mock_subprocess_error):
        """Test that errors are captured and returned."""
        mock_run.return_value = mock_subprocess_error

        result = run_opencode_subprocess("Bad prompt")

        assert result["success"] is False
        assert result["output"] == ""
        assert "model not found" in result["error"]

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_timeout_handling(self, mock_which, mock_run, mock_subprocess_timeout):
        """Test that timeouts are handled gracefully."""
        mock_run.side_effect = mock_subprocess_timeout

        result = run_opencode_subprocess("Long running task")

        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    @patch("src.services.opencode_subprocess.shutil.which", return_value=None)
    def test_opencode_not_installed(self, mock_which):
        """Test error when opencode is not installed."""
        result = run_opencode_subprocess("Any prompt")

        assert result["success"] is False
        assert (
            "not installed" in result["error"].lower()
            or "not found" in result["error"].lower()
        )

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_no_model_flag_when_none(
        self, mock_which, mock_run, mock_subprocess_success
    ):
        """Test that --model is not passed when model=None."""
        mock_run.return_value = mock_subprocess_success

        run_opencode_subprocess("Hello", model=None)

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--model" not in cmd

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_no_session_flag_when_none(
        self, mock_which, mock_run, mock_subprocess_success
    ):
        """Test that --session is not passed when session_id=None."""
        mock_run.return_value = mock_subprocess_success

        run_opencode_subprocess("Hello", session_id=None)

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--session" not in cmd

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_subprocess_exception(self, mock_which, mock_run):
        """Test handling of unexpected subprocess exceptions."""
        mock_run.side_effect = OSError("Permission denied")

        result = run_opencode_subprocess("Test prompt")

        assert result["success"] is False
        assert "Permission denied" in result["error"]

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_uses_opencode_run_command(
        self, mock_which, mock_run, mock_subprocess_success
    ):
        """Test that the subprocess uses 'opencode run' subcommand."""
        mock_run.return_value = mock_subprocess_success

        run_opencode_subprocess("Do something")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        # First two elements should be opencode binary path and "run"
        assert cmd[0] == "/usr/local/bin/opencode"
        assert "run" in cmd

    @patch("src.services.opencode_subprocess.subprocess.run")
    @patch(
        "src.services.opencode_subprocess.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_timeout_value_passed(self, mock_which, mock_run, mock_subprocess_success):
        """Test that the timeout value is passed to subprocess.run."""
        mock_run.return_value = mock_subprocess_success

        run_opencode_subprocess("Quick task")

        call_args = mock_run.call_args
        assert call_args[1]["timeout"] == OPENCODE_TIMEOUT_SECONDS


# =============================================================================
# Tests: parse_opencode_output
# =============================================================================


class TestParseOpencodeOutput:
    """Tests for output parsing from OpenCode."""

    def test_parse_plain_text_output(self):
        """Test parsing plain text output."""
        raw = "Here is the code you asked for:\n\ndef hello():\n    print('world')\n"
        result = parse_opencode_output(raw)
        assert "hello()" in result
        assert "print" in result

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        result = parse_opencode_output("")
        assert result == ""

    def test_parse_multiline_output(self):
        """Test parsing multi-line output preserves structure."""
        raw = "Line 1\nLine 2\nLine 3"
        result = parse_opencode_output(raw)
        assert "Line 1" in result
        assert "Line 3" in result

    def test_parse_strips_whitespace(self):
        """Test that output is stripped of leading/trailing whitespace."""
        raw = "  \n  Content here  \n  "
        result = parse_opencode_output(raw)
        assert result == "Content here"


# =============================================================================
# Tests: OpenCodeService
# =============================================================================


class TestOpenCodeService:
    """Tests for the OpenCode service layer."""

    @patch("src.services.opencode_service.run_opencode_subprocess")
    @pytest.mark.asyncio
    async def test_run_query_basic(self, mock_subprocess, opencode_service):
        """Test basic query execution through the service."""
        mock_subprocess.return_value = {
            "success": True,
            "output": "The answer is 42.",
            "error": None,
            "session_id": None,
        }

        result = await opencode_service.run_opencode_query(
            chat_id=123, prompt="What is the meaning of life?"
        )

        assert result == "The answer is 42."
        mock_subprocess.assert_called_once()

    @patch("src.services.opencode_service.run_opencode_subprocess")
    @pytest.mark.asyncio
    async def test_run_query_with_model(self, mock_subprocess, opencode_service):
        """Test query with specific model selection."""
        mock_subprocess.return_value = {
            "success": True,
            "output": "Response",
            "error": None,
            "session_id": None,
        }

        await opencode_service.run_opencode_query(
            chat_id=123, prompt="Test", model="openai:gpt-4o"
        )

        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs["model"] == "openai:gpt-4o"

    @patch("src.services.opencode_service.run_opencode_subprocess")
    @pytest.mark.asyncio
    async def test_run_query_error_returns_message(
        self, mock_subprocess, opencode_service
    ):
        """Test that errors return an error message string."""
        mock_subprocess.return_value = {
            "success": False,
            "output": "",
            "error": "API key invalid",
            "session_id": None,
        }

        result = await opencode_service.run_opencode_query(chat_id=123, prompt="Test")

        assert "error" in result.lower() or "API key invalid" in result

    @patch("src.services.opencode_service.run_opencode_subprocess")
    @pytest.mark.asyncio
    async def test_session_create_and_resume(self, mock_subprocess, opencode_service):
        """Test creating a session and resuming it."""
        # First call creates session
        mock_subprocess.return_value = {
            "success": True,
            "output": "Session started.",
            "error": None,
            "session_id": "sess-new-123",
        }

        result1 = await opencode_service.run_opencode_query(
            chat_id=100, prompt="Start project"
        )
        assert result1 == "Session started."

        # Verify session was stored
        session_id = opencode_service.get_session(100)
        assert session_id == "sess-new-123"

        # Second call resumes session
        mock_subprocess.return_value = {
            "success": True,
            "output": "Continued work.",
            "error": None,
            "session_id": "sess-new-123",
        }

        result2 = await opencode_service.run_opencode_query(
            chat_id=100, prompt="Continue"
        )
        assert result2 == "Continued work."

        # Verify session_id was passed to subprocess
        second_call_kwargs = mock_subprocess.call_args[1]
        assert second_call_kwargs["session_id"] == "sess-new-123"

    @patch(
        "src.services.opencode_service.shutil.which",
        return_value="/usr/local/bin/opencode",
    )
    def test_is_available_when_installed(self, mock_which, opencode_service):
        """Test is_available returns True when opencode is installed."""
        assert opencode_service.is_available() is True

    @patch("src.services.opencode_service.shutil.which", return_value=None)
    def test_is_available_when_not_installed(self, mock_which, opencode_service):
        """Test is_available returns False when opencode is not installed."""
        assert opencode_service.is_available() is False

    def test_list_sessions_empty(self, opencode_service):
        """Test listing sessions when none exist."""
        sessions = opencode_service.list_sessions(chat_id=999)
        assert sessions == []

    @patch("src.services.opencode_service.run_opencode_subprocess")
    @pytest.mark.asyncio
    async def test_list_sessions_after_queries(self, mock_subprocess, opencode_service):
        """Test listing sessions after running queries."""
        mock_subprocess.return_value = {
            "success": True,
            "output": "Done.",
            "error": None,
            "session_id": "sess-list-1",
        }

        await opencode_service.run_opencode_query(chat_id=200, prompt="First")

        sessions = opencode_service.list_sessions(chat_id=200)
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "sess-list-1"

    def test_clear_session(self, opencode_service):
        """Test clearing a session for a chat."""
        opencode_service._sessions[42] = "sess-to-clear"
        opencode_service.clear_session(42)
        assert opencode_service.get_session(42) is None

    @patch("src.services.opencode_service.run_opencode_subprocess")
    @pytest.mark.asyncio
    async def test_default_model_from_settings(self, mock_subprocess, opencode_service):
        """Test that default model comes from settings when not specified."""
        mock_subprocess.return_value = {
            "success": True,
            "output": "Ok",
            "error": None,
            "session_id": None,
        }

        with patch("src.services.opencode_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                opencode_model="anthropic:claude-sonnet-4-20250514",
                opencode_work_dir=None,
                claude_code_work_dir="~/Research/vault",
            )
            await opencode_service.run_opencode_query(chat_id=123, prompt="Test")

        call_kwargs = mock_subprocess.call_args[1]
        assert call_kwargs["model"] == "anthropic:claude-sonnet-4-20250514"


# =============================================================================
# Tests: Agent Backend Abstraction
# =============================================================================


class TestAgentBackend:
    """Tests for the agent backend abstraction and factory."""

    def test_claude_code_backend_is_available(self):
        """Test ClaudeCodeBackend.is_available() checks for claude binary."""
        with patch(
            "src.services.agent_backend.shutil.which",
            return_value="/usr/local/bin/claude",
        ):
            backend = ClaudeCodeBackend()
            assert backend.is_available() is True

    def test_claude_code_backend_not_available(self):
        """Test ClaudeCodeBackend.is_available() when claude is not installed."""
        with patch("src.services.agent_backend.shutil.which", return_value=None):
            backend = ClaudeCodeBackend()
            assert backend.is_available() is False

    def test_opencode_backend_is_available(self):
        """Test OpenCodeBackend.is_available() checks for opencode binary."""
        with patch(
            "src.services.agent_backend.shutil.which",
            return_value="/usr/local/bin/opencode",
        ):
            backend = OpenCodeBackend()
            assert backend.is_available() is True

    def test_opencode_backend_not_available(self):
        """Test OpenCodeBackend.is_available() when opencode is not installed."""
        with patch("src.services.agent_backend.shutil.which", return_value=None):
            backend = OpenCodeBackend()
            assert backend.is_available() is False

    def test_factory_returns_claude_code_by_default(self):
        """Test factory returns ClaudeCodeBackend when config is 'claude_code'."""
        with patch("src.services.agent_backend.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ai_agent_backend="claude_code")
            backend = get_agent_backend()
            assert isinstance(backend, ClaudeCodeBackend)

    def test_factory_returns_opencode_when_configured(self):
        """Test factory returns OpenCodeBackend when config is 'opencode'."""
        with (
            patch("src.services.agent_backend.get_settings") as mock_settings,
            patch(
                "src.services.agent_backend.shutil.which",
                return_value="/usr/bin/opencode",
            ),
        ):
            mock_settings.return_value = MagicMock(ai_agent_backend="opencode")
            backend = get_agent_backend()
            assert isinstance(backend, OpenCodeBackend)

    def test_factory_explicit_backend_name_override(self):
        """Test factory respects explicit backend_name parameter."""
        with patch(
            "src.services.agent_backend.shutil.which", return_value="/usr/bin/opencode"
        ):
            backend = get_agent_backend(backend_name="opencode")
            assert isinstance(backend, OpenCodeBackend)

        backend = get_agent_backend(backend_name="claude_code")
        assert isinstance(backend, ClaudeCodeBackend)

    def test_factory_unknown_backend_raises(self):
        """Test factory raises ValueError for unknown backend."""
        with pytest.raises(ValueError, match="Unknown agent backend"):
            get_agent_backend(backend_name="unknown_agent")

    def test_factory_fallback_when_opencode_not_available(self):
        """Test factory falls back to claude_code when opencode is unavailable."""
        with patch("src.services.agent_backend.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ai_agent_backend="opencode")
            with patch("src.services.agent_backend.shutil.which", return_value=None):
                backend = get_agent_backend()
                # Should fall back to ClaudeCodeBackend
                assert isinstance(backend, ClaudeCodeBackend)

    @pytest.mark.asyncio
    async def test_opencode_backend_run_query(self):
        """Test OpenCodeBackend.run_query delegates to OpenCodeService."""
        backend = OpenCodeBackend()
        with patch.object(
            backend._service, "run_opencode_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = "Mocked response"

            result = await backend.run_query(chat_id=1, prompt="Test")

            assert result == "Mocked response"
            mock_query.assert_called_once_with(chat_id=1, prompt="Test", model=None)

    @pytest.mark.asyncio
    async def test_opencode_backend_list_sessions(self):
        """Test OpenCodeBackend.list_sessions delegates to OpenCodeService."""
        backend = OpenCodeBackend()
        backend._service._sessions[1] = "sess-1"
        backend._service._session_history[1] = [
            {"session_id": "sess-1", "prompt": "test"}
        ]

        sessions = await backend.list_sessions(chat_id=1)
        assert len(sessions) == 1

    @pytest.mark.asyncio
    async def test_claude_code_backend_run_query(self):
        """Test ClaudeCodeBackend.run_query delegates to ClaudeCodeService."""
        backend = ClaudeCodeBackend()
        # Mock the underlying service execute_prompt which is an async generator
        mock_gen_result = [
            ("text", "Hello from Claude", None),
            ("done", "{}", "session-abc"),
        ]

        async def mock_execute(*args, **kwargs):
            for item in mock_gen_result:
                yield item

        with patch.object(backend._service, "execute_prompt", side_effect=mock_execute):
            result = await backend.run_query(chat_id=1, prompt="Hello")
            assert "Hello from Claude" in result

    @pytest.mark.asyncio
    async def test_claude_code_backend_list_sessions(self):
        """Test ClaudeCodeBackend.list_sessions delegates to ClaudeCodeService."""
        backend = ClaudeCodeBackend()
        mock_sessions = [
            MagicMock(session_id="s1", name="Session 1"),
            MagicMock(session_id="s2", name="Session 2"),
        ]

        with patch.object(
            backend._service, "get_user_sessions", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_sessions
            sessions = await backend.list_sessions(chat_id=1)
            assert len(sessions) == 2

    def test_backend_name_property(self):
        """Test that backend name property returns correct values."""
        claude_backend = ClaudeCodeBackend()
        assert claude_backend.name == "claude_code"

        opencode_backend = OpenCodeBackend()
        assert opencode_backend.name == "opencode"
