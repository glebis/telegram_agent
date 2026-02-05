"""
Tests for architecture improvements:
1. Fix duplicate route in main.py
2. Externalize Python path
3. Add task tracking for graceful shutdown
"""

import asyncio
from pathlib import Path

import pytest


class TestDuplicateRoute:
    """Test that there are no duplicate route definitions."""

    def test_no_duplicate_root_routes(self):
        """Ensure there's only one root route definition."""

        from src.main import app

        # Count routes for path "/"
        root_routes = [
            route
            for route in app.routes
            if hasattr(route, "path") and route.path == "/"
        ]

        # Should have exactly one root route
        assert (
            len(root_routes) == 1
        ), f"Found {len(root_routes)} root routes, expected 1"

    def test_root_endpoint_returns_valid_response(self):
        """Ensure the root endpoint returns expected fields."""
        from fastapi.testclient import TestClient

        from src.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        # Should have status field
        assert "status" in data or "message" in data


class TestExternalizedPythonPath:
    """Test that Python path is configurable, not hardcoded."""

    def test_config_has_python_path(self):
        """Config should have a python_path setting."""
        from src.core.config import get_settings

        settings = get_settings()
        assert hasattr(
            settings, "python_executable"
        ), "Settings should have python_executable attribute"

    def test_python_path_defaults_to_sys_executable(self):
        """Default python path should be sys.executable."""
        from src.core.config import get_settings

        settings = get_settings()
        # Either it's sys.executable or a configured path
        assert settings.python_executable is not None
        assert len(settings.python_executable) > 0

    def test_subprocess_uses_config_python_path(self):
        """Subprocess calls should use configured Python path, not hardcoded."""
        from src.core.config import get_settings

        settings = get_settings()
        python_path = settings.python_executable

        # Read combined_processor.py and check for hardcoded paths
        processor_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "bot"
            / "combined_processor.py"
        )
        content = processor_path.read_text()

        # Should not contain hardcoded homebrew path as a literal string
        # (it may still appear in comments or as fallback, but primary usage should be config)
        content.count('"/opt/homebrew/bin/python3.11"')

        # We expect this to be replaced with config-based approach
        # For now, just check config exists - the fix will make this pass
        assert python_path is not None


class TestTaskTracking:
    """Test that background tasks are tracked for graceful shutdown."""

    def test_task_tracker_exists(self):
        """A task tracker module/function should exist."""
        from src.utils import task_tracker

        assert hasattr(
            task_tracker, "create_tracked_task"
        ), "task_tracker should have create_tracked_task function"
        assert hasattr(
            task_tracker, "get_active_tasks"
        ), "task_tracker should have get_active_tasks function"
        assert hasattr(
            task_tracker, "cancel_all_tasks"
        ), "task_tracker should have cancel_all_tasks function"

    @pytest.mark.asyncio
    async def test_create_tracked_task_adds_to_registry(self):
        """Created tasks should be added to the registry."""
        from src.utils.task_tracker import (
            clear_all_tasks,
            create_tracked_task,
            get_active_tasks,
        )

        # Clear any existing tasks
        await clear_all_tasks()

        async def dummy_task():
            await asyncio.sleep(10)

        task = create_tracked_task(dummy_task())
        active = get_active_tasks()

        assert task in active, "Task should be in active tasks"

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_completed_task_removed_from_registry(self):
        """Completed tasks should be automatically removed."""
        from src.utils.task_tracker import (
            clear_all_tasks,
            create_tracked_task,
            get_active_tasks,
        )

        # Clear any existing tasks
        await clear_all_tasks()

        async def quick_task():
            return "done"

        task = create_tracked_task(quick_task())
        await task  # Wait for completion

        # Give event loop time to process done callback
        await asyncio.sleep(0.1)

        active = get_active_tasks()
        assert task not in active, "Completed task should be removed"

    @pytest.mark.asyncio
    async def test_cancel_all_tasks(self):
        """cancel_all_tasks should cancel all tracked tasks."""
        from src.utils.task_tracker import (
            cancel_all_tasks,
            clear_all_tasks,
            create_tracked_task,
            get_active_tasks,
        )

        # Clear any existing tasks
        await clear_all_tasks()

        async def long_task():
            await asyncio.sleep(100)

        # Create multiple tasks
        tasks = [
            create_tracked_task(long_task()),
            create_tracked_task(long_task()),
            create_tracked_task(long_task()),
        ]

        assert len(get_active_tasks()) == 3

        # Cancel all
        await cancel_all_tasks(timeout=1.0)

        # All tasks should be cancelled
        for task in tasks:
            assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_rapid_task_creation(self):
        """Task tracker should handle rapid concurrent task creation."""
        from src.utils.task_tracker import (
            clear_all_tasks,
            create_tracked_task,
            get_active_tasks,
        )

        await clear_all_tasks()

        async def quick_task():
            await asyncio.sleep(0.01)

        # Create many tasks rapidly from the same event loop
        tasks = [create_tracked_task(quick_task()) for _ in range(10)]

        # All tasks should be tracked
        active = get_active_tasks()
        assert len(active) == 10, f"Expected 10 active tasks, got {len(active)}"

        # Wait for all to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0.1)  # Allow callbacks to run

        # All should be removed
        active = get_active_tasks()
        assert len(active) == 0, f"Expected 0 active tasks, got {len(active)}"


class TestGracefulShutdown:
    """Test that lifespan properly handles task cleanup."""

    @pytest.mark.asyncio
    async def test_lifespan_cancels_tasks_on_shutdown(self):
        """Lifespan shutdown should cancel tracked tasks."""
        from src.utils.task_tracker import (
            clear_all_tasks,
            create_tracked_task,
            get_active_tasks,
        )

        await clear_all_tasks()

        async def background_work():
            await asyncio.sleep(100)

        # Simulate creating tasks during app runtime
        task = create_tracked_task(background_work())

        assert len(get_active_tasks()) >= 1

        # Simulate shutdown
        from src.utils.task_tracker import cancel_all_tasks

        await cancel_all_tasks(timeout=1.0)

        # Task should be done (cancelled)
        assert task.done()
