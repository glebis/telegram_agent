"""
Base class for proactive tasks.

All scheduled tasks should inherit from BaseTask and implement the execute() method.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of a task execution."""
    success: bool
    message: str
    outputs: Dict[str, Any] = field(default_factory=dict)
    files: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def mark_complete(self):
        """Mark the task as complete with current timestamp."""
        self.completed_at = datetime.now()

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "outputs": self.outputs,
            "files": [str(f) for f in self.files],
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }


class BaseTask(ABC):
    """
    Abstract base class for all proactive tasks.

    Subclasses must implement:
    - name: Task identifier
    - description: Human-readable description
    - execute(): Main task logic
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize task with optional configuration."""
        self.config = config or {}
        self._logger = logging.getLogger(f"{__name__}.{self.name}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique task identifier (e.g., 'daily-research')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable task description."""
        pass

    @property
    def default_schedule(self) -> Dict[str, int]:
        """Default launchd schedule (can be overridden in registry)."""
        return {"hour": 10, "minute": 0}

    @abstractmethod
    async def execute(self) -> TaskResult:
        """
        Execute the task.

        Returns:
            TaskResult with success status, message, and outputs.
        """
        pass

    def validate_config(self) -> List[str]:
        """
        Validate task configuration.

        Returns:
            List of validation errors (empty if valid).
        """
        return []

    async def on_success(self, result: TaskResult) -> None:
        """Hook called after successful execution."""
        self._logger.info(f"Task {self.name} completed successfully: {result.message}")

    async def on_failure(self, result: TaskResult) -> None:
        """Hook called after failed execution."""
        self._logger.error(f"Task {self.name} failed: {result.message}")
        for error in result.errors:
            self._logger.error(f"  - {error}")

    async def run(self) -> TaskResult:
        """
        Run the task with pre/post hooks.

        This is the main entry point for task execution.
        """
        self._logger.info(f"Starting task: {self.name}")

        # Validate config
        errors = self.validate_config()
        if errors:
            result = TaskResult(
                success=False,
                message="Configuration validation failed",
                errors=errors,
            )
            result.mark_complete()
            await self.on_failure(result)
            return result

        try:
            result = await self.execute()
            result.mark_complete()

            if result.success:
                await self.on_success(result)
            else:
                await self.on_failure(result)

            return result

        except Exception as e:
            self._logger.exception(f"Task {self.name} raised exception")
            result = TaskResult(
                success=False,
                message=f"Task failed with exception: {str(e)}",
                errors=[str(e)],
            )
            result.mark_complete()
            await self.on_failure(result)
            return result
