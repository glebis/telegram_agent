"""
Tests for auto-forward voice messages to Claude Code session (#13).

Tests cover:
- auto_forward_voice setting default value
- Setting getter/setter functions
- Settings keyboard includes toggle
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db_chat():
    """Create a mock database Chat object."""
    chat = MagicMock()
    chat.id = 1
    chat.chat_id = 67890
    chat.user_id = 1
    chat.auto_forward_voice = True  # Default ON
    chat.claude_mode = False
    return chat


# =============================================================================
# Test: Chat Model has auto_forward_voice
# =============================================================================


class TestChatModel:
    """Test the Chat model has auto_forward_voice column."""

    def test_chat_model_has_auto_forward_voice_column(self):
        """Chat model should have auto_forward_voice attribute."""
        from src.models.chat import Chat

        assert hasattr(
            Chat, "auto_forward_voice"
        ), "Chat model should have auto_forward_voice column"


# =============================================================================
# Test: auto_forward_voice Setting Functions
# =============================================================================


class TestAutoForwardVoiceSetting:
    """Test the auto_forward_voice setting functions."""

    @pytest.mark.asyncio
    async def test_get_auto_forward_voice_returns_default_true_for_unknown_chat(self):
        """get_auto_forward_voice should return True for unknown chats."""
        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_ctx.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )
            mock_session.return_value.__aenter__.return_value = mock_ctx

            from src.services.keyboard_service import get_auto_forward_voice

            result = await get_auto_forward_voice(99999)
            assert result is True, "Default should be True for unknown chats"

    @pytest.mark.asyncio
    async def test_get_auto_forward_voice_returns_saved_value(self, mock_db_chat):
        """get_auto_forward_voice should return saved database value."""
        mock_db_chat.auto_forward_voice = False

        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_ctx.execute = AsyncMock(
                return_value=MagicMock(
                    scalar_one_or_none=MagicMock(return_value=mock_db_chat)
                )
            )
            mock_session.return_value.__aenter__.return_value = mock_ctx

            from src.services.keyboard_service import get_auto_forward_voice

            result = await get_auto_forward_voice(67890)
            assert result is False, "Should return saved value from database"

    @pytest.mark.asyncio
    async def test_set_auto_forward_voice_updates_chat(self, mock_db_chat):
        """set_auto_forward_voice should update the chat setting."""
        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_ctx.execute = AsyncMock(
                return_value=MagicMock(
                    scalar_one_or_none=MagicMock(return_value=mock_db_chat)
                )
            )
            mock_ctx.commit = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_ctx

            from src.services.keyboard_service import set_auto_forward_voice

            result = await set_auto_forward_voice(67890, False)

            assert result is True, "Should return True on success"
            assert (
                mock_db_chat.auto_forward_voice is False
            ), "Should update chat setting"
            mock_ctx.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_auto_forward_voice_returns_false_for_unknown_chat(self):
        """set_auto_forward_voice should return False for unknown chats."""
        with patch("src.services.keyboard_service.get_db_session") as mock_session:
            mock_ctx = AsyncMock()
            mock_ctx.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )
            mock_session.return_value.__aenter__.return_value = mock_ctx

            from src.services.keyboard_service import set_auto_forward_voice

            result = await set_auto_forward_voice(99999, False)
            assert result is False, "Should return False for unknown chat"


# =============================================================================
# Test: Settings Keyboard
# =============================================================================


class TestSettingsKeyboard:
    """Test settings keyboard includes voice forward toggle."""

    def test_settings_keyboard_has_voice_forward_toggle_enabled(self):
        """Settings keyboard should show voice forward ON when enabled."""
        from src.bot.keyboard_utils import KeyboardUtils

        kb = KeyboardUtils()
        keyboard = kb.create_settings_keyboard(
            keyboard_enabled=True, auto_forward_voice=True
        )

        # Find the voice forward button
        found_button = False
        for row in keyboard.inline_keyboard:
            for button in row:
                if "Voice → Claude" in button.text:
                    found_button = True
                    assert "ON" in button.text, "Should show ON when enabled"
                    assert button.callback_data == "settings:toggle_voice_forward"

        assert found_button, "Settings keyboard should have voice forward toggle"

    def test_settings_keyboard_has_voice_forward_toggle_disabled(self):
        """Settings keyboard should show voice forward OFF when disabled."""
        from src.bot.keyboard_utils import KeyboardUtils

        kb = KeyboardUtils()
        keyboard = kb.create_settings_keyboard(
            keyboard_enabled=True, auto_forward_voice=False
        )

        # Find the voice forward button
        for row in keyboard.inline_keyboard:
            for button in row:
                if "Voice → Claude" in button.text:
                    assert "OFF" in button.text, "Should show OFF when disabled"
                    return

        pytest.fail("Voice forward toggle button not found")


# =============================================================================
# Test: forward_voice_to_claude Function Exists
# =============================================================================


class TestForwardVoiceToClaude:
    """Test the forward_voice_to_claude function."""

    def test_forward_voice_to_claude_function_exists(self):
        """forward_voice_to_claude function should exist."""
        from src.bot.handlers.claude_commands import forward_voice_to_claude

        assert callable(
            forward_voice_to_claude
        ), "forward_voice_to_claude should be a callable function"

    def test_forward_voice_to_claude_is_async(self):
        """forward_voice_to_claude should be an async function."""
        import inspect

        from src.bot.handlers.claude_commands import forward_voice_to_claude

        assert inspect.iscoroutinefunction(
            forward_voice_to_claude
        ), "forward_voice_to_claude should be an async function"


# =============================================================================
# Test: Integration - Voice Handler Uses Auto-Forward
# =============================================================================


class TestVoiceHandlerIntegration:
    """Test that voice handler integrates with auto-forward."""

    def test_voice_handler_imports_auto_forward_functions(self):
        """Voice handler should be able to import auto-forward functions."""
        # This tests that the imports work correctly
        from src.bot.handlers.claude_commands import forward_voice_to_claude
        from src.services.keyboard_service import get_auto_forward_voice

        assert callable(get_auto_forward_voice)
        assert callable(forward_voice_to_claude)

    def test_voice_handler_has_auto_forward_logic(self):
        """Voice handler should contain auto-forward logic."""
        import inspect

        from src.bot import message_handlers

        source = inspect.getsource(message_handlers.handle_voice_message)

        # Check that the handler references auto-forward
        assert (
            "get_auto_forward_voice" in source
        ), "Voice handler should call get_auto_forward_voice"
        assert (
            "forward_voice_to_claude" in source
        ), "Voice handler should call forward_voice_to_claude"
