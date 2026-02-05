"""
Job Queue Service - Interface for submitting jobs to the worker queue.
"""

import logging
import os
import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import uuid4

logger = logging.getLogger(__name__)

_job_queue_service = None

# Strict slug pattern: alphanumeric, hyphens, underscores only
_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Shell operators that indicate command chaining
_SHELL_OPERATORS = re.compile(r"[;&|]")


def validate_job_id(job_id: str) -> bool:
    """Validate that a job ID uses strict slug format.

    Only alphanumeric characters, hyphens, and underscores are allowed.
    No path separators, dots-prefix, spaces, or special characters.

    Args:
        job_id: The job ID to validate.

    Returns:
        True if the job ID is valid, False otherwise.
    """
    return bool(_JOB_ID_PATTERN.match(job_id))


def validate_command_allowlist(command: str) -> None:
    """Validate a command against the WORKER_COMMAND_ALLOWLIST env var.

    Checks that:
    1. An allowlist is configured (non-empty WORKER_COMMAND_ALLOWLIST env var)
    2. The command contains no shell chaining operators (; & |)
    3. The base executable is in the allowlist

    Args:
        command: The shell command string to validate.

    Raises:
        ValueError: If the command is not permitted.
    """
    allowlist_raw = os.getenv("WORKER_COMMAND_ALLOWLIST", "")
    allowlist: List[str] = [c.strip() for c in allowlist_raw.split(",") if c.strip()]

    if not allowlist:
        raise ValueError(
            "Custom command rejected: no allowlist configured. "
            "Set WORKER_COMMAND_ALLOWLIST env var."
        )

    # Reject shell chaining operators
    if _SHELL_OPERATORS.search(command):
        raise ValueError(
            f"Custom command rejected: shell operator detected in {command!r}. "
            "Commands must be simple (no ;, &, or | chaining)."
        )

    # Extract the base executable (first whitespace-delimited token)
    base_cmd = command.strip().split()[0] if command.strip() else ""
    # Handle absolute paths: /usr/bin/echo -> echo
    base_name = os.path.basename(base_cmd)

    if base_name not in allowlist:
        raise ValueError(
            f"Command {base_name!r} not in allowlist. "
            f"Allowed: {allowlist}"
        )


class JobQueueService:
    """Service for submitting long-running jobs to the worker queue."""

    def __init__(self, queue_dir: Path = None):
        self.queue_dir = queue_dir or Path.home() / "Research/agent_tasks"
        self.pending_dir = self.queue_dir / "pending"
        self.pending_dir.mkdir(parents=True, exist_ok=True)

    def _safe_write(self, job_file: Path, job: Dict[str, Any]) -> None:
        """Write a job YAML file, verifying the path stays within the queue directory.

        Args:
            job_file: Target path for the job file.
            job: Job data dictionary to serialize.

        Raises:
            ValueError: If the resolved path escapes the queue directory.
        """
        resolved = Path(os.path.realpath(str(job_file)))
        queue_real = Path(os.path.realpath(str(self.queue_dir)))
        if not str(resolved).startswith(str(queue_real) + os.sep):
            raise ValueError(
                f"Job file path {job_file} resolves outside queue directory"
            )
        with open(job_file, 'w') as f:
            yaml.dump(job, f, default_flow_style=False)

    def submit_pdf_convert(
        self,
        url: str,
        chat_id: int,
        message_id: int = None,
        priority: str = "medium"
    ) -> str:
        """
        Submit a PDF conversion job.

        Args:
            url: PDF URL to convert
            chat_id: Telegram chat ID for notification
            message_id: Optional message ID to reply to
            priority: Job priority (high, medium, low)

        Returns:
            Job ID
        """
        job_id = f"pdf_convert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"

        job = {
            "id": job_id,
            "type": "pdf_convert",
            "created": datetime.now().isoformat(),
            "priority": priority,
            "params": {
                "url": url,
            },
            "telegram_chat_id": chat_id,
            "telegram_message_id": message_id,
            "status": "pending"
        }

        job_file = self.pending_dir / f"{job_id}.yaml"
        self._safe_write(job_file, job)

        logger.info(f"Submitted PDF convert job: {job_id}")
        return job_id

    def submit_pdf_save(
        self,
        url: str,
        chat_id: int,
        message_id: int = None,
        vault_path: str = None,
        priority: str = "medium"
    ) -> str:
        """
        Submit a PDF save to vault job.

        Args:
            url: PDF URL to convert and save
            chat_id: Telegram chat ID for notification
            message_id: Optional message ID to reply to
            vault_path: Vault path (defaults to ~/Research/vault)
            priority: Job priority

        Returns:
            Job ID
        """
        job_id = f"pdf_save_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"

        job = {
            "id": job_id,
            "type": "pdf_save",
            "created": datetime.now().isoformat(),
            "priority": priority,
            "params": {
                "url": url,
                "vault_path": vault_path or "~/Research/vault"
            },
            "telegram_chat_id": chat_id,
            "telegram_message_id": message_id,
            "status": "pending"
        }

        job_file = self.pending_dir / f"{job_id}.yaml"
        self._safe_write(job_file, job)

        logger.info(f"Submitted PDF save job: {job_id}")
        return job_id

    def submit_custom_command(
        self,
        command: str,
        chat_id: int,
        message_id: int = None,
        timeout: int = 300,
        priority: str = "low"
    ) -> str:
        """
        Submit a custom shell command job.

        The command is validated against the WORKER_COMMAND_ALLOWLIST env var.
        If no allowlist is configured, ALL custom commands are rejected.
        Shell chaining operators (; & |) are not permitted.

        Args:
            command: Shell command to execute
            chat_id: Telegram chat ID for notification
            message_id: Optional message ID to reply to
            timeout: Command timeout in seconds
            priority: Job priority

        Returns:
            Job ID

        Raises:
            ValueError: If the command is not in the allowlist or uses shell operators.
        """
        # Validate command against allowlist before creating the job
        validate_command_allowlist(command)

        job_id = f"command_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"

        job = {
            "id": job_id,
            "type": "custom_command",
            "created": datetime.now().isoformat(),
            "priority": priority,
            "params": {
                "command": command,
                "timeout": timeout
            },
            "telegram_chat_id": chat_id,
            "telegram_message_id": message_id,
            "status": "pending"
        }

        job_file = self.pending_dir / f"{job_id}.yaml"
        self._safe_write(job_file, job)

        logger.info(f"Submitted custom command job: {job_id}")
        return job_id

    def get_queue_status(self) -> Dict[str, int]:
        """Get current queue status."""
        return {
            "pending": len(list(self.pending_dir.glob("*.yaml"))),
            "in_progress": len(list((self.queue_dir / "in_progress").glob("*.yaml"))),
            "completed": len(list((self.queue_dir / "completed").glob("*.yaml"))),
            "failed": len(list((self.queue_dir / "failed").glob("*.yaml")))
        }


def get_job_queue_service(queue_dir: Path = None) -> JobQueueService:
    """Get singleton job queue service (simple in-memory holder)."""
    global _job_queue_service
    if _job_queue_service is None or queue_dir:
        _job_queue_service = JobQueueService(queue_dir)
    return _job_queue_service
