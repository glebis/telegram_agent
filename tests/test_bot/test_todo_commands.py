"""Tests for todo command handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, InlineKeyboardMarkup, Message, Update, User
from telegram.ext import ContextTypes

from src.bot.handlers.todo_commands import (
    CB_TODO_DETAILS,
    CB_TODO_DONE,
    CB_TODO_LIST,
    CB_TODO_STATUS,
    handle_todo_callback,
    todo_command,
)


@pytest.fixture
def mock_update():
    """Create mock Update object."""
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = 12345
    return update


@pytest.fixture
def mock_context():
    """Create mock Context object."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []
    return context


@pytest.fixture
def mock_todo_service():
    """Mock TodoService."""
    with patch("src.bot.handlers.todo_commands.get_todo_service") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


class TestTodoCommandDispatcher:
    """Test /todo command dispatcher."""

    @pytest.mark.asyncio
    async def test_todo_no_args_lists_active(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo with no args lists active todos."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task-1",
                    "title": "Buy milk",
                    "status": "inbox",
                    "priority": "medium",
                }
            ]
        )

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "📋" in call_args[0][0]  # Has header emoji
        assert "Buy milk" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_todo_add_creates_task(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo add creates new task."""
        # Arrange
        mock_context.args = ["add", "Buy", "milk"]
        mock_todo_service.create_task = AsyncMock(return_value="/path/to/task.md")

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_todo_service.create_task.assert_called_once_with(
            title="Buy milk", source="telegram"
        )
        mock_update.message.reply_text.assert_called_once()
        assert "✅" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_todo_done_completes_task(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo done marks task complete."""
        # Arrange
        mock_context.args = ["done", "task-1"]
        mock_todo_service.complete_task = AsyncMock(return_value=True)

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_todo_service.complete_task.assert_called_once_with("task-1")
        mock_update.message.reply_text.assert_called_once()
        assert "✅" in mock_update.message.reply_text.call_args[0][0]
        assert "task-1" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_todo_list_filters_by_status(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo list [status] filters."""
        # Arrange
        mock_context.args = ["list", "completed"]
        mock_todo_service.list_tasks = AsyncMock(return_value=[])

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_todo_service.list_tasks.assert_called_once()
        call_kwargs = mock_todo_service.list_tasks.call_args[1]
        assert call_kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_todo_show_displays_details(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo show displays task details."""
        # Arrange
        mock_context.args = ["show", "task-1"]
        mock_todo_service.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task-1",
                    "title": "Buy milk",
                    "status": "inbox",
                    "priority": "high",
                    "due": "2026-02-15",
                    "tags": ["shopping"],
                    "context": "Get organic milk from store",
                }
            ]
        )

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Buy milk" in call_text
        assert "high" in call_text
        assert "2026-02-15" in call_text
        assert "shopping" in call_text

    @pytest.mark.asyncio
    async def test_todo_invalid_command_shows_usage(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test invalid command shows usage."""
        # Arrange
        mock_context.args = ["invalid"]

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Usage:" in call_text


class TestTodoListDisplay:
    """Test task list display formatting."""

    @pytest.mark.asyncio
    async def test_list_empty_todos(self, mock_update, mock_context, mock_todo_service):
        """Test listing when no todos exist."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(return_value=[])

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        assert "No" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_with_inline_keyboards(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test list includes inline keyboards."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task-1",
                    "title": "Buy milk",
                    "status": "inbox",
                    "priority": "medium",
                }
            ]
        )

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        call_kwargs = mock_update.message.reply_text.call_args[1]
        assert "reply_markup" in call_kwargs
        assert isinstance(call_kwargs["reply_markup"], InlineKeyboardMarkup)

    @pytest.mark.asyncio
    async def test_list_includes_status_emojis(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test list includes status emojis."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task-1",
                    "title": "Inbox task",
                    "status": "inbox",
                    "priority": "medium",
                },
                {
                    "id": "task-2",
                    "title": "Active task",
                    "status": "active",
                    "priority": "high",
                },
            ]
        )

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "📥" in call_text  # Inbox emoji
        assert "🔄" in call_text  # Active emoji

    @pytest.mark.asyncio
    async def test_list_shows_due_dates(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test list shows due dates when present."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task-1",
                    "title": "Task with due",
                    "status": "inbox",
                    "due": "2026-02-15",
                }
            ]
        )

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "📅" in call_text
        assert "2026-02-15" in call_text

    @pytest.mark.asyncio
    async def test_list_shows_tags(self, mock_update, mock_context, mock_todo_service):
        """Test list shows tags when present."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task-1",
                    "title": "Tagged task",
                    "status": "inbox",
                    "tags": ["work", "urgent"],
                }
            ]
        )

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "🏷" in call_text
        assert "work" in call_text
        assert "urgent" in call_text

    @pytest.mark.asyncio
    async def test_list_limits_to_10_tasks(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test list limits display to 10 tasks."""
        # Arrange
        tasks = [
            {"id": f"task-{i}", "title": f"Task {i}", "status": "inbox"}
            for i in range(15)
        ]
        mock_todo_service.list_tasks = AsyncMock(return_value=tasks)

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        call_text = mock_update.message.reply_text.call_args[0][0]
        # Count task IDs in output
        task_count = sum(1 for i in range(15) if f"task-{i}" in call_text)
        assert task_count <= 10


