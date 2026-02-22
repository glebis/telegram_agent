"""
Klodkot Plugin - Draft post generator for @klodkot Telegram channel.

Usage:
  /klodkot <link or text>  — Generate a draft post from a link or text

This plugin runs a Claude session that:
1. Reads Channels/klodkot/klodkot.md for channel voice & guidelines
2. Writes a draft post for the given link or text
3. Downloads video with yt-dlp if the post has video
4. Saves the draft to Channels/klodkot/drafts/
"""

import asyncio
import logging
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.plugins.base import BasePlugin, PluginCapabilities, PluginMetadata

logger = logging.getLogger(__name__)


class KlodkotPlugin(BasePlugin):
    """
    Klodkot draft post generator plugin.

    Generates channel posts by running a Claude session with the channel
    guide context and user-provided link/text.
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="klodkot",
            version="1.0.0",
            description="Draft post generator for @klodkot Telegram channel",
            author="Telegram Agent",
            requires=[],
            dependencies=[],
            priority=80,
            enabled_by_default=True,
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            services=[],
            commands=["/klodkot"],
            callbacks=[],
            api_routes=False,
            message_handler=False,
        )

    async def on_load(self, container) -> bool:
        """Load plugin and verify dependencies."""
        logger.info("Loading Klodkot plugin...")

        # Get configuration
        self._work_dir = str(
            Path(self.get_config_value("work_dir", "~/Research/vault")).expanduser()
        )
        self._channel_guide = self.get_config_value(
            "channel_guide", "Channels/klodkot/klodkot.md"
        )
        self._drafts_dir = self.get_config_value(
            "drafts_dir", "Channels/klodkot/drafts"
        )
        self._videos_dir = self.get_config_value(
            "videos_dir", "Channels/klodkot/videos"
        )
        self._timeout = self.get_config_value("query_timeout_seconds", 300)

        # Verify claude binary exists — check common locations since
        # launchd PATH doesn't include ~/.local/bin
        self._claude_bin = shutil.which("claude")
        if not self._claude_bin:
            fallback = Path.home() / ".local" / "bin" / "claude"
            if fallback.exists() and fallback.is_file():
                self._claude_bin = str(fallback)
            else:
                logger.error(
                    "Claude binary not found in PATH or ~/.local/bin/claude"
                )
                return False

        logger.info(f"Claude binary found at: {self._claude_bin}")

        # Check yt-dlp availability (optional — warn but don't fail)
        self._ytdlp_bin = shutil.which("yt-dlp")
        if not self._ytdlp_bin:
            logger.warning("yt-dlp not found — video downloads will be skipped")
        else:
            logger.info(f"yt-dlp found at: {self._ytdlp_bin}")

        # Verify channel guide exists
        guide_path = Path(self._work_dir) / self._channel_guide
        if not guide_path.exists():
            logger.warning(f"Channel guide not found at {guide_path}")

        # Ensure drafts directory exists
        drafts_path = Path(self._work_dir) / self._drafts_dir
        drafts_path.mkdir(parents=True, exist_ok=True)

        # Ensure videos directory exists
        videos_path = Path(self._work_dir) / self._videos_dir
        videos_path.mkdir(parents=True, exist_ok=True)

        return True

    async def on_activate(self, app) -> bool:
        """Activate plugin."""
        logger.info("Activating Klodkot plugin...")
        return True

    def get_command_handlers(self) -> List:
        """Return command handlers for this plugin."""
        return [
            CommandHandler("klodkot", self._handle_klodkot),
        ]

    async def _handle_klodkot(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /klodkot command."""
        user = update.effective_user
        chat = update.effective_chat
        message = update.message

        if not user or not chat or not message:
            return

        # Check admin access (reuse claude_code admin check)
        from src.services.claude_code_service import is_claude_code_admin

        if not await is_claude_code_admin(chat.id):
            await message.reply_text("You don't have permission to use /klodkot.")
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

        # Parse input — everything after /klodkot
        input_text = " ".join(context.args) if context.args else ""

        if not input_text.strip():
            await message.reply_text(
                "<b>📝 klodkot — draft post generator</b>\n\n"
                "<b>Usage:</b>\n"
                "<code>/klodkot &lt;link or text&gt;</code>\n\n"
                "<b>Examples:</b>\n"
                "<code>/klodkot https://example.com/article</code>\n"
                "<code>/klodkot Interesting insight about Claude Code agents</code>\n\n"
                "The bot will read the channel guide, draft a post, "
                "download any video, and save to drafts.",
                parse_mode="HTML",
            )
            return

        await self._generate_draft(update, context, input_text)

    async def _generate_draft(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        input_text: str,
    ) -> None:
        """Generate a draft post using Claude CLI."""
        message = update.message
        if not message:
            return

        from src.bot.handlers import edit_message_sync, send_message_sync

        # Send status message
        status_text = (
            "<b>📝 klodkot</b>\n\n"
            f"<i>{self._escape_html(input_text[:100])}</i>\n\n"
            "⏳ Generating draft..."
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

        # Build date prefix for draft filename
        date_prefix = datetime.now().strftime("%Y%m%d")

        # Build the Claude prompt
        prompt = self._build_prompt(input_text, date_prefix)

        # Build Claude CLI command
        cmd = (
            f"{shlex.quote(self._claude_bin)} "
            f"--print "
            f"--dangerously-skip-permissions "
            f"-p {shlex.quote(prompt)}"
        )

        logger.info(f"Executing klodkot draft generation: {cmd[:200]}...")

        try:
            output = await asyncio.to_thread(
                self._run_subprocess, cmd, self._work_dir, self._timeout
            )

            # Format the response
            formatted = self._format_output(output, input_text)

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

            # Check if draft was saved — try to find it
            drafts_path = Path(self._work_dir) / self._drafts_dir
            new_drafts = sorted(
                drafts_path.glob(f"{date_prefix}*.md"), key=lambda p: p.stat().st_mtime
            )
            if new_drafts:
                latest_draft = new_drafts[-1]
                send_message_sync(
                    chat_id=message.chat_id,
                    text=f"📄 Draft saved: <code>{latest_draft.name}</code>",
                    parse_mode="HTML",
                )

            # Check if video was downloaded
            videos_path = Path(self._work_dir) / self._videos_dir
            new_videos = sorted(
                videos_path.glob(f"{date_prefix}*"),
                key=lambda p: p.stat().st_mtime,
            )
            if new_videos:
                latest_video = new_videos[-1]
                send_message_sync(
                    chat_id=message.chat_id,
                    text=f"🎬 Video saved: <code>{latest_video.name}</code>",
                    parse_mode="HTML",
                )

        except subprocess.TimeoutExpired:
            error_text = (
                f"<b>⏱️ Timeout</b>\n\n"
                f"Draft generation exceeded {self._timeout}s timeout."
            )
            edit_message_sync(
                chat_id=message.chat_id,
                message_id=status_msg_id,
                text=error_text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Klodkot draft generation failed: {e}", exc_info=True)
            error_text = (
                f"<b>❌ Error</b>\n\n<code>{self._escape_html(str(e)[:500])}</code>"
            )
            edit_message_sync(
                chat_id=message.chat_id,
                message_id=status_msg_id,
                text=error_text,
                parse_mode="HTML",
            )

    def _build_prompt(self, input_text: str, date_prefix: str) -> str:
        """Build the Claude prompt for draft generation."""
        drafts_dir = self._drafts_dir
        videos_dir = self._videos_dir
        channel_guide = self._channel_guide

        prompt = f"""Read {channel_guide} for channel voice and guidelines.

Write a draft post for this link or text:
{input_text}

Instructions:
- Follow the channel voice and style from the guide
- Write the post in Russian (the channel language)
- If the source has video content, download it using yt-dlp and save to {videos_dir}/ with prefix {date_prefix}
- Save the draft as a markdown file to {drafts_dir}/ with filename format: {date_prefix}-<short-slug>.md
- The draft file should contain the post text ready to publish
- Include the source link at the end of the post using the channel's link format"""

        return prompt

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
            raise RuntimeError(
                f"Claude failed (exit {result.returncode}): {error[:500]}"
            )

        return result.stdout

    def _format_output(self, output: str, input_text: str) -> str:
        """Format Claude output for Telegram."""
        if not output.strip():
            return "<b>📝 klodkot</b>\n\n<i>No output from Claude.</i>"

        escaped = self._escape_html(output.strip())

        header = (
            f"<b>📝 klodkot</b>\n"
            f"<i>{self._escape_html(input_text[:80])}</i>\n\n"
        )

        return header + escaped

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    async def on_deactivate(self) -> None:
        """Deactivate plugin."""
        logger.info("Deactivating Klodkot plugin...")

    async def on_unload(self) -> None:
        """Unload plugin."""
        logger.info("Unloading Klodkot plugin...")
