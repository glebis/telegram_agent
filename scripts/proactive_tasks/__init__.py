"""
Proactive Task Framework

A system for managing scheduled agent tasks similar to health reviews.
Tasks are defined in task_registry.yaml and executed via launchd.
"""

from .base_task import BaseTask, TaskResult
from .task_runner import run_task, list_tasks

__all__ = ["BaseTask", "TaskResult", "run_task", "list_tasks"]
