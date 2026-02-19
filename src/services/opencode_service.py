"""OpenCode service layer for managing queries and sessions.

Mirrors the interface of ``claude_code_service.py`` but delegates execution
to the OpenCode CLI via ``opencode_subprocess.py``.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.core.config import get_settings

from .opencode_subprocess import run_opencode_subprocess

logger = logging.getLogger(__name__)


class OpenCodeService:
    """Service for executing OpenCode prompts with session management.

    Provides a high-level interface matching ClaudeCodeService patterns:
    - ``run_opencode_query()`` for prompt execution
    - Session tracking per chat_id
    - Availability checking
    """

    def __init__(self, work_dir: Optional[str] = None):
        """Initialize the OpenCode service.

        Args:
            work_dir: Working directory for OpenCode. Defaults to the
                configured opencode_work_dir, or claude_code_work_dir as fallback.
        """
        if work_dir is not None:
            self.work_dir = Path(work_dir).expanduser()
        else:
            try:
                settings = get_settings()
                configured_dir = (
                    settings.opencode_work_dir or settings.claude_code_work_dir
                )
                self.work_dir = Path(configured_dir).expanduser()
            except Exception:
                self.work_dir = Path("~/Research/vault").expanduser()

        # Session tracking: chat_id -> session_id
        self._sessions: Dict[int, str] = {}
        # Session history: chat_id -> list of session info dicts
        self._session_history: Dict[int, List[Dict]] = {}

    def is_available(self) -> bool:
        """Check if the OpenCode CLI is installed and accessible.

        Returns:
            True if ``opencode`` is found in PATH, False otherwise.
        """
        return shutil.which("opencode") is not None

    def get_session(self, chat_id: int) -> Optional[str]:
        """Get the active session ID for a chat.

        Args:
            chat_id: Telegram chat ID.

        Returns:
            Session ID string if one exists, None otherwise.
        """
        return self._sessions.get(chat_id)

    def clear_session(self, chat_id: int) -> None:
        """Clear the active session for a chat.

        Args:
            chat_id: Telegram chat ID.
        """
        self._sessions.pop(chat_id, None)
        logger.info(f"Cleared OpenCode session for chat {chat_id}")

    def list_sessions(self, chat_id: int) -> List[Dict]:
        """List all recorded sessions for a chat.

        Args:
            chat_id: Telegram chat ID.

        Returns:
            List of session info dictionaries with keys:
            session_id, first_prompt, created_at.
        """
        return self._session_history.get(chat_id, [])

    async def run_opencode_query(
        self,
        chat_id: int,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Execute a prompt through OpenCode and return the response.

        Manages session persistence automatically: if a session exists
        for the chat_id, it will be resumed.

        Args:
            chat_id: Telegram chat ID for session tracking.
            prompt: The prompt to send to OpenCode.
            model: Optional model override. Defaults to settings.opencode_model.

        Returns:
            The response text from OpenCode, or an error message string.
        """
        # Resolve model from settings if not provided
        if model is None:
            try:
                settings = get_settings()
                model = settings.opencode_model
            except Exception:
                model = "anthropic:claude-sonnet-4-20250514"

        # Get existing session for this chat
        session_id = self._sessions.get(chat_id)

        logger.info(
            f"Running OpenCode query for chat {chat_id}, "
            f"model={model}, session={session_id or 'new'}"
        )

        # Run the subprocess (blocking call wrapped for async compatibility)
        result = run_opencode_subprocess(
            prompt=prompt,
            model=model,
            session_id=session_id,
            cwd=str(self.work_dir),
        )

        if result["success"]:
            # Update session tracking
            returned_session = result.get("session_id")
            if returned_session:
                self._sessions[chat_id] = returned_session

                # Track in history if it is a new session
                if chat_id not in self._session_history:
                    self._session_history[chat_id] = []

                # Check if this session is already in history
                existing_ids = {s["session_id"] for s in self._session_history[chat_id]}
                if returned_session not in existing_ids:
                    self._session_history[chat_id].append(
                        {
                            "session_id": returned_session,
                            "first_prompt": prompt[:200],
                            "created_at": datetime.utcnow().isoformat() + "Z",
                        }
                    )

            return result["output"]
        else:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"OpenCode query failed for chat {chat_id}: {error_msg}")
            return f"OpenCode error: {error_msg}"


def get_opencode_service() -> OpenCodeService:
    """Get the global OpenCode service instance (delegates to DI container)."""
    from ..core.services import Services, get_service

    return get_service(Services.OPENCODE)
