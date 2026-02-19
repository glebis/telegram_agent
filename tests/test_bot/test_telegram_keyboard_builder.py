"""Tests for TelegramKeyboardBuilder adapter implementing KeyboardBuilder port."""

from src.domain.ports.keyboard_builder import KeyboardBuilder


class TestTelegramKeyboardBuilder:
    """TelegramKeyboardBuilder must implement the KeyboardBuilder protocol."""

    def test_implements_keyboard_builder_protocol(self):
        """TelegramKeyboardBuilder is a KeyboardBuilder."""
        from src.bot.adapters.telegram_keyboard_builder import (
            TelegramKeyboardBuilder,
        )

        builder = TelegramKeyboardBuilder()
        assert isinstance(builder, KeyboardBuilder)

    def test_build_inline_keyboard_returns_inline_keyboard_markup(self):
        """build_inline_keyboard returns an InlineKeyboardMarkup."""
        from telegram import InlineKeyboardMarkup

        from src.bot.adapters.telegram_keyboard_builder import (
            TelegramKeyboardBuilder,
        )

        builder = TelegramKeyboardBuilder()
        rows = [[{"text": "OK", "callback_data": "ok"}]]
        result = builder.build_inline_keyboard(rows)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_build_inline_keyboard_preserves_button_data(self):
        """Buttons preserve text and callback_data."""
        from src.bot.adapters.telegram_keyboard_builder import (
            TelegramKeyboardBuilder,
        )

        builder = TelegramKeyboardBuilder()
        rows = [
            [
                {"text": "Yes", "callback_data": "yes"},
                {"text": "No", "callback_data": "no"},
            ],
            [{"text": "Maybe", "callback_data": "maybe"}],
        ]
        result = builder.build_inline_keyboard(rows)
        assert result.inline_keyboard[0][0].text == "Yes"
        assert result.inline_keyboard[0][0].callback_data == "yes"
        assert result.inline_keyboard[0][1].text == "No"
        assert result.inline_keyboard[1][0].text == "Maybe"

    def test_build_reply_keyboard_returns_reply_keyboard_markup(self):
        """build_reply_keyboard returns a ReplyKeyboardMarkup."""
        from telegram import ReplyKeyboardMarkup

        from src.bot.adapters.telegram_keyboard_builder import (
            TelegramKeyboardBuilder,
        )

        builder = TelegramKeyboardBuilder()
        rows = [["Option A", "Option B"]]
        result = builder.build_reply_keyboard(rows)
        assert isinstance(result, ReplyKeyboardMarkup)