class TestTodoCallbackHandlers:
    """Test callback query handlers."""

    @pytest.fixture
    def mock_callback_update(self):
        """Create mock Update with callback query."""
        update = MagicMock(spec=Update)
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.answer = AsyncMock()
        update.callback_query.message = MagicMock(spec=Message)
        update.callback_query.message.edit_text = AsyncMock()
        update.callback_query.message.reply_text = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_callback_done_completes_task(
        self, mock_callback_update, mock_context, mock_todo_service
    ):
        """Test done callback completes task."""
        # Arrange
        mock_todo_service.complete_task = AsyncMock(return_value=True)
        callback_data = f"{CB_TODO_DONE}:task-1"

        # Act
        await handle_todo_callback(mock_callback_update, mock_context, callback_data)

        # Assert
        mock_todo_service.complete_task.assert_called_once_with("task-1")
        mock_callback_update.callback_query.answer.assert_called_once()
        mock_callback_update.callback_query.message.edit_text.assert_called_once()
        call_text = mock_callback_update.callback_query.message.edit_text.call_args[0][
            0
        ]
        assert "✅" in call_text
        assert "task-1" in call_text

    @pytest.mark.asyncio
    async def test_callback_done_handles_failure(
        self, mock_callback_update, mock_context, mock_todo_service
    ):
        """Test done callback handles failure."""
        # Arrange
        mock_todo_service.complete_task = AsyncMock(return_value=False)
        callback_data = f"{CB_TODO_DONE}:task-1"

        # Act
        await handle_todo_callback(mock_callback_update, mock_context, callback_data)

        # Assert
        mock_callback_update.callback_query.message.reply_text.assert_called_once()
        call_text = mock_callback_update.callback_query.message.reply_text.call_args[0][
            0
        ]
        assert "❌" in call_text

    @pytest.mark.asyncio
    async def test_callback_status_filter(
        self, mock_callback_update, mock_context, mock_todo_service
    ):
        """Test status filter callback."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(return_value=[])
        callback_data = f"{CB_TODO_STATUS}:completed"

        # Act
        await handle_todo_callback(mock_callback_update, mock_context, callback_data)

        # Assert
        mock_todo_service.list_tasks.assert_called_once()
        call_kwargs = mock_todo_service.list_tasks.call_args[1]
        assert call_kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_callback_details_shows_task(
        self, mock_callback_update, mock_context, mock_todo_service
    ):
        """Test details callback shows task."""
        # Arrange
        mock_todo_service.list_tasks = AsyncMock(
            return_value=[
                {
                    "id": "task-1",
                    "title": "Buy milk",
                    "status": "inbox",
                    "priority": "medium",
                }
            ]
        )
        callback_data = f"{CB_TODO_DETAILS}:task-1"

        # Act
        await handle_todo_callback(mock_callback_update, mock_context, callback_data)

        # Assert
        mock_callback_update.callback_query.message.reply_text.assert_called_once()
        call_text = mock_callback_update.callback_query.message.reply_text.call_args[0][
            0
        ]
        assert "Buy milk" in call_text


class TestTodoCommandEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_add_without_text_shows_usage(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo add without text shows usage."""
        # Arrange
        mock_context.args = ["add"]

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "❌" in call_text
        assert "Usage:" in call_text

    @pytest.mark.asyncio
    async def test_done_without_id_shows_usage(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo done without ID shows usage."""
        # Arrange
        mock_context.args = ["done"]

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "❌" in call_text
        assert "Usage:" in call_text

    @pytest.mark.asyncio
    async def test_show_without_id_shows_usage(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo show without ID shows usage."""
        # Arrange
        mock_context.args = ["show"]

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "❌" in call_text
        assert "Usage:" in call_text

    @pytest.mark.asyncio
    async def test_show_nonexistent_task(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo show with nonexistent task."""
        # Arrange
        mock_context.args = ["show", "nonexistent"]
        mock_todo_service.list_tasks = AsyncMock(return_value=[])

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "❌" in call_text
        assert "not found" in call_text

    @pytest.mark.asyncio
    async def test_done_nonexistent_task(
        self, mock_update, mock_context, mock_todo_service
    ):
        """Test /todo done with nonexistent task."""
        # Arrange
        mock_context.args = ["done", "nonexistent"]
        mock_todo_service.complete_task = AsyncMock(return_value=False)

        # Act
        await todo_command(mock_update, mock_context)

        # Assert
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "❌" in call_text
        assert "not found" in call_text
