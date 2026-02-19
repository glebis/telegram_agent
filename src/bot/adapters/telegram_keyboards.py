"""Telegram keyboard adapters.

Converts plain keyboard data dicts returned by KeyboardService into
Telegram-specific markup objects.
"""

from typing import Any, Dict, List, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def reply_keyboard_from_data(data: Optional[Dict]) -> Optional[ReplyKeyboardMarkup]:
    """Convert a keyboard data dict to ReplyKeyboardMarkup.

    Args:
        data: Dict with 'keyboard' (List[List[str]]),
              'resize_keyboard', 'one_time_keyboard'. Or None.

    Returns:
        ReplyKeyboardMarkup or None.
    """
    if data is None:
        return None

    rows: List[List[str]] = data.get("keyboard", [])
    tg_rows = [[KeyboardButton(text=text) for text in row] for row in rows]

    return ReplyKeyboardMarkup(
        tg_rows,
        resize_keyboard=data.get("resize_keyboard", True),
        one_time_keyboard=data.get("one_time_keyboard", False),
    )


def inline_keyboard_from_rows(
    rows: List[List[Dict[str, str]]],
) -> InlineKeyboardMarkup:
    """Convert rows of {text, callback_data} dicts to InlineKeyboardMarkup.

    Args:
        rows: List of rows, each row a list of dicts with
              'text' and 'callback_data' keys.

    Returns:
        InlineKeyboardMarkup.
    """
    tg_rows = [
        [
            InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
            for btn in row
        ]
        for row in rows
    ]
    return InlineKeyboardMarkup(tg_rows)
