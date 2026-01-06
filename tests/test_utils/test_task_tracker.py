"""
Tests for the Task Tracker utility.

Tests cover:
- Task creation and tracking
- Task lifecycle (completion, cancellation, exceptions)
- Cancel all tasks functionality
- Wait for tasks functionality
- Clear all tasks functionality
- Edge cases and concurrent operations
"""

import asyncio
from unittest.mock import patch

import pytest

from src.utils import task_tracker
from src.utils.task_tracker import (
    cancel_all_tasks,
    clear_all_tasks,
    create_tracked_task,
    get_active_task_count,
    get_active_tasks,
    wait_for_tasks,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
async def clean_task_registry():
    """Clean up task registry before and after each test."""
    # Clear before test
    await clear_all_tasks()
    yield
    # Clear after test
    await clear_all_tasks()


# =============================================================================
# Helper Coroutines
# =============================================================================


async def quick_task():
    """A task that completes quickly."""
    await asyncio.sleep(0.01)
    return "done"


async def slow_task():
    """A task that takes a while."""
    await asyncio.sleep(1.0)
    return "done"


async def failing_task():
    """A task that raises an exception."""
    await asyncio.sleep(0.01)
    raise ValueError("Task failed!")


async def cancellable_task():
    """A task that can be cancelled."""
    try:
        await asyncio.sleep(10.0)
    except asyncio.CancelledError:
        raise


async def task_with_result(result):
    """A task that returns a specific result."""
    await asyncio.sleep(0.01)
    return result


# =============================================================================
# Create Tracked Task Tests
# =============================================================================


class TestCreateTrackedTask:
    """Tests for create_tracked_task function."""

    @pytest.mark.asyncio
    async def test_create_task_returns_task(self):
        """Test that create_tracked_task returns an asyncio Task."""
        task = create_tracked_task(quick_task())

        assert isinstance(task, asyncio.Task)
        await task

    @pytest.mark.asyncio
    async def test_create_task_with_name(self):
        """Test creating task with custom name."""
        task = create_tracked_task(quick_task(), name="my_custom_task")

        assert task.get_name() == "my_custom_task"
        await task

    @pytest.mark.asyncio
    async def test_create_task_without_name(self):
        """Test creating task without name uses default."""
        task = create_tracked_task(quick_task())

        # Should have some name (default naming)
        assert task.get_name() is not None
        await task

    @pytest.mark.asyncio
    async def test_task_added_to_registry(self):
        """Test that created task is added to active tasks."""
        initial_count = get_active_task_count()

        task = create_tracked_task(slow_task())

        assert get_active_task_count() == initial_count + 1
        assert task in get_active_tasks()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_task_executes_coroutine(self):
        """Test that the task actually executes the coroutine."""
        result_holder = []

        async def capturing_task():
            result_holder.append("executed")
            return "result"

        task = create_tracked_task(capturing_task())
        result = await task

        assert result_holder == ["executed"]
        assert result == "result"


# =============================================================================
# Task Lifecycle Tests
# =============================================================================


class TestTaskLifecycle:
    """Tests for task lifecycle management."""

    @pytest.mark.asyncio
    async def test_completed_task_removed_from_registry(self):
        """Test that completed task is removed from registry."""
        task = create_tracked_task(quick_task())

        assert task in get_active_tasks()

        await task

        # Give callback time to execute
        await asyncio.sleep(0.01)

        assert task not in get_active_tasks()

    @pytest.mark.asyncio
    async def test_cancelled_task_removed_from_registry(self):
        """Test that cancelled task is removed from registry."""
        task = create_tracked_task(slow_task())

        assert task in get_active_tasks()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Give callback time to execute
        await asyncio.sleep(0.01)

        assert task not in get_active_tasks()

    @pytest.mark.asyncio
    async def test_failed_task_removed_from_registry(self):
        """Test that failed task is removed from registry."""
        task = create_tracked_task(failing_task())

        assert task in get_active_tasks()

        try:
            await task
        except ValueError:
            pass

        # Give callback time to execute
        await asyncio.sleep(0.01)

        assert task not in get_active_tasks()

    @pytest.mark.asyncio
    async def test_multiple_tasks_tracked(self):
        """Test tracking multiple tasks simultaneously."""
        tasks = [
            create_tracked_task(quick_task(), name=f"task_{i}")
            for i in range(5)
        ]

        assert get_active_task_count() == 5

        await asyncio.gather(*tasks)

        # Give callbacks time to execute
        await asyncio.sleep(0.05)

        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_task_result_preserved(self):
        """Test that task result is preserved after completion."""
        task = create_tracked_task(task_with_result("my_result"))

        result = await task

        assert result == "my_result"

    @pytest.mark.asyncio
    async def test_task_exception_preserved(self):
        """Test that task exception is preserved and raised."""
        task = create_tracked_task(failing_task())

        with pytest.raises(ValueError, match="Task failed"):
            await task


# =============================================================================
# Get Active Tasks Tests
# =============================================================================


class TestGetActiveTasks:
    """Tests for get_active_tasks function."""

    @pytest.mark.asyncio
    async def test_get_active_tasks_empty(self):
        """Test getting active tasks when none exist."""
        tasks = get_active_tasks()

        assert isinstance(tasks, set)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_get_active_tasks_returns_copy(self):
        """Test that get_active_tasks returns a copy."""
        task = create_tracked_task(slow_task())

        tasks1 = get_active_tasks()
        tasks2 = get_active_tasks()

        # Should be different set objects
        assert tasks1 is not tasks2
        # But contain same tasks
        assert tasks1 == tasks2

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_get_active_tasks_content(self):
        """Test that get_active_tasks contains created tasks."""
        task1 = create_tracked_task(slow_task(), name="task1")
        task2 = create_tracked_task(slow_task(), name="task2")

        active = get_active_tasks()

        assert task1 in active
        assert task2 in active

        # Cleanup
        task1.cancel()
        task2.cancel()
        try:
            await asyncio.gather(task1, task2)
        except asyncio.CancelledError:
            pass


# =============================================================================
# Get Active Task Count Tests
# =============================================================================


class TestGetActiveTaskCount:
    """Tests for get_active_task_count function."""

    @pytest.mark.asyncio
    async def test_count_starts_at_zero(self):
        """Test that count starts at zero."""
        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_count_increases_on_create(self):
        """Test that count increases when tasks are created."""
        assert get_active_task_count() == 0

        task1 = create_tracked_task(slow_task())
        assert get_active_task_count() == 1

        task2 = create_tracked_task(slow_task())
        assert get_active_task_count() == 2

        # Cleanup
        task1.cancel()
        task2.cancel()
        try:
            await asyncio.gather(task1, task2)
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_count_decreases_on_completion(self):
        """Test that count decreases when tasks complete."""
        task = create_tracked_task(quick_task())
        assert get_active_task_count() == 1

        await task
        await asyncio.sleep(0.01)  # Let callback run

        assert get_active_task_count() == 0


# =============================================================================
# Cancel All Tasks Tests
# =============================================================================


class TestCancelAllTasks:
    """Tests for cancel_all_tasks function."""

    @pytest.mark.asyncio
    async def test_cancel_all_no_tasks(self):
        """Test cancel_all_tasks with no active tasks."""
        cancelled = await cancel_all_tasks()

        assert cancelled == 0

    @pytest.mark.asyncio
    async def test_cancel_all_single_task(self):
        """Test cancelling a single task."""
        task = create_tracked_task(slow_task())

        assert get_active_task_count() == 1

        cancelled = await cancel_all_tasks()

        assert cancelled == 1
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_cancel_all_multiple_tasks(self):
        """Test cancelling multiple tasks."""
        tasks = [
            create_tracked_task(slow_task(), name=f"task_{i}")
            for i in range(5)
        ]

        assert get_active_task_count() == 5

        cancelled = await cancel_all_tasks()

        assert cancelled == 5
        assert all(t.cancelled() for t in tasks)

    @pytest.mark.asyncio
    async def test_cancel_all_with_timeout(self):
        """Test cancel_all_tasks with custom timeout."""
        task = create_tracked_task(cancellable_task())

        cancelled = await cancel_all_tasks(timeout=0.5)

        assert cancelled == 1

    @pytest.mark.asyncio
    async def test_cancel_all_already_done_tasks(self):
        """Test cancel_all_tasks when some tasks already done."""
        # Create and complete a task
        done_task = create_tracked_task(quick_task())
        await done_task
        await asyncio.sleep(0.01)  # Let callback run

        # Create a slow task
        slow = create_tracked_task(slow_task())

        # Only the slow task should be in registry
        # (done_task was removed by callback)
        cancelled = await cancel_all_tasks()

        # Only the slow task should be counted
        assert cancelled == 1

    @pytest.mark.asyncio
    async def test_cancel_all_clears_registry(self):
        """Test that cancel_all_tasks clears the registry."""
        for i in range(3):
            create_tracked_task(slow_task(), name=f"task_{i}")

        assert get_active_task_count() == 3

        await cancel_all_tasks()

        # Registry should be cleared after cancellation
        await asyncio.sleep(0.1)  # Let callbacks run
        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_cancel_all_timeout_exceeded(self):
        """Test cancel_all_tasks when timeout is exceeded."""
        async def stubborn_task():
            """Task that ignores cancellation."""
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                # Ignore cancellation and keep running
                await asyncio.sleep(10.0)

        task = create_tracked_task(stubborn_task())

        # This should timeout since task ignores cancellation
        cancelled = await cancel_all_tasks(timeout=0.1)

        # Task was requested to cancel
        assert task.cancelled() or not task.done()


# =============================================================================
# Wait For Tasks Tests
# =============================================================================


class TestWaitForTasks:
    """Tests for wait_for_tasks function."""

    @pytest.mark.asyncio
    async def test_wait_no_tasks(self):
        """Test wait_for_tasks with no active tasks."""
        # Should return immediately without error
        await wait_for_tasks()

    @pytest.mark.asyncio
    async def test_wait_for_single_task(self):
        """Test waiting for a single task."""
        task = create_tracked_task(quick_task())

        await wait_for_tasks()

        assert task.done()

    @pytest.mark.asyncio
    async def test_wait_for_multiple_tasks(self):
        """Test waiting for multiple tasks."""
        tasks = [
            create_tracked_task(quick_task(), name=f"task_{i}")
            for i in range(5)
        ]

        await wait_for_tasks()

        assert all(t.done() for t in tasks)

    @pytest.mark.asyncio
    async def test_wait_with_timeout(self):
        """Test wait_for_tasks with timeout returns early."""
        start_time = asyncio.get_event_loop().time()

        task = create_tracked_task(slow_task())  # Takes 1 second

        # Should timeout since task takes 1 second but timeout is 0.05s
        await wait_for_tasks(timeout=0.05)

        elapsed = asyncio.get_event_loop().time() - start_time

        # Should have returned quickly (near timeout, not 1 second)
        assert elapsed < 0.5

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_wait_without_timeout(self):
        """Test wait_for_tasks without timeout waits indefinitely."""
        task = create_tracked_task(quick_task())

        # Should wait for task to complete
        await wait_for_tasks(timeout=None)

        assert task.done()

    @pytest.mark.asyncio
    async def test_wait_handles_failed_tasks(self):
        """Test wait_for_tasks handles failed tasks gracefully."""
        task = create_tracked_task(failing_task())

        # Should not raise, exceptions are gathered
        await wait_for_tasks()

        assert task.done()


# =============================================================================
# Clear All Tasks Tests
# =============================================================================


class TestClearAllTasks:
    """Tests for clear_all_tasks function."""

    @pytest.mark.asyncio
    async def test_clear_no_tasks(self):
        """Test clear_all_tasks with no active tasks."""
        await clear_all_tasks()

        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_clear_cancels_and_clears(self):
        """Test that clear cancels tasks and clears registry."""
        tasks = [
            create_tracked_task(slow_task(), name=f"task_{i}")
            for i in range(3)
        ]

        assert get_active_task_count() == 3

        await clear_all_tasks()

        assert get_active_task_count() == 0
        assert all(t.cancelled() or t.done() for t in tasks)

    @pytest.mark.asyncio
    async def test_clear_uses_short_timeout(self):
        """Test that clear_all_tasks uses a short timeout."""
        async def stubborn_task():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                await asyncio.sleep(10.0)

        task = create_tracked_task(stubborn_task())

        # Should complete quickly (1 second timeout in implementation)
        await asyncio.wait_for(clear_all_tasks(), timeout=2.0)


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_rapid_task_creation(self):
        """Test creating many tasks rapidly."""
        tasks = [
            create_tracked_task(quick_task(), name=f"rapid_{i}")
            for i in range(100)
        ]

        assert get_active_task_count() == 100

        await asyncio.gather(*tasks)
        await asyncio.sleep(0.1)

        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_nested_task_creation(self):
        """Test creating tasks from within tasks."""
        inner_completed = []

        async def outer_task():
            inner = create_tracked_task(quick_task(), name="inner")
            await inner
            inner_completed.append(True)
            return "outer_done"

        outer = create_tracked_task(outer_task(), name="outer")
        result = await outer

        assert result == "outer_done"
        assert inner_completed == [True]

    @pytest.mark.asyncio
    async def test_same_name_multiple_tasks(self):
        """Test creating multiple tasks with same name."""
        tasks = [
            create_tracked_task(quick_task(), name="same_name")
            for _ in range(3)
        ]

        assert get_active_task_count() == 3

        await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_task_that_creates_more_tasks(self):
        """Test a task that spawns more tasks."""
        spawned = []

        async def spawning_task():
            for i in range(3):
                t = create_tracked_task(quick_task(), name=f"spawned_{i}")
                spawned.append(t)
            return "spawned"

        main = create_tracked_task(spawning_task(), name="main")
        await main

        # Wait for spawned tasks
        await asyncio.gather(*spawned)
        await asyncio.sleep(0.05)

        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_immediate_cancellation(self):
        """Test cancelling task immediately after creation."""
        task = create_tracked_task(slow_task())
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        await asyncio.sleep(0.01)
        assert task not in get_active_tasks()

    @pytest.mark.asyncio
    async def test_exception_in_callback_doesnt_break_registry(self):
        """Test that registry remains consistent even with callback issues."""
        # Create and complete several tasks
        for i in range(5):
            task = create_tracked_task(quick_task(), name=f"task_{i}")
            await task

        await asyncio.sleep(0.05)

        # Registry should be clean
        assert get_active_task_count() == 0


# =============================================================================
# Logging Tests
# =============================================================================


class TestLogging:
    """Tests for logging behavior."""

    @pytest.mark.asyncio
    async def test_logs_task_creation(self):
        """Test that task creation is logged."""
        with patch.object(task_tracker.logger, 'debug') as mock_debug:
            task = create_tracked_task(quick_task(), name="logged_task")
            await task

            # Check that debug was called with task creation message
            calls = [str(c) for c in mock_debug.call_args_list]
            assert any("logged_task" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_logs_task_completion(self):
        """Test that task completion is logged."""
        with patch.object(task_tracker.logger, 'debug') as mock_debug:
            task = create_tracked_task(quick_task(), name="complete_task")
            await task
            await asyncio.sleep(0.01)

            calls = [str(c) for c in mock_debug.call_args_list]
            assert any("completed" in str(c).lower() for c in calls)

    @pytest.mark.asyncio
    async def test_logs_task_cancellation(self):
        """Test that task cancellation is logged."""
        with patch.object(task_tracker.logger, 'debug') as mock_debug:
            task = create_tracked_task(slow_task(), name="cancel_task")
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            await asyncio.sleep(0.01)
            calls = [str(c) for c in mock_debug.call_args_list]
            assert any("cancelled" in str(c).lower() for c in calls)

    @pytest.mark.asyncio
    async def test_logs_task_failure(self):
        """Test that task failure is logged."""
        with patch.object(task_tracker.logger, 'error') as mock_error:
            task = create_tracked_task(failing_task(), name="fail_task")

            try:
                await task
            except ValueError:
                pass

            await asyncio.sleep(0.01)
            mock_error.assert_called()


# =============================================================================
# Concurrent Operations Tests
# =============================================================================


class TestConcurrentOperations:
    """Tests for concurrent operations on the task registry."""

    @pytest.mark.asyncio
    async def test_concurrent_create_and_complete(self):
        """Test creating and completing tasks concurrently."""
        async def create_and_wait():
            task = create_tracked_task(quick_task())
            await task

        await asyncio.gather(*[create_and_wait() for _ in range(20)])

        await asyncio.sleep(0.1)
        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_concurrent_cancel_while_creating(self):
        """Test cancelling tasks while others are being created."""
        tasks = []

        for i in range(10):
            task = create_tracked_task(slow_task(), name=f"task_{i}")
            tasks.append(task)

        # Cancel half while creating more
        for i, task in enumerate(tasks):
            if i % 2 == 0:
                task.cancel()
            else:
                create_tracked_task(quick_task(), name=f"new_task_{i}")

        # Cleanup
        await cancel_all_tasks()

    @pytest.mark.asyncio
    async def test_get_tasks_during_modifications(self):
        """Test getting tasks while registry is being modified."""
        async def modifier():
            for i in range(10):
                task = create_tracked_task(quick_task())
                await task
                await asyncio.sleep(0.001)

        async def reader():
            for _ in range(20):
                get_active_tasks()
                get_active_task_count()
                await asyncio.sleep(0.001)

        await asyncio.gather(modifier(), reader())


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple operations."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete task lifecycle."""
        # Create tasks
        tasks = [
            create_tracked_task(quick_task(), name=f"lifecycle_{i}")
            for i in range(5)
        ]

        assert get_active_task_count() == 5

        # Wait for some to complete
        await asyncio.sleep(0.05)

        # Check they completed
        await asyncio.sleep(0.05)
        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_graceful_shutdown_simulation(self):
        """Test simulating a graceful shutdown scenario."""
        # Create various tasks
        quick_tasks = [
            create_tracked_task(quick_task(), name=f"quick_{i}")
            for i in range(3)
        ]
        slow_tasks = [
            create_tracked_task(slow_task(), name=f"slow_{i}")
            for i in range(2)
        ]

        # Wait briefly for quick tasks
        await asyncio.sleep(0.05)

        # Cancel remaining (slow tasks)
        cancelled = await cancel_all_tasks(timeout=0.5)

        # At least the slow tasks should be cancelled
        assert cancelled >= 2

        # Registry should be empty
        await asyncio.sleep(0.1)
        assert get_active_task_count() == 0

    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test that system recovers after task errors."""
        # Create a failing task
        failing = create_tracked_task(failing_task(), name="failing")

        try:
            await failing
        except ValueError:
            pass

        await asyncio.sleep(0.01)

        # Create more tasks - should work fine
        new_task = create_tracked_task(quick_task(), name="new_after_fail")
        result = await new_task

        assert result == "done"
