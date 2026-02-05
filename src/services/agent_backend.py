"""Agent backend abstraction for pluggable AI coding agents.

Provides a unified interface (``AgentBackend``) with concrete implementations
for Claude Code and OpenCode, plus a factory function to select the active
backend based on configuration.

Usage::

    from src.services.agent_backend import get_agent_backend

    backend = get_agent_backend()          # from config
    backend = get_agent_backend("opencode")  # explicit override

    result = await backend.run_query(chat_id=123, prompt="Hello")
    sessions = await backend.list_sessions(chat_id=123)
"""

import logging
import shutil
from abc import ABC, abstractmethod
from typing import List, Optional

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class AgentBackend(ABC):
    """Abstract base class for AI coding agent backends.

    All agent backends must implement this interface so that handler
    code can work with any backend interchangeably.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend identifier string."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the backend CLI tool is installed.

        Returns:
            True if the tool binary is found in PATH.
        """
        ...

    @abstractmethod
    async def run_query(
        self,
        chat_id: int,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Execute a prompt and return the response text.

        Args:
            chat_id: Telegram chat ID for session tracking.
            prompt: The user prompt.
            model: Optional model override.

        Returns:
            Response text or error message.
        """
        ...

    @abstractmethod
    async def list_sessions(self, chat_id: int) -> List[dict]:
        """List sessions for a chat.

        Args:
            chat_id: Telegram chat ID.

        Returns:
            List of session info dicts.
        """
        ...


class ClaudeCodeBackend(AgentBackend):
    """Backend implementation delegating to ClaudeCodeService."""

    def __init__(self):
        from .claude_code_service import get_claude_code_service

        self._service = get_claude_code_service()

    @property
    def name(self) -> str:
        return "claude_code"

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    async def run_query(
        self,
        chat_id: int,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Execute a prompt through Claude Code and collect the full response.

        This collects all streamed text chunks into a single response string.
        For full streaming support, use ClaudeCodeService.execute_prompt directly.
        """
        text_parts = []
        try:
            async for msg_type, content, session_id in self._service.execute_prompt(
                prompt=prompt,
                chat_id=chat_id,
                user_id=0,  # Simplified; real usage would supply actual user_id
                model=model,
            ):
                if msg_type == "text":
                    text_parts.append(content)
                elif msg_type == "error":
                    if not text_parts:
                        return f"Claude Code error: {content}"
        except Exception as e:
            logger.error(f"ClaudeCodeBackend.run_query failed: {e}")
            return f"Claude Code error: {e}"

        return "".join(text_parts) if text_parts else "No response from Claude Code."

    async def list_sessions(self, chat_id: int) -> List[dict]:
        """List Claude Code sessions for a chat."""
        try:
            sessions = await self._service.get_user_sessions(chat_id)
            return [
                {
                    "session_id": s.session_id,
                    "name": getattr(s, "name", None),
                    "last_used": str(getattr(s, "last_used", "")),
                    "is_active": getattr(s, "is_active", False),
                }
                for s in sessions
            ]
        except Exception as e:
            logger.error(f"ClaudeCodeBackend.list_sessions failed: {e}")
            return []


class OpenCodeBackend(AgentBackend):
    """Backend implementation delegating to OpenCodeService."""

    def __init__(self):
        from .opencode_service import OpenCodeService

        self._service = OpenCodeService()

    @property
    def name(self) -> str:
        return "opencode"

    def is_available(self) -> bool:
        return shutil.which("opencode") is not None

    async def run_query(
        self,
        chat_id: int,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Execute a prompt through OpenCode."""
        return await self._service.run_opencode_query(
            chat_id=chat_id,
            prompt=prompt,
            model=model,
        )

    async def list_sessions(self, chat_id: int) -> List[dict]:
        """List OpenCode sessions for a chat."""
        return self._service.list_sessions(chat_id)


def get_agent_backend(backend_name: Optional[str] = None) -> AgentBackend:
    """Factory function to get the configured agent backend.

    Resolution order:
    1. Explicit ``backend_name`` parameter.
    2. ``Settings.ai_agent_backend`` from config / environment.

    When ``opencode`` is selected but is not available (CLI not installed),
    falls back to ``claude_code`` with a warning.

    Args:
        backend_name: Optional explicit backend name override.
            Values: ``"claude_code"`` or ``"opencode"``.

    Returns:
        An ``AgentBackend`` instance.

    Raises:
        ValueError: If the backend_name is not recognized.
    """
    if backend_name is None:
        try:
            settings = get_settings()
            backend_name = settings.ai_agent_backend
        except Exception:
            backend_name = "claude_code"

    if backend_name == "claude_code":
        return ClaudeCodeBackend()
    elif backend_name == "opencode":
        # Check availability; fall back to Claude Code if not installed
        if shutil.which("opencode") is None:
            logger.warning(
                "OpenCode backend requested but 'opencode' CLI not found in PATH. "
                "Falling back to claude_code backend."
            )
            return ClaudeCodeBackend()
        return OpenCodeBackend()
    else:
        raise ValueError(
            f"Unknown agent backend: '{backend_name}'. "
            f"Valid options: 'claude_code', 'opencode'."
        )
