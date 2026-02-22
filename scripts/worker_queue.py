#!/usr/bin/env python3
"""
Async Job Queue Worker for Verity

Handles long-running tasks like PDF conversion that shouldn't block the bot.
Uses a file-based queue (default: ~/agent_tasks) and sends results via Telegram.

Usage:
    python3 worker_queue.py              # Run worker daemon
    python3 worker_queue.py --once       # Process queue once and exit
    python3 worker_queue.py --job <id>   # Process specific job
"""

import asyncio
import logging
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import argparse
import subprocess
import aiofiles
from dataclasses import dataclass, asdict
from enum import Enum
import re
import os
import shutil

# Configure logging
log_dir_env = os.getenv("JOB_QUEUE_LOG_DIR")
log_dir = Path(log_dir_env).expanduser() if log_dir_env else Path.cwd() / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'worker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class JobType(Enum):
    """Types of jobs the worker can handle."""
    PDF_CONVERT = "pdf_convert"
    PDF_SAVE = "pdf_save"
    RESEARCH = "research"
    TRANSCRIBE = "transcribe"
    CUSTOM_COMMAND = "custom_command"


class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a job in the queue."""
    id: str
    type: JobType
    created: str
    priority: str  # high, medium, low
    params: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    telegram_chat_id: Optional[int] = None
    telegram_message_id: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """Create Job from dict."""
        data['type'] = JobType(data['type'])
        data['status'] = JobStatus(data.get('status', 'pending'))
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for YAML serialization."""
        data = asdict(self)
        data['type'] = self.type.value
        data['status'] = self.status.value
        return data


