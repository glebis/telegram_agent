import logging
import os
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .callback_handlers import handle_callback_query
from .handlers import (
    analyze_command,
    claude_command,
    coach_command,
    coco_command,
    collect_command,
    creative_command,
    formal_command,
    gallery_command,
    help_command,
    menu_command,
    meta_command,
    mode_command,
    note_command,
    quick_command,
    settings_command,
    start_command,
    tags_command,
)
from ..services.message_buffer import get_message_buffer
from .combined_processor import process_combined_message

logger = logging.getLogger(__name__)


async def toggle_collect_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Toggle collect mode on/off."""
    from ..services.collect_service import get_collect_service
    from .handlers import _collect_start, _collect_stop

    chat = update.effective_chat
    if not chat or not update.message:
        return

    collect_service = get_collect_service()
    is_collecting = await collect_service.is_collecting(chat.id)

    if is_collecting:
        await _collect_stop(update, context)
    else:
        await _collect_start(update, context)


async def route_keyboard_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE, action: str
) -> None:
    """Route keyboard button action to appropriate command handler."""
    from .handlers import (
        _claude_new,
        _claude_sessions,
        _collect_go,
        _collect_stop,
        _collect_clear,
        _collect_exit,
    )

    # Map actions to command handlers
    if action == "/claude":
        await claude_command(update, context)
    elif action == "/claude:new":
        await _claude_new(update, context)
    elif action == "/claude:collect":
        await toggle_collect_mode(update, context)
    elif action == "/claude:sessions":
        await _claude_sessions(update, context)
    elif action == "/collect:go":
        await _collect_go(update, context)
    elif action == "/collect:stop":
        await _collect_stop(update, context)
    elif action == "/collect:clear":
        await _collect_clear(update, context)
    elif action == "/collect:exit":
        await _collect_exit(update, context)
    elif action == "/settings":
        await settings_command(update, context)
    elif action == "/menu":
        await menu_command(update, context)
    elif action == "/mode":
        await mode_command(update, context)
    elif action == "/help":
        await help_command(update, context)
    elif action == "/gallery":
        await gallery_command(update, context)
    elif action == "/start":
        await start_command(update, context)
    else:
        logger.warning(f"Unknown keyboard action: {action}")
        if update.message:
            await update.message.reply_text(f"Unknown action: {action}")


# Buffered message handlers - add to buffer instead of processing immediately
async def buffered_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route message through buffer for combining."""
    msg = update.message

    # Check if this is a keyboard button press
    if msg and msg.text:
        from ..services.keyboard_service import get_keyboard_service

        keyboard_service = get_keyboard_service()
        action = keyboard_service.get_action_for_button_text(msg.text)

        if action:
            # Route to command handler
            logger.info(f"Keyboard button pressed: {msg.text} -> {action}")
            await route_keyboard_action(update, context, action)
            return

    buffer = get_message_buffer()

    # Log incoming message details
    if msg:
        # Use getattr for forward_origin as it may not exist on all Message objects
        has_forward = getattr(msg, 'forward_origin', None) is not None
        msg_type = "text" if msg.text else "photo" if msg.photo else "document" if msg.document else "voice" if msg.voice else "video" if msg.video else "poll" if msg.poll else "other"
        logger.info(f"Incoming message: id={msg.message_id}, type={msg_type}, has_text={bool(msg.text)}, has_doc={bool(msg.document)}, has_forward={has_forward}")

    # Check if collect mode is active - bypass buffer and add directly
    from ..services.collect_service import get_collect_service

    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None

    if chat_id:
        collect_service = get_collect_service()
        if await collect_service.is_collecting(chat_id):
            logger.info(f"Collect mode active for {chat_id}, bypassing buffer")
            # Create single-message CombinedMessage and process immediately
            buffered_msg = buffer._create_buffered_message(update, context, msg)
            if buffered_msg:
                from ..services.message_buffer import CombinedMessage
                combined = CombinedMessage(
                    chat_id=chat_id,
                    user_id=user_id,
                    messages=[buffered_msg],
                    combined_text=buffered_msg.text or buffered_msg.caption or "",
                    images=[buffered_msg] if buffered_msg.message_type == "photo" else [],
                    voices=[buffered_msg] if buffered_msg.message_type == "voice" else [],
                    videos=[buffered_msg] if buffered_msg.message_type == "video" else [],
                    documents=[buffered_msg] if buffered_msg.message_type == "document" else [],
                    contacts=[buffered_msg] if buffered_msg.message_type == "contact" else [],
                    polls=[buffered_msg] if buffered_msg.message_type == "poll" else [],
                )
                await process_combined_message(combined)
                return

    # Try to buffer the message
    was_buffered = await buffer.add_message(update, context)

    if not was_buffered:
        # Message wasn't buffered (e.g., command) - should be handled elsewhere
        # This shouldn't normally happen since commands have their own handlers
        logger.info(f"Message not buffered, type: {update.message.text[:20] if update.message and update.message.text else 'non-text'}")


