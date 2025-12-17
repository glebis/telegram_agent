import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, Optional, Tuple

from sqlalchemy import select

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from ..core.database import get_db_session
from ..models.admin_contact import AdminContact
from ..models.claude_session import ClaudeSession
from ..models.user import User

logger = logging.getLogger(__name__)


def _format_tool_use(tool_name: str, tool_input: dict) -> str:
    """Format tool use for display with relevant details."""
    # Extract the most relevant info based on tool type
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        # Show just filename for brevity
        filename = path.split("/")[-1] if "/" in path else path
        return f"📖 Read: {filename}"

    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        filename = path.split("/")[-1] if "/" in path else path
        return f"✍️ Write: {filename}"

    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        filename = path.split("/")[-1] if "/" in path else path
        return f"✏️ Edit: {filename}"

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"🔍 Glob: {pattern}"

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        if path:
            return f"🔎 Grep: '{pattern}' in {path.split('/')[-1]}"
        return f"🔎 Grep: '{pattern}'"

    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Truncate long commands
        if len(cmd) > 40:
            cmd = cmd[:37] + "..."
        return f"⚡ Bash: {cmd}"

    elif tool_name == "Skill":
        skill_name = tool_input.get("skill", "")
        return f"🎯 Skill: {skill_name}"

    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        agent_type = tool_input.get("subagent_type", "")
        if desc:
            return f"🤖 Task: {desc}"
        elif agent_type:
            return f"🤖 Task: {agent_type}"
        return "🤖 Task: spawning agent"

    elif tool_name == "WebFetch":
        url = tool_input.get("url", "")
        # Show domain only
        if url:
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc
                return f"🌐 Fetch: {domain}"
            except:
                pass
        return "🌐 WebFetch"

    elif tool_name == "WebSearch":
        query = tool_input.get("query", "")
        if len(query) > 30:
            query = query[:27] + "..."
        return f"🔍 Search: {query}"

    else:
        return f"🔧 {tool_name}"


async def is_claude_code_admin(chat_id: int) -> bool:
    """Check if user is authorized for Claude Code."""
    async with get_db_session() as session:
        result = await session.execute(
            select(AdminContact).where(
                AdminContact.chat_id == chat_id, AdminContact.active == True
            )
        )
        return result.scalar_one_or_none() is not None


