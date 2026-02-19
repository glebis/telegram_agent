"""PollSender port -- abstracts sending polls to a chat."""

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class PollSender(Protocol):
    """Sends a poll to a chat and returns result metadata."""

    async def send_poll(
        self,
        chat_id: int,
        question: str,
        options: List[str],
        is_anonymous: bool = False,
        allows_multiple_answers: bool = False,
    ) -> Dict[str, Any]:
        """Send a poll; return dict with at least 'poll_id' and 'message_id'."""
        ...
