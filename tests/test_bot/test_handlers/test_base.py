"""Tests for base handler utilities."""

from unittest.mock import MagicMock, patch

import pytest


class TestClaudeModeCache:
    """Tests for Claude mode caching functionality."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset the cache before each test."""
        from src.bot.handlers.base import _claude_mode_cache

        _claude_mode_cache.clear()
        yield
        _claude_mode_cache.clear()

    def test_cache_direct_set_and_get(self):
        """Direct cache operations work correctly."""
        from src.bot.handlers.base import _claude_mode_cache

        # Direct cache manipulation (testing the cache itself)
        _claude_mode_cache[12345] = True
        assert _claude_mode_cache.get(12345) is True

        _claude_mode_cache[12345] = False
        assert _claude_mode_cache.get(12345) is False

    def test_cache_multiple_chats_isolated(self):
        """Different chats have isolated cache entries."""
        from src.bot.handlers.base import _claude_mode_cache

        _claude_mode_cache[111] = True
        _claude_mode_cache[222] = False
        _claude_mode_cache[333] = True

        assert _claude_mode_cache.get(111) is True
        assert _claude_mode_cache.get(222) is False
        assert _claude_mode_cache.get(333) is True

    def test_cache_returns_none_for_missing(self):
        """Cache returns None for non-existent keys."""
        from src.bot.handlers.base import _claude_mode_cache

        assert _claude_mode_cache.get(99999) is None

    @pytest.mark.asyncio
    @patch("src.core.mode_cache.get_db_session")
    async def test_set_claude_mode_updates_cache_and_db(self, mock_get_session):
        """set_claude_mode updates both cache and database."""
        from unittest.mock import AsyncMock

        from src.bot.handlers.base import _claude_mode_cache, set_claude_mode

        # Setup mock session that returns a chat record
        mock_chat = MagicMock()
        mock_chat.claude_mode = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_chat

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        result = await set_claude_mode(12345, True)

        assert result is True
        assert _claude_mode_cache.get(12345) is True
        assert mock_chat.claude_mode is True


class TestTelegramApiSync:
    """Tests for synchronous Telegram API calls."""

    @patch("src.utils.telegram_api.run_python_script")
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token"})
    def test_run_telegram_api_sync_success(self, mock_run):
        """Successful API call returns parsed JSON."""
        from src.bot.handlers.base import _run_telegram_api_sync

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = '{"success": true, "result": {"message_id": 123}}'
        mock_run.return_value = mock_result

        result = _run_telegram_api_sync("sendMessage", {"chat_id": 1, "text": "hi"})

        assert result is not None
        assert result.get("message_id") == 123

    @patch("src.utils.telegram_api.run_python_script")
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token"})
    def test_run_telegram_api_sync_failure(self, mock_run):
        """Failed subprocess raises RetryableError after exhausting retries."""
        from src.bot.handlers.base import _run_telegram_api_sync
        from src.utils.retry import RetryableError

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Network error"
        mock_run.return_value = mock_result

        with pytest.raises(RetryableError):
            _run_telegram_api_sync("sendMessage", {"chat_id": 1, "text": "hi"})

    @patch("src.utils.telegram_api.run_python_script")
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token"})
    def test_run_telegram_api_sync_invalid_json(self, mock_run):
        """Invalid JSON response returns None."""
        from src.bot.handlers.base import _run_telegram_api_sync

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = "not json"
        mock_run.return_value = mock_result

        result = _run_telegram_api_sync("sendMessage", {"chat_id": 1, "text": "hi"})
        assert result is None

    @patch("src.utils.telegram_api.run_python_script")
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token"})
    def test_run_telegram_api_sync_exception(self, mock_run):
        """Exception during API call returns None."""
        from src.bot.handlers.base import _run_telegram_api_sync

        mock_run.side_effect = Exception("Subprocess failed")

        result = _run_telegram_api_sync("sendMessage", {"chat_id": 1, "text": "hi"})
        assert result is None

    def test_run_telegram_api_sync_no_token(self):
        """Missing token returns None."""
        from src.bot.handlers.base import _run_telegram_api_sync

        with patch.dict("os.environ", {}, clear=True):
            # Remove token from environment
            import os

            old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            try:
                result = _run_telegram_api_sync(
                    "sendMessage", {"chat_id": 1, "text": "hi"}
                )
                assert result is None
            finally:
                if old_token:
                    os.environ["TELEGRAM_BOT_TOKEN"] = old_token


