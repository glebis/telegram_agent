import logging
import os
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .callback_handlers import handle_callback_query
from .handlers import (
    analyze_command,
    coach_command,
    coco_command,
    creative_command,
    formal_command,
    gallery_command,
    help_command,
    mode_command,
    quick_command,
    start_command,
    tags_command,
)
from .message_handlers import handle_image_message, handle_text_message, handle_voice_message

logger = logging.getLogger(__name__)


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
        # Create application
        self.application = Application.builder().token(self.token).build()

        # Add command handlers
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(CommandHandler("help", help_command))
        self.application.add_handler(CommandHandler("mode", mode_command))
        self.application.add_handler(
            CommandHandler("modes", mode_command)
        )  # Alias for mode command
        self.application.add_handler(CommandHandler("gallery", gallery_command))

        # Add command aliases
        self.application.add_handler(CommandHandler("analyze", analyze_command))
        self.application.add_handler(CommandHandler("coach", coach_command))
        self.application.add_handler(CommandHandler("creative", creative_command))
        self.application.add_handler(CommandHandler("quick", quick_command))
        self.application.add_handler(CommandHandler("formal", formal_command))
        self.application.add_handler(CommandHandler("tags", tags_command))
        self.application.add_handler(CommandHandler("coco", coco_command))

        # Add callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(handle_callback_query))

        # Add message handlers
        self.application.add_handler(
            MessageHandler(filters.PHOTO, handle_image_message)
        )
        self.application.add_handler(
            MessageHandler(filters.Document.IMAGE, handle_image_message)
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
        )
        self.application.add_handler(
            MessageHandler(filters.VOICE, handle_voice_message)
        )

        logger.info("Telegram bot application configured")

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
        except Exception as e:
            logger.error(f"Error initializing bot: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown the bot application"""
        try:
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

    bot = get_bot()
    await bot.initialize()
    return bot


async def shutdown_bot() -> None:
    """Shutdown the global bot instance"""
    global _bot_instance
    if _bot_instance:
        await _bot_instance.shutdown()
        _bot_instance = None
