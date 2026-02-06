import asyncio
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, Optional, Tuple

# Timeout for Claude Code queries (5 minutes) - configurable via env
CLAUDE_QUERY_TIMEOUT_SECONDS = int(os.getenv("CLAUDE_QUERY_TIMEOUT", "300"))
# Session idle timeout (8 hours default) - configurable via env
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "480"))

from sqlalchemy import select  # noqa: E402

from ..core.database import get_db_session  # noqa: E402
from ..models.admin_contact import AdminContact  # noqa: E402
from ..models.claude_session import ClaudeSession  # noqa: E402
from ..utils.lru_cache import LRUCache  # noqa: E402
from ..utils.task_tracker import create_tracked_task  # noqa: E402

# Import subprocess-based Claude execution to avoid event loop blocking
from .claude_subprocess import execute_claude_subprocess  # noqa: E402
from .conversation_archive import archive_conversation  # noqa: E402
from .design_skills_service import get_design_system_prompt  # noqa: E402
from .session_naming import generate_session_name  # noqa: E402

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
        import threading

        self.work_dir = Path(work_dir).expanduser()
        self.active_sessions: Dict[int, str] = {}  # chat_id -> session_id
        # Track pending session creation to prevent duplicate sessions
        # when messages arrive while a session is being initialized
        self._pending_sessions: Dict[int, asyncio.Event] = {}  # chat_id -> ready_event
        self._pending_session_ids: Dict[int, Optional[str]] = (
            {}
        )  # chat_id -> session_id once ready
        # Track sessions that timed out for context in resume prompts
        self._timeout_sessions: Dict[int, Dict[str, Any]] = (
            {}
        )  # chat_id -> timeout_info
        # Lock to prevent concurrent Claude sessions from racing on os.environ
        self._api_key_lock = threading.Lock()

    def _kill_stuck_processes(self) -> int:
        """Kill any stuck Claude processes. Returns number of processes killed.

        Finds Claude processes that have been running for more than 15 minutes
        and kills them. This prevents zombie processes from consuming CPU.
        """
        killed = 0
        try:
            # Resolve the claude binary path dynamically
            claude_bin = shutil.which("claude")
            if not claude_bin:
                logger.debug("Claude binary not found in PATH, skipping process reaper")
                return 0

            # Find all Claude processes with their runtime
            # ps output: PID ELAPSED_TIME COMMAND
            # ELAPSED_TIME format: [[dd-]hh:]mm:ss
            result = subprocess.run(
                ["ps", "-eo", "pid,etime,command"],
                capture_output=True,
                text=True,
            )
            if not result.stdout:
                return 0

            lines = result.stdout.strip().split("\n")[1:]  # Skip header
            for line in lines:
                parts = line.split(None, 2)  # Split into PID, ETIME, COMMAND
                if len(parts) < 3:
                    continue

                pid, etime, command = parts

                # Check if it's a Claude Code CLI process (not other things with "claude" in the name)
                # Must be the actual Claude Code binary, not node/python wrappers
                if claude_bin not in command:
                    continue

                # Skip if it's just the shell snapshot tool
                if "shell-snapshots" in command:
                    continue

                # Parse elapsed time to seconds
                try:
                    elapsed_seconds = self._parse_etime(etime)
                except Exception:
                    continue

                # Kill if running longer than 15 minutes (900 seconds)
                if elapsed_seconds > 900:
                    try:
                        subprocess.run(["kill", "-9", pid], capture_output=True)
                        killed += 1
                        logger.warning(
                            f"Killed stuck Claude process PID {pid} "
                            f"(running for {elapsed_seconds // 60} min)"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to kill process {pid}: {e}")

        except Exception as e:
            logger.warning(f"Error checking for stuck processes: {e}")

        return killed

    def _parse_etime(self, etime: str) -> int:
        """Parse ps ELAPSED time format to seconds.

        Formats:
        - mm:ss
        - hh:mm:ss
        - dd-hh:mm:ss

        Returns:
            Elapsed time in seconds
        """
        # Handle dd-hh:mm:ss format
        if "-" in etime:
            days, rest = etime.split("-", 1)
            days = int(days)
        else:
            days = 0
            rest = etime

        # Handle hh:mm:ss or mm:ss
        parts = rest.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(int, parts)
        else:
            raise ValueError(f"Invalid etime format: {etime}")

        total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds
        return total_seconds

    def start_pending_session(self, chat_id: int) -> None:
        """Mark that a session is being created for this chat.

        Called when /claude:new with prompt starts executing.
        Other messages should wait for this session to be ready.
        """
        if chat_id not in self._pending_sessions:
            self._pending_sessions[chat_id] = asyncio.Event()
            self._pending_session_ids[chat_id] = None
            logger.info(f"Started pending session for chat {chat_id}")

    def complete_pending_session(self, chat_id: int, session_id: str) -> None:
        """Mark that the pending session is ready.

        Called when the new session has been initialized.
        """
        if chat_id in self._pending_sessions:
            self._pending_session_ids[chat_id] = session_id
            self._pending_sessions[chat_id].set()
            logger.info(
                f"Completed pending session for chat {chat_id}: {session_id[:8]}..."
            )

    def cancel_pending_session(self, chat_id: int) -> None:
        """Cancel pending session (e.g., on error)."""
        if chat_id in self._pending_sessions:
            self._pending_sessions[chat_id].set()  # Wake up any waiters
            del self._pending_sessions[chat_id]
            self._pending_session_ids.pop(chat_id, None)
            logger.info(f"Cancelled pending session for chat {chat_id}")

    async def wait_for_pending_session(
        self, chat_id: int, timeout: float = 30.0
    ) -> Optional[str]:
        """Wait for a pending session to be ready.

        Returns the session ID if one was created, or None if no pending session
        or timeout occurred.
        """
        if chat_id not in self._pending_sessions:
            return None

        event = self._pending_sessions[chat_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            session_id = self._pending_session_ids.get(chat_id)
            # Clean up after waiting
            self._pending_sessions.pop(chat_id, None)
            self._pending_session_ids.pop(chat_id, None)
            return session_id
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for pending session for chat {chat_id}")
            # Clean up on timeout - the session creation failed or is stuck
            self._pending_sessions.pop(chat_id, None)
            self._pending_session_ids.pop(chat_id, None)
            return None

    def has_pending_session(self, chat_id: int) -> bool:
        """Check if there's a pending session being created."""
        return chat_id in self._pending_sessions

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
        system_prompt_prefix: Optional[str] = None,
        thinking_effort: Optional[str] = None,
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
        # Save and restore using a lock to prevent concurrent sessions from racing
        # on this process-global value (see docs/UNIFIED_IMPROVEMENT_PLAN.md P0-3)
        with self._api_key_lock:
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

CRITICAL - Note References: When you mention or reference vault notes in your responses, ALWAYS use the
full absolute path. The bot automatically converts these paths to clickable Obsidian deep links.

Examples:
- When creating: "Created note: /Users/server/Research/vault/Folder/Note-Name.md"
- When referencing: "See /Users/server/Research/vault/Mem0.md for details"
- When listing: "Updated files: /Users/server/Research/vault/Config.md, /Users/server/Research/vault/Index.md"

The full path will become a clickable link that opens the note in Telegram and Obsidian.

VAULT SEMANTIC SEARCH (supplemental to Grep/Glob):
Use for discovering related notes, building See Also sections, or exploratory searches.
NOT a replacement for exact text search (use Grep) or file lookup (use Glob).

Commands (require: source /Volumes/LaCie/DataLake/.venv/bin/activate):
- Search: python3 ~/Research/vault/scripts/vault_search.py "query" [--format see-also|wikilinks]
- Embed new note: python3 ~/Research/vault/scripts/embed_note.py "/path/to/note.md"

WORKFLOW for creating notes:
1. Write note with Write tool
2. ALWAYS mention the full path in your response (e.g., "Created: /full/path/to/note.md")
3. Embed it: python3 ~/Research/vault/scripts/embed_note.py "/path/to/note.md"
4. Find related: python3 ~/Research/vault/scripts/vault_search.py "note title concepts" -f see-also -n 5 -e "note name"
5. Append See also section to the note"""

        # Add design skills guidance if available
        try:
            design_guidance = get_design_system_prompt()
            if design_guidance:
                telegram_system_prompt += "\n\n" + design_guidance
                logger.debug("Added design skills guidance to system prompt")
        except Exception as e:
            logger.warning(f"Failed to load design skills guidance: {e}")

        # Append per-chat memory (highest priority — user prefs win)
        from .workspace_service import ensure_workspace, get_memory

        ensure_workspace(chat_id)
        chat_memory = get_memory(chat_id)
        if chat_memory:
            telegram_system_prompt += "\n\n# User Memory\n" + chat_memory
            logger.debug(
                "Appended per-chat memory to system prompt for chat %s", chat_id
            )

        # Prepend caller-supplied system prompt (e.g. research mode)
        if system_prompt_prefix:
            telegram_system_prompt = (
                system_prompt_prefix + "\n\n" + telegram_system_prompt
            )
            logger.info("Prepended system_prompt_prefix to system prompt")

        # Get default model from environment or use sonnet
        default_model = os.getenv("CLAUDE_CODE_MODEL", "sonnet")
        selected_model = model or default_model

        # Use custom cwd if provided, otherwise use default work_dir
        work_directory = cwd or str(self.work_dir)

        # Check if resuming after timeout - add context to prompt
        timeout_info = self._timeout_sessions.get(chat_id)
        if timeout_info and session_id == timeout_info.get("session_id"):
            timeout_at = timeout_info.get("timeout_at")
            last_prompt = timeout_info.get("last_prompt", "")
            if timeout_at:
                minutes_ago = (datetime.utcnow() - timeout_at).total_seconds() / 60
                context_prefix = (
                    f"[CONTEXT: The previous session timed out {minutes_ago:.0f} minutes ago "
                    f"while working on: '{last_prompt}'. The user is now continuing.]\n\n"
                )
                prompt = context_prefix + prompt
                logger.info(
                    f"Added timeout context to resume prompt for chat {chat_id}"
                )

        logger.info(
            f"Executing Claude Code prompt for chat {chat_id}, "
            f"session={session_id or 'new'}, model={selected_model}, cwd={work_directory}"
        )

        result_session_id = None
        # Collect messages for conversation archiving
        archive_messages: list[dict] = [
            {
                "role": "user",
                "content": prompt,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ]

        # Cleanup callback for timeout/error
        def cleanup_on_timeout():
            """Cancel pending session on timeout."""
            self.cancel_pending_session(chat_id)
            logger.info(f"Cleaned up pending session for chat {chat_id} on timeout")

        try:
            # Use subprocess-based execution to avoid event loop blocking
            logger.info("Starting Claude subprocess execution...")
            async for msg_type, content, sid in execute_claude_subprocess(
                prompt=prompt,
                cwd=work_directory,
                model=selected_model,
                allowed_tools=None,  # Resolved from config by get_configured_tools()
                system_prompt=telegram_system_prompt,
                stop_check=stop_check,
                session_id=session_id,
                cleanup_callback=cleanup_on_timeout,
                thinking_effort=thinking_effort,
            ):
                logger.info(
                    f"Subprocess message: type={msg_type}, content_len={len(content) if content else 0}"
                )

                if msg_type == "init":
                    result_session_id = sid
                elif msg_type == "text":
                    if on_text:
                        on_text(content)
                    archive_messages.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                        }
                    )
                    yield ("text", content, None)
                elif msg_type == "tool":
                    archive_messages.append(
                        {
                            "role": "tool",
                            "content": content,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                        }
                    )
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
                        # Clear timeout state on successful completion
                        self._timeout_sessions.pop(chat_id, None)
                        # Archive conversation async (non-blocking)
                        create_tracked_task(
                            self._archive_conversation(
                                chat_id, result_session_id, archive_messages
                            ),
                            name=f"archive_conversation_{chat_id}",
                        )
                    # Pass stats through content field
                    yield ("done", content, result_session_id)
                elif msg_type == "error":
                    # Check if this is a timeout error
                    if "timeout" in content.lower():
                        pass
                        # Store timeout info for context in next prompt
                        if result_session_id or session_id:
                            self._timeout_sessions[chat_id] = {
                                "session_id": result_session_id or session_id,
                                "last_prompt": prompt[:200],
                                "timeout_at": datetime.utcnow(),
                            }
                    yield ("error", content, None)

        except Exception as e:
            logger.error(f"Error executing Claude Code prompt: {e}")
            yield ("error", f"\n\nError: {str(e)}", None)
        finally:
            # Clean up pending session state if still present (timeout/error case)
            if self.has_pending_session(chat_id):
                self.cancel_pending_session(chat_id)
                logger.info(
                    f"Cleaned up pending session for chat {chat_id} in finally block"
                )

            # Restore ANTHROPIC_API_KEY if it was set (under lock to prevent races)
            with self._api_key_lock:
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

        New sessions automatically get AI-generated names from the first prompt.
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
                # Generate AI-powered session name for new sessions
                session_name = None
                try:
                    session_name = await generate_session_name(last_prompt)
                    logger.info(
                        f"Generated session name: '{session_name}' for session {session_id[:8]}..."
                    )
                except Exception as e:
                    logger.error(f"Failed to generate session name: {e}")
                    # Continue without name - user can rename later

                new_session = ClaudeSession(
                    user_id=user_id,
                    chat_id=chat_id,
                    session_id=session_id,
                    name=session_name,  # Auto-generated name
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
                    logger.info(
                        f"Auto-enabled locked mode for chat {chat_id} (new session created)"
                    )
                    # Update cache to avoid database lookup
                    from ..bot.handlers.base import _claude_mode_cache

                    _claude_mode_cache[chat_id] = True

            await session.commit()
            logger.info(f"Saved session {session_id[:8]}... for chat {chat_id}")

    async def _archive_conversation(
        self,
        chat_id: int,
        session_id: str,
        messages: list[dict],
    ) -> None:
        """Archive conversation transcript to disk (runs as background task)."""
        try:
            path = archive_conversation(
                chat_id=chat_id,
                session_id=session_id,
                messages=messages,
            )
            logger.info(f"Archived conversation to {path}")
        except Exception as e:
            logger.error(f"Failed to archive conversation for chat {chat_id}: {e}")

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
                .where(
                    ClaudeSession.chat_id == chat_id, ClaudeSession.is_active == True
                )
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
                select(ClaudeSession).where(
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
                logger.info(
                    f"Reactivated session {session_id[:8]}... for chat {chat_id}"
                )
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

    async def find_session_by_timestamp(
        self, chat_id: int, message_timestamp: datetime, tolerance_seconds: int = 30
    ) -> Optional[str]:
        """Find a Claude session by correlating message timestamp with session last_used.

        This is used when reply context cache misses occur (e.g., after bot restart)
        to restore session continuity by finding the session that was active when
        the bot message was sent.

        Args:
            chat_id: Chat ID
            message_timestamp: Timestamp of the bot message being replied to
            tolerance_seconds: How far apart timestamps can be (default 30s)

        Returns:
            session_id if found, None otherwise
        """
        # Look for sessions updated within tolerance window of the message
        time_lower = message_timestamp - timedelta(seconds=tolerance_seconds)
        time_upper = message_timestamp + timedelta(seconds=tolerance_seconds)

        async with get_db_session() as session:
            result = await session.execute(
                select(ClaudeSession)
                .where(
                    ClaudeSession.chat_id == chat_id,
                    ClaudeSession.last_used >= time_lower,
                    ClaudeSession.last_used <= time_upper,
                )
                .order_by(ClaudeSession.last_used.desc())
                .limit(1)
            )
            db_session = result.scalar_one_or_none()

            if db_session:
                logger.info(
                    f"Found session {db_session.session_id[:8]}... by timestamp correlation "
                    f"(message={message_timestamp}, session={db_session.last_used})"
                )
                return db_session.session_id

        return None

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
                logger.info(
                    f"Set active session {session_id[:8]}... for chat {chat_id}"
                )
                return True

        return False

    async def rename_session(self, session_id: str, new_name: str) -> bool:
        """Rename a session.

        Args:
            session_id: Session ID to rename
            new_name: New name for the session

        Returns:
            True if session was renamed successfully
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(ClaudeSession).where(ClaudeSession.session_id == session_id)
            )
            db_session = result.scalar_one_or_none()

            if db_session:
                db_session.name = new_name
                await session.commit()
                logger.info(f"Renamed session {session_id[:8]}... to '{new_name}'")
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


async def run_periodic_process_reaper(interval_hours: float = 1.0) -> None:
    """Periodically kill stuck Claude processes.

    Args:
        interval_hours: How often to run the reaper (default: every hour)
    """
    interval_seconds = interval_hours * 3600
    logger.info(
        f"Starting periodic Claude process reaper (interval: {interval_hours}h)"
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            # Kill stuck processes
            service = get_claude_code_service()
            killed_count = service._kill_stuck_processes()

            if killed_count > 0:
                logger.warning(f"⚠️ Killed {killed_count} stuck Claude process(es)")
            else:
                logger.debug("No stuck Claude processes found")

        except asyncio.CancelledError:
            logger.info("Claude process reaper task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in Claude process reaper: {e}", exc_info=True)
            # Continue running despite errors