class TestSendMessageSync:
    """Tests for send_message_sync function."""

    @patch("src.utils.telegram_api._run_telegram_api_sync")
    def test_basic_message(self, mock_api):
        """Basic message call with required parameters."""
        from src.bot.handlers.base import send_message_sync

        mock_api.return_value = {"ok": True, "result": {"message_id": 123}}

        send_message_sync(12345, "Hello")

        mock_api.assert_called_once()
        call_args = mock_api.call_args
        assert call_args[0][0] == "sendMessage"
        payload = call_args[0][1]
        assert payload["chat_id"] == 12345
        assert payload["text"] == "Hello"
        assert payload["parse_mode"] == "HTML"

    @patch("src.utils.telegram_api._run_telegram_api_sync")
    def test_message_with_reply(self, mock_api):
        """Message with reply_to parameter."""
        from src.bot.handlers.base import send_message_sync

        mock_api.return_value = {"ok": True}

        send_message_sync(12345, "Reply", reply_to=999)

        payload = mock_api.call_args[0][1]
        assert payload["reply_to_message_id"] == 999

    @patch("src.utils.telegram_api._run_telegram_api_sync")
    def test_message_with_markup(self, mock_api):
        """Message with reply_markup parameter."""
        from src.bot.handlers.base import send_message_sync

        mock_api.return_value = {"ok": True}
        keyboard = {"inline_keyboard": [[{"text": "Button", "callback_data": "test"}]]}

        send_message_sync(12345, "Choose", reply_markup=keyboard)

        payload = mock_api.call_args[0][1]
        assert payload["reply_markup"] == keyboard


class TestEditMessageSync:
    """Tests for edit_message_sync function."""

    @patch("src.utils.telegram_api._run_telegram_api_sync")
    def test_edit_message(self, mock_api):
        """Edit message with required parameters."""
        from src.bot.handlers.base import edit_message_sync

        mock_api.return_value = {"ok": True}

        edit_message_sync(12345, 999, "Updated text")

        call_args = mock_api.call_args
        assert call_args[0][0] == "editMessageText"
        payload = call_args[0][1]
        assert payload["chat_id"] == 12345
        assert payload["message_id"] == 999
        assert payload["text"] == "Updated text"

    @patch("src.utils.telegram_api._run_telegram_api_sync")
    def test_edit_with_markup(self, mock_api):
        """Edit message with new keyboard."""
        from src.bot.handlers.base import edit_message_sync

        mock_api.return_value = {"ok": True}
        keyboard = {"inline_keyboard": []}

        edit_message_sync(12345, 999, "Updated", reply_markup=keyboard)

        payload = mock_api.call_args[0][1]
        assert payload["reply_markup"] == keyboard


class TestInitializeUserChat:
    """Tests for user/chat initialization."""

    @pytest.mark.asyncio
    @patch("src.bot.handlers.base.get_db_session")
    async def test_initialize_new_user(self, mock_get_session):
        """Initialize a new user creates records."""
        from src.bot.handlers.base import initialize_user_chat

        # Setup mock session
        mock_session = MagicMock()
        mock_session.__aenter__ = MagicMock(return_value=mock_session)
        mock_session.__aexit__ = MagicMock(return_value=None)
        mock_session.execute = MagicMock()
        mock_session.commit = MagicMock()

        # Mock the query result
        from unittest.mock import AsyncMock

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # User doesn't exist
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        await initialize_user_chat(user_id=123, chat_id=456, username="testuser")

        # Should have made database calls
        assert mock_session.execute.called


class TestModuleImports:
    """Test that all expected functions are importable."""

    def test_import_base_functions(self):
        """All base functions can be imported."""
        from src.bot.handlers.base import (
            _run_telegram_api_sync,
            edit_message_sync,
            get_claude_mode,
            init_claude_mode_cache,
            initialize_user_chat,
            send_message_sync,
            set_claude_mode,
        )

        assert callable(initialize_user_chat)
        assert callable(send_message_sync)
        assert callable(edit_message_sync)
        assert callable(get_claude_mode)
        assert callable(set_claude_mode)
        assert callable(init_claude_mode_cache)
        assert callable(_run_telegram_api_sync)

    def test_import_from_package(self):
        """Functions can be imported from package __init__."""
        from src.bot.handlers import (
            escape_html,
            initialize_user_chat,
        )

        assert callable(initialize_user_chat)
        assert callable(escape_html)
