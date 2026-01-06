"""
Job Queue Service - Interface for submitting jobs to the worker queue.
"""

import logging
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class JobQueueService:
    """Service for submitting long-running jobs to the worker queue."""

    def __init__(self, queue_dir: Path = None):
        self.queue_dir = queue_dir or Path.home() / "Research/agent_tasks"
        self.pending_dir = self.queue_dir / "pending"
        self.pending_dir.mkdir(parents=True, exist_ok=True)

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
        with open(job_file, 'w') as f:
            yaml.dump(job, f, default_flow_style=False)

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
        with open(job_file, 'w') as f:
            yaml.dump(job, f, default_flow_style=False)

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

        Args:
            command: Shell command to execute
            chat_id: Telegram chat ID for notification
            message_id: Optional message ID to reply to
            timeout: Command timeout in seconds
            priority: Job priority

        Returns:
            Job ID
        """
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
        with open(job_file, 'w') as f:
            yaml.dump(job, f, default_flow_style=False)

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
