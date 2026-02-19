"""Tests for TodoService - subprocess wrapper for task_manager.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.services.todo_service import TodoService, get_todo_service


@pytest.fixture
def todo_service():
    """Create TodoService instance."""
    return TodoService()


@pytest.fixture
def mock_subprocess():
    """Mock asyncio.create_subprocess_exec."""
    with patch("asyncio.create_subprocess_exec") as mock:
        yield mock


class TestTodoServiceListTasks:
    """Test TodoService.list_tasks()."""

    @pytest.mark.asyncio
    async def test_list_tasks_all(self, todo_service, mock_subprocess):
        """Test listing all tasks."""
        # Arrange
        tasks_json = json.dumps(
            [
                {
                    "id": "2026-02-12-buy-milk",
                    "title": "Buy milk",
                    "status": "inbox",
                    "priority": "medium",
                    "created": "2026-02-12T10:30:00",
                },
                {
                    "id": "2026-02-11-review-pr",
                    "title": "Review PR #123",
                    "status": "active",
                    "priority": "high",
                    "created": "2026-02-11T09:00:00",
                    "tags": ["code", "review"],
                },
            ]
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (tasks_json.encode(), b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        # Act
        result = await todo_service.list_tasks()

        # Assert
        assert len(result) == 2
        assert result[0]["id"] == "2026-02-12-buy-milk"
        assert result[1]["id"] == "2026-02-11-review-pr"
        assert result[1]["tags"] == ["code", "review"]

        # Verify subprocess called correctly
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0]
        assert call_args[0] == "/opt/homebrew/bin/python3.11"
        assert "task_manager.py" in call_args[1]
        assert "list" in call_args
        assert "--format" in call_args
        assert "json" in call_args

    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, todo_service, mock_subprocess):
        """Test listing tasks filtered by status."""
        # Arrange
        tasks_json = json.dumps(
            [{"id": "task-1", "title": "Task 1", "status": "active"}]
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (tasks_json.encode(), b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        # Act
        result = await todo_service.list_tasks(status="active")

        # Assert
        assert len(result) == 1

        # Verify status filter passed to subprocess
        call_args = mock_subprocess.call_args[0]
        assert "--status" in call_args
        assert "active" in call_args

    @pytest.mark.asyncio
    async def test_list_tasks_by_tags(self, todo_service, mock_subprocess):
        """Test listing tasks filtered by tags."""
        # Arrange
        tasks_json = json.dumps(
            [{"id": "task-1", "title": "Task 1", "tags": ["work", "urgent"]}]
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (tasks_json.encode(), b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        # Act
        result = await todo_service.list_tasks(tags=["work", "urgent"])

        # Assert
        assert len(result) == 1

        # Verify tags passed to subprocess
        call_args = mock_subprocess.call_args[0]
        assert "--tags" in call_args
        work_idx = call_args.index("work")
        urgent_idx = call_args.index("urgent")
        assert work_idx > 0
        assert urgent_idx > work_idx

    @pytest.mark.asyncio
    async def test_list_tasks_subprocess_error(self, todo_service, mock_subprocess):
        """Test handling subprocess error."""
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"Task manager error")
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        # Act & Assert
        with pytest.raises(RuntimeError, match="task_manager.py failed"):
            await todo_service.list_tasks()

    @pytest.mark.asyncio
    async def test_list_tasks_invalid_json(self, todo_service, mock_subprocess):
        """Test handling invalid JSON response."""
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"invalid json{", b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            await todo_service.list_tasks()


class TestTodoServiceCreateTask:
    """Test TodoService.create_task()."""

    @pytest.mark.asyncio
    async def test_create_task_minimal(self, todo_service, mock_subprocess):
        """Test creating task with minimal args."""
        # Arrange
        output = (
            "Created: /Users/server/Research/vault/Tasks/inbox/2026-02-12-buy-milk.md"
        )
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (output.encode(), b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        # Act
        result = await todo_service.create_task(title="Buy milk")

        # Assert
        assert "2026-02-12-buy-milk.md" in result

        # Verify subprocess called correctly
        call_args = mock_subprocess.call_args[0]
        assert "create" in call_args
        assert "--title" in call_args
        assert "Buy milk" in call_args
        assert "--source" in call_args
        assert "telegram" in call_args
        assert "--priority" in call_args
        assert "medium" in call_args

    @pytest.mark.asyncio
    async def test_create_task_with_all_fields(self, todo_service, mock_subprocess):
        """Test creating task with all fields."""
        # Arrange
        output = "Created: /Users/server/Research/vault/Tasks/inbox/task.md"
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (output.encode(), b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        # Act
        result = await todo_service.create_task(
            title="Review PR",
            context="Review security fixes in PR #123",
            due="2026-02-15",
            tags=["code", "review"],
            priority="high",
            source="voice",
        )

        # Assert
        assert "task.md" in result

        # Verify all fields passed to subprocess
        call_args = mock_subprocess.call_args[0]
        assert "--title" in call_args
        assert "Review PR" in call_args
        assert "--context" in call_args
        assert "Review security fixes in PR #123" in call_args
        assert "--due" in call_args
        assert "2026-02-15" in call_args
        assert "--tags" in call_args
        assert "code" in call_args
        assert "review" in call_args
        assert "--priority" in call_args
        assert "high" in call_args
        assert "--source" in call_args
        assert "voice" in call_args

    @pytest.mark.asyncio
    async def test_create_task_subprocess_error(self, todo_service, mock_subprocess):
        """Test handling subprocess error."""
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"Failed to create task")
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        # Act & Assert
        with pytest.raises(RuntimeError, match="task_manager.py failed"):
            await todo_service.create_task(title="Test")


class TestTodoServiceCompleteTask:
    """Test TodoService.complete_task()."""

    @pytest.mark.asyncio
    async def test_complete_task_success(self, todo_service, mock_subprocess):
        """Test completing task successfully."""
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 0
        mock_subprocess.return_value = mock_proc

        # Act
        result = await todo_service.complete_task("2026-02-12-buy-milk")

        # Assert
        assert result is True

        # Verify subprocess called correctly
        call_args = mock_subprocess.call_args[0]
        assert "complete" in call_args
        assert "2026-02-12-buy-milk" in call_args

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self, todo_service, mock_subprocess):
        """Test completing non-existent task."""
        # Arrange
        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 1
        mock_subprocess.return_value = mock_proc

        # Act
        result = await todo_service.complete_task("nonexistent-task")

        # Assert
        assert result is False


class TestTodoServiceSingleton:
    """Test singleton pattern for TodoService."""

    def test_get_todo_service_returns_same_instance(self):
        """Test that get_todo_service() returns singleton."""
        service1 = get_todo_service()
        service2 = get_todo_service()

        assert service1 is service2

    def test_get_todo_service_returns_todo_service_instance(self):
        """Test that get_todo_service() returns TodoService."""
        service = get_todo_service()

        assert isinstance(service, TodoService)
