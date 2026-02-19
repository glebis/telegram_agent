"""Tests that SRSService uses injected KeyboardBuilder instead of direct imports."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.ports.keyboard_builder import KeyboardBuilder


class TestSRSServiceKeyboardInjection:
    """SRSService must accept and use a KeyboardBuilder, not import telegram_keyboards."""

    @pytest.fixture
    def mock_keyboard_builder(self):
        """A mock KeyboardBuilder that records calls."""
        builder = MagicMock(spec=KeyboardBuilder)
        builder.build_inline_keyboard.return_value = "FAKE_MARKUP"
        return builder

    @pytest.fixture
    def srs_service(self, mock_keyboard_builder):
        """SRSService created with an injected KeyboardBuilder."""
        with (
            patch("src.services.srs_service.get_due_cards"),
            patch("src.services.srs_service.update_card_rating"),
            patch("src.services.srs_service.send_morning_batch"),
            patch("src.services.srs_service.get_review_command_cards"),
            patch("src.services.srs_service.get_config"),
            patch("src.services.srs_service.set_config"),
            patch("src.services.srs_service.load_note_content"),
            patch("src.services.srs_service.get_backlinks"),
        ):
            from src.services.srs_service import SRSService

            return SRSService(keyboard_builder=mock_keyboard_builder)

    def test_constructor_accepts_keyboard_builder(self, mock_keyboard_builder):
        """SRSService.__init__ must accept a keyboard_builder parameter."""
        with (
            patch("src.services.srs_service.get_due_cards"),
            patch("src.services.srs_service.update_card_rating"),
            patch("src.services.srs_service.send_morning_batch"),
            patch("src.services.srs_service.get_review_command_cards"),
            patch("src.services.srs_service.get_config"),
            patch("src.services.srs_service.set_config"),
            patch("src.services.srs_service.load_note_content"),
            patch("src.services.srs_service.get_backlinks"),
        ):
            from src.services.srs_service import SRSService

            service = SRSService(keyboard_builder=mock_keyboard_builder)
            assert service.keyboard_builder is mock_keyboard_builder

    @pytest.mark.asyncio
    async def test_send_card_uses_injected_builder(
        self, srs_service, mock_keyboard_builder
    ):
        """send_card must call keyboard_builder.build_inline_keyboard."""
        update = MagicMock()
        update.effective_chat.id = 123
        context = MagicMock()
        context.bot.send_message = AsyncMock()

        card = {
            "card_id": 1,
            "note_path": "test.md",
            "message": "Test card",
        }

        await srs_service.send_card(update, context, card)

        mock_keyboard_builder.build_inline_keyboard.assert_called_once()
        context.bot.send_message.assert_called_once()
        call_kwargs = context.bot.send_message.call_args.kwargs
        assert call_kwargs["reply_markup"] == "FAKE_MARKUP"

    @pytest.mark.asyncio
    async def test_send_morning_batch_uses_injected_builder(
        self, srs_service, mock_keyboard_builder
    ):
        """send_morning_batch must use keyboard_builder."""
        context = MagicMock()
        context.bot.send_message = AsyncMock()

        with patch(
            "src.services.srs_service.send_morning_batch",
            return_value=[
                {"card_id": 1, "note_path": "a.md", "message": "Card 1"},
            ],
        ):
            await srs_service.send_morning_batch(chat_id=123, context=context)

        mock_keyboard_builder.build_inline_keyboard.assert_called_once()
