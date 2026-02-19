"""
Combined message processor — routing logic.

CombinedMessageProcessor is the main class that inherits from all mixin
classes and implements the process() routing method.

Extracted from combined_processor.py as part of #152.
"""

import asyncio
import logging
import time
from typing import Optional

from ...core.config import get_config_value
from ...core.error_messages import sanitize_error
from ...services.message_buffer import CombinedMessage
from ...services.message_persistence_service import persist_message
from ...services.reply_context import (
    MessageType,
    ReplyContext,
    get_reply_context_service,
)
from ...utils.task_tracker import create_tracked_task
from .collect import CollectProcessorMixin
from .content import ContentProcessorMixin
from .media import MediaProcessorMixin
from .text import TextProcessorMixin

logger = logging.getLogger(__name__)


class CombinedMessageProcessor(
    MediaProcessorMixin,
    ContentProcessorMixin,
    TextProcessorMixin,
    CollectProcessorMixin,
):
    """
    Processes combined messages after buffering.

    Routes to appropriate handlers based on:
    - Message content (text, image, voice, etc.)
    - Reply context (if replying to a previous message)
    - Current mode (Claude locked, normal, etc.)
    """

    def __init__(self):
        self.reply_service = get_reply_context_service()

    async def process(self, combined: CombinedMessage) -> None:
        """
        Process a combined message.

        Routing logic:
        0. Check for /claude command (takes priority)
        1. Check for reply context
        2. Check current mode (Claude locked?)
        3. Route based on content type:
           - Has images → image handler (with text as prompt)
           - Has voice → voice handler (with text as additional context)
           - Has contacts → contact handler
           - Text only → text handler
        """
        logger.info(
            f"Processing combined message: chat={combined.chat_id}, "
            f"user={combined.user_id}, images={len(combined.images)}, "
            f"voices={len(combined.voices)}, videos={len(combined.videos)}, "
            f"polls={len(combined.polls)}, "
            f"text_len={len(combined.combined_text)}, "
            f"reply_to={combined.reply_to_message_id}"
        )

        # Fire-and-forget: persist each incoming message to the database
        for buf_msg in combined.messages:
            create_tracked_task(
                persist_message(
                    telegram_chat_id=combined.chat_id,
                    from_user_id=combined.user_id,
                    message_id=buf_msg.message_id,
                    text=buf_msg.text or buf_msg.caption,
                    message_type=buf_msg.message_type,
                    timestamp=buf_msg.timestamp,
                ),
                name=f"persist_msg_{buf_msg.message_id}",
            )

        # Check plugin message processors first (highest priority)
        try:
            from ...plugins import get_plugin_manager

            plugin_manager = get_plugin_manager()
            if await plugin_manager.route_message(combined):
                logger.debug("Message handled by plugin")
                return
        except Exception as e:
            logger.error(f"Plugin routing error: {e}", exc_info=True)

        # Check for /claude, /meta, or /dev commands first - these take priority
        if combined.has_command():
            await self._process_command(combined)
            return

        # Check for collect mode
        from ...services.collect_service import get_collect_service

        collect_service = get_collect_service()
        is_collecting = await collect_service.is_collecting(combined.chat_id)

        # Check if Claude mode is active (early check for auto-collect)
        from ...services.claude_code_service import is_claude_code_admin
        from ..handlers import _claude_mode_cache

        claude_mode_active = _claude_mode_cache.get(combined.chat_id, False)
        is_claude_locked = False
        if claude_mode_active:
            try:
                is_claude_locked = await is_claude_code_admin(combined.chat_id)
            except Exception as e:
                logger.error(f"Error checking Claude admin: {e}")

        # When Claude lock mode is active, handle media messages based on context:
        # - Voice messages → forward directly to Claude (no collect mode)
        # - Other media (images, videos without voice) behavior controlled by config
        if is_claude_locked and not is_collecting:
            # Check if this message contains a trigger keyword
            has_trigger = collect_service.check_trigger_keywords(combined.combined_text)

            has_voice = combined.has_voice()
            has_other_media = combined.has_videos() or combined.has_images()

            # Check config for auto-collect behavior
            auto_collect_enabled = get_config_value(
                "bot.auto_collect_media_in_claude_mode", False
            )
            show_confirmation = get_config_value(
                "bot.show_auto_collect_confirmation", True
            )

            # For media WITHOUT voice and WITHOUT text trigger, optionally collect instead of immediate send
            if (
                has_other_media
                and not has_voice
                and not has_trigger
                and auto_collect_enabled
            ):
                logger.info(
                    f"Claude lock mode: auto-starting collect for non-voice media in chat {combined.chat_id}"
                )
                # Auto-start collect session for Claude lock mode
                await collect_service.start_session(combined.chat_id, combined.user_id)

                # Send confirmation message if configured
                if show_confirmation:
                    from ...utils.telegram_api import send_message_sync

                    confirmation_msg = get_config_value(
                        "messages.collect_mode_on",
                        '📥 <b>Collect mode ON</b>\n\nSend files, voice, images, text — I\'ll collect them silently.\n\nWhen ready, tap <b>▶️ Go</b> or say <i>"now respond"</i>',
                    )
                    try:
                        send_message_sync(
                            chat_id=combined.chat_id,
                            text=confirmation_msg,
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send auto-collect confirmation: {e}")

                # Add to collect queue (will transcribe voice/video)
                try:
                    await self._add_to_collect_queue(combined)
                except Exception as e:
                    logger.error(
                        f"Error adding to collect queue in Claude lock mode: {e}",
                        exc_info=True,
                    )
                    # Still return to avoid further processing
                return

            # If trigger keyword detected, check if there are collected items to process
            if has_trigger:
                session = await collect_service.get_session(combined.chat_id)
                if session and session.item_count > 0:
                    logger.info(
                        f"Claude lock mode: trigger detected with {session.item_count} collected items"
                    )
                    await self._process_collect_trigger(combined)
                    return

        if is_collecting:
            # Check for trigger keywords that should process the collected items
            if collect_service.check_trigger_keywords(combined.combined_text):
                logger.info(
                    f"Collect trigger keyword detected in chat {combined.chat_id}"
                )
                # Process collected items - trigger /collect:go
                await self._process_collect_trigger(combined)
                return

            # Add items to collect queue and react with 👀
            await self._add_to_collect_queue(combined)
            return

        # Get reply context if this is a reply
        reply_context: Optional[ReplyContext] = None
        if combined.reply_to_message_id:
            reply_context = self.reply_service.get_context(
                combined.chat_id,
                combined.reply_to_message_id,
            )
            if reply_context:
                logger.info(
                    f"Found reply context: type={reply_context.message_type.value}, "
                    f"session={reply_context.session_id}"
                )
            elif combined.reply_to_message_text:
                # Cache miss - create context from extracted reply content
                from ...services.claude_code_service import get_claude_code_service

                # Determine message type: if from bot, it's a Claude response
                msg_type = (
                    MessageType.CLAUDE_RESPONSE
                    if combined.reply_to_message_from_bot
                    else MessageType.USER_TEXT
                )

                logger.info(
                    f"Cache miss for reply {combined.reply_to_message_id}, "
                    f"creating context from extracted content (type={combined.reply_to_message_type}, "
                    f"from_bot={combined.reply_to_message_from_bot}, message_type={msg_type.value})"
                )

                # If it's a Claude response, try to look up session_id from database
                # with timeout protection to prevent hanging voice processing
                session_id = None
                if msg_type == MessageType.CLAUDE_RESPONSE:
                    try:
                        logger.info(
                            f"Cache miss for Claude response - attempting DB lookup for chat {combined.chat_id}"
                        )
                        lookup_start = time.perf_counter()

                        async def lookup_session():
                            service = get_claude_code_service()
                            # Try timestamp correlation first for precise session matching
                            sid = None
                            if combined.reply_to_message_date:
                                sid = await service.find_session_by_timestamp(
                                    combined.chat_id,
                                    combined.reply_to_message_date,
                                )
                                if sid:
                                    logger.info(
                                        f"Restored session_id via timestamp correlation: {sid[:8]}..."
                                    )
                            # Fall back to most recent active session
                            if not sid:
                                sid = await service.get_active_session(combined.chat_id)
                                if sid:
                                    logger.info(
                                        f"Restored session_id from active session fallback: {sid[:8]}..."
                                    )
                            if not sid:
                                logger.warning(
                                    f"No active session found in database for chat {combined.chat_id}"
                                )
                            return sid

                        # Use asyncio.wait instead of wait_for to avoid cancellation deadlock
                        # with aiosqlite (wait_for can hang when cancelling DB operations)
                        lookup_task = asyncio.create_task(lookup_session())
                        done, pending = await asyncio.wait({lookup_task}, timeout=10.0)

                        if lookup_task in done:
                            # Lookup completed within timeout
                            session_id = lookup_task.result()
                            lookup_duration = time.perf_counter() - lookup_start
                            logger.debug(
                                f"DB lookup completed in {lookup_duration:.2f}s, "
                                f"session_id={'found' if session_id else 'none'}"
                            )
                            if lookup_duration > 2.0:
                                logger.warning(
                                    f"⚠️ Slow reply context DB lookup: {lookup_duration:.2f}s for chat {combined.chat_id}"
                                )
                        else:
                            # Timeout - don't cancel, just proceed without session_id
                            logger.error(
                                f"⏱️ Reply context DB lookup timed out after 10s for chat {combined.chat_id}. "
                                f"Task continues in background. Processing message without session context."
                            )
                            session_id = None

                    except asyncio.CancelledError:
                        # Parent task cancelled - re-raise to propagate
                        logger.warning(
                            f"⏸️ Session lookup cancelled for chat {combined.chat_id}"
                        )
                        raise
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to look up session_id for cache miss: {e}",
                            exc_info=True,
                        )

                reply_context = ReplyContext(
                    message_id=combined.reply_to_message_id,
                    chat_id=combined.chat_id,
                    user_id=combined.user_id,
                    message_type=msg_type,
                    original_text=combined.reply_to_message_text,
                    session_id=session_id,  # Include restored session_id
                )
                # Track it for future replies
                self.reply_service._cache[
                    self.reply_service._make_key(
                        combined.chat_id, combined.reply_to_message_id
                    )
                ] = reply_context
                logger.debug(
                    f"Created and cached reply context for message {combined.reply_to_message_id}"
                )

        # Handle todo list numeric replies
        if reply_context and reply_context.message_type == MessageType.TODO_LIST:
            # Check if reply is a number
            text = combined.combined_text.strip()
            if text.isdigit():
                logger.info(f"Processing todo list numeric reply: {text}")
                logger.debug(f"Reply context metadata: {reply_context.metadata}")

                try:
                    number = int(text)
                    task_ids = reply_context.metadata.get("task_ids", [])
                    logger.info(f"Task IDs from metadata: {task_ids}, number: {number}")

                    # Check if number is in valid range
                    if 1 <= number <= len(task_ids):
                        task_id = task_ids[number - 1]
                        logger.info(f"Selected task_id: {task_id}")

                        # Send response asynchronously to avoid blocking
                        response_text = (
                            f"📋 Task #{number}: `{task_id}`\n\n"
                            f"Run `/todo show {task_id}` for full details"
                        )
                        logger.info(
                            f"Sending reply asynchronously: {response_text[:50]}..."
                        )

                        # Use asyncio.create_task to avoid blocking the webhook response
                        async def send_reply():
                            try:
                                await combined.primary_context.bot.send_message(
                                    chat_id=combined.chat_id,
                                    text=response_text,
                                    parse_mode="Markdown",
                                    reply_to_message_id=combined.primary_message.message_id,
                                )
                                logger.info(f"Sent task info for #{number}: {task_id}")
                            except Exception as e:
                                logger.error(
                                    f"Failed to send task info: {e}", exc_info=True
                                )

                        asyncio.create_task(send_reply())
                        return  # Message handled
                    else:
                        # Send error message asynchronously
                        async def send_error():
                            try:
                                await combined.primary_context.bot.send_message(
                                    chat_id=combined.chat_id,
                                    text=f"❌ Invalid number. Please choose 1-{len(task_ids)}",
                                    reply_to_message_id=combined.primary_message.message_id,
                                )
                            except Exception as e:
                                logger.error(f"Failed to send error message: {e}")

                        asyncio.create_task(send_error())
                        return
                except Exception as e:
                    logger.error(
                        f"Error handling todo numeric reply: {e}", exc_info=True
                    )

                    # Send error message asynchronously
                    async def send_exception_error():
                        try:
                            await combined.primary_context.bot.send_message(
                                chat_id=combined.chat_id,
                                text="❌ Error showing task details",
                                reply_to_message_id=combined.primary_message.message_id,
                            )
                        except Exception as send_error:
                            logger.error(f"Failed to send error message: {send_error}")

                    asyncio.create_task(send_exception_error())
                    return

        # Handle life weeks reflection replies
        if (
            reply_context
            and reply_context.message_type == MessageType.LIFE_WEEKS_REFLECTION
        ):
            from ...services.life_weeks_reply_handler import (
                get_obsidian_uri,
                handle_life_weeks_reply,
            )

            logger.info("Processing life weeks reflection reply")

            try:
                saved_path = await handle_life_weeks_reply(
                    user_id=combined.user_id,
                    reply_text=combined.combined_text,
                    context=reply_context,
                )

                # Send confirmation with clickable Obsidian link
                confirmation = (
                    f"✍️ <b>Reflection saved!</b>\n\n"
                    f"📝 {saved_path.name}\n"
                    f'🔗 <a href="{get_obsidian_uri(saved_path)}">Open in Obsidian</a>'
                )

                await combined.primary_message.reply_text(
                    confirmation, parse_mode="HTML"
                )
                logger.info(f"Life weeks reflection saved to {saved_path}")
                return  # Message handled

            except Exception as e:
                logger.error(
                    f"Failed to save life weeks reflection: {e}", exc_info=True
                )
                await combined.primary_message.reply_text(
                    f"❌ {sanitize_error(e, context='saving reflection')}",
                    parse_mode="HTML",
                )
                return

        # Check if Claude mode is active
        # Use cache-only check to avoid database deadlocks during message processing
        from ...services.claude_code_service import is_claude_code_admin
        from ..handlers import _claude_mode_cache

        try:
            # Fast path: check cache only (no database call)
            claude_mode_active = _claude_mode_cache.get(combined.chat_id, False)

            if claude_mode_active:
                # Only check admin if Claude mode is enabled
                is_admin = await is_claude_code_admin(combined.chat_id)
                is_claude_mode = is_admin
            else:
                is_claude_mode = False
        except Exception as e:
            logger.error(f"Error checking Claude mode: {e}", exc_info=True)
            is_claude_mode = False

        logger.info(f"Claude mode check result: is_claude_mode={is_claude_mode}")

        # Route based on content
        try:
            if combined.has_images():
                logger.info("Routing to: _process_with_images")
                await self._process_with_images(combined, reply_context, is_claude_mode)
            elif combined.has_voice():
                logger.info("Routing to: _process_with_voice")
                await self._process_with_voice(combined, reply_context, is_claude_mode)
            elif combined.has_videos():
                logger.info("Routing to: _process_with_videos")
                await self._process_with_videos(combined, reply_context, is_claude_mode)
            elif combined.has_polls():
                logger.info("Routing to: _process_with_polls")
                await self._process_with_polls(combined, reply_context, is_claude_mode)
            elif combined.contacts:
                logger.info("Routing to: _process_contacts")
                await self._process_contacts(combined)
            elif combined.has_documents():
                logger.info("Routing to: _process_documents")
                await self._process_documents(combined, reply_context, is_claude_mode)
            elif combined.combined_text:
                logger.info("Routing to: _process_text")
                await self._process_text(combined, reply_context, is_claude_mode)
            else:
                logger.warning("Combined message has no processable content")

            # Notify user if messages were dropped due to buffer overflow
            if combined.overflow_count > 0:
                try:
                    n = combined.overflow_count
                    await combined.primary_message.reply_text(
                        f"Note: {n} message(s) were dropped because too many were sent at once."
                    )
                except Exception as e:
                    logger.error(f"Failed to send overflow notification: {e}")

            logger.debug(
                f"✅ Completed process() for chat {combined.chat_id}, "
                f"message {combined.primary_message.message_id}"
            )
        except asyncio.CancelledError:
            logger.warning(
                f"⏸️ Message processing cancelled for chat {combined.chat_id}, "
                f"message {combined.primary_message.message_id}"
            )
            raise  # Re-raise to preserve cancellation
        except Exception as e:
            logger.error(
                f"❌ Error processing combined message for chat {combined.chat_id}: {e}",
                exc_info=True,
            )
            # Try to notify user of error
            try:
                await combined.primary_message.reply_text(
                    "Error processing your message. Please try again."
                )
            except Exception:
                pass


# Global processor instance
_processor: Optional[CombinedMessageProcessor] = None


def get_combined_processor() -> CombinedMessageProcessor:
    """Get the global combined message processor."""
    global _processor
    if _processor is None:
        _processor = CombinedMessageProcessor()
    return _processor


async def process_combined_message(combined: CombinedMessage) -> None:
    """Process a combined message (callback for MessageBuffer)."""
    processor = get_combined_processor()
    await processor.process(combined)