class ClaudeCodeService:
    """Service for executing Claude Code prompts with session management."""

    def __init__(self, work_dir: str = "~/Research/vault"):
        self.work_dir = Path(work_dir).expanduser()
        self.active_sessions: Dict[int, str] = {}  # chat_id -> session_id

    async def execute_prompt(
        self,
        prompt: str,
        chat_id: int,
        user_id: int,
        session_id: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None,
    ) -> AsyncGenerator[Tuple[str, Optional[str]], None]:
        """
        Execute a Claude Code prompt with streaming output.

        Args:
            prompt: The prompt to send to Claude
            chat_id: Telegram chat ID
            user_id: Database user ID
            session_id: Optional session ID to resume
            on_text: Optional callback for text chunks

        Yields:
            Tuple of (text_chunk, session_id) - session_id is None until final result
        """
        # Unset ANTHROPIC_API_KEY to use subscription instead of API credits
        # Save original value to restore later
        original_api_key = os.environ.pop("ANTHROPIC_API_KEY", None)

        # Build environment without the API key
        env = os.environ.copy()

        # System prompt for Telegram integration context
        telegram_system_prompt = """You are running inside a Telegram bot. Important capabilities:

FILE SENDING: When you create or reference files (PDF, images, audio, video, documents),
the bot will automatically detect file paths in your response and send them to the user.
Just mention the full file path and the file will be delivered. You CAN send files!

Supported formats: .pdf, .png, .jpg, .jpeg, .gif, .mp3, .mp4, .wav, .doc, .docx, .xlsx, .csv, .zip

Example: After creating a PDF, say "Created: /path/to/file.pdf" and it will be sent automatically.

FORMATTING: Your responses are converted to Telegram HTML. Markdown works (bold, italic, code, links).
Tables are converted to ASCII format for readability."""

        # Build options
        options = ClaudeCodeOptions(
            resume=session_id,
            cwd=str(self.work_dir),
            allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
            system_prompt=telegram_system_prompt,
            env=env,
        )

        logger.info(
            f"Executing Claude Code prompt for chat {chat_id}, "
            f"session={session_id or 'new'}, cwd={self.work_dir}"
        )
        logger.info(
            f"ANTHROPIC_API_KEY unset: {original_api_key is not None}, using subscription"
        )

        result_session_id = None
        accumulated_text = ""

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            accumulated_text += block.text
                            if on_text:
                                on_text(block.text)
                            yield ("text", block.text, None)
                        elif isinstance(block, ToolUseBlock):
                            # Extract tool details for display
                            tool_detail = _format_tool_use(block.name, block.input)
                            yield ("tool", tool_detail, None)

                elif isinstance(message, SystemMessage):
                    if message.subtype == "init" and message.data:
                        init_session_id = message.data.get("session_id")
                        if init_session_id:
                            result_session_id = init_session_id
                            logger.info(f"Session initialized: {init_session_id}")

                elif isinstance(message, ResultMessage):
                    result_session_id = message.session_id
                    logger.info(
                        f"Claude Code completed: session={result_session_id}, "
                        f"turns={message.num_turns}, cost=${message.total_cost_usd:.4f}"
                    )

            # Save/update session in database
            if result_session_id:
                await self._save_session(
                    chat_id=chat_id,
                    user_id=user_id,
                    session_id=result_session_id,
                    last_prompt=prompt[:500],  # Truncate for storage
                )
                self.active_sessions[chat_id] = result_session_id
                yield ("done", "", result_session_id)

        except Exception as e:
            logger.error(f"Error executing Claude Code prompt: {e}")
            yield ("error", f"\n\nError: {str(e)}", None)
            raise
        finally:
            # Restore ANTHROPIC_API_KEY if it was set
            if original_api_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = original_api_key
                logger.debug("Restored ANTHROPIC_API_KEY")

    async def _save_session(
        self,
        chat_id: int,
        user_id: int,
        session_id: str,
        last_prompt: str,
    ) -> None:
        """Save or update a Claude session in the database."""
        async with get_db_session() as session:
            # Check if session exists
            result = await session.execute(
                select(ClaudeSession).where(ClaudeSession.session_id == session_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.last_prompt = last_prompt
                existing.last_used = datetime.utcnow()
                existing.is_active = True
            else:
                new_session = ClaudeSession(
                    user_id=user_id,
                    chat_id=chat_id,
                    session_id=session_id,
                    last_prompt=last_prompt,
                    last_used=datetime.utcnow(),
                    is_active=True,
                )
                session.add(new_session)

            await session.commit()
            logger.info(f"Saved session {session_id[:8]}... for chat {chat_id}")

    async def get_active_session(self, chat_id: int) -> Optional[str]:
        """Get the active session ID for a chat."""
        # Check in-memory cache first
        if chat_id in self.active_sessions:
            return self.active_sessions[chat_id]

        # Check database
        async with get_db_session() as session:
            result = await session.execute(
                select(ClaudeSession)
                .where(ClaudeSession.chat_id == chat_id, ClaudeSession.is_active == True)
                .order_by(ClaudeSession.last_used.desc())
            )
            db_session = result.scalar_one_or_none()

            if db_session:
                self.active_sessions[chat_id] = db_session.session_id
                return db_session.session_id

        return None

    async def get_user_sessions(
        self, chat_id: int, limit: int = 10
    ) -> list[ClaudeSession]:
        """Get recent sessions for a chat."""
        async with get_db_session() as session:
            result = await session.execute(
                select(ClaudeSession)
                .where(ClaudeSession.chat_id == chat_id)
                .order_by(ClaudeSession.last_used.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def end_session(self, chat_id: int) -> bool:
        """End the active session for a chat."""
        session_id = self.active_sessions.pop(chat_id, None)

        if session_id:
            async with get_db_session() as session:
                result = await session.execute(
                    select(ClaudeSession).where(ClaudeSession.session_id == session_id)
                )
                db_session = result.scalar_one_or_none()
                if db_session:
                    db_session.is_active = False
                    await session.commit()
                    logger.info(f"Ended session {session_id[:8]}... for chat {chat_id}")
                    return True

        return False

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session from the database."""
        async with get_db_session() as session:
            result = await session.execute(
                select(ClaudeSession).where(ClaudeSession.session_id == session_id)
            )
            db_session = result.scalar_one_or_none()
            if db_session:
                # Remove from active sessions cache
                for chat_id, sid in list(self.active_sessions.items()):
                    if sid == session_id:
                        del self.active_sessions[chat_id]

                await session.delete(db_session)
                await session.commit()
                logger.info(f"Deleted session {session_id[:8]}...")
                return True

        return False

    async def set_active_session(self, chat_id: int, session_id: str) -> bool:
        """Set a specific session as active for a chat."""
        async with get_db_session() as session:
            # Verify session exists and belongs to this chat
            result = await session.execute(
                select(ClaudeSession).where(
                    ClaudeSession.session_id == session_id,
                    ClaudeSession.chat_id == chat_id,
                )
            )
            db_session = result.scalar_one_or_none()

            if db_session:
                db_session.is_active = True
                db_session.last_used = datetime.utcnow()
                await session.commit()
                self.active_sessions[chat_id] = session_id
                logger.info(f"Set active session {session_id[:8]}... for chat {chat_id}")
                return True

        return False


# Global instance
_claude_code_service: Optional[ClaudeCodeService] = None


def get_claude_code_service() -> ClaudeCodeService:
    """Get the global Claude Code service instance."""
    global _claude_code_service
    if _claude_code_service is None:
        work_dir = os.getenv("CLAUDE_CODE_WORK_DIR", "~/Research/vault")
        _claude_code_service = ClaudeCodeService(work_dir=work_dir)
    return _claude_code_service