async def setup_message_buffer() -> None:
    """Setup the message buffer with the combined processor callback."""
    buffer = get_message_buffer()
    buffer.set_process_callback(process_combined_message)
    logger.info("Message buffer configured with combined processor")

    # Initialize caches from database to avoid deadlocks during message processing
    from .handlers import init_claude_mode_cache
    from ..services.claude_code_service import init_admin_cache

    await init_claude_mode_cache()
    await init_admin_cache()


class TelegramBot:
    """Telegram bot application wrapper"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("Telegram bot token is required")

        self.application = None
        self._setup_application()

    def _setup_application(self) -> None:
        """Setup the telegram application with handlers"""
        from telegram.ext import JobQueue

        # Configure with longer timeouts and HTTP/1.1 for better compatibility
        # This helps with IPv6/connectivity issues
        self.application = (
            Application.builder()
            .token(self.token)
            .job_queue(JobQueue())  # Enable job queue for scheduled tasks
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .pool_timeout(30.0)
            .connection_pool_size(8)
            .http_version("1.1")  # Use HTTP/1.1 for better compatibility
            .get_updates_connect_timeout(30.0)
            .get_updates_read_timeout(30.0)
            .get_updates_write_timeout(30.0)
            .get_updates_pool_timeout(30.0)
            .get_updates_http_version("1.1")
            .build()
        )

        # Core commands
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(CommandHandler("help", help_command))
        self.application.add_handler(CommandHandler("menu", menu_command))
        self.application.add_handler(CommandHandler("settings", settings_command))
        self.application.add_handler(CommandHandler("mode", mode_command))
        self.application.add_handler(CommandHandler("gallery", gallery_command))
        self.application.add_handler(CommandHandler("note", note_command))

        # Mode shortcuts
        self.application.add_handler(CommandHandler("analyze", analyze_command))
        self.application.add_handler(CommandHandler("coach", coach_command))
        self.application.add_handler(CommandHandler("creative", creative_command))
        self.application.add_handler(CommandHandler("quick", quick_command))
        self.application.add_handler(CommandHandler("formal", formal_command))
        self.application.add_handler(CommandHandler("tags", tags_command))
        self.application.add_handler(CommandHandler("coco", coco_command))

        # Claude Code - unified command with :subcommand syntax
        # Supports: /claude, /claude:new, /claude:reset, /claude:lock, /claude:unlock, /claude:sessions
        self.application.add_handler(CommandHandler("claude", claude_command))

        # Session management - rename, list, info
        from .handlers.claude_commands import session_command
        self.application.add_handler(CommandHandler("session", session_command))

        # Meta - Claude Code in telegram_agent directory
        self.application.add_handler(CommandHandler("meta", meta_command))

        # Collect Mode - batch input accumulation
        # Supports: /collect:start, /collect:go, /collect:stop, /collect:status
        self.application.add_handler(CommandHandler("collect", collect_command))

        # SRS (Spaced Repetition System) - vault idea review
        from .handlers.srs_handlers import register_srs_handlers
        register_srs_handlers(self.application)

        # Trail Review - vault trail review with polls
        from .handlers.trail_handlers import register_trail_handlers
        register_trail_handlers(self.application)

        # Poll System - user state tracking polls
        from .handlers.poll_handlers import register_poll_handlers
        register_poll_handlers(self.application)

        # Add callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(handle_callback_query))

        # Add message handlers - all routed through buffer for combining
        # The buffer will combine messages sent within a short window
        # and then route to the appropriate processor
        self.application.add_handler(
            MessageHandler(filters.CONTACT, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.PHOTO, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.Document.IMAGE, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.Document.ALL, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.VOICE, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.AUDIO, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.VIDEO, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.VIDEO_NOTE, buffered_message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.POLL, buffered_message_handler)
        )
        # Handle forwarded messages explicitly (they may not match other filters)
        self.application.add_handler(
            MessageHandler(filters.FORWARDED, buffered_message_handler)
        )

        logger.info("Telegram bot application configured with message buffering")

    async def process_update(self, update_data: dict) -> bool:
        """Process a webhook update"""
        try:
            # Convert dict to Update object
            update = Update.de_json(update_data, self.application.bot)
            if update:
                # Process the update
                await self.application.process_update(update)
                return True
            else:
                logger.warning("Failed to parse update from webhook data")
                return False

        except Exception as e:
            logger.error(f"Error processing update: {e}")
            return False

    async def set_webhook(
        self, webhook_url: str, secret_token: Optional[str] = None
    ) -> bool:
        """Set the webhook URL for the bot"""
        try:
            await self.application.bot.set_webhook(
                url=webhook_url, secret_token=secret_token, drop_pending_updates=True
            )
            logger.info(f"Webhook set to: {webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            return False

    async def delete_webhook(self) -> bool:
        """Delete the current webhook"""
        try:
            await self.application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted")
            return True
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
            return False

    async def get_webhook_info(self) -> dict:
        """Get current webhook information"""
        try:
            webhook_info = await self.application.bot.get_webhook_info()
            return {
                "url": webhook_info.url,
                "has_custom_certificate": webhook_info.has_custom_certificate,
                "pending_update_count": webhook_info.pending_update_count,
                "last_error_date": webhook_info.last_error_date,
                "last_error_message": webhook_info.last_error_message,
                "max_connections": webhook_info.max_connections,
                "allowed_updates": webhook_info.allowed_updates,
            }
        except Exception as e:
            logger.error(f"Error getting webhook info: {e}")
            return {}

    async def get_bot_info(self) -> dict:
        """Get bot information"""
        try:
            bot = await self.application.bot.get_me()
            return {
                "id": bot.id,
                "username": bot.username,
                "first_name": bot.first_name,
                "can_join_groups": bot.can_join_groups,
                "can_read_all_group_messages": bot.can_read_all_group_messages,
                "supports_inline_queries": bot.supports_inline_queries,
            }
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return {}

    async def send_message(self, chat_id: int, text: str, **kwargs) -> bool:
        """Send a message to a chat"""
        try:
            await self.application.bot.send_message(
                chat_id=chat_id, text=text, **kwargs
            )
            return True
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return False

    async def initialize(self) -> None:
        """Initialize the bot application"""
        try:
            await self.application.initialize()
            logger.info("Bot application initialized")

            # Start job queue for scheduled tasks (required in webhook mode)
            if self.application.job_queue:
                await self.application.job_queue.start()
                logger.info("✅ Job queue started for scheduled polls")
            else:
                logger.warning("⚠️ Job queue not available - scheduled tasks will not run")
        except Exception as e:
            logger.error(f"Error initializing bot: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown the bot application"""
        try:
            # Stop job queue first
            if self.application.job_queue:
                await self.application.job_queue.stop()
                logger.info("Job queue stopped")

            await self.application.shutdown()
            logger.info("Bot application shutdown")
        except Exception as e:
            logger.error(f"Error shutting down bot: {e}")


