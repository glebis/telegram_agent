"""
Tests for BotInitState — a richer state object replacing the boolean
_bot_fully_initialized flag in src/lifecycle.py.

The state object must track four distinct states:
  not_started -> initializing -> initialized (success path)
  not_started -> initializing -> failed      (failure path)

Backward compatibility: is_bot_initialized() returns True only when
the state is "initialized".
"""

import pytest

from src.lifecycle import BotInitState, is_bot_initialized


class TestBotInitStateConstruction:
    """A newly created BotInitState starts in 'not_started'."""

    def test_initial_state_is_not_started(self):
        state = BotInitState()
        assert state.state == "not_started"

    def test_initial_state_has_no_error(self):
        state = BotInitState()
        assert state.last_error is None


class TestBotInitStateTransitions:
    """State transitions follow the expected lifecycle."""

    def test_transition_to_initializing(self):
        state = BotInitState()
        state.set_initializing()
        assert state.state == "initializing"

    def test_transition_to_initialized(self):
        state = BotInitState()
        state.set_initializing()
        state.set_initialized()
        assert state.state == "initialized"

    def test_transition_to_failed_with_error_message(self):
        state = BotInitState()
        state.set_initializing()
        state.set_failed("Connection refused")
        assert state.state == "failed"

    def test_failed_state_preserves_error_message(self):
        state = BotInitState()
        state.set_initializing()
        state.set_failed("Timeout after 30s")
        assert state.last_error == "Timeout after 30s"

    def test_initialized_state_clears_error(self):
        """When transitioning to initialized, any prior error is cleared."""
        state = BotInitState()
        state.set_initializing()
        state.set_initialized()
        assert state.last_error is None


class TestBotInitStateQueryMethods:
    """Convenience query methods on the state object."""

    def test_is_initialized_true_only_when_initialized(self):
        state = BotInitState()
        assert state.is_initialized is False

        state.set_initializing()
        assert state.is_initialized is False

        state.set_initialized()
        assert state.is_initialized is True

    def test_is_failed_true_only_when_failed(self):
        state = BotInitState()
        assert state.is_failed is False

        state.set_initializing()
        assert state.is_failed is False

        state.set_failed("err")
        assert state.is_failed is True


class TestBackwardCompatibility:
    """is_bot_initialized() must still return a bool for existing callers."""

    def test_is_bot_initialized_returns_bool(self):
        result = is_bot_initialized()
        assert isinstance(result, bool)


class TestBotInitStateRepr:
    """String representation aids debugging in logs and health endpoints."""

    def test_state_is_stringifiable(self):
        state = BotInitState()
        text = str(state)
        assert "not_started" in text

    def test_failed_state_includes_error_in_repr(self):
        state = BotInitState()
        state.set_initializing()
        state.set_failed("socket hang up")
        text = str(state)
        assert "failed" in text
        assert "socket hang up" in text
