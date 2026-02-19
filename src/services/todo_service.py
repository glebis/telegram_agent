"""TodoService - Wrapper for task_manager.py via async subprocess.

This service provides async access to task management functionality stored
in the Obsidian vault, following the subprocess isolation pattern required
for external I/O operations.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to task_manager.py CLI
TASK_MANAGER_PATH = Path(__file__).parent.parent.parent / "scripts" / "task_manager.py"
PYTHON_PATH = "/opt/homebrew/bin/python3.11"


class TodoService:
    """Service for managing todos in Obsidian vault via subprocess."""

    async def list_tasks(
        self,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks from vault.

        Args:
            status: Filter by status (inbox/active/completed)
            tags: Filter by tags

        Returns:
            List of task dictionaries with id, title, status, etc.

        Raises:
            RuntimeError: If subprocess fails
            json.JSONDecodeError: If response is invalid JSON
        """
        cmd = [
            PYTHON_PATH,
            str(TASK_MANAGER_PATH),
            "list",
            "--format",
            "json",
        ]

        if status:
            cmd.extend(["--status", status])

        if tags:
            cmd.extend(["--tags"] + tags)

        logger.debug(f"Executing task_manager.py list: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"task_manager.py list failed: {error_msg}")
            raise RuntimeError(f"task_manager.py failed: {error_msg}")

        tasks = json.loads(stdout.decode())

        # Process each task to add 'id' and flatten frontmatter
        for task in tasks:
            # Extract ID from path (filename without extension)
            if "path" in task:
                filename = task["path"].split("/")[-1]  # Get filename
                task["id"] = filename.replace(".md", "")  # Remove extension

            # Flatten frontmatter fields to top level
            if "frontmatter" in task:
                fm = task["frontmatter"]
                task["priority"] = fm.get("priority", "medium")
                task["due"] = fm.get("due", "")
                task["tags"] = fm.get("tags", [])
                task["context"] = fm.get("context", "")
                task["created"] = fm.get("created", "")

        logger.info(f"Listed {len(tasks)} tasks (status={status}, tags={tags})")

        return tasks

    async def create_task(
        self,
        title: str,
        context: Optional[str] = None,
        due: Optional[str] = None,
        tags: Optional[List[str]] = None,
        priority: str = "medium",
        source: str = "telegram",
    ) -> str:
        """Create new task in vault.

        Args:
            title: Task title
            context: Task description/context
            due: Due date (YYYY-MM-DD)
            tags: List of tags
            priority: Priority (low/medium/high)
            source: Source of task (telegram/voice/claude/manual)

        Returns:
            Path to created task file

        Raises:
            RuntimeError: If subprocess fails
        """
        cmd = [
            PYTHON_PATH,
            str(TASK_MANAGER_PATH),
            "create",
            "--title",
            title,
            "--source",
            source,
            "--priority",
            priority,
        ]

        if context:
            cmd.extend(["--context", context])

        if due:
            cmd.extend(["--due", due])

        if tags:
            cmd.extend(["--tags"] + tags)

        logger.debug(f"Executing task_manager.py create: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"task_manager.py create failed: {error_msg}")
            raise RuntimeError(f"task_manager.py failed: {error_msg}")

        task_path = stdout.decode().strip()
        logger.info(f"Created task: {title} at {task_path}")

        return task_path

    async def complete_task(self, task_id: str) -> bool:
        """Mark task as complete.

        Args:
            task_id: Task ID (filename without .md)

        Returns:
            True if successful, False if task not found
        """
        cmd = [
            PYTHON_PATH,
            str(TASK_MANAGER_PATH),
            "complete",
            task_id,
        ]

        logger.debug(f"Executing task_manager.py complete: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(*cmd)
        returncode = await proc.wait()

        if returncode == 0:
            logger.info(f"Completed task: {task_id}")
            return True
        else:
            logger.warning(f"Failed to complete task: {task_id}")
            return False


def get_todo_service() -> TodoService:
    """Get singleton TodoService instance (delegates to DI container)."""
    from ..core.services import Services, get_service

    return get_service(Services.TODO)
