"""
Codex Plugin - OpenAI Codex CLI integration.

This plugin provides Codex CLI integration for AI-assisted code analysis.
It handles:
- Command processing (/codex, /codex:resume, /codex:help)
- Subprocess execution of codex CLI
- Progress updates via Telegram
"""

import asyncio
import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import List

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.plugins.base import BasePlugin, PluginCapabilities, PluginMetadata

logger = logging.getLogger(__name__)


class CodexPlugin(BasePlugin):
    """
    Codex CLI integration plugin.

    Provides code analysis and refactoring via OpenAI Codex CLI.
    Features:
    - Execute prompts with /codex command
    - Resume sessions with /codex:resume
    - Configurable model, reasoning effort, and sandbox modes
    - Inline flag overrides (--model, --effort, --sandbox, -C)
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="codex",
            version="1.0.0",
            description="OpenAI Codex CLI integration for code analysis",
            author="Verity",
            requires=[],
            dependencies=[],
            priority=70,
            enabled_by_default=True,
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            services=["codex"],
            commands=["/codex", "/codex:resume", "/codex:help"],
            callbacks=["codex:*"],
            api_routes=False,
            message_handler=False,
        )

    async def on_load(self, container) -> bool:
        """Load plugin and verify codex binary exists."""
        logger.info("Loading Codex plugin...")

        # Get configuration
        self._work_dir = self.get_config_value("work_dir", "~/Research/vault")
        self._default_model = self.get_config_value("default_model", "gpt-5-codex")
        self._default_reasoning = self.get_config_value("default_reasoning", "high")
        self._default_sandbox = self.get_config_value("default_sandbox", "read-only")
        self._codex_binary = self.get_config_value(
            "codex_binary", "/usr/local/bin/codex"
        )
        self._timeout = self.get_config_value("query_timeout_seconds", 600)

        # Verify codex binary exists
        try:
            result = subprocess.run(
                [self._codex_binary, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info(f"Codex binary found: {result.stdout.strip()}")
            else:
                logger.warning(
                    f"Codex binary check failed: {result.stderr or 'Unknown error'}"
                )
                return False
        except FileNotFoundError:
            logger.error(f"Codex binary not found at {self._codex_binary}")
            return False
        except Exception as e:
            logger.error(f"Failed to verify codex binary: {e}")
            return False

        return True

    async def on_activate(self, app) -> bool:
        """Activate plugin."""
        logger.info("Activating Codex plugin...")
        return True

    def get_command_handlers(self) -> List:
        """Return command handlers for this plugin."""
        return [
            CommandHandler("codex", self._handle_codex),
        ]

    async def _handle_codex(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /codex command with subcommand routing."""
        user = update.effective_user
        chat = update.effective_chat
        message = update.message

        if not user or not chat or not message:
            return

        # Check admin access
        from src.services.claude_code_service import is_claude_code_admin

        if not await is_claude_code_admin(chat.id):
            await message.reply_text("You don't have permission to use Codex.")
            return

        # Initialize user/chat
        from src.bot.handlers import initialize_user_chat

        await initialize_user_chat(
            user_id=user.id,
            chat_id=chat.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )

        # Parse command text
        text = message.text or ""

        # Check for :subcommand
        if ":" in text.split()[0]:
            cmd_parts = text.split()[0].split(":")
            subcommand = cmd_parts[1] if len(cmd_parts) > 1 else ""
            remaining = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""

            if subcommand == "resume":
                await self._codex_resume(update, context, remaining)
            elif subcommand == "help":
                await self._codex_help(update)
            else:
                await message.reply_text(f"Unknown subcommand: {subcommand}")
        else:
            # Regular /codex <prompt>
            prompt = " ".join(context.args) if context.args else ""
            if not prompt:
                await self._codex_help(update)
                return

            await self._execute_codex(update, context, prompt, resume=False)

    async def _codex_resume(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str
    ) -> None:
        """Handle /codex:resume command."""
        if not prompt.strip():
            if update.message:
                await update.message.reply_text(
                    "Please provide a prompt to continue the session.\n"
                    "Example: <code>/codex:resume Add error handling</code>",
                    parse_mode="HTML",
                )
            return

        await self._execute_codex(update, context, prompt, resume=True)

    async def _codex_help(self, update: Update) -> None:
        """Show Codex help text."""
        help_text = """<b>🔍 Codex CLI</b>

<b>Basic Usage:</b>
<code>/codex &lt;prompt&gt;</code> — Run code analysis
<code>/codex:resume &lt;prompt&gt;</code> — Continue last session
<code>/codex:help</code> — This help

<b>Inline Flags:</b>
<code>--model gpt-5|gpt-5-codex</code> — Override model
<code>--effort low|medium|high</code> — Reasoning effort
<code>--sandbox read-only|workspace-write|danger-full-access</code>
<code>-C /path/to/dir</code> — Custom working directory

<b>Examples:</b>
<code>/codex Analyze auth module for security issues</code>
<code>/codex --effort medium Refactor login function</code>
<code>/codex --sandbox workspace-write Fix all type errors</code>
<code>/codex -C ~/projects/myapp Check test coverage</code>
<code>/codex:resume Add docstrings to all functions</code>

<b>Defaults:</b>
Model: <code>gpt-5-codex</code>
Effort: <code>high</code>
Sandbox: <code>read-only</code>
Directory: <code>~/Research/vault</code>

<b>Note:</b> Thinking tokens are suppressed by default."""

        if update.message:
            await update.message.reply_text(help_text, parse_mode="HTML")

    async def _execute_codex(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        prompt: str,
        resume: bool = False,
    ) -> None:
        """Execute Codex CLI with streaming updates."""
        message = update.message
        if not message:
            return

        # Parse inline flags
        parsed = self._parse_flags(prompt)
        model = parsed["model"]
        effort = parsed["effort"]
        sandbox = parsed["sandbox"]
        cwd = parsed["cwd"]
        clean_prompt = parsed["prompt"]

        # Expand home directory
        if cwd.startswith("~"):
            cwd = str(Path(cwd).expanduser())

        # Send status message
        from src.bot.handlers import edit_message_sync, send_message_sync

        model_display = model.replace("gpt-5-codex", "5-codex").replace("gpt-5", "5")
        cwd_display = cwd.replace(str(Path.home()), "~")

        status_text = (
            f"<b>🔍 Codex</b> · {model_display} · {effort} reasoning\n"
            f"<i>{self._escape_html(clean_prompt[:60])}...</i>\n\n"
            f"⏳ {'Resuming session' if resume else 'Running'}...\n"
            f"📂 {cwd_display}\n"
            f"🔒 {sandbox}"
        )

        result = send_message_sync(
            chat_id=message.chat_id,
            text=status_text,
            parse_mode="HTML",
            reply_to=message.message_id,
        )

        if not result:
            logger.error("Failed to send status message")
            return

        status_msg_id = result.get("message_id")

        # Build command
        if resume:
            # Resume: echo "prompt" | codex exec resume --last 2>/dev/null
            cmd = (
                f"echo {shlex.quote(clean_prompt)} | "
                f"{self._codex_binary} exec --skip-git-repo-check "
                f"resume --last 2>/dev/null"
            )
        else:
            # New session
            cmd = [
                self._codex_binary,
                "exec",
                "-m",
                model,
                "--config",
                f'model_reasoning_effort="{effort}"',
                "--sandbox",
                sandbox,
                "--full-auto",
                "--skip-git-repo-check",
                clean_prompt,
            ]
            # Suppress stderr (thinking tokens)
            cmd_str = " ".join([shlex.quote(str(arg)) for arg in cmd]) + " 2>/dev/null"
            cmd = cmd_str

        logger.info(
            f"Executing codex: {cmd if isinstance(cmd, str) else ' '.join(cmd)}"
        )

        # Run in background thread
        try:
            output = await asyncio.to_thread(
                self._run_subprocess, cmd, cwd, self._timeout
            )

            # Format output
            formatted = self._format_output(output)

            # Split if too long
            from src.bot.handlers import split_message

            chunks = split_message(formatted, max_length=4000)

            # Edit status message with first chunk
            edit_message_sync(
                chat_id=message.chat_id,
                message_id=status_msg_id,
                text=chunks[0],
                parse_mode="HTML",
            )

            # Send remaining chunks
            for chunk in chunks[1:]:
                send_message_sync(
                    chat_id=message.chat_id,
                    text=chunk,
                    parse_mode="HTML",
                    reply_to=message.message_id,
                )

            # Add resume hint
            hint_text = (
                "\n\n💡 <i>Continue this session: "
                "<code>/codex:resume your next prompt</code></i>"
            )
            send_message_sync(
                chat_id=message.chat_id,
                text=hint_text,
                parse_mode="HTML",
            )

        except subprocess.TimeoutExpired:
            error_text = (
                f"<b>⏱️ Timeout</b>\n\n"
                f"Codex execution exceeded {self._timeout}s timeout."
            )
            edit_message_sync(
                chat_id=message.chat_id,
                message_id=status_msg_id,
                text=error_text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Codex execution failed: {e}", exc_info=True)
            error_text = f"<b>❌ Error</b>\n\n<code>{self._escape_html(str(e))}</code>"
            edit_message_sync(
                chat_id=message.chat_id,
                message_id=status_msg_id,
                text=error_text,
                parse_mode="HTML",
            )

    def _parse_flags(self, prompt: str) -> dict:
        """Parse inline flags from prompt.

        Flags:
        --model gpt-5|gpt-5-codex
        --effort low|medium|high
        --sandbox read-only|workspace-write|danger-full-access
        -C /path/to/dir

        Returns dict with: model, effort, sandbox, cwd, prompt
        """
        model = self._default_model
        effort = self._default_reasoning
        sandbox = self._default_sandbox
        cwd = str(Path(self._work_dir).expanduser())

        # Extract flags using regex
        remaining = prompt

        # --model
        match = re.search(r"--model\s+(gpt-5-codex|gpt-5)", remaining)
        if match:
            model = match.group(1)
            remaining = remaining.replace(match.group(0), "")

        # --effort
        match = re.search(r"--effort\s+(low|medium|high)", remaining)
        if match:
            effort = match.group(1)
            remaining = remaining.replace(match.group(0), "")

        # --sandbox
        match = re.search(
            r"--sandbox\s+(read-only|workspace-write|danger-full-access)", remaining
        )
        if match:
            sandbox = match.group(1)
            remaining = remaining.replace(match.group(0), "")

        # -C /path
        match = re.search(r"-C\s+(\S+)", remaining)
        if match:
            cwd = match.group(1)
            remaining = remaining.replace(match.group(0), "")

        # Clean up remaining prompt
        clean_prompt = " ".join(remaining.split())

        return {
            "model": model,
            "effort": effort,
            "sandbox": sandbox,
            "cwd": cwd,
            "prompt": clean_prompt,
        }

    def _run_subprocess(self, cmd: str, cwd: str, timeout: int) -> str:
        """Run subprocess and return output."""
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            error = result.stderr or result.stdout or "Unknown error"
            raise RuntimeError(f"Codex failed (exit {result.returncode}): {error}")

        return result.stdout

    def _format_output(self, output: str) -> str:
        """Format codex output for Telegram."""
        if not output.strip():
            return "<i>No output</i>"

        # Escape HTML
        escaped = self._escape_html(output)

        # Wrap in code block if it looks like code
        if any(marker in output for marker in ["```", "def ", "class ", "import "]):
            return f"<pre>{escaped}</pre>"

        return escaped

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    async def on_deactivate(self) -> None:
        """Deactivate plugin."""
        logger.info("Deactivating Codex plugin...")

    async def on_unload(self) -> None:
        """Unload plugin."""
        logger.info("Unloading Codex plugin...")
