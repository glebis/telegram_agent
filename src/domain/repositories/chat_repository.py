"""ChatRepository protocol — defines chat lookup contract."""

from typing import List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ChatRepository(Protocol):
    """Repository interface for Chat entity access."""

    async def get_by_telegram_id(self, telegram_chat_id: int) -> Optional[object]:
        """Look up a chat by its Telegram chat ID.

        Args:
            telegram_chat_id: The Telegram-assigned chat ID.

        Returns:
            The Chat object, or None if not found.
        """
        ...

    async def get_by_user_id(self, user_id: int) -> List[object]:
        """Get all chats belonging to a user (by internal user ID).

        Args:
            user_id: The internal (primary key) user ID.

        Returns:
            List of Chat objects (may be empty).
        """
        ...
