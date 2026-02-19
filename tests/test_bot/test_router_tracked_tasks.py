"""
Tests that router.py uses create_tracked_task() instead of raw asyncio.create_task().

Issue #211: Replace raw asyncio.create_task() with create_tracked_task() in router.
"""

import ast
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROUTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "bot"
    / "processors"
    / "router.py"
)


class TestNoRawCreateTask:
    """Ensure router.py never calls asyncio.create_task() directly."""

    def test_no_asyncio_create_task_calls(self):
        """router.py must not contain any asyncio.create_task() calls."""
        source = ROUTER_PATH.read_text()
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            # Match asyncio.create_task(...)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "asyncio"
                and node.func.attr == "create_task"
            ):
                violations.append(node.lineno)

        assert violations == [], (
            f"Found asyncio.create_task() at line(s) {violations}. "
            f"Use create_tracked_task() from src/utils/task_tracker instead."
        )


class TestTodoReplyTrackedTasks:
    """Verify that todo-reply fire-and-forget paths use create_tracked_task."""

    @pytest.fixture
    def combined_msg(self):
        """Minimal CombinedMessage-like mock for todo reply routing."""
        msg = MagicMock()
        msg.chat_id = 123
        msg.user_id = 456
        msg.combined_text = "1"
        msg.messages = []
        msg.images = []
        msg.voices = []
        msg.videos = []
        msg.polls = []
        msg.contacts = []
        msg.overflow_count = 0
        msg.reply_to_message_id = 999
        msg.reply_to_message_text = None
        msg.reply_to_message_from_bot = False
        msg.reply_to_message_type = None
        msg.reply_to_message_date = None
        msg.has_command = MagicMock(return_value=False)
        msg.has_images = MagicMock(return_value=False)
        msg.has_voice = MagicMock(return_value=False)
        msg.has_videos = MagicMock(return_value=False)
        msg.has_polls = MagicMock(return_value=False)
        msg.has_documents = MagicMock(return_value=False)
        msg.primary_message = MagicMock()
        msg.primary_message.message_id = 1000
        msg.primary_context = MagicMock()
        msg.primary_context.bot = MagicMock()
        msg.primary_context.bot.send_message = AsyncMock()
        return msg

    @pytest.fixture
    def todo_reply_context(self):
        """ReplyContext for a TODO_LIST message type."""
        from src.services.reply_context import MessageType, ReplyContext

        return ReplyContext(
            message_id=999,
            chat_id=123,
            user_id=456,
            message_type=MessageType.TODO_LIST,
            original_text="1. Task A\n2. Task B",
            metadata={"task_ids": ["abc123", "def456"]},
        )

    @pytest.mark.asyncio
    async def test_todo_reply_uses_tracked_task(
        self, combined_msg, todo_reply_context
    ):
        """When handling a todo numeric reply, create_tracked_task is used."""
        from src.bot.processors.router import CombinedMessageProcessor

        processor = CombinedMessageProcessor()

        with (
            patch.object(
                processor.reply_service,
                "get_context",
                return_value=todo_reply_context,
            ),
            patch(
                "src.bot.processors.router.create_tracked_task"
            ) as mock_tracked,
            patch(
                "src.bot.processors.router.get_config_value", return_value=False
            ),
            patch(
                "src.services.collect_service.get_collect_service"
            ) as mock_collect,
            patch(
                "src.bot.handlers._claude_mode_cache", {123: False}
            ),
        ):
            mock_collect_svc = MagicMock()
            mock_collect_svc.is_collecting = AsyncMock(return_value=False)
            mock_collect.return_value = mock_collect_svc

            await processor.process(combined_msg)

            mock_tracked.assert_called_once()
            call_kwargs = mock_tracked.call_args
            assert "todo_reply" in call_kwargs.kwargs.get("name", ""), (
                "Task name should contain 'todo_reply'"
            )

    @pytest.mark.asyncio
    async def test_todo_invalid_number_uses_tracked_task(
        self, combined_msg, todo_reply_context
    ):
        """When todo reply has invalid number, error send uses tracked task."""
        combined_msg.combined_text = "99"  # Out of range

        from src.bot.processors.router import CombinedMessageProcessor

        processor = CombinedMessageProcessor()

        with (
            patch.object(
                processor.reply_service,
                "get_context",
                return_value=todo_reply_context,
            ),
            patch(
                "src.bot.processors.router.create_tracked_task"
            ) as mock_tracked,
            patch(
                "src.bot.processors.router.get_config_value", return_value=False
            ),
            patch(
                "src.services.collect_service.get_collect_service"
            ) as mock_collect,
            patch(
                "src.bot.handlers._claude_mode_cache", {123: False}
            ),
        ):
            mock_collect_svc = MagicMock()
            mock_collect_svc.is_collecting = AsyncMock(return_value=False)
            mock_collect.return_value = mock_collect_svc

            await processor.process(combined_msg)

            mock_tracked.assert_called_once()
            call_kwargs = mock_tracked.call_args
            assert "todo_reply_error" in call_kwargs.kwargs.get("name", ""), (
                "Task name should contain 'todo_reply_error'"
            )


class TestSessionLookupTrackedTask:
    """Verify that the session lookup task uses create_tracked_task."""

    def test_no_raw_create_task_in_session_lookup_block(self):
        """The asyncio.wait() block for session lookup must not use raw create_task."""
        source = ROUTER_PATH.read_text()
        # This is covered by test_no_asyncio_create_task_calls above,
        # but this test focuses specifically on the lookup pattern.
        assert "asyncio.create_task(lookup_session())" not in source, (
            "Session lookup should use create_tracked_task, not asyncio.create_task"
        )
