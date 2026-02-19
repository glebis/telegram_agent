"""UserRepository protocol — defines user lookup contract."""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class UserRepository(Protocol):
    """Repository interface for User entity access."""

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[object]:
        """Look up a user by their Telegram user ID.

        Args:
            telegram_user_id: The Telegram-assigned user ID.

        Returns:
            The User object, or None if not found.
        """
        ...

    async def get_by_id(self, user_id: int) -> Optional[object]:
        """Look up a user by internal database ID.

        Args:
            user_id: The internal (primary key) user ID.

        Returns:
            The User object, or None if not found.
        """
        ...
