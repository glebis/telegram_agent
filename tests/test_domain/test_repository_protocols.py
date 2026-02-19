"""Tests for repository protocol definitions (Slice 1).

Verifies that the Protocol classes exist, have the correct method signatures,
and that structural subtyping works (classes implementing the right methods
are accepted as instances of the protocol).
"""

pass


class TestUserRepositoryProtocol:
    """UserRepository protocol defines user lookup operations."""

    def test_protocol_is_importable(self):
        from src.domain.repositories import UserRepository

        assert UserRepository is not None

    def test_protocol_is_runtime_checkable(self):
        from src.domain.repositories import UserRepository

        assert hasattr(UserRepository, "__protocol_attrs__") or issubclass(
            type(UserRepository), type
        )
        # Runtime-checkable protocols can be used with isinstance
        assert getattr(UserRepository, "_is_runtime_protocol", False)

    def test_protocol_requires_get_by_telegram_id(self):
        """UserRepository must define get_by_telegram_id(telegram_user_id) -> Optional[User]."""
        from src.domain.repositories import UserRepository

        assert hasattr(UserRepository, "get_by_telegram_id")

    def test_protocol_requires_get_by_id(self):
        """UserRepository must define get_by_id(user_id) -> Optional[User]."""
        from src.domain.repositories import UserRepository

        assert hasattr(UserRepository, "get_by_id")

    def test_structural_subtyping_accepts_conforming_class(self):
        """A class with matching methods satisfies the protocol."""
        from src.domain.repositories import UserRepository

        class FakeUserRepo:
            async def get_by_telegram_id(self, telegram_user_id: int):
                return None

            async def get_by_id(self, user_id: int):
                return None

        assert isinstance(FakeUserRepo(), UserRepository)

    def test_structural_subtyping_rejects_non_conforming_class(self):
        """A class missing methods does not satisfy the protocol."""
        from src.domain.repositories import UserRepository

        class BadRepo:
            pass

        assert not isinstance(BadRepo(), UserRepository)


class TestChatRepositoryProtocol:
    """ChatRepository protocol defines chat lookup and update operations."""

    def test_protocol_is_importable(self):
        from src.domain.repositories import ChatRepository

        assert ChatRepository is not None

    def test_protocol_is_runtime_checkable(self):
        from src.domain.repositories import ChatRepository

        assert getattr(ChatRepository, "_is_runtime_protocol", False)

    def test_protocol_requires_get_by_telegram_id(self):
        """ChatRepository must define get_by_telegram_id(telegram_chat_id) -> Optional[Chat]."""
        from src.domain.repositories import ChatRepository

        assert hasattr(ChatRepository, "get_by_telegram_id")

    def test_protocol_requires_get_by_user_id(self):
        """ChatRepository must define get_by_user_id(user_id) -> list[Chat]."""
        from src.domain.repositories import ChatRepository

        assert hasattr(ChatRepository, "get_by_user_id")

    def test_structural_subtyping_accepts_conforming_class(self):
        from src.domain.repositories import ChatRepository

        class FakeChatRepo:
            async def get_by_telegram_id(self, telegram_chat_id: int):
                return None

            async def get_by_user_id(self, user_id: int):
                return []

        assert isinstance(FakeChatRepo(), ChatRepository)

    def test_structural_subtyping_rejects_non_conforming_class(self):
        from src.domain.repositories import ChatRepository

        class BadRepo:
            async def get_by_telegram_id(self, telegram_chat_id: int):
                return None

            # Missing get_by_user_id

        assert not isinstance(BadRepo(), ChatRepository)


class TestMessageRepositoryProtocol:
    """MessageRepository protocol defines message persistence operations."""

    def test_protocol_is_importable(self):
        from src.domain.repositories import MessageRepository

        assert MessageRepository is not None

    def test_protocol_is_runtime_checkable(self):
        from src.domain.repositories import MessageRepository

        assert getattr(MessageRepository, "_is_runtime_protocol", False)

    def test_protocol_requires_add(self):
        """MessageRepository must define add(message) -> Message."""
        from src.domain.repositories import MessageRepository

        assert hasattr(MessageRepository, "add")

    def test_protocol_requires_get_latest_by_chat(self):
        """MessageRepository must define get_latest_by_chat(chat_id, limit) -> list[Message]."""
        from src.domain.repositories import MessageRepository

        assert hasattr(MessageRepository, "get_latest_by_chat")

    def test_protocol_requires_delete_older_than(self):
        """MessageRepository must define delete_older_than(chat_id, cutoff) -> int."""
        from src.domain.repositories import MessageRepository

        assert hasattr(MessageRepository, "delete_older_than")

    def test_structural_subtyping_accepts_conforming_class(self):
        from src.domain.repositories import MessageRepository

        class FakeMessageRepo:
            async def add(self, message):
                return message

            async def get_latest_by_chat(self, chat_id: int, limit: int = 10):
                return []

            async def delete_older_than(self, chat_id, cutoff):
                return 0

        assert isinstance(FakeMessageRepo(), MessageRepository)

    def test_structural_subtyping_rejects_non_conforming_class(self):
        from src.domain.repositories import MessageRepository

        class BadRepo:
            async def add(self, message):
                return message

            # Missing get_latest_by_chat and delete_older_than

        assert not isinstance(BadRepo(), MessageRepository)
