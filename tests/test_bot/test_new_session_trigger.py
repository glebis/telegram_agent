"""
Tests for 'new session' trigger for conversation splitting (#14).

Tests cover:
- Trigger phrase detection
- Extracting prompt after trigger
- Force new session when trigger detected
- Case insensitivity
- Integration with voice forward
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# Test: Trigger Phrase Detection
# =============================================================================


class TestNewSessionTriggerDetection:
    """Test detection of 'new session' trigger phrase."""

    def test_detects_new_session_at_start(self):
        """Should detect 'new session' at the start of message."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("new session help me write code")
        assert result is not None
        assert result["triggered"] is True
        assert result["prompt"] == "help me write code"

    def test_detects_new_session_case_insensitive(self):
        """Should detect trigger regardless of case."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        # Various case combinations
        assert detect_new_session_trigger("New Session hello")["triggered"] is True
        assert detect_new_session_trigger("NEW SESSION hello")["triggered"] is True
        assert detect_new_session_trigger("nEw SeSsIoN hello")["triggered"] is True

    def test_extracts_prompt_after_trigger(self):
        """Should extract the text after trigger as prompt."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("new session Write a poem about cats")
        assert result["prompt"] == "Write a poem about cats"

    def test_handles_trigger_without_prompt(self):
        """Should handle 'new session' with no following text."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("new session")
        assert result["triggered"] is True
        assert result["prompt"] == ""

    def test_handles_trigger_with_only_whitespace(self):
        """Should handle 'new session' followed by only whitespace."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("new session   ")
        assert result["triggered"] is True
        assert result["prompt"] == ""

    def test_no_trigger_when_not_at_start(self):
        """Should NOT trigger when phrase is not at start."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("please start a new session")
        assert result["triggered"] is False

    def test_no_trigger_for_normal_text(self):
        """Should NOT trigger for normal text."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("help me write code")
        assert result["triggered"] is False

    def test_handles_newline_after_trigger(self):
        """Should handle newline between trigger and prompt."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("new session\nWrite a function")
        assert result["triggered"] is True
        assert result["prompt"] == "Write a function"


# =============================================================================
# Test: Alternative Trigger Phrases
# =============================================================================


class TestAlternativeTriggerPhrases:
    """Test alternative trigger phrases."""

    def test_detects_start_new_session(self):
        """Should detect 'start new session' as trigger."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("start new session help me")
        assert result["triggered"] is True
        assert result["prompt"] == "help me"

    def test_detects_fresh_session(self):
        """Should detect 'fresh session' as trigger."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("fresh session build an API")
        assert result["triggered"] is True
        assert result["prompt"] == "build an API"

    def test_detects_russian_trigger(self):
        """Should detect Russian trigger phrase."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("новая сессия напиши код")
        assert result["triggered"] is True
        assert result["prompt"] == "напиши код"


# =============================================================================
# Test: Integration with Voice Forward
# =============================================================================


class TestNewSessionWithVoiceForward:
    """Test new session trigger with voice forward flow."""

    @pytest.mark.asyncio
    async def test_voice_forward_forces_new_session_on_trigger(self):
        """Voice forward should force new session when trigger detected."""
        # When voice transcription starts with "new session",
        # forward_voice_to_claude should be called with force_new=True
        # or session_id=None to create a new session
        pass  # Will be tested after implementation

    @pytest.mark.asyncio
    async def test_voice_forward_uses_prompt_after_trigger(self):
        """Voice forward should use only the text after trigger as prompt."""
        # "new session help me" should send only "help me" to Claude
        pass  # Will be tested after implementation


# =============================================================================
# Test: Integration with Collect Mode
# =============================================================================


class TestNewSessionWithCollectMode:
    """Test new session trigger in collect mode."""

    @pytest.mark.asyncio
    async def test_collect_trigger_starts_new_session(self):
        """Collect trigger with 'new session' should start fresh session."""
        pass  # Will be tested after implementation

    @pytest.mark.asyncio
    async def test_collect_splits_at_new_session(self):
        """Messages before 'new session' should be separate from after."""
        pass  # Will be tested after implementation


# =============================================================================
# Test: Function Exists
# =============================================================================


class TestNewSessionTriggerFunctionExists:
    """Test that required functions exist."""

    def test_detect_new_session_trigger_exists(self):
        """detect_new_session_trigger function should exist."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        assert callable(detect_new_session_trigger)

    def test_detect_new_session_trigger_returns_dict(self):
        """detect_new_session_trigger should return a dict."""
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        result = detect_new_session_trigger("test message")
        assert isinstance(result, dict)
        assert "triggered" in result
        assert "prompt" in result
