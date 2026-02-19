"""
Tests for Chat model domain behavior methods.

These test pure domain logic on model instances — no database needed.
"""

import pytest

from src.models.chat import Chat


class TestChatSwitchMode:
    """Tests for Chat.switch_mode()."""

    def test_switch_mode_updates_current_mode(self):
        chat = Chat(chat_id=1, user_id=1, current_mode="default")
        chat.switch_mode("formal")
        assert chat.current_mode == "formal"

    def test_switch_mode_updates_preset(self):
        chat = Chat(chat_id=1, user_id=1, current_mode="default")
        chat.switch_mode("artistic", preset="vintage")
        assert chat.current_mode == "artistic"
        assert chat.current_preset == "vintage"

    def test_switch_mode_clears_preset_when_not_provided(self):
        chat = Chat(
            chat_id=1, user_id=1, current_mode="artistic", current_preset="vintage"
        )
        chat.switch_mode("default")
        assert chat.current_mode == "default"
        assert chat.current_preset is None

    def test_switch_mode_returns_self_for_chaining(self):
        chat = Chat(chat_id=1, user_id=1, current_mode="default")
        result = chat.switch_mode("formal")
        assert result is chat

    def test_switch_mode_to_same_mode(self):
        chat = Chat(chat_id=1, user_id=1, current_mode="formal")
        chat.switch_mode("formal", preset="structured")
        assert chat.current_mode == "formal"
        assert chat.current_preset == "structured"


class TestChatClaudeMode:
    """Tests for Chat.is_claude_locked(), enable_claude_mode(), disable_claude_mode()."""

    def test_is_claude_locked_false_by_default(self):
        chat = Chat(chat_id=1, user_id=1)
        assert chat.is_claude_locked() is False

    def test_is_claude_locked_true_when_enabled(self):
        chat = Chat(chat_id=1, user_id=1, claude_mode=True)
        assert chat.is_claude_locked() is True

    def test_enable_claude_mode(self):
        chat = Chat(chat_id=1, user_id=1)
        chat.enable_claude_mode()
        assert chat.claude_mode is True
        assert chat.is_claude_locked() is True

    def test_disable_claude_mode(self):
        chat = Chat(chat_id=1, user_id=1, claude_mode=True)
        chat.disable_claude_mode()
        assert chat.claude_mode is False
        assert chat.is_claude_locked() is False

    def test_enable_claude_mode_returns_self(self):
        chat = Chat(chat_id=1, user_id=1)
        result = chat.enable_claude_mode()
        assert result is chat

    def test_disable_claude_mode_returns_self(self):
        chat = Chat(chat_id=1, user_id=1, claude_mode=True)
        result = chat.disable_claude_mode()
        assert result is chat

    def test_enable_already_enabled_is_idempotent(self):
        chat = Chat(chat_id=1, user_id=1, claude_mode=True)
        chat.enable_claude_mode()
        assert chat.claude_mode is True

    def test_disable_already_disabled_is_idempotent(self):
        chat = Chat(chat_id=1, user_id=1, claude_mode=False)
        chat.disable_claude_mode()
        assert chat.claude_mode is False


class TestChatGetEffectiveModel:
    """Tests for Chat.get_effective_model()."""

    def test_returns_stored_model(self):
        chat = Chat(chat_id=1, user_id=1, claude_model="sonnet")
        assert chat.get_effective_model() == "sonnet"

    def test_returns_default_when_none(self):
        chat = Chat(chat_id=1, user_id=1, claude_model=None)
        assert chat.get_effective_model() == "opus"

    def test_returns_default_when_empty_string(self):
        chat = Chat(chat_id=1, user_id=1, claude_model="")
        assert chat.get_effective_model() == "opus"


class TestChatGetEffectiveThinkingEffort:
    """Tests for Chat.get_effective_thinking_effort()."""

    def test_returns_stored_effort(self):
        chat = Chat(chat_id=1, user_id=1, thinking_effort="high")
        assert chat.get_effective_thinking_effort() == "high"

    def test_returns_default_when_none(self):
        chat = Chat(chat_id=1, user_id=1, thinking_effort=None)
        assert chat.get_effective_thinking_effort() == "medium"

    def test_returns_default_when_empty_string(self):
        chat = Chat(chat_id=1, user_id=1, thinking_effort="")
        assert chat.get_effective_thinking_effort() == "medium"
