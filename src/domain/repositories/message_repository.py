"""MessageRepository protocol — defines message persistence contract."""

from datetime import datetime
from typing import List, Protocol, runtime_checkable


@runtime_checkable
class MessageRepository(Protocol):
    """Repository interface for Message entity access and persistence."""

    async def add(self, message: object) -> object:
        """Persist a new message.

        Args:
            message: The Message object to persist.

        Returns:
            The persisted Message object (with ID populated).
        """
        ...

    async def get_latest_by_chat(self, chat_id: int, limit: int = 10) -> List[object]:
        """Get the most recent messages for a chat.

        Args:
            chat_id: The internal (primary key) chat ID.
            limit: Maximum number of messages to return.

        Returns:
            List of Message objects, newest first.
        """
        ...

    async def delete_older_than(self, chat_id: int, cutoff: datetime) -> int:
        """Delete messages older than a cutoff date for a given chat.

        Args:
            chat_id: The internal (primary key) chat ID.
            cutoff: Delete messages with created_at before this datetime.

        Returns:
            Number of messages deleted.
        """
        ...
