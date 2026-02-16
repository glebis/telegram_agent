"""
Task Tracker for Graceful Shutdown

Tracks all background asyncio tasks to ensure proper cleanup on shutdown.
"""

import asyncio
import logging
from typing import Coroutine, Optional, Set

logger = logging.getLogger(__name__)

# Registry of active tasks
_active_tasks: Set[asyncio.Task] = set()

# Lock for thread-safe operations
_lock = asyncio.Lock()


def create_tracked_task(
    coro: Coroutine,
    name: Optional[str] = None,
) -> asyncio.Task:
    """
    Create an asyncio task and track it for graceful shutdown.

    Args:
        coro: The coroutine to run as a task
        name: Optional name for the task (for debugging)

    Returns:
        The created task
    """
    task = asyncio.create_task(coro, name=name)

    # Add to registry
    _active_tasks.add(task)

    # Remove from registry when done
    def _on_done(t: asyncio.Task) -> None:
        _active_tasks.discard(t)
        task_name = t.get_name()
        if t.cancelled():
            logger.info(f"⏸️ Task cancelled: {task_name}")
        elif t.exception():
            exc = t.exception()
            assert exc is not None  # guarded by elif above
            logger.error(
                f"❌ Task failed: {task_name}",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        else:
            logger.debug(f"✅ Task completed: {task_name}")

    task.add_done_callback(_on_done)

    logger.debug(f"Created tracked task: {task.get_name()}")
    return task


def get_active_tasks() -> Set[asyncio.Task]:
    """Get the set of currently active tracked tasks."""
    return _active_tasks.copy()


def get_active_task_count() -> int:
    """Get the count of active tasks."""
    return len(_active_tasks)


async def cancel_all_tasks(timeout: float = 5.0) -> int:
    """
    Cancel all tracked tasks and wait for them to complete.

    Args:
        timeout: Maximum time to wait for tasks to cancel

    Returns:
        Number of tasks that were cancelled
    """
    if not _active_tasks:
        logger.info("No active tasks to cancel")
        return 0

    tasks_to_cancel = list(_active_tasks)
    count = len(tasks_to_cancel)
    logger.info(f"Cancelling {count} active tasks...")

    # Cancel all tasks
    for task in tasks_to_cancel:
        if not task.done():
            task.cancel()

    # Wait for all tasks to complete (with timeout)
    if tasks_to_cancel:
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout waiting for tasks to cancel. "
                f"Remaining: {len([t for t in tasks_to_cancel if not t.done()])}"
            )

    cancelled = sum(1 for t in tasks_to_cancel if t.cancelled())
    logger.info(f"Cancelled {cancelled}/{count} tasks")
    return cancelled


async def clear_all_tasks() -> None:
    """Clear the task registry (for testing)."""
    await cancel_all_tasks(timeout=1.0)
    _active_tasks.clear()


async def wait_for_tasks(timeout: Optional[float] = None) -> None:
    """
    Wait for all tracked tasks to complete.

    Args:
        timeout: Maximum time to wait (None = wait forever)
    """
    if not _active_tasks:
        return

    tasks = list(_active_tasks)
    logger.info(f"Waiting for {len(tasks)} tasks to complete...")

    try:
        if timeout:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        else:
            await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.TimeoutError:
        logger.warning("Timeout waiting for tasks")
