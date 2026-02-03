"""Shared utilities for setup wizard steps."""

from typing import Tuple

import httpx


def validate_bot_token(token: str) -> Tuple[bool, str]:
    """Validate a Telegram bot token via getMe API call.

    Returns:
        Tuple of (is_valid, bot_username).
    """
    try:
        response = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return True, data["result"].get("username", "")
        return False, ""
    except Exception:
        return False, ""
