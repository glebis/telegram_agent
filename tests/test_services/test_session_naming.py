"""
Tests for the Session Naming Service.

Tests cover:
- Session name generation from prompts (via Claude SDK subprocess)
- Fallback behavior when subprocess fails
- Name sanitization and validation
"""

import json
import re
from unittest.mock import AsyncMock, patch

import pytest

from src.services.session_naming import generate_session_name


def _make_subprocess_result(name_text: str, returncode: int = 0):
    """Helper: create mock stdout/stderr for a successful subprocess."""
    stdout = json.dumps({"type": "result", "text": name_text}).encode() + b"\n"
    stderr = b""
    return stdout, stderr, returncode


def _make_subprocess_error(error_text: str = "API Error"):
    """Helper: create mock stdout/stderr for a failed subprocess."""
    stdout = json.dumps({"type": "error", "text": error_text}).encode() + b"\n"
    stderr = b""
    return stdout, stderr, 1


class _FakeProcess:
    """Fake asyncio subprocess for testing."""

    def __init__(self, stdout_bytes: bytes, stderr_bytes: bytes, returncode: int):
        self._stdout = stdout_bytes
        self._stderr = stderr_bytes
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


class TestGenerateSessionName:
    """Tests for generate_session_name function."""

    @pytest.mark.asyncio
    async def test_generates_valid_kebab_case_name(self):
        """Test that generated names are valid kebab-case."""
        stdout, stderr, rc = _make_subprocess_result("test-session-name")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Test prompt for session naming")

            assert name == "test-session-name"
            assert name.islower()
            assert re.match(r"^[a-z0-9-]+$", name)

    @pytest.mark.asyncio
    async def test_sanitizes_special_characters(self):
        """Test that special characters are removed from generated names."""
        stdout, stderr, rc = _make_subprocess_result("Test@Session#Name!")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Any prompt")

            # Special chars should be removed
            assert "@" not in name
            assert "#" not in name
            assert "!" not in name
            assert name == "testsessionname"

    @pytest.mark.asyncio
    async def test_removes_multiple_hyphens(self):
        """Test that multiple consecutive hyphens are collapsed."""
        stdout, stderr, rc = _make_subprocess_result("test---session---name")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Any prompt")

            assert "---" not in name
            assert name == "test-session-name"

    @pytest.mark.asyncio
    async def test_removes_leading_trailing_hyphens(self):
        """Test that leading and trailing hyphens are removed."""
        stdout, stderr, rc = _make_subprocess_result("-test-session-name-")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Any prompt")

            assert not name.startswith("-")
            assert not name.endswith("-")
            assert name == "test-session-name"

    @pytest.mark.asyncio
    async def test_limits_name_length(self):
        """Test that names are limited to 50 characters."""
        stdout, stderr, rc = _make_subprocess_result("a" * 100)
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Any prompt")

            assert len(name) <= 50

    @pytest.mark.asyncio
    async def test_truncates_long_prompt(self):
        """Test that very long prompts are truncated before sending to subprocess."""
        stdout, stderr, rc = _make_subprocess_result("truncated-prompt")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))
            with patch(
                "src.services.session_naming._build_naming_script"
            ) as mock_build:
                mock_build.return_value = "pass"  # dummy script

                long_prompt = "x" * 1000
                await generate_session_name(long_prompt)

                # Verify the prompt was passed to _build_naming_script
                # (which internally truncates to 500 chars)
                mock_build.assert_called_once_with(long_prompt)


