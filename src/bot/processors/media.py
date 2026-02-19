"""
Media processor mixin — image and voice handling.

Methods:
- _process_with_images: Route images to Claude or LLM handler
- _send_images_to_claude: Download, validate, and send images to Claude
- _process_with_voice: Download, transcribe, and route voice messages
- _handle_transcription_routing: Voice routing UI for non-Claude mode

Extracted from combined_processor.py as part of #152.
"""

import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ...core.config import get_settings
from ...core.error_messages import sanitize_error
from ...core.i18n import get_user_locale
from ...services.media_validator import strip_metadata, validate_media
from ...services.message_buffer import CombinedMessage
from ...services.reply_context import ReplyContext
from ...services.stt_service import get_stt_service
from ...utils.subprocess_helper import download_telegram_file
from ...utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)


class MediaProcessorMixin:
    """Mixin for image and voice message processing."""

    if TYPE_CHECKING:
        # Provided by CombinedMessageProcessor / TextProcessorMixin at runtime
        reply_service: Any
        _mark_as_read_sync: Any
        _send_typing_sync: Any
        _send_message_sync: Any

    async def _process_with_images(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process message with images."""
        from ..message_handlers import handle_image_message

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
        from ..handlers import execute_claude_prompt

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
                        text=sanitize_error(e, context="processing image"),
                    )
                except Exception:
                    pass

        create_tracked_task(run_claude(), name="claude_image_analysis")

    async def _process_with_voice(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process message with voice."""

        from ...services.voice_service import get_voice_service
        from ..handlers import execute_claude_prompt

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

                # Validate downloaded voice file
                from ...services.media_validator import validate_voice

                voice_val = validate_voice(audio_path, audio_path.name)
                if not voice_val.valid:
                    logger.warning("Voice validation failed: %s", voice_val.reason)
                    continue

                # Determine transcription language
                from ...services.keyboard_service import get_whisper_use_locale

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

        from ...services.keyboard_service import get_show_transcript

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
            from ...services.trail_review_service import get_trail_review_service

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
                            text=sanitize_error(e, context="processing voice message"),
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

        from ...services.link_service import track_capture
        from ...services.voice_service import get_voice_service

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
                        {"text": "📝 Daily", "callback_data": f"voice:daily:{msg_id}"},
                        {"text": "📥 Inbox", "callback_data": f"voice:inbox:{msg_id}"},
                    ],
                    [
                        {
                            "text": "📋 Create Task",
                            "callback_data": f"voice:create_task:{msg_id}",
                        },
                    ],
                    [
                        {"text": "❌ Done", "callback_data": f"voice:done:{msg_id}"},
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
