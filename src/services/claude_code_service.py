import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, Optional, Tuple

# Timeout for Claude Code queries (5 minutes) - configurable via env
CLAUDE_QUERY_TIMEOUT_SECONDS = int(os.getenv("CLAUDE_QUERY_TIMEOUT", "300"))
# Session idle timeout (8 hours default) - configurable via env
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "480"))

from sqlalchemy import select

# Import subprocess-based Claude execution to avoid event loop blocking
from .claude_subprocess import execute_claude_subprocess

from ..core.database import get_db_session
from ..models.admin_contact import AdminContact
from ..utils.lru_cache import LRUCache
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
            except Exception:
                pass
        return "🌐 WebFetch"

    elif tool_name == "WebSearch":
        query = tool_input.get("query", "")
        if len(query) > 30:
            query = query[:27] + "..."
        return f"🔍 Search: {query}"

    else:
        return f"🔧 {tool_name}"


# Cache for admin status to avoid database deadlocks
# LRU cache with 1k max entries (admins are a small set)
_admin_cache: LRUCache[int, bool] = LRUCache(max_size=1000)


async def init_admin_cache() -> None:
    """Initialize admin cache from database on startup."""
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(AdminContact).where(AdminContact.active == True)
            )
            admins = result.scalars().all()
            for admin in admins:
                _admin_cache[admin.chat_id] = True
            logger.info(f"Initialized admin cache with {len(admins)} admins")
    except Exception as e:
        logger.error(f"Error initializing admin cache: {e}")


async def is_claude_code_admin(chat_id: int) -> bool:
    """Check if user is authorized for Claude Code."""
    # Check cache first
    if chat_id in _admin_cache:
        return _admin_cache[chat_id]

    # Fall back to database
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(AdminContact).where(
                    AdminContact.chat_id == chat_id, AdminContact.active == True
                )
            )
            is_admin = result.scalar_one_or_none() is not None
            _admin_cache[chat_id] = is_admin
            return is_admin
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


