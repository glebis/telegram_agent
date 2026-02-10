"""
Combined Message Processor

Processes combined messages from the MessageBuffer.
Handles reply context injection and routes to appropriate handlers.
"""

import asyncio
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from ..core.config import get_config_value, get_settings
from ..core.i18n import get_user_locale
from ..services.media_validator import strip_metadata, validate_media
from ..services.message_buffer import BufferedMessage, CombinedMessage
from ..services.message_persistence_service import persist_message
from ..services.reply_context import (
    MessageType,
    ReplyContext,
    get_reply_context_service,
)
from ..services.stt_service import get_stt_service
from ..utils.subprocess_helper import (
    download_telegram_file,
    extract_audio_from_video,
)
from ..utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)


class CombinedMessageProcessor:
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
            from ..plugins import get_plugin_manager

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
        from ..services.collect_service import get_collect_service

        collect_service = get_collect_service()
        is_collecting = await collect_service.is_collecting(combined.chat_id)

        # Check if Claude mode is active (early check for auto-collect)
        from ..services.claude_code_service import is_claude_code_admin
        from .handlers import _claude_mode_cache

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
                    from .handlers.formatting import send_message_sync

                    confirmation_msg = get_config_value(
                        "messages.collect_mode_on",
                        '📥 <b>Collect mode ON</b>\n\nSend files, voice, images, text — I\'ll collect them silently.\n\nWhen ready, tap <b>▶️ Go</b> or say <i>"now respond"</i>',
                    )
                    try:
                        send_message_sync(
                            chat_id=combined.chat_id,
                            text=confirmation_msg,
                            token=get_settings().telegram_bot_token,
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
                from ..services.claude_code_service import get_claude_code_service

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

                        # Add 5-second timeout to prevent hanging on DB issues
                        session_id = await asyncio.wait_for(lookup_session(), timeout=5.0)

                        # Log timing for slow lookups
                        lookup_duration = time.perf_counter() - lookup_start
                        if lookup_duration > 1.0:
                            logger.warning(
                                f"⚠️ Slow reply context DB lookup: {lookup_duration:.2f}s for chat {combined.chat_id}"
                            )

                    except asyncio.TimeoutError:
                        logger.error(
                            f"⏱️ Reply context DB lookup timed out after 5s for chat {combined.chat_id}. "
                            f"Processing message without session context to prevent loss."
                        )
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

        # Handle life weeks reflection replies
        if (
            reply_context
            and reply_context.message_type == MessageType.LIFE_WEEKS_REFLECTION
        ):
            from ..services.life_weeks_reply_handler import (
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

                await combined.reply_text(confirmation, parse_mode="HTML")
                logger.info(f"Life weeks reflection saved to {saved_path}")
                return  # Message handled

            except Exception as e:
                logger.error(
                    f"Failed to save life weeks reflection: {e}", exc_info=True
                )
                await combined.reply_text(
                    f"❌ Failed to save reflection: {str(e)}",
                    parse_mode="HTML",
                )
                return

        # Check if Claude mode is active
        # Use cache-only check to avoid database deadlocks during message processing
        from ..services.claude_code_service import is_claude_code_admin
        from .handlers import _claude_mode_cache

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
        except Exception as e:
            logger.error(f"Error processing combined message: {e}", exc_info=True)
            # Try to notify user of error
            try:
                await combined.primary_message.reply_text(
                    "Error processing your message. Please try again."
                )
            except Exception:
                pass

    async def _process_with_images(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process message with images."""
        from .message_handlers import handle_image_message

        logger.info(
            f"_process_with_images: claude_mode={is_claude_mode}, "
            f"images={len(combined.images)}, reply_context={reply_context is not None}"
        )

        # Build prompt from text + captions
        prompt_parts = []

        # Add reply context if present
        if reply_context:
            prompt_parts.append(
                self.reply_service.build_reply_prompt(
                    reply_context,
                    combined.combined_text or "Follow up on this image",
                    include_original=True,
                )
            )
        elif combined.combined_text:
            prompt_parts.append(combined.combined_text)

        prompt = "\n".join(prompt_parts) if prompt_parts else None

        # Route to Claude if:
        # 1. Claude mode is active, OR
        # 2. Replying to a Claude Code session message
        should_route_to_claude = is_claude_mode or (
            reply_context and reply_context.session_id
        )

        if should_route_to_claude:
            # Route to Claude with images
            await self._send_images_to_claude(combined, prompt)
        else:
            # Process each image with the LLM image handler
            # For now, process the first image (could extend to multi-image)
            if combined.images:
                first_image = combined.images[0]
                # Add combined text as context
                if prompt and first_image.message:
                    # We can't modify the message, so we'll handle this in the handler
                    pass

                # Use existing handler (it gets text from message.caption)
                await handle_image_message(
                    first_image.update,
                    first_image.context,
                )

    async def _send_images_to_claude(
        self,
        combined: CombinedMessage,
        prompt: Optional[str],
        custom_cwd: Optional[str] = None,
    ) -> None:
        """Send images to Claude for analysis with optional custom working directory."""
        from .handlers import execute_claude_prompt

        logger.info(
            f"_send_images_to_claude: Starting image processing for chat {combined.chat_id}, "
            f"images={len(combined.images)}, prompt_len={len(prompt) if prompt else 0}"
        )

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        # Get bot token from environment
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set in environment!")
            await message.reply_text("Bot configuration error - token not set")
            return

        # Create temp directory
        temp_dir = Path(get_settings().vault_temp_images_dir).expanduser()
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Download images to temp location
        image_paths = []

        for i, img_msg in enumerate(combined.images):
            try:
                if not img_msg.file_id:
                    logger.warning(f"Image {i} has no file_id, skipping")
                    continue

                file_id = img_msg.file_id
                logger.info(f"Downloading image {i}, file_id length={len(file_id)}")

                # Use secure subprocess helper to download image
                try:
                    image_filename = f"telegram_{uuid.uuid4().hex[:8]}.jpg"
                    image_path = temp_dir / image_filename

                    logger.info("Downloading image using secure subprocess helper...")
                    result = download_telegram_file(
                        file_id=file_id,
                        bot_token=bot_token,
                        output_path=image_path,
                        timeout=120,
                    )

                    if result.success:
                        # Validate downloaded image before processing
                        validation = validate_media(
                            image_path,
                            image_filename,
                        )
                        if not validation.valid:
                            logger.warning(
                                "Image %d rejected by validator: %s",
                                i,
                                validation.reason,
                            )
                            # Clean up rejected file
                            try:
                                image_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            continue

                        # Strip EXIF metadata before further processing
                        stripped = strip_metadata(image_path, image_path)
                        if stripped:
                            logger.debug("Stripped metadata from image %d", i)

                        image_paths.append(str(image_path))
                        logger.info(f"Downloaded image for Claude: {image_path}")
                    else:
                        logger.error(
                            f"Download failed: {result.error} - {result.stderr}"
                        )

                except Exception as e:
                    logger.error(f"Error downloading image {i}: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error processing image {i}: {e}", exc_info=True)

        if not image_paths:
            await message.reply_text("Failed to download images for Claude.")
            return

        # Build Claude prompt
        if len(image_paths) == 1:
            image_ref = f"Look at this image: {image_paths[0]}"
        else:
            image_ref = "Look at these images:\n" + "\n".join(
                f"- {p}" for p in image_paths
            )

        if prompt:
            full_prompt = f"{image_ref}\n\n{prompt}"
        else:
            full_prompt = f"{image_ref}\n\nAnalyze this image."

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to image prompt: {forward_context}")

        # Run Claude execution in a background task to avoid blocking

        async def run_claude():
            try:
                await execute_claude_prompt(
                    update, context, full_prompt, custom_cwd=custom_cwd
                )
            except Exception as e:
                logger.error(f"Error in image Claude execution: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=f"Error processing image: {str(e)[:100]}",
                    )
                except Exception:
                    pass

        create_tracked_task(run_claude(), name="claude_image_analysis")

    def _mark_as_read_sync(
        self,
        chat_id: int,
        message_ids: list,
        emoji: str = "👀",
    ) -> None:
        """Mark messages as read by reacting with an emoji (sync subprocess version).

        Note: Telegram only allows specific emojis for reactions. Valid ones include:
        👍, 👎, ❤️, 🔥, 👏, 😁, 🤔, 👀, 🎉, 🤩, 😎, 🙏, etc.
        NOT valid: ✅, ✔️, and many other common emojis
        """
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return

        for msg_id in message_ids:
            try:
                # Use requests in sync mode to avoid async blocking
                url = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
                payload = {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "reaction": [{"type": "emoji", "emoji": emoji}],
                }
                response = requests.post(url, json=payload, timeout=5)
                result = response.json()
                if result.get("ok"):
                    logger.info(f"Marked message {msg_id} with {emoji}")
                else:
                    logger.warning(
                        f"Failed to react to {msg_id}: {result.get('description', 'Unknown error')}"
                    )
            except Exception as e:
                logger.debug(f"Could not react to message {msg_id}: {e}")

    def _send_typing_sync(self, chat_id: int) -> None:
        """Send typing indicator (sync version to avoid async blocking)."""
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
            payload = {"chat_id": chat_id, "action": "typing"}
            requests.post(url, json=payload, timeout=5)
            logger.debug(f"Sent typing indicator to {chat_id}")
        except Exception as e:
            logger.debug(f"Could not send typing indicator: {e}")

    def _send_message_sync(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_to_message_id: int = None,
    ) -> bool:
        """Send a message using sync requests to avoid async blocking."""
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return False

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id

            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            if result.get("ok"):
                logger.info(f"Sent message to {chat_id}: {text[:50]}...")
                return True
            else:
                logger.error(f"Failed to send message: {result}")
                return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def _process_with_voice(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process message with voice."""

        from ..services.voice_service import get_voice_service
        from .handlers import execute_claude_prompt

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        get_voice_service()

        # Mark as "processing" when transcription starts (sync to avoid async blocking)
        # Using 👀 (valid Telegram reaction emoji) to indicate we're working on it
        message_ids = [msg.message_id for msg in combined.messages]
        self._mark_as_read_sync(combined.chat_id, message_ids, "👀")

        # Send typing indicator while processing
        self._send_typing_sync(combined.chat_id)

        # Get bot token for subprocess download
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set!")
            await message.reply_text("Bot configuration error")
            return

        # Transcribe all voice messages
        transcriptions = []

        for voice_msg in combined.voices:
            audio_path = None
            try:
                if not voice_msg.file_id:
                    continue

                logger.info(f"Processing voice file_id: {voice_msg.file_id[:50]}...")

                # Download voice file using secure subprocess helper
                import tempfile as tf

                with tf.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                    audio_path = Path(tmp.name)

                download_result = download_telegram_file(
                    file_id=voice_msg.file_id,
                    bot_token=bot_token,
                    output_path=audio_path,
                    timeout=90,
                )

                if not download_result.success:
                    logger.error(f"Failed to download voice: {download_result.error}")
                    continue

                logger.info(f"Downloaded voice to: {audio_path}")

                # Determine transcription language
                from ..services.keyboard_service import get_whisper_use_locale

                use_user_locale = await get_whisper_use_locale(combined.chat_id)
                stt_language = (
                    get_user_locale(combined.user_id) if use_user_locale else "en"
                )

                # Transcribe using STT service (with fallback chain)
                stt_service = get_stt_service()
                stt_result = stt_service.transcribe(
                    audio_path=audio_path,
                    model="whisper-large-v3-turbo",
                    language=stt_language,
                )

                if stt_result.success and stt_result.text:
                    transcriptions.append(stt_result.text)
                    logger.info(
                        f"Transcribed via {stt_result.provider} (lang={stt_language}): "
                        f"{stt_result.text[:100]}..."
                    )
                else:
                    logger.error(f"Transcription failed: {stt_result.error}")

            except Exception as e:
                logger.error(f"Error processing voice: {e}", exc_info=True)
            finally:
                if audio_path:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except Exception:
                        pass

        if not transcriptions:
            self._send_message_sync(
                combined.chat_id, "Failed to transcribe voice messages."
            )
            return

        logger.info(f"Voice transcription complete, {len(transcriptions)} segments")

        # Send transcript as a reply (if enabled in settings)
        transcript_text = "\n".join(transcriptions)
        first_voice_msg_id = combined.voices[0].message_id if combined.voices else None

        from ..services.keyboard_service import get_show_transcript

        logger.info(f"Checking show_transcript for chat {combined.chat_id}")
        show_transcript = await get_show_transcript(combined.chat_id)
        logger.info(f"show_transcript={show_transcript} for chat {combined.chat_id}")
        if show_transcript:
            self._send_message_sync(
                combined.chat_id,
                f"📝 <b>Transcript:</b>\n\n{transcript_text}",
                parse_mode="HTML",
                reply_to_message_id=first_voice_msg_id,
            )
            logger.info("Transcript sent")

        # Mark as "completed" after successful transcription with 👍
        self._mark_as_read_sync(combined.chat_id, message_ids, "👍")
        logger.info("Marked as read with 👍")

        # Combine transcriptions with text
        full_text_parts = transcriptions

        if combined.combined_text:
            full_text_parts.append(combined.combined_text)

        full_text = "\n".join(full_text_parts)

        # Check if this is a reply to a trail review completion
        is_trail_reply = False
        if (
            reply_context
            and hasattr(reply_context, "trail_path")
            and reply_context.trail_path
        ):
            is_trail_reply = True
            from ..services.trail_review_service import get_trail_review_service

            trail_service = get_trail_review_service()
            full_text = trail_service.build_trail_context_for_claude(
                trail_path=reply_context.trail_path,
                trail_name=getattr(reply_context, "trail_name", "Unknown"),
                answers=getattr(reply_context, "trail_answers", {}),
                user_comment=full_text,
            )
            logger.info(
                f"Trail review voice reply detected: trail={reply_context.trail_name}, "
                f"transcription_len={len(full_text)}"
            )
        elif reply_context:
            # Add reply context for non-trail replies
            full_text = self.reply_service.build_reply_prompt(
                reply_context,
                full_text,
                include_original=True,
            )

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_text = f"{forward_context}\n\n{full_text}"
            logger.info(f"Added forward context to voice prompt: {forward_context}")

        # Route to Claude if:
        # 1. Claude mode is active, OR
        # 2. Replying to a Claude Code session message, OR
        # 3. Replying to a trail review completion
        should_route_to_claude = (
            is_claude_mode
            or is_trail_reply
            or (reply_context and reply_context.session_id)
        )

        logger.info(
            f"Voice routing: should_route_to_claude={should_route_to_claude}, is_claude_mode={is_claude_mode}, is_trail_reply={is_trail_reply}"
        )

        if should_route_to_claude:
            # Run Claude execution in a background task to avoid blocking
            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_text)
                except Exception as e:
                    logger.error(f"Error in voice Claude execution: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=f"Error processing voice: {str(e)[:100]}",
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_voice_analysis")
        else:
            # Use existing voice handler logic for routing
            pass

            logger.info("Routing voice to _handle_transcription_routing")
            # For non-Claude mode, use existing handler
            # But we've already transcribed, so send as text
            await self._handle_transcription_routing(
                combined,
                full_text,
                transcriptions[0] if transcriptions else "",
            )
            logger.info("_handle_transcription_routing completed")

    async def _handle_transcription_routing(
        self,
        combined: CombinedMessage,
        full_text: str,
        primary_transcription: str,
    ) -> None:
        """Handle routing for transcribed voice (non-Claude mode).

        Uses sync requests to avoid blocking in the webhook handler context.
        """
        import json

        import requests as req

        from ..services.link_service import track_capture
        from ..services.voice_service import get_voice_service

        voice_service = get_voice_service()

        # Detect intent
        intent_info = voice_service.detect_intent(primary_transcription)
        formatted = voice_service.format_for_obsidian(
            primary_transcription, intent_info
        )
        destination = intent_info.get("destination", "daily")
        intent_display = intent_info.get("intent", "quick").title()

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set for voice routing")
            return

        # Use a placeholder msg_id for callback_data; will update after send
        # Send message with inline keyboard directly (sync to avoid blocking)
        text = (
            f"<b>Transcription</b>\n\n"
            f"{primary_transcription}\n\n"
            f"<i>Detected: {intent_display}</i>\n"
            f"<i>Will save to: {destination}</i>"
        )

        try:
            # First send without keyboard to get msg_id
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": combined.chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            response = req.post(url, json=payload, timeout=10)
            result = response.json()

            if not result.get("ok"):
                logger.error(f"Failed to send routing message: {result}")
                return

            msg_id = result["result"]["message_id"]

            # Now edit to add inline keyboard with correct msg_id
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "Daily", "callback_data": f"voice:daily:{msg_id}"},
                        {"text": "Inbox", "callback_data": f"voice:inbox:{msg_id}"},
                    ],
                    [
                        {"text": "Task", "callback_data": f"voice:task:{msg_id}"},
                        {"text": "Done", "callback_data": f"voice:done:{msg_id}"},
                    ],
                ]
            }

            edit_url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
            edit_payload = {
                "chat_id": combined.chat_id,
                "message_id": msg_id,
                "reply_markup": json.dumps(keyboard),
            }
            edit_response = req.post(edit_url, json=edit_payload, timeout=10)
            edit_result = edit_response.json()

            if not edit_result.get("ok"):
                logger.warning(f"Failed to add routing buttons: {edit_result}")

            # Store for routing callback
            track_capture(msg_id, formatted)
            logger.info(
                f"Voice routing message sent: msg_id={msg_id}, destination={destination}"
            )

        except Exception as e:
            logger.error(f"Error in voice routing: {e}", exc_info=True)

    async def _process_contacts(self, combined: CombinedMessage) -> None:
        """Process contact messages."""
        from .message_handlers import handle_contact_message

        # Process first contact
        if combined.contacts:
            first_contact = combined.contacts[0]
            await handle_contact_message(
                first_contact.update,
                first_contact.context,
            )

    async def _process_with_polls(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process poll messages - format poll content and route to Claude or display."""
        from .handlers import execute_claude_prompt

        logger.info(
            f"_process_with_polls: claude_mode={is_claude_mode}, "
            f"polls={len(combined.polls)}, text_len={len(combined.combined_text)}"
        )

        update = combined.primary_update
        context = combined.primary_context
        combined.primary_message

        # Build a text representation of each poll
        poll_descriptions = []
        for poll_msg in combined.polls:
            desc_parts = []
            question = poll_msg.poll_question or "Unknown question"
            options = poll_msg.poll_options or []
            poll_type = poll_msg.poll_type or "regular"
            voter_count = poll_msg.poll_total_voter_count or 0

            desc_parts.append(f'📊 Poll: "{question}"')
            desc_parts.append(f"   Type: {poll_type}")
            if voter_count > 0:
                desc_parts.append(f"   Total votes: {voter_count}")

            # Format options with numbering
            for i, opt in enumerate(options, 1):
                desc_parts.append(f"   {i}. {opt}")

            # Check if this poll has been voted on (from Telegram's Poll object)
            # The message.poll object may contain the user's chosen option
            if poll_msg.message and poll_msg.message.poll:
                poll_obj = poll_msg.message.poll
                # Check each option for voter count or is_chosen
                voted_options = []
                for i, opt in enumerate(poll_obj.options):
                    if getattr(opt, "voter_count", 0) > 0:
                        voted_options.append(f"{opt.text} ({opt.voter_count} votes)")

                if voted_options:
                    desc_parts.append(f"   Votes: {', '.join(voted_options)}")

            poll_descriptions.append("\n".join(desc_parts))

        poll_text = "\n\n".join(poll_descriptions)

        # Build full prompt
        prompt_parts = []

        # Add reply context if present
        if reply_context:
            prompt_parts.append(
                self.reply_service.build_reply_prompt(
                    reply_context,
                    combined.combined_text or "",
                    include_original=True,
                )
            )

        # Add poll content
        prompt_parts.append(poll_text)

        # Add any accompanying text
        if combined.combined_text:
            prompt_parts.append(combined.combined_text)

        full_prompt = "\n\n".join(prompt_parts)

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to poll prompt: {forward_context}")

        # Route to Claude if:
        # 1. Claude mode is active, OR
        # 2. Replying to a Claude Code session message
        should_route_to_claude = is_claude_mode or (
            reply_context and reply_context.session_id
        )

        if should_route_to_claude:
            # Run Claude execution in a background task
            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_prompt)
                except Exception as e:
                    logger.error(f"Error in poll Claude execution: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=f"Error processing poll: {str(e)[:100]}",
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_poll_analysis")
        else:
            # Non-Claude mode: display the poll content as formatted text
            display_parts = ["<b>📊 Poll received:</b>\n"]
            for poll_msg in combined.polls:
                question = poll_msg.poll_question or "Unknown"
                options = poll_msg.poll_options or []
                display_parts.append(f"<b>{question}</b>")
                for i, opt in enumerate(options, 1):
                    display_parts.append(f"  {i}. {opt}")

                if poll_msg.message and poll_msg.message.poll:
                    poll_obj = poll_msg.message.poll
                    for opt in poll_obj.options:
                        if getattr(opt, "voter_count", 0) > 0:
                            display_parts.append(
                                f"  📌 {opt.text}: {opt.voter_count} vote(s)"
                            )

            display_text = "\n".join(display_parts)

            self._send_message_sync(
                combined.chat_id,
                display_text,
                parse_mode="HTML",
            )

    async def _process_with_videos(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process video messages - extract audio, transcribe, and process like voice."""

        from .handlers import execute_claude_prompt

        logger.info(
            f"_process_with_videos: claude_mode={is_claude_mode}, "
            f"videos={len(combined.videos)}, text_len={len(combined.combined_text)}"
        )

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        # Mark as "processing" when transcription starts (sync to avoid async blocking)
        # Using 👀 (valid Telegram reaction emoji) to indicate we're working on it
        message_ids = [msg.message_id for msg in combined.messages]
        self._mark_as_read_sync(combined.chat_id, message_ids, "👀")

        # Send typing indicator while processing
        self._send_typing_sync(combined.chat_id)

        # Get bot token for downloading
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set!")
            await message.reply_text("Bot configuration error")
            return

        # Create unique temp directory per request to avoid collisions
        temp_dir = (
            Path(tempfile.gettempdir()) / f"telegram_videos_{uuid.uuid4().hex[:8]}"
        )
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Process each video - download, extract audio, transcribe
        transcriptions = []

        try:
            for video_msg in combined.videos:
                try:
                    if not video_msg.file_id:
                        continue

                    logger.info(
                        f"Processing video file_id: {video_msg.file_id[:50]}..."
                    )

                    # Check file size first (prevents wasting time on >20MB files)
                    from ..utils.subprocess_helper import get_telegram_file_info

                    file_info_result = get_telegram_file_info(
                        file_id=video_msg.file_id,
                        bot_token=bot_token,
                        timeout=30,
                    )

                    if file_info_result.success:
                        try:
                            import json

                            file_info = json.loads(file_info_result.stdout)
                            file_size = file_info.get("file_size")
                            if file_size:
                                size_mb = file_size / (1024 * 1024)
                                logger.info(f"Video file size: {size_mb:.2f} MB")

                                if file_size > 20 * 1024 * 1024:  # >20MB
                                    logger.warning(
                                        f"⚠️ Video is {size_mb:.2f}MB (>20MB limit). "
                                        f"Bot API cannot download this file."
                                    )
                                    # Send user-friendly error message
                                    await message.reply_text(
                                        f"⚠️ This video is {size_mb:.1f}MB, which exceeds Telegram Bot API's 20MB download limit.\n\n"
                                        f"To process this video:\n"
                                        f"1️⃣ Download it to your device\n"
                                        f"2️⃣ Send it directly to me (not as a forward)\n\n"
                                        f"Or I can implement Telethon integration to handle large files automatically. "
                                        f"See: https://github.com/glebis/telegram_agent/issues/194"
                                    )
                                    continue
                        except Exception as e:
                            logger.warning(f"Could not parse file info: {e}")

                    # Download video (only if <20MB or size unknown)
                    video_filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
                    video_path = temp_dir / video_filename

                    download_result = download_telegram_file(
                        file_id=video_msg.file_id,
                        bot_token=bot_token,
                        output_path=video_path,
                        timeout=180,  # Videos can be large
                    )

                    if not download_result.success:
                        logger.error(
                            f"Failed to download video: {download_result.error}"
                        )
                        # Clean up temp file on download failure
                        video_path.unlink(missing_ok=True)
                        continue

                    logger.info(f"Downloaded video to: {video_path}")

                    # Extract audio from video
                    audio_path = temp_dir / f"audio_{uuid.uuid4().hex[:8]}.ogg"

                    extract_result = extract_audio_from_video(
                        video_path=video_path,
                        output_path=audio_path,
                        timeout=120,
                    )

                    # Clean up video file
                    try:
                        video_path.unlink()
                    except Exception:
                        pass

                    if not extract_result.success:
                        logger.error(f"Failed to extract audio: {extract_result.error}")
                        # Clean up audio temp file on extract failure
                        audio_path.unlink(missing_ok=True)
                        continue

                    logger.info(f"Extracted audio to: {audio_path}")

                    # Determine transcription language
                    from ..services.keyboard_service import get_whisper_use_locale

                    use_user_locale = await get_whisper_use_locale(combined.chat_id)
                    stt_language = (
                        get_user_locale(combined.user_id) if use_user_locale else "en"
                    )

                    # Transcribe audio using STT service (with fallback chain)
                    stt_service = get_stt_service()
                    stt_result = stt_service.transcribe(
                        audio_path=audio_path,
                        model="whisper-large-v3-turbo",
                        language=stt_language,
                    )

                    # Clean up audio file
                    try:
                        audio_path.unlink()
                    except Exception:
                        pass

                    if stt_result.success and stt_result.text:
                        transcriptions.append(stt_result.text)
                        logger.info(
                            f"Transcribed video via {stt_result.provider} (lang={stt_language}): "
                            f"{stt_result.text[:100]}..."
                        )
                    else:
                        logger.error(f"Transcription failed: {stt_result.error}")

                except Exception as e:
                    logger.error(f"Error processing video: {e}", exc_info=True)
        finally:
            # Clean up temp directory and any leftover files
            import shutil

            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

        if not transcriptions:
            # Fall back to caption-only processing if no audio could be extracted
            prompt = combined.combined_text or "Video message received (no audio)"
            prompt = prompt.encode("utf-8", errors="replace").decode("utf-8")

            forward_context = combined.get_forward_context()
            if forward_context:
                prompt = f"{forward_context}\n\n{prompt}"

            if is_claude_mode:

                async def run_claude():
                    try:
                        await execute_claude_prompt(update, context, prompt)
                    except Exception as e:
                        logger.error(
                            f"Error in video Claude execution: {e}", exc_info=True
                        )

                create_tracked_task(run_claude(), name="claude_video_caption")
            else:
                await message.reply_text(
                    "Could not extract audio from video. Enable Claude mode to discuss it."
                )
            return

        # Send transcript as a reply (if enabled in settings)
        transcript_text = "\n".join(transcriptions)
        first_video_msg_id = combined.videos[0].message_id if combined.videos else None

        from ..services.keyboard_service import (
            get_show_transcript as get_show_transcript_v,
        )

        show_transcript_v = await get_show_transcript_v(combined.chat_id)
        if show_transcript_v:
            self._send_message_sync(
                combined.chat_id,
                f"📝 <b>Video Transcript:</b>\n\n{transcript_text}",
                parse_mode="HTML",
                reply_to_message_id=first_video_msg_id,
            )

        # Mark as "completed" after successful transcription with 👍
        self._mark_as_read_sync(combined.chat_id, message_ids, "👍")

        # Combine transcriptions with any caption text
        full_text_parts = transcriptions

        if combined.combined_text:
            full_text_parts.append(combined.combined_text)

        full_text = "\n".join(full_text_parts)

        # Add reply context
        if reply_context:
            full_text = self.reply_service.build_reply_prompt(
                reply_context,
                full_text,
                include_original=True,
            )

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_text = f"{forward_context}\n\n{full_text}"
            logger.info(f"Added forward context to video prompt: {forward_context}")

        # Route to Claude if:
        # 1. Claude mode is active, OR
        # 2. Replying to a Claude Code session message
        should_route_to_claude = is_claude_mode or (
            reply_context and reply_context.session_id
        )

        if should_route_to_claude:
            # Run Claude execution in a background task
            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_text)
                except Exception as e:
                    logger.error(f"Error in video Claude execution: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=f"Error processing video: {str(e)[:100]}",
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_video_transcript")
        else:
            # Use voice routing for non-Claude mode
            from ..services.voice_service import get_voice_service

            get_voice_service()

            await self._handle_transcription_routing(
                combined,
                full_text,
                transcriptions[0] if transcriptions else "",
            )

    async def _process_documents(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process document messages."""
        import uuid

        from .handlers import execute_claude_prompt

        logger.info(
            f"_process_documents: claude_mode={is_claude_mode}, "
            f"docs={len(combined.documents)}, text_len={len(combined.combined_text)}"
        )

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        # Route to Claude if:
        # 1. Claude mode is active, OR
        # 2. Replying to a Claude Code session message
        should_route_to_claude = is_claude_mode or (
            reply_context and reply_context.session_id
        )

        if not should_route_to_claude:
            # For non-Claude mode, just acknowledge
            await message.reply_text(
                "Documents received. Enable Claude mode to analyze them."
            )
            return

        # Check if this is a forwarded message with caption - skip download
        # and just use the caption + forward context
        forward_context = combined.get_forward_context()
        if forward_context and combined.combined_text:
            logger.info("Forwarded document with caption - using caption only")
            prompt = f"{forward_context}\n\n{combined.combined_text}"

            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, prompt)
                except Exception as e:
                    logger.error(
                        f"Error in document Claude execution: {e}", exc_info=True
                    )

            create_tracked_task(run_claude(), name="claude_forwarded_doc")
            return

        # Download documents for Claude using subprocess helper
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set!")
            await message.reply_text("Bot configuration error")
            return

        doc_paths = []

        for doc_msg in combined.documents:
            try:
                if not doc_msg.file_id:
                    continue

                # Create temp directory
                temp_dir = Path(get_settings().vault_temp_docs_dir).expanduser()
                temp_dir.mkdir(parents=True, exist_ok=True)

                # Get filename
                original_name = "document"
                if doc_msg.message.document and doc_msg.message.document.file_name:
                    original_name = doc_msg.message.document.file_name

                doc_filename = f"{uuid.uuid4().hex[:8]}_{original_name}"
                doc_path = temp_dir / doc_filename

                # Download using subprocess helper
                logger.info(f"Downloading document using subprocess: {original_name}")
                result = download_telegram_file(
                    file_id=doc_msg.file_id,
                    bot_token=bot_token,
                    output_path=doc_path,
                    timeout=120,
                )

                if result.success:
                    # Validate downloaded document (size check, basic sniffing)
                    # Use a broad extension list for documents
                    doc_allowed_exts = [
                        "pdf",
                        "txt",
                        "md",
                        "csv",
                        "json",
                        "xml",
                        "doc",
                        "docx",
                        "xls",
                        "xlsx",
                        "ppt",
                        "pptx",
                        "jpg",
                        "jpeg",
                        "png",
                        "webp",
                        "gif",
                        "py",
                        "js",
                        "ts",
                        "html",
                        "css",
                        "yaml",
                        "yml",
                        "zip",
                        "tar",
                        "gz",
                    ]
                    validation = validate_media(
                        doc_path,
                        original_name,
                        allowed_extensions=doc_allowed_exts,
                    )
                    if not validation.valid:
                        logger.warning(
                            "Document rejected by validator: %s",
                            validation.reason,
                        )
                        try:
                            doc_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        continue

                    doc_paths.append(str(doc_path))
                    logger.info(f"Downloaded document for Claude: {doc_path}")
                else:
                    logger.error(f"Download failed: {result.error}")

            except Exception as e:
                logger.error(f"Error downloading document: {e}", exc_info=True)

        if not doc_paths:
            # Fall back to just using caption if available
            if combined.combined_text:
                logger.info("Document download failed, using caption only")
                prompt = combined.combined_text
                if forward_context:
                    prompt = f"{forward_context}\n\n{prompt}"

                async def run_claude():
                    try:
                        await execute_claude_prompt(update, context, prompt)
                    except Exception as e:
                        logger.error(
                            f"Error in document Claude execution: {e}", exc_info=True
                        )

                create_tracked_task(run_claude(), name="claude_doc_caption")
                return

            await message.reply_text("Failed to download documents.")
            return

        # Build prompt
        if len(doc_paths) == 1:
            doc_ref = f"Read this file: {doc_paths[0]}"
        else:
            doc_ref = "Read these files:\n" + "\n".join(f"- {p}" for p in doc_paths)

        prompt_parts = [doc_ref]

        if reply_context:
            prompt_parts.append(
                self.reply_service.build_reply_prompt(
                    reply_context,
                    combined.combined_text or "",
                    include_original=True,
                )
            )
        elif combined.combined_text:
            prompt_parts.append(combined.combined_text)
        else:
            prompt_parts.append("Summarize the contents.")

        full_prompt = "\n\n".join(prompt_parts)

        await execute_claude_prompt(update, context, full_prompt)

    async def _process_command(self, combined: CombinedMessage) -> None:
        """
        Process a combined message that contains a /claude, /meta, or /dev command.

        Routes to appropriate handler based on command type:
        - /claude: default behavior (current working directory)
        - /meta: execute in telegram_agent directory
        - /dev: execute in current working directory
        """
        from .handlers import execute_claude_prompt

        # Get the command message
        cmd_msg = combined.get_command_message()
        if not cmd_msg:
            logger.error("No command found in combined message")
            return

        update = cmd_msg.update
        context = cmd_msg.context
        command_type = cmd_msg.command_type

        # Determine custom_cwd based on command type
        custom_cwd = None
        if command_type == "meta":
            from ..core.config import PROJECT_ROOT

            custom_cwd = str(PROJECT_ROOT)
            logger.info(f"Using custom_cwd for /meta: {custom_cwd}")
        # /dev and /claude use default (None)

        # The combined_text already includes the command prompt + any follow-up text
        full_prompt = combined.combined_text

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to prompt: {forward_context}")

        logger.info(
            f"Processing /{command_type} command with combined prompt: "
            f"chat={combined.chat_id}, prompt_len={len(full_prompt)}, "
            f"messages_combined={len(combined.messages)}"
        )

        # Run command execution in a background task to avoid blocking
        async def run_command():
            try:
                if combined.has_images():
                    # Download and include images in the prompt
                    await self._send_images_to_claude(
                        combined, full_prompt, custom_cwd=custom_cwd
                    )
                elif combined.has_voice():
                    # Transcribe voice and add to prompt
                    await self._process_with_voice(combined, None, is_claude_mode=True)
                elif combined.has_documents():
                    # Include documents
                    await self._process_documents(combined, None, is_claude_mode=True)
                else:
                    # Text-only prompt - detect URLs for logging
                    from .message_handlers import extract_urls

                    urls = extract_urls(full_prompt)
                    if urls:
                        logger.info(
                            f"Detected {len(urls)} URL(s) in prompt: {urls[:3]}"
                        )  # Log first 3
                    logger.info(
                        f"Calling execute_claude_prompt with {len(full_prompt)} chars"
                    )
                    await execute_claude_prompt(
                        update, context, full_prompt, custom_cwd=custom_cwd
                    )
                    logger.info("execute_claude_prompt completed")
            except Exception as e:
                logger.error(f"Error in _process_command: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=f"Error processing /{command_type} command: {str(e)[:100]}",
                    )
                except Exception:
                    pass

        # Schedule the task to run in the background
        create_tracked_task(run_command(), name=f"{command_type}_command")

    async def _process_claude_command(self, combined: CombinedMessage) -> None:
        """
        Process a combined message that contains a /claude command.

        The /claude command prompt is combined with any follow-up text messages
        that arrived within the buffer timeout window.
        """
        from .handlers import execute_claude_prompt

        # Get the /claude command message for update/context
        claude_msg = combined.get_claude_command_message()
        if not claude_msg:
            logger.error("No /claude command found in combined message")
            return

        update = claude_msg.update
        context = claude_msg.context

        # The combined_text already includes the /claude prompt + any follow-up text
        full_prompt = combined.combined_text

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to prompt: {forward_context}")

        logger.info(
            f"Processing /claude command with combined prompt: "
            f"chat={combined.chat_id}, prompt_len={len(full_prompt)}, "
            f"messages_combined={len(combined.messages)}"
        )

        # Check for images that should be included
        # Run Claude execution in a background task to avoid blocking

        async def run_claude():
            try:
                if combined.has_images():
                    # Download and include images in the prompt
                    await self._send_images_to_claude(combined, full_prompt)
                elif combined.has_voice():
                    # Transcribe voice and add to prompt
                    await self._process_with_voice(combined, None, is_claude_mode=True)
                elif combined.has_documents():
                    # Include documents
                    await self._process_documents(combined, None, is_claude_mode=True)
                else:
                    # Text-only prompt - detect URLs for logging
                    from .message_handlers import extract_urls

                    urls = extract_urls(full_prompt)
                    if urls:
                        logger.info(
                            f"Detected {len(urls)} URL(s) in prompt: {urls[:3]}"
                        )  # Log first 3
                    logger.info(
                        f"Calling execute_claude_prompt with {len(full_prompt)} chars"
                    )
                    await execute_claude_prompt(update, context, full_prompt)
                    logger.info("execute_claude_prompt completed")
            except Exception as e:
                logger.error(f"Error in _process_claude_command: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=f"Error processing Claude command: {str(e)[:100]}",
                    )
                except Exception:
                    pass

        # Schedule the task to run in the background
        create_tracked_task(run_claude(), name="claude_command")

    async def _process_text(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process text-only message."""
        from .handlers import execute_claude_prompt
        from .message_handlers import (
            extract_urls,
            handle_link_message,
            handle_text_message,
        )

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        text = combined.combined_text

        # Check if this is a reply to a trail review completion
        is_trail_reply = False
        trail_prompt = None
        if (
            reply_context
            and hasattr(reply_context, "trail_path")
            and reply_context.trail_path
        ):
            is_trail_reply = True
            from ..services.trail_review_service import get_trail_review_service

            trail_service = get_trail_review_service()
            trail_prompt = trail_service.build_trail_context_for_claude(
                trail_path=reply_context.trail_path,
                trail_name=getattr(reply_context, "trail_name", "Unknown"),
                answers=getattr(reply_context, "trail_answers", {}),
                user_comment=text,
            )
            logger.info(
                f"Trail review reply detected: trail={reply_context.trail_name}, "
                f"comment_len={len(text)}"
            )

        # Build full prompt with reply context
        # Track if we're replying to a Claude message (should continue that session)
        is_claude_reply = False

        if trail_prompt:
            full_prompt = trail_prompt
        elif reply_context:
            full_prompt = self.reply_service.build_reply_prompt(
                reply_context,
                text,
                include_original=True,
            )

            # If replying to Claude response, use that session
            if reply_context.message_type == MessageType.CLAUDE_RESPONSE:
                is_claude_reply = True
                # Force use of the same session
                if reply_context.session_id:
                    context.user_data["force_session_id"] = reply_context.session_id
                    logger.info(
                        f"Replying to Claude message, forcing session: {reply_context.session_id}"
                    )

        else:
            full_prompt = text

        # Check for link + comment pair (takes precedence over forward_context)
        link_comment_ctx = combined.get_link_comment_context()
        if link_comment_ctx:
            full_prompt = link_comment_ctx
            logger.info("Using link + comment semantic formatting for prompt")

        # Check for URLs - but only capture to inbox if NOT in Claude mode
        # and NOT replying to a Claude message or trail review
        urls = extract_urls(text)

        if urls and not is_claude_mode and not is_claude_reply and not is_trail_reply:
            # Handle as link capture to Obsidian inbox
            await handle_link_message(message, urls)
            return

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to text prompt: {forward_context}")

        # Route to Claude if: Claude mode is active OR replying to a Claude message
        # OR replying to a trail review (always goes to Claude)
        if is_claude_mode or is_claude_reply or is_trail_reply:
            # Run Claude execution in a background task to avoid blocking webhook
            pass

            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_prompt)
                except Exception as e:
                    logger.error(
                        f"Error in _process_text Claude execution: {e}", exc_info=True
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=f"Error processing message: {str(e)[:100]}",
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_text")
        else:
            # Use existing text handler
            await handle_text_message(update, context)

    async def _transcribe_voice_for_collect(
        self, voice_msg: BufferedMessage, chat_id: int, user_id: int
    ) -> Optional[str]:
        """Transcribe a voice message and return the transcription."""
        import tempfile as tf

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return None

        if not voice_msg.file_id:
            return None

        audio_path = None
        try:
            # Download voice file
            with tf.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                audio_path = Path(tmp.name)

            download_result = download_telegram_file(
                file_id=voice_msg.file_id,
                bot_token=bot_token,
                output_path=audio_path,
                timeout=90,
            )

            if not download_result.success:
                logger.error(f"Failed to download voice: {download_result.error}")
                return None

            # Determine transcription language
            from ..services.keyboard_service import get_whisper_use_locale

            use_user_locale = await get_whisper_use_locale(chat_id)
            stt_language = get_user_locale(user_id) if use_user_locale else "en"

            # Transcribe using STT service (with fallback chain)
            stt_service = get_stt_service()
            stt_result = stt_service.transcribe(
                audio_path=audio_path,
                model="whisper-large-v3-turbo",
                language=stt_language,
            )

            if stt_result.success and stt_result.text:
                logger.info(
                    f"Transcribed via {stt_result.provider} (lang={stt_language})"
                )
                return stt_result.text
            else:
                logger.error(f"Transcription failed: {stt_result.error}")
                return None

        except Exception as e:
            logger.error(f"Error transcribing voice: {e}", exc_info=True)
            return None
        finally:
            if audio_path:
                try:
                    audio_path.unlink(missing_ok=True)
                except Exception:
                    pass

    async def _transcribe_video_for_collect(
        self, video_msg: BufferedMessage, chat_id: int, user_id: int
    ) -> Optional[str]:
        """Transcribe a video message and return the transcription."""

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return None

        if not video_msg.file_id:
            return None

        video_path = None
        audio_path = None
        try:
            # Create temp directory
            temp_dir = Path(tempfile.gettempdir()) / "telegram_collect_videos"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Download video
            video_filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
            video_path = temp_dir / video_filename

            download_result = download_telegram_file(
                file_id=video_msg.file_id,
                bot_token=bot_token,
                output_path=video_path,
                timeout=180,
            )

            if not download_result.success:
                logger.error(f"Failed to download video: {download_result.error}")
                return None

            # Extract audio
            audio_path = temp_dir / f"audio_{uuid.uuid4().hex[:8]}.ogg"
            extract_result = extract_audio_from_video(
                video_path=video_path,
                output_path=audio_path,
                timeout=120,
            )

            if not extract_result.success:
                logger.error(f"Failed to extract audio: {extract_result.error}")
                return None

            # Determine transcription language
            from ..services.keyboard_service import get_whisper_use_locale

            use_user_locale = await get_whisper_use_locale(chat_id)
            stt_language = get_user_locale(user_id) if use_user_locale else "en"

            # Transcribe using STT service (with fallback chain)
            stt_service = get_stt_service()
            stt_result = stt_service.transcribe(
                audio_path=audio_path,
                model="whisper-large-v3-turbo",
                language=stt_language,
            )

            if stt_result.success and stt_result.text:
                logger.info(
                    f"Transcribed video via {stt_result.provider} (lang={stt_language})"
                )
                return stt_result.text
            else:
                logger.error(f"Transcription failed: {stt_result.error}")
                return None

        except Exception as e:
            logger.error(f"Error transcribing video: {e}", exc_info=True)
            return None
        finally:
            for p in [video_path, audio_path]:
                if p:
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass

    async def _add_to_collect_queue(self, combined: CombinedMessage) -> None:
        """Add items from combined message to the collect queue and react with 👀.

        Voice and video messages are transcribed immediately, with transcription
        sent as a reply to the original message.
        """
        from ..services.collect_service import CollectItemType, get_collect_service

        collect_service = get_collect_service()
        chat_id = combined.chat_id
        added_count = 0

        # DEBUG: Log what we're about to process
        logger.info(
            f"_add_to_collect_queue called: chat={chat_id}, "
            f"text_len={len(combined.combined_text)}, "
            f"images={len(combined.images)}, voices={len(combined.voices)}, "
            f"videos={len(combined.videos)}, docs={len(combined.documents)}"
        )
        if combined.voices:
            logger.info(
                f"Voice list contents: {[v.message_id for v in combined.voices]}"
            )

        # Process each type of content
        # Add text messages
        if combined.combined_text.strip():
            for msg in combined.messages:
                if msg.text and msg.message_type == "text":
                    await collect_service.add_item(
                        chat_id=chat_id,
                        item_type=CollectItemType.TEXT,
                        message_id=msg.message_id,
                        content=msg.text,
                    )
                    added_count += 1

        # Add images (BufferedMessage objects)
        for img in combined.images:
            await collect_service.add_item(
                chat_id=chat_id,
                item_type=CollectItemType.IMAGE,
                message_id=img.message_id,
                content=img.file_id or "",
                caption=img.caption,
            )
            added_count += 1

        # Add voices (BufferedMessage objects) - with transcription
        # Also handles audio files (mp3, etc.) that were converted to voice type
        for voice in combined.voices:
            # Get duration from the original message (voice or audio)
            duration = None
            if voice.message:
                if voice.message.voice:
                    duration = voice.message.voice.duration
                elif voice.message.audio:
                    duration = voice.message.audio.duration

            # React with 👀 to show processing started
            logger.info(
                f"Transcribing voice/audio message {voice.message_id} for collect queue"
            )
            self._mark_as_read_sync(chat_id, [voice.message_id], "👀")

            transcription = await self._transcribe_voice_for_collect(
                voice, chat_id, combined.user_id
            )

            if transcription:
                # React with 👍 to show transcription succeeded
                self._mark_as_read_sync(chat_id, [voice.message_id], "👍")
                logger.info(
                    f"Transcribed voice {voice.message_id}: {transcription[:50]}..."
                )

                # Send full transcript as reply (if enabled in settings)
                from ..services.keyboard_service import get_show_transcript as _get_st

                if await _get_st(chat_id):
                    self._send_message_sync(
                        chat_id,
                        f"📝 <b>Transcript:</b>\n\n{transcription}",
                        parse_mode="HTML",
                        reply_to_message_id=voice.message_id,
                    )
            else:
                # React with 🤔 to show transcription failed
                self._mark_as_read_sync(chat_id, [voice.message_id], "🤔")
                logger.warning(f"Failed to transcribe voice {voice.message_id}")

            await collect_service.add_item(
                chat_id=chat_id,
                item_type=CollectItemType.VOICE,
                message_id=voice.message_id,
                content=voice.file_id or "",
                duration=duration,
                transcription=transcription,
            )
            added_count += 1

        # Add documents (BufferedMessage objects)
        for doc in combined.documents:
            file_name = None
            mime_type = None
            if doc.message and doc.message.document:
                file_name = doc.message.document.file_name
                mime_type = doc.message.document.mime_type
            await collect_service.add_item(
                chat_id=chat_id,
                item_type=CollectItemType.DOCUMENT,
                message_id=doc.message_id,
                content=doc.file_id or "",
                caption=doc.caption,
                file_name=file_name,
                mime_type=mime_type,
            )
            added_count += 1

        # Add videos (BufferedMessage objects) - with transcription
        for video in combined.videos:
            duration = None
            file_name = None
            if video.message and video.message.video:
                duration = video.message.video.duration
                file_name = video.message.video.file_name

            # React with 👀 to show processing started
            logger.info(
                f"Transcribing video message {video.message_id} for collect queue"
            )
            self._mark_as_read_sync(chat_id, [video.message_id], "👀")

            transcription = await self._transcribe_video_for_collect(
                video, chat_id, combined.user_id
            )

            if transcription:
                # React with 👍 to show transcription succeeded
                self._mark_as_read_sync(chat_id, [video.message_id], "👍")
                logger.info(
                    f"Transcribed video {video.message_id}: {transcription[:50]}..."
                )

                # Send full transcript as reply (if enabled in settings)
                from ..services.keyboard_service import get_show_transcript as _get_st_v

                if await _get_st_v(chat_id):
                    self._send_message_sync(
                        chat_id,
                        f"📝 <b>Video Transcript:</b>\n\n{transcription}",
                        parse_mode="HTML",
                        reply_to_message_id=video.message_id,
                    )
            else:
                # React with 🤔 to show transcription failed
                self._mark_as_read_sync(chat_id, [video.message_id], "🤔")
                logger.warning(f"Failed to transcribe video {video.message_id}")

            await collect_service.add_item(
                chat_id=chat_id,
                item_type=CollectItemType.VIDEO,
                message_id=video.message_id,
                content=video.file_id or "",
                caption=video.caption,
                file_name=file_name,
                duration=duration,
                transcription=transcription,
            )
            added_count += 1

        # Add polls (BufferedMessage objects) - as text representation
        for poll_msg in combined.polls:
            poll_content_parts = []
            question = poll_msg.poll_question or "Unknown"
            options = poll_msg.poll_options or []
            poll_content_parts.append(f'📊 Poll: "{question}"')
            for i, opt in enumerate(options, 1):
                poll_content_parts.append(f"  {i}. {opt}")
            poll_content = "\n".join(poll_content_parts)

            await collect_service.add_item(
                chat_id=chat_id,
                item_type=CollectItemType.TEXT,  # Store polls as text
                message_id=poll_msg.message_id,
                content=poll_content,
            )
            added_count += 1

        logger.info(f"Added {added_count} items to collect queue for chat {chat_id}")

        # Collect all transcriptions to check for trigger keywords
        all_transcriptions = []
        session = await collect_service.get_session(chat_id)
        if session:
            for item in session.items:
                if item.transcription:
                    all_transcriptions.append(item.transcription)

        # Check if any transcription contains a trigger keyword
        trigger_found = False
        for transcription in all_transcriptions:
            if collect_service.check_trigger_keywords(transcription):
                logger.info(
                    f"Trigger keyword found in transcription for chat {chat_id}"
                )
                trigger_found = True
                break

        # If trigger found, process collected items
        if trigger_found and session and session.item_count > 0:
            logger.info(
                f"Auto-processing {session.item_count} collected items due to trigger in transcription"
            )
            await self._process_collect_trigger(combined)
            return

        # React with 👀 to non-voice/video messages (voices/videos already got reactions during transcription)
        voice_video_ids = {v.message_id for v in combined.voices} | {
            v.message_id for v in combined.videos
        }

        non_transcribed_ids = [
            msg.message_id
            for msg in combined.messages
            if msg.message_id not in voice_video_ids
        ]
        if non_transcribed_ids:
            self._mark_as_read_sync(chat_id, non_transcribed_ids, "👀")

    async def _process_collect_trigger(self, combined: CombinedMessage) -> None:
        """Process collected items when trigger keyword is detected."""
        from ..services.collect_service import TRIGGER_KEYWORDS
        from .handlers import _collect_go

        # Use actual update/context from the combined message
        update = combined.primary_update
        context = combined.primary_context

        # Extract any additional prompt from the text (remove trigger keywords)
        prompt = combined.combined_text
        prompt_lower = prompt.lower()
        for keyword in TRIGGER_KEYWORDS:
            # Find the keyword position and remove it (case-insensitive)
            idx = prompt_lower.find(keyword)
            if idx != -1:
                # Remove the keyword from the original prompt (preserve case for rest)
                prompt = prompt[:idx] + prompt[idx + len(keyword) :]
                prompt_lower = prompt.lower()

        prompt = prompt.strip()

        logger.info(
            f"Processing collect trigger for chat {combined.chat_id}, prompt: '{prompt[:50] if prompt else 'none'}...'"
        )

        # Run in background task to avoid blocking webhook
        async def run_collect():
            try:
                await _collect_go(update, context, prompt)
            except Exception as e:
                logger.error(f"Error in collect_go: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=f"Error processing collected items: {str(e)[:100]}",
                    )
                except Exception:
                    pass

        create_tracked_task(run_collect(), name="collect_trigger")


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
