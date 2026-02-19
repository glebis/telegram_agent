"""Telegram PollSender adapter.

Wraps telegram.Bot to implement the PollSender protocol.
"""

from typing import Any, Dict, List

from telegram import Bot


class TelegramPollSender:
    """Adapter: telegram.Bot -> PollSender protocol."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_poll(
        self,
        chat_id: int,
        question: str,
        options: List[str],
        is_anonymous: bool = False,
        allows_multiple_answers: bool = False,
    ) -> Dict[str, Any]:
        """Send a poll via Telegram Bot API and return result metadata."""
        poll_message = await self._bot.send_poll(
            chat_id=chat_id,
            question=question,
            options=options,
            is_anonymous=is_anonymous,
            allows_multiple_answers=allows_multiple_answers,
        )
        return {
            "poll_id": poll_message.poll.id,
            "message_id": poll_message.message_id,
        }
