"""
Tests for session_service — business logic extracted from handler layer.

Covers:
- detect_new_session_trigger() — trigger phrase detection
- NEW_SESSION_TRIGGERS constant availability
"""

import pytest


# =============================================================================
# detect_new_session_trigger
# =============================================================================


class TestDetectNewSessionTrigger:
    """Test detection of 'new session' trigger phrase (service layer)."""

    def test_import_from_service(self):
        """Function should be importable from services.session_service."""
        from src.services.session_service import detect_new_session_trigger

        assert callable(detect_new_session_trigger)

    def test_triggers_constant_importable(self):
        """NEW_SESSION_TRIGGERS should be importable from service."""
        from src.services.session_service import NEW_SESSION_TRIGGERS

        assert isinstance(NEW_SESSION_TRIGGERS, list)
        assert len(NEW_SESSION_TRIGGERS) > 0

    def test_detects_new_session_at_start(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("new session help me write code")
        assert result["triggered"] is True
        assert result["prompt"] == "help me write code"

    def test_detects_case_insensitive(self):
        from src.services.session_service import detect_new_session_trigger

        assert detect_new_session_trigger("New Session hello")["triggered"] is True
        assert detect_new_session_trigger("NEW SESSION hello")["triggered"] is True

    def test_extracts_prompt_after_trigger(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("new session Write a poem about cats")
        assert result["prompt"] == "Write a poem about cats"

    def test_trigger_without_prompt(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("new session")
        assert result["triggered"] is True
        assert result["prompt"] == ""

    def test_trigger_with_only_whitespace(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("new session   ")
        assert result["triggered"] is True
        assert result["prompt"] == ""

    def test_no_trigger_when_not_at_start(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("please start a new session")
        assert result["triggered"] is False

    def test_no_trigger_for_normal_text(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("help me write code")
        assert result["triggered"] is False

    def test_handles_newline_after_trigger(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("new session\nWrite a function")
        assert result["triggered"] is True
        assert result["prompt"] == "Write a function"

    def test_handles_empty_text(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("")
        assert result["triggered"] is False
        assert result["prompt"] == ""

    def test_handles_none_text(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger(None)
        assert result["triggered"] is False
        assert result["prompt"] == ""

    def test_detects_start_new_session(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("start new session help me")
        assert result["triggered"] is True
        assert result["prompt"] == "help me"

    def test_detects_fresh_session(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("fresh session build an API")
        assert result["triggered"] is True
        assert result["prompt"] == "build an API"

    def test_detects_russian_trigger(self):
        from src.services.session_service import detect_new_session_trigger

        result = detect_new_session_trigger("новая сессия напиши код")
        assert result["triggered"] is True
        assert result["prompt"] == "напиши код"


class TestBackwardsCompatibility:
    """The old import path should still work via re-export."""

    def test_old_import_still_works(self):
        from src.bot.handlers.claude_commands import detect_new_session_trigger

        assert callable(detect_new_session_trigger)

    def test_old_triggers_constant_still_works(self):
        from src.bot.handlers.claude_commands import NEW_SESSION_TRIGGERS

        assert isinstance(NEW_SESSION_TRIGGERS, list)

    def test_old_and_new_are_same_function(self):
        from src.bot.handlers.claude_commands import (
            detect_new_session_trigger as old_fn,
        )
        from src.services.session_service import (
            detect_new_session_trigger as new_fn,
        )

        assert old_fn is new_fn
