"""Tests for Telegram adapter implementations."""

from typing import Any, Dict, List

from src.bot.adapters.telegram_keyboards import (
    inline_keyboard_from_rows,
    reply_keyboard_from_data,
)
from src.domain.ports.poll_sender import PollSender


def test_reply_keyboard_from_data_none():
    """Passing None returns None."""
    assert reply_keyboard_from_data(None) is None


def test_reply_keyboard_from_data_basic():
    """Converts a dict to ReplyKeyboardMarkup."""
    data = {
        "keyboard": [["A", "B"], ["C"]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    markup = reply_keyboard_from_data(data)
    assert markup is not None
    assert markup.resize_keyboard is True
    assert markup.one_time_keyboard is False
    assert len(markup.keyboard) == 2
    assert markup.keyboard[0][0].text == "A"
    assert markup.keyboard[0][1].text == "B"
    assert markup.keyboard[1][0].text == "C"


def test_inline_keyboard_from_rows():
    """Converts rows of dicts to InlineKeyboardMarkup."""
    rows = [
        [
            {"text": "OK", "callback_data": "ok_1"},
            {"text": "Cancel", "callback_data": "cancel_1"},
        ]
    ]
    markup = inline_keyboard_from_rows(rows)
    assert len(markup.inline_keyboard) == 1
    assert markup.inline_keyboard[0][0].text == "OK"
    assert markup.inline_keyboard[0][0].callback_data == "ok_1"
    assert markup.inline_keyboard[0][1].text == "Cancel"


def test_telegram_poll_sender_is_poll_sender():
    """TelegramPollSender satisfies the PollSender protocol."""
    from src.bot.adapters.telegram_poll_sender import TelegramPollSender

    assert issubclass(TelegramPollSender, PollSender) or isinstance(
        TelegramPollSender.__new__(TelegramPollSender), PollSender
    )


def test_telegram_poll_sender_structural():
    """TelegramPollSender has the send_poll method matching the protocol."""
    from src.bot.adapters.telegram_poll_sender import TelegramPollSender

    # Verify it's recognized as implementing the protocol
    # (needs a bot arg, so we use a fake)
    class FakeBot:
        pass

    sender = TelegramPollSender(FakeBot())
    assert isinstance(sender, PollSender)
