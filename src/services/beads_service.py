"""Beads (bd) CLI integration for agent-side task persistence.

Wraps the bd CLI tool via subprocess for structured issue tracking
with dependency graphs, designed for AI agent workflows.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

# Module-level singleton
_beads_service: Optional["BeadsService"] = None


def get_beads_service() -> "BeadsService":
    """Get or create the singleton BeadsService instance."""
    global _beads_service
    if _beads_service is None:
        _beads_service = BeadsService(working_dir=_PROJECT_ROOT)
    return _beads_service


class BeadsNotInstalled(Exception):
    """Raised when the bd binary is not found on PATH."""

    pass


class BeadsNotInitialized(Exception):
    """Raised when bd has not been initialized in the working directory."""

    pass


class BeadsCommandError(Exception):
    """Raised when a bd command exits with non-zero status."""

    def __init__(self, message: str, stderr: str = "", returncode: int = 1):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class BeadsService:
    """Wraps the bd CLI for structured issue tracking."""

    def __init__(self, working_dir: Optional[str] = None):
        self.working_dir = working_dir

    async def _run_bd(
        self, *args: str
    ) -> Union[Dict[str, Any], List[Any]]:
        """Execute a bd command with --json output.

        Args:
            *args: Command arguments passed to bd.

        Returns:
            Parsed JSON output (dict or list) from bd.

        Raises:
            BeadsNotInstalled: If bd binary not found.
            BeadsCommandError: If bd exits with non-zero status.
        """
        cmd = ["bd", *args, "--json"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError:
            raise BeadsNotInstalled(
                "bd binary not found. Install beads: "
                "https://github.com/steveyegge/beads"
            )

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        if proc.returncode != 0:
            raise BeadsCommandError(
                f"bd {' '.join(args)} failed (exit {proc.returncode}): "
                f"{stderr_str}",
                stderr=stderr_str,
                returncode=proc.returncode,
            )

        if not stdout_str:
            return {}

        return json.loads(stdout_str)

    async def init(self) -> Dict[str, Any]:
        """Initialize beads in stealth mode.

        Returns:
            Parsed JSON output from bd init.
        """
        return await self._run_bd("init", "--stealth", "--quiet")

    async def create_issue(
        self,
        title: str,
        priority: int = 2,
        issue_type: str = "task",
    ) -> Dict[str, Any]:
        """Create a new beads issue.

        Args:
            title: Issue title.
            priority: Priority 0-3 (0=highest).
            issue_type: One of bug, feature, task, epic, chore.

        Returns:
            Created issue dict including 'id'.
        """
        return await self._run_bd(
            "create", title, "-p", str(priority), "-t", issue_type
        )

    async def ready(self) -> List[Dict[str, Any]]:
        """List issues with no open blockers.

        Returns:
            List of unblocked issue dicts.
        """
        result = await self._run_bd("ready")
        if isinstance(result, list):
            return result
        return []

    async def list_issues(self) -> List[Dict[str, Any]]:
        """List all issues.

        Returns:
            List of all issue dicts.
        """
        result = await self._run_bd("list")
        if isinstance(result, list):
            return result
        return []

    async def show(self, issue_id: str) -> Dict[str, Any]:
        """Show details for a single issue.

        Args:
            issue_id: Beads issue ID (e.g. 'bd-a1b2').

        Returns:
            Issue detail dict.
        """
        result = await self._run_bd("show", issue_id)
        if isinstance(result, dict):
            return result
        return {}

    async def update(
        self,
        issue_id: str,
        status: Optional[str] = None,
        claim: bool = False,
    ) -> Dict[str, Any]:
        """Update an issue's status or claim it.

        Args:
            issue_id: Beads issue ID.
            status: New status (e.g. 'in_progress').
            claim: Atomically claim the issue.

        Returns:
            Updated issue dict.
        """
        args: List[str] = ["update", issue_id]
        if status:
            args.extend(["--status", status])
        if claim:
            args.append("--claim")
        result = await self._run_bd(*args)
        if isinstance(result, dict):
            return result
        return {}

    async def close(
        self, issue_id: str, reason: str = "Done"
    ) -> Dict[str, Any]:
        """Close an issue.

        Args:
            issue_id: Beads issue ID.
            reason: Closure reason.

        Returns:
            Closed issue dict.
        """
        result = await self._run_bd(
            "close", issue_id, "--reason", reason
        )
        if isinstance(result, dict):
            return result
        return {}

    async def add_dependency(
        self, child_id: str, parent_id: str
    ) -> Dict[str, Any]:
        """Add a blocking dependency between issues.

        Args:
            child_id: Issue that is blocked.
            parent_id: Issue that blocks.

        Returns:
            Dependency result dict.
        """
        result = await self._run_bd("dep", "add", child_id, parent_id)
        if isinstance(result, dict):
            return result
        return {}

    async def stats(self) -> Dict[str, Any]:
        """Get project statistics.

        Returns:
            Stats dict (counts by status, priority, etc.).
        """
        result = await self._run_bd("stats")
        if isinstance(result, dict):
            return result
        return {}

    async def is_available(self) -> bool:
        """Check if bd is installed and initialized.

        Returns:
            True if bd can be used, False otherwise.
        """
        try:
            await self._run_bd("stats")
            return True
        except (BeadsNotInstalled, BeadsCommandError):
            return False