class TestFallbackBehavior:
    """Tests for fallback behavior when subprocess fails."""

    @pytest.mark.asyncio
    async def test_fallback_on_subprocess_error(self):
        """Test fallback name generation when subprocess call fails."""
        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(
                side_effect=Exception("Subprocess Error")
            )

            name = await generate_session_name("Help me analyze this video")

            # Should use fallback logic - first few meaningful words
            assert name  # Should not be empty
            assert re.match(r"^[a-z0-9-]+$", name)

    @pytest.mark.asyncio
    async def test_fallback_on_nonzero_exit(self):
        """Test fallback name generation when subprocess exits non-zero."""
        fake_proc = _FakeProcess(b"", b"some error", 1)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(b"", b"some error"))

            name = await generate_session_name("Help me analyze this video")

            assert name
            assert re.match(r"^[a-z0-9-]+$", name)

    @pytest.mark.asyncio
    async def test_fallback_filters_common_words(self):
        """Test that fallback filters articles and prepositions."""
        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(
                side_effect=Exception("Subprocess Error")
            )

            name = await generate_session_name("The quick fox in the forest")

            # Common words like 'the', 'in' should be filtered
            assert "the" not in name.split("-")
            assert "in" not in name.split("-")

    @pytest.mark.asyncio
    async def test_fallback_on_empty_response(self):
        """Test fallback when subprocess returns empty name."""
        stdout, stderr, rc = _make_subprocess_result("")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Test prompt")

            # Should use fallback
            assert name  # Should not be empty

    @pytest.mark.asyncio
    async def test_fallback_unnamed_session(self):
        """Test that empty prompts result in 'unnamed-session'."""
        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(
                side_effect=Exception("Subprocess Error")
            )

            # Prompt with only filtered words
            name = await generate_session_name("the a an to for in on")

            # After filtering common words, should fall back to 'unnamed-session'
            assert name == "unnamed-session"


class TestNameValidation:
    """Tests for name validation rules."""

    @pytest.mark.asyncio
    async def test_name_is_lowercase(self):
        """Test that generated names are always lowercase."""
        stdout, stderr, rc = _make_subprocess_result("UPPERCASE-NAME")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Any prompt")

            assert name.islower()
            assert name == "uppercase-name"

    @pytest.mark.asyncio
    async def test_spaces_converted_to_hyphens(self):
        """Test that spaces are converted to hyphens."""
        stdout, stderr, rc = _make_subprocess_result("test session name")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Any prompt")

            assert " " not in name
            assert name == "test-session-name"

    @pytest.mark.asyncio
    async def test_name_contains_only_valid_chars(self):
        """Test that names only contain a-z, 0-9, and hyphens."""
        stdout, stderr, rc = _make_subprocess_result("test123-name456")
        fake_proc = _FakeProcess(stdout, stderr, rc)

        with patch("src.services.session_naming.asyncio") as mock_asyncio:
            mock_asyncio.create_subprocess_exec = AsyncMock(return_value=fake_proc)
            mock_asyncio.wait_for = AsyncMock(return_value=(stdout, stderr))

            name = await generate_session_name("Any prompt")

            assert re.match(r"^[a-z0-9-]+$", name)
            assert name == "test123-name456"


class TestBuildNamingScript:
    """Tests for _build_naming_script helper."""

    def test_script_uses_haiku_model(self):
        """Test that the subprocess script specifies the haiku model."""
        from src.services.session_naming import _build_naming_script

        script = _build_naming_script("test prompt")
        assert 'model="haiku"' in script

    def test_script_unsets_api_key(self):
        """Test that the subprocess script unsets ANTHROPIC_API_KEY."""
        from src.services.session_naming import _build_naming_script

        script = _build_naming_script("test prompt")
        assert 'os.environ.pop("ANTHROPIC_API_KEY"' in script

    def test_script_uses_no_tools(self):
        """Test that the subprocess script disables tools."""
        from src.services.session_naming import _build_naming_script

        script = _build_naming_script("test prompt")
        assert "allowed_tools=[]" in script

    def test_script_limits_max_turns(self):
        """Test that the subprocess script limits to 1 turn."""
        from src.services.session_naming import _build_naming_script

        script = _build_naming_script("test prompt")
        assert "max_turns=1" in script

    def test_script_truncates_prompt(self):
        """Test that _build_naming_script truncates long prompts."""
        from src.services.session_naming import _build_naming_script

        long_prompt = "x" * 1000
        script = _build_naming_script(long_prompt)
        # The prompt in the script should be at most 500 chars
        # (json.dumps adds quotes but the content is truncated)
        assert "x" * 501 not in script