class JobQueue:
    """File-based job queue using ~/Research/agent_tasks/."""

    def __init__(self, queue_dir: Path = None):
        env_queue_dir = os.getenv("JOB_QUEUE_DIR")
        default_dir = Path.home() / "agent_tasks"
        self.queue_dir = Path(env_queue_dir).expanduser() if env_queue_dir else (queue_dir or default_dir)
        self.pending_dir = self.queue_dir / "pending"
        self.in_progress_dir = self.queue_dir / "in_progress"
        self.completed_dir = self.queue_dir / "completed"
        self.failed_dir = self.queue_dir / "failed"

        # Ensure directories exist
        for d in [self.pending_dir, self.in_progress_dir, self.completed_dir, self.failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Security toggles
        self.allow_custom_commands = os.getenv("ALLOW_CUSTOM_COMMANDS", "false").lower() == "true"
        self._job_id_pattern = re.compile(r"^[A-Za-z0-9_-]+$")

        # Command allowlist (comma-separated base executable names)
        allowlist_raw = os.getenv("WORKER_COMMAND_ALLOWLIST", "")
        self._command_allowlist: List[str] = [
            c.strip() for c in allowlist_raw.split(",") if c.strip()
        ]

        # Shell operators that indicate chaining (security risk)
        self._shell_operators = re.compile(r"[;&|]")

        # Required fields for a well-formed job YAML
        self._required_job_fields = {"id", "type"}

    def _validate_job_id(self, job_id: str) -> bool:
        """Allow only slug-like job IDs to prevent path traversal or unsafe names."""
        return bool(self._job_id_pattern.match(job_id))

    def _validate_job_data(self, data: Any) -> bool:
        """Validate that parsed YAML data has the required job structure.

        Returns True if data is a dict containing at least the required fields.
        """
        if not isinstance(data, dict):
            return False
        return self._required_job_fields.issubset(data.keys())

    def _validate_command(self, command: str) -> None:
        """Validate a command string against the allowlist and reject shell operators.

        Raises ValueError if the command is not permitted.
        """
        if not self._command_allowlist:
            raise ValueError(
                "Custom command rejected: no allowlist configured. "
                "Set WORKER_COMMAND_ALLOWLIST env var."
            )

        # Reject shell chaining operators
        if self._shell_operators.search(command):
            raise ValueError(
                f"Custom command rejected: shell operator detected in {command!r}. "
                "Commands must be simple (no ;, &, or | chaining)."
            )

        # Extract the base executable (first token)
        base_cmd = command.strip().split()[0] if command.strip() else ""
        # Also handle absolute paths: /usr/bin/echo -> echo
        base_name = os.path.basename(base_cmd)

        if base_name not in self._command_allowlist:
            raise ValueError(
                f"Command {base_name!r} not in allowlist. "
                f"Allowed: {self._command_allowlist}"
            )

    def _safe_resolve(self, path: Path) -> Path:
        """Resolve a path and verify it stays within the queue directory.

        Raises ValueError if the resolved path escapes the queue directory.
        """
        resolved = Path(os.path.realpath(str(path)))
        queue_real = Path(os.path.realpath(str(self.queue_dir)))
        if not str(resolved).startswith(str(queue_real) + os.sep) and resolved != queue_real:
            raise ValueError(
                f"Path {path} resolves outside queue directory "
                f"({resolved} not under {queue_real})"
            )
        return resolved

    async def add_job(self, job: Job) -> Path:
        """Add a new job to the queue."""
        if not self._validate_job_id(job.id):
            raise ValueError(f"Invalid job id: {job.id}")

        if job.type == JobType.CUSTOM_COMMAND:
            if not self.allow_custom_commands:
                raise ValueError("CUSTOM_COMMAND jobs are disabled")
            # Validate command against allowlist
            command = job.params.get("command", "")
            self._validate_command(command)

        job_file = self.pending_dir / f"{job.id}.yaml"
        self._safe_resolve(job_file)
        async with aiofiles.open(job_file, 'w') as f:
            await f.write(yaml.dump(job.to_dict(), default_flow_style=False))
        logger.info(f"Added job {job.id} to queue")
        return job_file

    async def get_next_job(self) -> Optional[Job]:
        """Get the next pending job based on priority."""
        pending_files = sorted(self.pending_dir.glob("*.yaml"))
        if not pending_files:
            return None

        # Sort by priority (high > medium > low), then by creation time
        priority_order = {"high": 0, "medium": 1, "low": 2}

        for job_file in pending_files:
            try:
                # Skip files with invalid names
                if not self._validate_job_id(job_file.stem):
                    logger.warning(f"Skipping job with invalid id in filename: {job_file.name}")
                    continue

                # Verify the file resolves within the queue directory
                self._safe_resolve(job_file)

                async with aiofiles.open(job_file, 'r') as f:
                    content = await f.read()
                    data = yaml.safe_load(content)

                # Validate job data structure
                if not self._validate_job_data(data):
                    logger.warning(
                        f"Skipping job file with invalid structure: {job_file.name}"
                    )
                    continue

                job = Job.from_dict(data)

                # Disallow custom_command unless enabled
                if job.type == JobType.CUSTOM_COMMAND and not self.allow_custom_commands:
                    logger.warning(f"Skipping disallowed custom_command job {job.id}")
                    job_file.unlink(missing_ok=True)
                    continue

                # Move to in_progress (verify destination stays in queue)
                new_path = self.in_progress_dir / job_file.name
                self._safe_resolve(new_path)
                job_file.rename(new_path)
                job.status = JobStatus.IN_PROGRESS
                job.started_at = datetime.now().isoformat()

                async with aiofiles.open(new_path, 'w') as f:
                    await f.write(yaml.dump(job.to_dict(), default_flow_style=False))

                logger.info(f"Retrieved job {job.id} from queue")
                return job

            except Exception as e:
                logger.error(f"Error loading job {job_file}: {e}")
                continue

        return None

    async def complete_job(self, job: Job, result: Dict[str, Any] = None):
        """Mark job as completed and move to completed directory."""
        if not self._validate_job_id(job.id):
            raise ValueError(f"Invalid job id: {job.id}")

        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = datetime.now().isoformat()

        job_file = self.in_progress_dir / f"{job.id}.yaml"
        new_path = self.completed_dir / f"{job.id}.yaml"

        # Verify paths stay within queue directory
        self._safe_resolve(job_file)
        self._safe_resolve(new_path)

        if job_file.exists():
            async with aiofiles.open(new_path, 'w') as f:
                await f.write(yaml.dump(job.to_dict(), default_flow_style=False))
            job_file.unlink()
            logger.info(f"Job {job.id} completed successfully")

    async def fail_job(self, job: Job, error: str):
        """Mark job as failed and move to failed directory."""
        if not self._validate_job_id(job.id):
            raise ValueError(f"Invalid job id: {job.id}")

        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = datetime.now().isoformat()

        job_file = self.in_progress_dir / f"{job.id}.yaml"
        new_path = self.failed_dir / f"{job.id}.yaml"

        # Verify paths stay within queue directory
        self._safe_resolve(job_file)
        self._safe_resolve(new_path)

        if job_file.exists():
            async with aiofiles.open(new_path, 'w') as f:
                await f.write(yaml.dump(job.to_dict(), default_flow_style=False))
            job_file.unlink()
            logger.error(f"Job {job.id} failed: {error}")


class TelegramNotifier:
    """Send notifications to Telegram."""

    def __init__(self, bot_token: str = None):
        self.bot_token = bot_token or self._load_token()

    def _load_token(self) -> str:
        """Load bot token from environment or .env file."""
        import os
        from dotenv import load_dotenv

        env_file = Path.home() / "ai_projects/telegram_agent/.env"
        if env_file.exists():
            load_dotenv(env_file)

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment")
        return token

    async def send_message(self, chat_id: int, text: str, reply_to: int = None) -> bool:
        """Send a message to Telegram chat."""
        import aiohttp

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(f"Sent message to chat {chat_id}")
                        return True
                    else:
                        logger.error(f"Failed to send message: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def send_document(self, chat_id: int, file_path: Path, caption: str = None) -> bool:
        """Send a document to Telegram chat."""
        import aiohttp

        url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"

        try:
            data = aiohttp.FormData()
            data.add_field('chat_id', str(chat_id))
            data.add_field('document', open(file_path, 'rb'), filename=file_path.name)
            if caption:
                data.add_field('caption', caption)

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        logger.info(f"Sent document to chat {chat_id}")
                        return True
                    else:
                        logger.error(f"Failed to send document: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Error sending document: {e}")
            return False


class JobExecutor:
    """Executes different types of jobs."""

    # Map job types to required CLI tools.
    # Before running a job the executor checks that all listed tools are on PATH.
    JOB_TOOL_REQUIREMENTS: Dict[str, List[str]] = {
        JobType.PDF_CONVERT.value: ["marker_single", "curl"],
        JobType.PDF_SAVE.value: ["marker_single", "curl"],
        # custom_command is validated via the allowlist, not here
    }

    def __init__(self):
        self.temp_dir = Path("/tmp/telegram_agent_pdf")
        self.temp_dir.mkdir(exist_ok=True)

    @staticmethod
    def _check_required_tools(job_type_value: str) -> None:
        """Verify that all CLI tools required for *job_type_value* are installed.

        Raises RuntimeError with a clear, actionable message if any tool is
        missing so the job fails gracefully instead of crashing mid-execution.
        """
        import platform as _platform

        required = JobExecutor.JOB_TOOL_REQUIREMENTS.get(job_type_value, [])
        if not required:
            return

        missing = [t for t in required if shutil.which(t) is None]
        if not missing:
            return

        plat = _platform.system().lower()
        hint_lines = []
        for tool in missing:
            if plat == "darwin":
                hint_lines.append(f"  - {tool}: install via Homebrew or pip (macOS)")
            else:
                hint_lines.append(f"  - {tool}: install via apt-get or pip (Linux)")

        msg = (
            f"Job requires tool(s) not found on this system: {', '.join(missing)}\n"
            + "\n".join(hint_lines)
        )
        raise RuntimeError(msg)

    async def execute(self, job: Job) -> Dict[str, Any]:
        """Execute a job based on its type."""
        # Gate: check required CLI tools before attempting execution
        self._check_required_tools(job.type.value)

        if job.type == JobType.PDF_CONVERT:
            return await self._execute_pdf_convert(job)
        elif job.type == JobType.PDF_SAVE:
            return await self._execute_pdf_save(job)
        elif job.type == JobType.CUSTOM_COMMAND:
            return await self._execute_custom_command(job)
        else:
            raise ValueError(f"Unknown job type: {job.type}")

    async def _execute_pdf_convert(self, job: Job) -> Dict[str, Any]:
        """Convert PDF to markdown."""
        url = job.params.get("url")
        if not url:
            raise ValueError("Missing 'url' parameter")

        # Download PDF
        pdf_path = await self._download_pdf(url)
        if not pdf_path:
            raise RuntimeError("Failed to download PDF")

        # Convert to markdown
        markdown = await self._convert_pdf_to_markdown(pdf_path)
        if not markdown:
            raise RuntimeError("Failed to convert PDF")

        # Save markdown
        md_filename = pdf_path.stem + ".md"
        md_path = self.temp_dir / md_filename
        async with aiofiles.open(md_path, 'w') as f:
            await f.write(markdown)

        # Cleanup PDF
        pdf_path.unlink()

        return {
            "markdown_path": str(md_path),
            "markdown_size": len(markdown),
            "filename": md_filename
        }

    async def _execute_pdf_save(self, job: Job) -> Dict[str, Any]:
        """Convert PDF and save to Obsidian vault."""
        url = job.params.get("url")
        vault_path = Path(job.params.get("vault_path", "~/Research/vault")).expanduser()

        # Download and convert
        pdf_path = await self._download_pdf(url)
        markdown = await self._convert_pdf_to_markdown(pdf_path)

        # Generate filename with date prefix
        today = datetime.now().strftime("%Y%m%d")
        base_name = pdf_path.stem
        filename = f"{today}-{base_name}.md"

        # Create frontmatter
        frontmatter = f"""---
created_date: '[[{today}]]'
source: {url}
type: pdf-source
tags:
  - source
  - pdf
---

"""
        full_content = frontmatter + markdown

        # Save to Sources folder
        sources_path = vault_path / "Sources"
        sources_path.mkdir(parents=True, exist_ok=True)
        output_path = sources_path / filename

        async with aiofiles.open(output_path, 'w') as f:
            await f.write(full_content)

        # Cleanup
        pdf_path.unlink()

        return {
            "vault_path": str(output_path),
            "filename": filename,
            "size": len(markdown)
        }

    async def _execute_custom_command(self, job: Job) -> Dict[str, Any]:
        """Execute a custom shell command.

        Defense-in-depth: validates the command against the allowlist even
        at execution time, in case a job file was placed directly on disk
        and bypassed the add_job() gate.
        """
        command = job.params.get("command")
        if not command:
            raise ValueError("Missing 'command' parameter")

        # Validate command against allowlist (defense in depth)
        self._validate_command_allowlist(command)

        timeout = job.params.get("timeout", 300)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "returncode": proc.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode()
            }
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"Command timed out after {timeout}s")

    @staticmethod
    def _validate_command_allowlist(command: str) -> None:
        """Validate command against the WORKER_COMMAND_ALLOWLIST env var.

        This is a defense-in-depth check at execution time.
        """
        allowlist_raw = os.getenv("WORKER_COMMAND_ALLOWLIST", "")
        allowlist = [c.strip() for c in allowlist_raw.split(",") if c.strip()]

        if not allowlist:
            raise ValueError(
                "Custom command rejected at execution: no allowlist configured. "
                "Set WORKER_COMMAND_ALLOWLIST env var."
            )

        # Reject shell chaining operators
        if re.search(r"[;&|]", command):
            raise ValueError(
                f"Custom command rejected at execution: shell operator in {command!r}"
            )

        base_cmd = command.strip().split()[0] if command.strip() else ""
        base_name = os.path.basename(base_cmd)

        if base_name not in allowlist:
            raise ValueError(
                f"Command {base_name!r} not in allowlist at execution. "
                f"Allowed: {allowlist}"
            )

    async def _download_pdf(self, url: str) -> Optional[Path]:
        """Download PDF from URL using curl."""
        from urllib.parse import urlparse, unquote

        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = Path(path).stem or "document"
        filename = filename.replace(" ", "-")[:100]
        pdf_path = self.temp_dir / f"{filename}.pdf"

        logger.info(f"Downloading PDF from {url}")

        proc = await asyncio.create_subprocess_exec(
            "curl", "-L", "-o", str(pdf_path), "--max-time", "120",
            "-A", "Mozilla/5.0", "-s", "-S", "--fail", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.wait_for(proc.communicate(), timeout=130)
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                logger.info(f"Downloaded PDF: {pdf_path.stat().st_size} bytes")
                return pdf_path
            return None
        except asyncio.TimeoutError:
            logger.error("PDF download timed out")
            return None

    async def _convert_pdf_to_markdown(self, pdf_path: Path) -> Optional[str]:
        """Convert PDF to markdown using marker_single."""
        output_dir = self.temp_dir / "output"
        output_dir.mkdir(exist_ok=True)

        logger.info(f"Converting PDF: {pdf_path}")

        proc = await asyncio.create_subprocess_exec(
            "marker_single", str(pdf_path),
            "--output_dir", str(output_dir),
            "--output_format", "markdown",
            "--disable_image_extraction",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.temp_dir)
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            # Find output markdown
            md_files = list(output_dir.glob("**/*.md"))
            if not md_files:
                logger.error("No markdown output found")
                return None

            md_path = md_files[0]
            async with aiofiles.open(md_path, 'r') as f:
                markdown = await f.read()

            logger.info(f"Converted to markdown: {len(markdown)} chars")

            # Cleanup output dir
            for f in output_dir.glob("**/*"):
                if f.is_file():
                    f.unlink()

            return markdown

        except asyncio.TimeoutError:
            logger.error("PDF conversion timed out")
            return None


class Worker:
    """Main worker that processes jobs from the queue."""

    def __init__(self, queue: JobQueue, notifier: TelegramNotifier, executor: JobExecutor):
        self.queue = queue
        self.notifier = notifier
        self.executor = executor

    async def process_job(self, job: Job) -> bool:
        """Process a single job."""
        logger.info(f"Processing job {job.id} (type: {job.type.value})")

        try:
            # Execute job
            result = await self.executor.execute(job)

            # Mark as completed
            await self.queue.complete_job(job, result)

            # Send notification to Telegram
            if job.telegram_chat_id:
                await self._notify_success(job, result)

            return True

        except Exception as e:
            logger.error(f"Job {job.id} failed: {e}", exc_info=True)
            await self.queue.fail_job(job, str(e))

            # Send error notification
            if job.telegram_chat_id:
                await self._notify_failure(job, str(e))

            return False

    async def _notify_success(self, job: Job, result: Dict[str, Any]):
        """Send success notification to Telegram."""
        if job.type == JobType.PDF_CONVERT:
            # Send markdown file
            md_path = Path(result['markdown_path'])
            await self.notifier.send_document(
                job.telegram_chat_id,
                md_path,
                caption=f"✅ PDF converted: {result['filename']}"
            )
            # Cleanup
            md_path.unlink()

        elif job.type == JobType.PDF_SAVE:
            await self.notifier.send_message(
                job.telegram_chat_id,
                f"✅ PDF saved to vault:\n<code>{result['filename']}</code>\n"
                f"Size: {result['size']} chars",
                reply_to=job.telegram_message_id
            )

        else:
            await self.notifier.send_message(
                job.telegram_chat_id,
                f"✅ Job {job.id} completed",
                reply_to=job.telegram_message_id
            )

    async def _notify_failure(self, job: Job, error: str):
        """Send failure notification to Telegram."""
        await self.notifier.send_message(
            job.telegram_chat_id,
            f"❌ Job {job.id} failed:\n{error[:200]}",
            reply_to=job.telegram_message_id
        )

    async def run_once(self):
        """Process all pending jobs once and exit."""
        logger.info("Processing queue once...")
        processed = 0

        while True:
            job = await self.queue.get_next_job()
            if not job:
                break

            await self.process_job(job)
            processed += 1

        logger.info(f"Processed {processed} jobs")

    async def run_daemon(self, poll_interval: int = 10):
        """Run as a daemon, polling for jobs."""
        logger.info(f"Starting worker daemon (poll interval: {poll_interval}s)")

        while True:
            try:
                job = await self.queue.get_next_job()

                if job:
                    await self.process_job(job)
                else:
                    # No jobs, wait before polling again
                    await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Verity Worker Queue")
    parser.add_argument("--once", action="store_true", help="Process queue once and exit")
    parser.add_argument("--job", type=str, help="Process specific job ID")
    parser.add_argument("--interval", type=int, default=10, help="Poll interval in seconds")
    args = parser.parse_args()

    # Initialize components
    queue = JobQueue()
    notifier = TelegramNotifier()
    executor = JobExecutor()
    worker = Worker(queue, notifier, executor)

    if args.once:
        await worker.run_once()
    else:
        await worker.run_daemon(poll_interval=args.interval)


if __name__ == "__main__":
    asyncio.run(main())