class ClaudeCodeService:
    """Service for executing Claude Code prompts with session management."""

    def __init__(self, work_dir: str = "~/Research/vault"):
        self.work_dir = Path(work_dir).expanduser()
        self.active_sessions: Dict[int, str] = {}  # chat_id -> session_id

    def _kill_stuck_processes(self) -> int:
        """Kill any stuck Claude processes. Returns number of processes killed."""
        killed = 0
        try:
            result = subprocess.run(
                ["pgrep", "-f", "claude.*--resume"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        subprocess.run(["kill", pid], capture_output=True)
                        killed += 1
                        logger.info(f"Killed stuck Claude process: {pid}")
                    except Exception as e:
                        logger.warning(f"Failed to kill process {pid}: {e}")
        except Exception as e:
            logger.warning(f"Error checking for stuck processes: {e}")
        return killed

    async def execute_prompt(
        self,
        prompt: str,
        chat_id: int,
        user_id: int,
        session_id: Optional[str] = None,
        on_text: Optional[Callable[[str], None]] = None,
        model: Optional[str] = None,
        stop_check: Optional[Callable[[], bool]] = None,
        cwd: Optional[str] = None,
    ) -> AsyncGenerator[Tuple[str, Optional[str]], None]:
        """
        Execute a Claude Code prompt with streaming output.

        Args:
            prompt: The prompt to send to Claude
            chat_id: Telegram chat ID
            user_id: Database user ID
            session_id: Optional session ID to resume
            on_text: Optional callback for text chunks
            model: Optional model override (sonnet, opus, haiku, or full model name)
            cwd: Optional working directory override

        Yields:
            Tuple of (text_chunk, session_id) - session_id is None until final result
        """
        # Unset ANTHROPIC_API_KEY to use subscription instead of API credits
        # Save original value to restore later
        original_api_key = os.environ.pop("ANTHROPIC_API_KEY", None)

        # System prompt for Telegram integration context
        telegram_system_prompt = """You are running inside a Telegram bot. Important capabilities:

FILE SENDING: When you create or reference files (PDF, images, audio, video, documents),
the bot will automatically detect file paths in your response and send them to the user.
Just mention the full file path and the file will be delivered. You CAN send files!

Supported formats: .pdf, .png, .jpg, .jpeg, .gif, .mp3, .mp4, .wav, .doc, .docx, .xlsx, .csv, .zip

Example: After creating a PDF, say "Created: /path/to/file.pdf" and it will be sent automatically.

FORMATTING: Your responses are converted to Telegram HTML. Markdown works (bold, italic, code, links).
Tables are converted to ASCII format for readability.

IMPORTANT - Note Links: When referencing markdown files in your responses (documentation, research notes, etc.),
always format them WITHOUT the .md extension. This creates clickable links in Telegram.
Example: "Documentation: ai-research/20260110-telegram-agent-response-formatting-fix" (not .md)

VAULT SEMANTIC SEARCH (supplemental to Grep/Glob):
Use for discovering related notes, building See Also sections, or exploratory searches.
NOT a replacement for exact text search (use Grep) or file lookup (use Glob).

Commands (require: source /Volumes/LaCie/DataLake/.venv/bin/activate):
- Search: python3 ~/Research/vault/scripts/vault_search.py "query" [--format see-also|wikilinks]
- Embed new note: python3 ~/Research/vault/scripts/embed_note.py "/path/to/note.md"

WORKFLOW for creating notes:
1. Write note with Write tool
2. Embed it: python3 ~/Research/vault/scripts/embed_note.py "/path/to/note.md"
3. Find related: python3 ~/Research/vault/scripts/vault_search.py "note title concepts" -f see-also -n 5 -e "note name"
4. Append See also section to the note"""

        # Get default model from environment or use sonnet
        default_model = os.getenv("CLAUDE_CODE_MODEL", "sonnet")
        selected_model = model or default_model

        # Use custom cwd if provided, otherwise use default work_dir
        work_directory = cwd or str(self.work_dir)

        logger.info(
            f"Executing Claude Code prompt for chat {chat_id}, "
            f"session={session_id or 'new'}, model={selected_model}, cwd={work_directory}"
        )

        result_session_id = None

        try:
            # Use subprocess-based execution to avoid event loop blocking
            logger.info(f"Starting Claude subprocess execution...")
            async for msg_type, content, sid in execute_claude_subprocess(
                prompt=prompt,
                cwd=work_directory,
                model=selected_model,
                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
                system_prompt=telegram_system_prompt,
                stop_check=stop_check,
                session_id=session_id,
            ):
                logger.info(f"Subprocess message: type={msg_type}, content_len={len(content) if content else 0}")

                if msg_type == "init":
                    result_session_id = sid
                elif msg_type == "text":
                    if on_text:
                        on_text(content)
                    yield ("text", content, None)
                elif msg_type == "tool":
                    yield ("tool", content, None)
                elif msg_type == "done":
                    result_session_id = sid or result_session_id
                    # Save session
                    if result_session_id:
                        await self._save_session(
                            chat_id=chat_id,
                            user_id=user_id,
                            session_id=result_session_id,
                            last_prompt=prompt[:500],
                        )
                        self.active_sessions[chat_id] = result_session_id
                    # Pass stats through content field
                    yield ("done", content, result_session_id)
                elif msg_type == "error":
                    yield ("error", content, None)

        except Exception as e:
            logger.error(f"Error executing Claude Code prompt: {e}")
            yield ("error", f"\n\nError: {str(e)}", None)
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
        """Save or update a Claude session in the database.

        When a new session is created, automatically enables locked mode (claude_mode=True)
        so all subsequent messages route to Claude without requiring /claude prefix.
        """
        async with get_db_session() as session:
            # Check if session exists
            result = await session.execute(
                select(ClaudeSession).where(ClaudeSession.session_id == session_id)
            )
            existing = result.scalar_one_or_none()

            is_new_session = existing is None

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

            # Auto-enable locked mode when creating a new session (#15)
            if is_new_session:
                from ..models.chat import Chat
                result = await session.execute(
                    select(Chat).where(Chat.chat_id == chat_id)
                )
                chat = result.scalar_one_or_none()
                if chat and not chat.claude_mode:
                    chat.claude_mode = True
                    logger.info(f"Auto-enabled locked mode for chat {chat_id} (new session created)")
                    # Update cache to avoid database lookup
                    from ..bot.handlers.base import _claude_mode_cache
                    _claude_mode_cache[chat_id] = True

            await session.commit()
            logger.info(f"Saved session {session_id[:8]}... for chat {chat_id}")

    async def get_active_session(self, chat_id: int) -> Optional[str]:
        """Get the active session ID for a chat.

        Returns None if:
        - No active session exists
        - Session has been idle for more than SESSION_IDLE_TIMEOUT_MINUTES
        """
        # Check database (always check to validate timestamp)
        async with get_db_session() as session:
            result = await session.execute(
                select(ClaudeSession)
                .where(ClaudeSession.chat_id == chat_id, ClaudeSession.is_active == True)
                .order_by(ClaudeSession.last_used.desc())
                .limit(1)
            )
            db_session = result.scalar_one_or_none()

            if db_session:
                # Check if session has been idle too long
                if db_session.last_used:
                    idle_time = datetime.utcnow() - db_session.last_used
                    if idle_time > timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES):
                        logger.info(
                            f"Session {db_session.session_id[:8]}... expired after "
                            f"{idle_time.total_seconds() // 60:.0f} minutes idle"
                        )
                        # Mark session as inactive
                        db_session.is_active = False
                        await session.commit()
                        # Remove from in-memory cache
                        self.active_sessions.pop(chat_id, None)
                        return None

                # Session is still valid
                self.active_sessions[chat_id] = db_session.session_id
                return db_session.session_id

        # No active session found, clear cache
        self.active_sessions.pop(chat_id, None)
        return None

    async def get_latest_session(
        self, chat_id: int
    ) -> Optional[tuple[str, datetime, bool]]:
        """Get the most recent session for a chat, regardless of active state.

        Returns tuple of (session_id, last_used, is_active) or None.
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(ClaudeSession)
                .where(ClaudeSession.chat_id == chat_id)
                .order_by(ClaudeSession.last_used.desc())
                .limit(1)
            )
            db_session = result.scalar_one_or_none()

            if db_session:
                return (
                    db_session.session_id,
                    db_session.last_used,
                    db_session.is_active,
                )

        return None

    async def reactivate_session(self, chat_id: int, session_id: str) -> bool:
        """Reactivate a session and set it as the active session for a chat."""
        async with get_db_session() as session:
            # First, deactivate any other active sessions for this chat
            await session.execute(
                select(ClaudeSession)
                .where(
                    ClaudeSession.chat_id == chat_id,
                    ClaudeSession.is_active == True,
                )
            )
            # Mark all active sessions for this chat as inactive
            result = await session.execute(
                select(ClaudeSession).where(
                    ClaudeSession.chat_id == chat_id,
                    ClaudeSession.is_active == True,
                )
            )
            for s in result.scalars().all():
                s.is_active = False

            # Activate the target session
            result = await session.execute(
                select(ClaudeSession).where(ClaudeSession.session_id == session_id)
            )
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.is_active = True
                db_session.last_used = datetime.utcnow()
                await session.commit()
                self.active_sessions[chat_id] = session_id
                logger.info(f"Reactivated session {session_id[:8]}... for chat {chat_id}")
                return True

        return False

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
