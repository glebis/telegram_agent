"""
Klodkot Plugin - Draft post generator for @klodkot Telegram channel.

Usage:
  /klodkot <link or text>  — Generate a draft post from a link or text

Routes through the standard Claude pipeline with message buffering,
so follow-up messages (e.g. a URL sent after the command) are combined.
"""

import logging
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

    Generates channel posts by buffering the /klodkot command through
    the standard Claude pipeline, which provides message combining,
    streaming updates, and session management.
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="klodkot",
            version="2.0.0",
            description="Draft post generator for @klodkot Telegram channel",
            author="Verity",
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

    def _build_system_prompt(self) -> str:
        """Build the klodkot system prompt for Claude."""
        date_prefix = datetime.now().strftime("%Y%m%d")
        return (
            f"Read {self._channel_guide} for channel voice and guidelines.\n\n"
            f"Instructions:\n"
            f"- Follow the channel voice and style from the guide\n"
            f"- Write the post in Russian (the channel language)\n"
            f"- If the source has video content, download it using yt-dlp "
            f"and save to {self._videos_dir}/ with prefix {date_prefix}\n"
            f"- Save the draft as a markdown file to {self._drafts_dir}/ "
            f"with filename format: {date_prefix}-<short-slug>.md\n"
            f"- The draft file should contain the post text ready to publish\n"
            f"- Include the source link at the end of the post "
            f"using the channel's link format"
        )

    async def _handle_klodkot(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /klodkot command by buffering through Claude pipeline."""
        user = update.effective_user
        chat = update.effective_chat
        message = update.message

        if not user or not chat or not message:
            return

        # Check admin access
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
                "<code>/klodkot Interesting insight about Claude Code</code>"
                "\n\n"
                "The bot will read the channel guide, draft a post, "
                "download any video, and save to drafts.\n"
                "Follow-up messages (links, text) sent within 2.5s "
                "will be combined with the command.",
                parse_mode="HTML",
            )
            return

        # Use generic plugin_claude_config pattern — any plugin can do this
        # to route its command through the Claude pipeline with buffering.
        # See docs/ARCHITECTURE.md for the plugin_claude_config convention.
        context.user_data["plugin_claude_config"] = {
            "system_prompt": self._build_system_prompt(),
            "cwd": self._work_dir,
        }

        # Buffer through the standard Claude pipeline
        from src.services.message_buffer import get_message_buffer

        buffer = get_message_buffer()
        await buffer.add_claude_command(update, context, input_text)
        logger.info(
            f"Buffered /klodkot command for chat {chat.id}, "
            f"waiting for potential follow-up messages"
        )

    async def on_deactivate(self) -> None:
        """Deactivate plugin."""
        logger.info("Deactivating Klodkot plugin...")

    async def on_unload(self) -> None:
        """Unload plugin."""
        logger.info("Unloading Klodkot plugin...")
