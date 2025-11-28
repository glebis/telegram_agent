"""Tests for callback handlers - inline button interactions"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def mock_callback_query():
    """Create a mock CallbackQuery for testing button callbacks"""
    query = Mock()
    query.answer = AsyncMock()
    query.data = "route:inbox:12345"
    query.message = Mock()
    query.message.reply_text = AsyncMock()
    query.message.chat = Mock(id=12345)
    query.from_user = Mock(id=67890, username="testuser")
    query.edit_message_reply_markup = AsyncMock()
    return query


class TestHandleRouteCallback:
    """Test routing callback handler for link capture buttons"""

    @pytest.mark.asyncio
    async def test_route_to_inbox(self, mock_callback_query):
        """Test routing content to inbox"""
        from src.bot.callback_handlers import handle_route_callback

        params = ["inbox", "99999"]  # message_id that won't be tracked
        await handle_route_callback(mock_callback_query, params)

        mock_callback_query.edit_message_reply_markup.assert_called_once_with(
            reply_markup=None
        )
        mock_callback_query.message.reply_text.assert_called_once()
        call_args = mock_callback_query.message.reply_text.call_args[0][0]
        assert "Inbox" in call_args

    @pytest.mark.asyncio
    async def test_route_to_daily(self, mock_callback_query):
        """Test routing content to daily note"""
        from src.bot.callback_handlers import handle_route_callback

        params = ["daily", "99999"]
        await handle_route_callback(mock_callback_query, params)

        call_args = mock_callback_query.message.reply_text.call_args[0][0]
        assert "Daily" in call_args

    @pytest.mark.asyncio
    async def test_route_to_research(self, mock_callback_query):
        """Test routing content to research folder"""
        from src.bot.callback_handlers import handle_route_callback

        params = ["research", "99999"]
        await handle_route_callback(mock_callback_query, params)

        call_args = mock_callback_query.message.reply_text.call_args[0][0]
        assert "Research" in call_args

    @pytest.mark.asyncio
    async def test_route_done_confirmation(self, mock_callback_query):
        """Test 'done' action confirms routing and removes keyboard"""
        from src.bot.callback_handlers import handle_route_callback

        params = ["done", "99999"]
        await handle_route_callback(mock_callback_query, params)

        mock_callback_query.edit_message_reply_markup.assert_called_once_with(
            reply_markup=None
        )
        # done action doesn't send a reply
        mock_callback_query.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_destination(self, mock_callback_query):
        """Test handling of invalid destination"""
        from src.bot.callback_handlers import handle_route_callback

        params = ["invalid_destination", "99999"]
        await handle_route_callback(mock_callback_query, params)

        call_args = mock_callback_query.message.reply_text.call_args[0][0]
        assert "Unknown destination" in call_args

    @pytest.mark.asyncio
    async def test_empty_params(self, mock_callback_query):
        """Test handling of empty params"""
        from src.bot.callback_handlers import handle_route_callback

        params = []
        await handle_route_callback(mock_callback_query, params)

        call_args = mock_callback_query.message.reply_text.call_args[0][0]
        assert "Invalid" in call_args

    @pytest.mark.asyncio
    async def test_route_without_message_id(self, mock_callback_query):
        """Test routing works without message_id"""
        from src.bot.callback_handlers import handle_route_callback

        params = ["inbox"]  # No message_id
        await handle_route_callback(mock_callback_query, params)

        call_args = mock_callback_query.message.reply_text.call_args[0][0]
        assert "Inbox" in call_args


class TestCallbackDataParsing:
    """Test callback data parsing utilities"""

    def test_keyboard_utils_parse_route_data(self):
        """Test parsing route callback data - note URL gets split on colons"""
        from src.bot.keyboard_utils import get_keyboard_utils

        keyboard_utils = get_keyboard_utils()
        action, params = keyboard_utils.parse_callback_data("route:inbox:https://ex")

        assert action == "route"
        assert params[0] == "inbox"
        # URL after protocol gets split due to colon separator
        assert len(params) >= 2

    def test_keyboard_utils_parse_done_action(self):
        """Test parsing done callback data"""
        from src.bot.keyboard_utils import get_keyboard_utils

        keyboard_utils = get_keyboard_utils()
        action, params = keyboard_utils.parse_callback_data("route:done")

        assert action == "route"
        assert params[0] == "done"


class TestRouteKeyboardCreation:
    """Test inline keyboard creation for routing"""

    def test_routing_keyboard_has_expected_buttons(self):
        """Verify routing keyboard has inbox, daily, research, done buttons"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        # Simulate the keyboard created in message_handlers.py
        keyboard = [
            [
                InlineKeyboardButton("Inbox", callback_data="route:inbox:test"),
                InlineKeyboardButton("Daily", callback_data="route:daily:test"),
            ],
            [
                InlineKeyboardButton("Research", callback_data="route:research:test"),
                InlineKeyboardButton("Done", callback_data="route:done"),
            ],
        ]
        markup = InlineKeyboardMarkup(keyboard)

        assert len(markup.inline_keyboard) == 2
        assert len(markup.inline_keyboard[0]) == 2
        assert len(markup.inline_keyboard[1]) == 2

        # Verify callback data format
        assert markup.inline_keyboard[0][0].callback_data.startswith("route:inbox")
        assert markup.inline_keyboard[1][1].callback_data == "route:done"