# Global bot instance
_bot_instance: Optional[TelegramBot] = None


def get_bot() -> TelegramBot:
    """Get the global bot instance"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = TelegramBot()
    return _bot_instance


async def initialize_bot() -> TelegramBot:
    """Initialize and return the bot instance"""
    import os
    import logging

    logger = logging.getLogger(__name__)

    # Log environment variables for debugging
    environment = os.getenv("ENVIRONMENT", "development").lower()
    webhook_base_url = os.getenv("WEBHOOK_BASE_URL")

    logger.info(f"🔍 BOT INIT: Environment detected: '{environment}'")
    logger.info(f"🔍 BOT INIT: WEBHOOK_BASE_URL: '{webhook_base_url}'")

    # Setup message buffer before initializing bot
    await setup_message_buffer()

    bot = get_bot()
    await bot.initialize()

    # Setup trail review scheduler
    from ..services.trail_scheduler import setup_trail_scheduler
    setup_trail_scheduler(bot.application)

    # Setup poll scheduler for user state tracking
    from ..services.poll_scheduler import setup_poll_scheduler
    setup_poll_scheduler(bot.application)

    return bot


async def shutdown_bot() -> None:
    """Shutdown the global bot instance"""
    global _bot_instance
    if _bot_instance:
        await _bot_instance.shutdown()
        _bot_instance = None
