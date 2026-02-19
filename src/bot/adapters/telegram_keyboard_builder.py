"""TelegramKeyboardBuilder -- implements KeyboardBuilder port for Telegram."""

from typing import Dict, List

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.domain.ports.keyboard_builder import KeyboardBuilder


class TelegramKeyboardBuilder(KeyboardBuilder):
    """Builds Telegram-specific keyboard markup from plain data dicts."""

    def build_inline_keyboard(
        self, rows: List[List[Dict[str, str]]]
    ) -> InlineKeyboardMarkup:
        """Build an inline keyboard from rows of {text, callback_data} dicts."""
        tg_rows = [
            [
                InlineKeyboardButton(
                    text=btn["text"], callback_data=btn["callback_data"]
                )
                for btn in row
            ]
            for row in rows
        ]
        return InlineKeyboardMarkup(tg_rows)

    def build_reply_keyboard(
        self,
        rows: List[List[str]],
        resize_keyboard: bool = True,
        one_time_keyboard: bool = False,
    ) -> ReplyKeyboardMarkup:
        """Build a reply keyboard from rows of button-text strings."""
        tg_rows = [[KeyboardButton(text=text) for text in row] for row in rows]
        return ReplyKeyboardMarkup(
            tg_rows,
            resize_keyboard=resize_keyboard,
            one_time_keyboard=one_time_keyboard,
        )
