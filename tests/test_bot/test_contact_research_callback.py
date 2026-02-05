"""
Tests for contact_research callback handler (Issue #51).

The security hardening commit introduced inline keyboard buttons with
callback_data="contact_research:{message_id}" and "contact_research:skip",
but no handler was added to callback_handlers.py. These tests verify
that the contact_research action is properly routed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_query():
    """Create a mock callback query."""
    query = AsyncMock()
    query.data = "contact_research:12345"
    query.answer = AsyncMock()
    query.from_user = MagicMock()
    query.from_user.id = 100
    query.message = MagicMock()
    query.message.chat = MagicMock()
    query.message.chat.id = 200
    query.message.reply_text = AsyncMock()
    query.message.message_id = 12345
    query.edit_message_reply_markup = AsyncMock()
    return query


@pytest.fixture
def mock_update(mock_query):
    """Create a mock Update with callback query."""
    update = MagicMock()
    update.callback_query = mock_query
    update.effective_user = mock_query.from_user
    update.effective_chat = mock_query.message.chat
    return update


@pytest.fixture
def mock_context():
    """Create a mock context."""
    context = MagicMock()
    context.user_data = {}
    return context


class TestContactResearchCallback:
    """Tests for contact_research callback handling."""

    @pytest.mark.asyncio
    async def test_contact_research_action_is_handled(self, mock_update, mock_context):
        """contact_research action should NOT fall through to 'Unknown action'."""
        mock_query = mock_update.callback_query
        mock_query.data = "contact_research:12345"

        with (
            patch("src.bot.callback_handlers.get_callback_data_manager") as mock_cdm,
            patch("src.bot.callback_handlers.get_keyboard_utils") as mock_ku,
        ):
            # Setup callback data parsing to return contact_research action
            cdm = MagicMock()
            cdm.parse_callback_data.return_value = (
                "contact_research",
                None,
                ["12345"],
            )
            mock_cdm.return_value = cdm

            ku = MagicMock()
            ku.parse_callback_data.return_value = ("contact_research", ["12345"])
            mock_ku.return_value = ku

            from src.bot.callback_handlers import handle_callback_query

            await handle_callback_query(mock_update, mock_context)

            # Should NOT show "Unknown action" error
            for call in mock_query.message.reply_text.call_args_list:
                args = call[0] if call[0] else []
                kwargs = call[1] if call[1] else {}
                text = args[0] if args else kwargs.get("text", "")
                assert (
                    "Unknown action" not in text
                ), "contact_research should be handled, not fall through to Unknown action"

    @pytest.mark.asyncio
    async def test_contact_research_skip_is_handled(self, mock_update, mock_context):
        """contact_research:skip should acknowledge and dismiss the keyboard."""
        mock_query = mock_update.callback_query
        mock_query.data = "contact_research:skip"

        with (
            patch("src.bot.callback_handlers.get_callback_data_manager") as mock_cdm,
            patch("src.bot.callback_handlers.get_keyboard_utils") as mock_ku,
        ):
            cdm = MagicMock()
            cdm.parse_callback_data.return_value = (
                "contact_research",
                None,
                ["skip"],
            )
            mock_cdm.return_value = cdm

            ku = MagicMock()
            ku.parse_callback_data.return_value = ("contact_research", ["skip"])
            mock_ku.return_value = ku

            from src.bot.callback_handlers import handle_callback_query

            await handle_callback_query(mock_update, mock_context)

            # Should NOT show "Unknown action" error
            for call in mock_query.message.reply_text.call_args_list:
                args = call[0] if call[0] else []
                kwargs = call[1] if call[1] else {}
                text = args[0] if args else kwargs.get("text", "")
                assert (
                    "Unknown action" not in text
                ), "contact_research:skip should be handled, not fall through"
