"""
Claude Code Plugin - Main plugin class.

This plugin provides Claude Code CLI integration for AI-assisted development.
It handles:
- Command processing (/claude, /claude:new, etc.)
- Session management
- Message routing in Claude lock mode
- Inline keyboard callbacks
"""

import logging
from pathlib import Path
from typing import List, Optional, Type

from telegram.ext import CommandHandler

from src.plugins.base import BasePlugin, PluginMetadata, PluginCapabilities

logger = logging.getLogger(__name__)


class ClaudeCodePlugin(BasePlugin):
    """
    Claude Code integration plugin.

    Provides AI-assisted development via the Claude Code CLI.
    Features:
    - Execute prompts with /claude command
    - Session management (new, reset, switch)
    - Lock mode for continuous conversation
    - Multi-model support (haiku, sonnet, opus)
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="claude-code",
            version="1.0.0",
            description="Claude Code integration for AI-assisted development",
            author="Telegram Agent",
            requires=[],  # ANTHROPIC_API_KEY optional - uses subscription
            dependencies=[],
            priority=50,
            enabled_by_default=True,
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            services=["claude", "claude_subprocess"],
            commands=[
                "/claude",
                "/claude:new",
                "/claude:reset",
                "/claude:lock",
                "/claude:unlock",
                "/claude:sessions",
                "/claude:status",
            ],
            callbacks=["claude:*"],
            api_routes=False,
            message_handler=True,
        )

    async def on_load(self, container) -> bool:
        """Load plugin and register services."""
        logger.info("Loading Claude Code plugin...")

        # Get configuration
        work_dir = self.get_config_value("work_dir", "~/Research/vault")
        default_model = self.get_config_value("default_model", "opus")

        # Store config for later use
        self._work_dir = work_dir
        self._default_model = default_model

        # Register Claude service
        # Note: For now, we use the existing service from src/services
        # In a full extraction, we would move the service code here
        try:
            from src.services.claude_code_service import ClaudeCodeService

            def create_claude_service(c):
                return ClaudeCodeService()

            container.register("claude", create_claude_service)
            logger.info("Registered Claude service")
        except ImportError as e:
            logger.error(f"Failed to import Claude service: {e}")
            return False

        return True

    async def on_activate(self, app) -> bool:
        """Activate plugin - initialize caches."""
        logger.info("Activating Claude Code plugin...")

        # Initialize admin cache
        try:
            from src.services.claude_code_service import init_admin_cache

            await init_admin_cache()
            logger.info("Initialized Claude admin cache")
        except Exception as e:
            logger.warning(f"Failed to initialize admin cache: {e}")

        return True

    def get_command_handlers(self) -> List:
        """Return command handlers for this plugin."""
        # Import handlers from the existing handlers module
        # In a full extraction, these would be in handlers/commands.py
        from src.bot.handlers import claude_command

        return [
            CommandHandler("claude", claude_command),
        ]

    def get_callback_prefix(self) -> str:
        """Return callback prefix for this plugin."""
        return "claude"

    async def handle_callback(self, query, action: str, params: List[str], context) -> bool:
        """
        Handle Claude-related callbacks.

        Returns False to let the main callback handler process claude callbacks.
        This avoids duplicate processing (plugin + main handler both calling handle_claude_callback).
        """
        return False

    def get_message_processor(self):
        """
        Return message processor for Claude lock mode.

        When Claude mode is locked, this processor handles incoming messages.
        """

        async def process_claude_messages(combined) -> bool:
            """Process messages in Claude lock mode."""
            # Check if Claude mode is active for this chat
            try:
                from src.bot.handlers import _claude_mode_cache
                from src.services.claude_code_service import is_claude_code_admin

                claude_mode = _claude_mode_cache.get(combined.chat_id, False)
                if not claude_mode:
                    return False

                # Verify admin access
                is_admin = await is_claude_code_admin(combined.chat_id)
                if not is_admin:
                    return False

                # Message should be processed by Claude
                # But let the existing combined_processor handle it
                # since it has special logic for collecting voice/images
                return False

            except Exception as e:
                logger.error(f"Claude message processor error: {e}")
                return False

        return process_claude_messages

    def get_database_models(self) -> List[Type]:
        """Return database models for this plugin."""
        # Use existing model from src/models
        # In a full extraction, we would move this to models/session.py
        try:
            from src.models.claude_session import ClaudeSession

            return [ClaudeSession]
        except ImportError:
            return []

    async def on_deactivate(self) -> None:
        """Deactivate plugin."""
        logger.info("Deactivating Claude Code plugin...")

    async def on_unload(self) -> None:
        """Unload plugin."""
        logger.info("Unloading Claude Code plugin...")
