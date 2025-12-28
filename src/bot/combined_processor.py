"""
Combined Message Processor

Processes combined messages from the MessageBuffer.
Handles reply context injection and routes to appropriate handlers.
"""

import asyncio
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from ..core.config import get_settings
from ..services.message_buffer import CombinedMessage, BufferedMessage
from ..services.reply_context import (
    get_reply_context_service,
    ReplyContext,
    MessageType,
)
from ..utils.task_tracker import create_tracked_task
from ..utils.subprocess_helper import download_telegram_file, transcribe_audio, extract_audio_from_video

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
            f"text_len={len(combined.combined_text)}"
        )

        # Check for /claude command first - this takes priority
        if combined.has_claude_command():
            await self._process_claude_command(combined)
            return

        # Check for collect mode
        from ..services.collect_service import get_collect_service

        collect_service = get_collect_service()
        is_collecting = await collect_service.is_collecting(combined.chat_id)

        if is_collecting:
            # Check for trigger keywords that should process the collected items
            if collect_service.check_trigger_keywords(combined.combined_text):
                logger.info(f"Collect trigger keyword detected in chat {combined.chat_id}")
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

        # Check if Claude mode is active
        # Use cache-only check to avoid database deadlocks during message processing
        from .handlers import _claude_mode_cache
        from ..services.claude_code_service import is_claude_code_admin

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
                    f"Error processing your message. Please try again."
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
        from .handlers import execute_claude_prompt
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

        if is_claude_mode:
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
    ) -> None:
        """Send images to Claude for analysis."""
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

                    logger.info(f"Downloading image using secure subprocess helper...")
                    result = download_telegram_file(
                        file_id=file_id,
                        bot_token=bot_token,
                        output_path=image_path,
                        timeout=120,
                    )

                    if result.success:
                        image_paths.append(str(image_path))
                        logger.info(f"Downloaded image for Claude: {image_path}")
                    else:
                        logger.error(f"Download failed: {result.error} - {result.stderr}")

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
        import asyncio

        async def run_claude():
            try:
                await execute_claude_prompt(update, context, full_prompt)
            except Exception as e:
                logger.error(f"Error in image Claude execution: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=f"Error processing image: {str(e)[:100]}"
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
                    logger.warning(f"Failed to react to {msg_id}: {result.get('description', 'Unknown error')}")
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
        from .handlers import execute_claude_prompt
        from ..services.voice_service import get_voice_service
        import subprocess
        import json

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        voice_service = get_voice_service()

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

                # Transcribe using secure subprocess helper
                groq_api_key = os.environ.get("GROQ_API_KEY", "")
                if not groq_api_key:
                    logger.error("GROQ_API_KEY not set!")
                    continue

                transcribe_result = transcribe_audio(
                    audio_path=audio_path,
                    api_key=groq_api_key,
                    model="whisper-large-v3-turbo",
                    language="en",
                    timeout=90,
                )

                # Clean up temp file
                try:
                    audio_path.unlink()
                except Exception:
                    pass

                transcribed_text = None
                if transcribe_result.success:
                    import json
                    try:
                        data = json.loads(transcribe_result.stdout)
                        transcribed_text = data.get("text", "").strip()
                    except json.JSONDecodeError:
                        # Fallback to raw output
                        transcribed_text = transcribe_result.stdout.strip()
                else:
                    logger.error(f"Transcription error: {transcribe_result.error}")

                if transcribed_text:
                    transcriptions.append(transcribed_text)
                    logger.info(f"Transcribed: {transcribed_text[:100]}...")
                else:
                    logger.error(f"Transcription failed: {transcribe_result.stderr}")

            except Exception as e:
                logger.error(f"Error processing voice: {e}", exc_info=True)

        if not transcriptions:
            self._send_message_sync(combined.chat_id, "Failed to transcribe voice messages.")
            return

        # ALWAYS send transcript as a reply to the first voice message
        transcript_text = "\n".join(transcriptions)
        first_voice_msg_id = combined.voices[0].message_id if combined.voices else None
        self._send_message_sync(
            combined.chat_id,
            f"📝 <b>Transcript:</b>\n\n{transcript_text}",
            parse_mode="HTML",
            reply_to_message_id=first_voice_msg_id,
        )

        # Mark as "completed" after successful transcription with 👍
        self._mark_as_read_sync(combined.chat_id, message_ids, "👍")

        # Combine transcriptions with text
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
            logger.info(f"Added forward context to voice prompt: {forward_context}")

        if is_claude_mode:
            # Run Claude execution in a background task to avoid blocking
            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_text)
                except Exception as e:
                    logger.error(f"Error in voice Claude execution: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=f"Error processing voice: {str(e)[:100]}"
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_voice_analysis")
        else:
            # Use existing voice handler logic for routing
            from .message_handlers import handle_voice_message
            # For non-Claude mode, use existing handler
            # But we've already transcribed, so send as text
            await self._handle_transcription_routing(
                combined,
                full_text,
                transcriptions[0] if transcriptions else "",
            )

    async def _handle_transcription_routing(
        self,
        combined: CombinedMessage,
        full_text: str,
        primary_transcription: str,
    ) -> None:
        """Handle routing for transcribed voice (non-Claude mode)."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from ..services.voice_service import get_voice_service
        from ..services.link_service import track_capture

        message = combined.primary_message
        voice_service = get_voice_service()

        # Detect intent
        intent_info = voice_service.detect_intent(primary_transcription)
        formatted = voice_service.format_for_obsidian(primary_transcription, intent_info)
        destination = intent_info.get("destination", "daily")

        # Create routing buttons
        processing_msg = await message.reply_text("Processing voice...")
        msg_id = processing_msg.message_id

        keyboard = [
            [
                InlineKeyboardButton("Daily", callback_data=f"voice:daily:{msg_id}"),
                InlineKeyboardButton("Inbox", callback_data=f"voice:inbox:{msg_id}"),
            ],
            [
                InlineKeyboardButton("Task", callback_data=f"voice:task:{msg_id}"),
                InlineKeyboardButton("Done", callback_data=f"voice:done:{msg_id}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        intent_display = intent_info.get("intent", "quick").title()

        await processing_msg.edit_text(
            f"<b>Transcription</b>\n\n"
            f"{primary_transcription}\n\n"
            f"<i>Detected: {intent_display}</i>\n"
            f"<i>Will save to: {destination}</i>",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

        # Store for routing callback
        track_capture(msg_id, formatted)

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

    async def _process_with_videos(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process video messages - extract audio, transcribe, and process like voice."""
        from .handlers import execute_claude_prompt
        import json

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

        # Create temp directory
        temp_dir = Path(tempfile.gettempdir()) / "telegram_videos"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Process each video - download, extract audio, transcribe
        transcriptions = []

        for video_msg in combined.videos:
            try:
                if not video_msg.file_id:
                    continue

                logger.info(f"Processing video file_id: {video_msg.file_id[:50]}...")

                # Download video
                video_filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
                video_path = temp_dir / video_filename

                download_result = download_telegram_file(
                    file_id=video_msg.file_id,
                    bot_token=bot_token,
                    output_path=video_path,
                    timeout=180,  # Videos can be large
                )

                if not download_result.success:
                    logger.error(f"Failed to download video: {download_result.error}")
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
                    continue

                logger.info(f"Extracted audio to: {audio_path}")

                # Transcribe audio
                groq_api_key = os.environ.get("GROQ_API_KEY", "")
                if not groq_api_key:
                    logger.error("GROQ_API_KEY not set!")
                    continue

                transcribe_result = transcribe_audio(
                    audio_path=audio_path,
                    api_key=groq_api_key,
                    model="whisper-large-v3-turbo",
                    language="en",
                    timeout=90,
                )

                # Clean up audio file
                try:
                    audio_path.unlink()
                except Exception:
                    pass

                if transcribe_result.success:
                    try:
                        data = json.loads(transcribe_result.stdout)
                        transcribed_text = data.get("text", "").strip()
                        if transcribed_text:
                            transcriptions.append(transcribed_text)
                            logger.info(f"Transcribed video: {transcribed_text[:100]}...")
                    except json.JSONDecodeError:
                        transcribed_text = transcribe_result.stdout.strip()
                        if transcribed_text:
                            transcriptions.append(transcribed_text)
                else:
                    logger.error(f"Transcription failed: {transcribe_result.error}")

            except Exception as e:
                logger.error(f"Error processing video: {e}", exc_info=True)

        if not transcriptions:
            # Fall back to caption-only processing if no audio could be extracted
            prompt = combined.combined_text or "Video message received (no audio)"
            prompt = prompt.encode('utf-8', errors='replace').decode('utf-8')

            forward_context = combined.get_forward_context()
            if forward_context:
                prompt = f"{forward_context}\n\n{prompt}"

            if is_claude_mode:
                async def run_claude():
                    try:
                        await execute_claude_prompt(update, context, prompt)
                    except Exception as e:
                        logger.error(f"Error in video Claude execution: {e}", exc_info=True)

                create_tracked_task(run_claude(), name="claude_video_caption")
            else:
                await message.reply_text(
                    "Could not extract audio from video. Enable Claude mode to discuss it."
                )
            return

        # ALWAYS send transcript as a reply to the first video message
        transcript_text = "\n".join(transcriptions)
        first_video_msg_id = combined.videos[0].message_id if combined.videos else None
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

        if is_claude_mode:
            # Run Claude execution in a background task
            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_text)
                except Exception as e:
                    logger.error(f"Error in video Claude execution: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=f"Error processing video: {str(e)[:100]}"
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_video_transcript")
        else:
            # Use voice routing for non-Claude mode
            from ..services.voice_service import get_voice_service
            voice_service = get_voice_service()

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
        from .handlers import execute_claude_prompt
        from pathlib import Path
        import uuid

        logger.info(
            f"_process_documents: claude_mode={is_claude_mode}, "
            f"docs={len(combined.documents)}, text_len={len(combined.combined_text)}"
        )

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        if not is_claude_mode:
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
                    logger.error(f"Error in document Claude execution: {e}", exc_info=True)

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
                        logger.error(f"Error in document Claude execution: {e}", exc_info=True)

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
        import asyncio

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
                    # Text-only prompt
                    logger.info(f"Calling execute_claude_prompt with {len(full_prompt)} chars")
                    await execute_claude_prompt(update, context, full_prompt)
                    logger.info("execute_claude_prompt completed")
            except Exception as e:
                logger.error(f"Error in _process_claude_command: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=f"Error processing Claude command: {str(e)[:100]}"
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
        from .message_handlers import handle_text_message, extract_urls, handle_link_message

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        text = combined.combined_text

        # Check for URLs first
        urls = extract_urls(text)

        if urls and not is_claude_mode:
            # Handle as link capture
            await handle_link_message(message, urls)
            return

        # Build full prompt with reply context
        if reply_context:
            full_prompt = self.reply_service.build_reply_prompt(
                reply_context,
                text,
                include_original=True,
            )

            # If replying to Claude response, use that session
            if reply_context.message_type == MessageType.CLAUDE_RESPONSE:
                # Force use of the same session
                if reply_context.session_id:
                    context.user_data["force_session_id"] = reply_context.session_id
                    logger.info(f"Forcing session: {reply_context.session_id}")

        else:
            full_prompt = text

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to text prompt: {forward_context}")

        if is_claude_mode:
            # Run Claude execution in a background task to avoid blocking webhook
            import asyncio

            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_prompt)
                except Exception as e:
                    logger.error(f"Error in _process_text Claude execution: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=f"Error processing message: {str(e)[:100]}"
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_text")
        else:
            # Use existing text handler
            await handle_text_message(update, context)

    async def _transcribe_voice_for_collect(
        self, voice_msg: BufferedMessage, chat_id: int
    ) -> Optional[str]:
        """Transcribe a voice message and return the transcription."""
        import json
        import tempfile as tf

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        groq_api_key = os.environ.get("GROQ_API_KEY", "")

        if not bot_token or not groq_api_key:
            logger.error("TELEGRAM_BOT_TOKEN or GROQ_API_KEY not set")
            return None

        if not voice_msg.file_id:
            return None

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

            # Transcribe
            transcribe_result = transcribe_audio(
                audio_path=audio_path,
                api_key=groq_api_key,
                model="whisper-large-v3-turbo",
                language="en",
                timeout=90,
            )

            # Clean up
            try:
                audio_path.unlink()
            except Exception:
                pass

            if transcribe_result.success:
                try:
                    data = json.loads(transcribe_result.stdout)
                    return data.get("text", "").strip()
                except json.JSONDecodeError:
                    return transcribe_result.stdout.strip()
            else:
                logger.error(f"Transcription failed: {transcribe_result.error}")
                return None

        except Exception as e:
            logger.error(f"Error transcribing voice: {e}", exc_info=True)
            return None

    async def _transcribe_video_for_collect(
        self, video_msg: BufferedMessage, chat_id: int
    ) -> Optional[str]:
        """Transcribe a video message and return the transcription."""
        import json

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        groq_api_key = os.environ.get("GROQ_API_KEY", "")

        if not bot_token or not groq_api_key:
            logger.error("TELEGRAM_BOT_TOKEN or GROQ_API_KEY not set")
            return None

        if not video_msg.file_id:
            return None

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

            # Clean up video
            try:
                video_path.unlink()
            except Exception:
                pass

            if not extract_result.success:
                logger.error(f"Failed to extract audio: {extract_result.error}")
                return None

            # Transcribe
            transcribe_result = transcribe_audio(
                audio_path=audio_path,
                api_key=groq_api_key,
                model="whisper-large-v3-turbo",
                language="en",
                timeout=90,
            )

            # Clean up audio
            try:
                audio_path.unlink()
            except Exception:
                pass

            if transcribe_result.success:
                try:
                    data = json.loads(transcribe_result.stdout)
                    return data.get("text", "").strip()
                except json.JSONDecodeError:
                    return transcribe_result.stdout.strip()
            else:
                logger.error(f"Transcription failed: {transcribe_result.error}")
                return None

        except Exception as e:
            logger.error(f"Error transcribing video: {e}", exc_info=True)
            return None

    async def _add_to_collect_queue(self, combined: CombinedMessage) -> None:
        """Add items from combined message to the collect queue and react with 👀.

        Voice and video messages are transcribed immediately, with transcription
        sent as a reply to the original message.
        """
        from ..services.collect_service import get_collect_service, CollectItemType
        from telegram import ReactionTypeEmoji

        collect_service = get_collect_service()
        chat_id = combined.chat_id
        added_count = 0

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
            logger.info(f"Transcribing voice/audio message {voice.message_id} for collect queue")
            self._mark_as_read_sync(chat_id, [voice.message_id], "👀")

            transcription = await self._transcribe_voice_for_collect(voice, chat_id)

            if transcription:
                # React with 👍 to show transcription succeeded
                self._mark_as_read_sync(chat_id, [voice.message_id], "👍")
                logger.info(f"Transcribed voice {voice.message_id}: {transcription[:50]}...")

                # Send brief transcript preview as reply
                preview = transcription[:200] + "..." if len(transcription) > 200 else transcription
                self._send_message_sync(chat_id, f"📝 {preview}", reply_to_message_id=voice.message_id)
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
            logger.info(f"Transcribing video message {video.message_id} for collect queue")
            self._mark_as_read_sync(chat_id, [video.message_id], "👀")

            transcription = await self._transcribe_video_for_collect(video, chat_id)

            if transcription:
                # React with 👍 to show transcription succeeded
                self._mark_as_read_sync(chat_id, [video.message_id], "👍")
                logger.info(f"Transcribed video {video.message_id}: {transcription[:50]}...")

                # Send brief transcript preview as reply
                preview = transcription[:200] + "..." if len(transcription) > 200 else transcription
                self._send_message_sync(chat_id, f"🎬 {preview}", reply_to_message_id=video.message_id)
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

        logger.info(f"Added {added_count} items to collect queue for chat {chat_id}")

        # React with 👀 to non-voice/video messages (voices/videos already got reactions during transcription)
        voice_video_ids = {v.message_id for v in combined.voices} | {v.message_id for v in combined.videos}

        try:
            for msg in combined.messages:
                # Skip voice/video - they already got reactions during transcription
                if msg.message_id in voice_video_ids:
                    continue

                try:
                    # Use context.bot if available, otherwise use primary_message
                    bot = combined.primary_message._bot
                    await bot.set_message_reaction(
                        chat_id=chat_id,
                        message_id=msg.message_id,
                        reaction=[ReactionTypeEmoji("👀")],
                    )
                except Exception as e:
                    logger.debug(f"Could not react to message {msg.message_id}: {e}")
        except Exception as e:
            logger.error(f"Error reacting to collected messages: {e}")

    async def _process_collect_trigger(self, combined: CombinedMessage) -> None:
        """Process collected items when trigger keyword is detected."""
        from .handlers import _collect_go
        from ..services.collect_service import TRIGGER_KEYWORDS

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
                prompt = prompt[:idx] + prompt[idx + len(keyword):]
                prompt_lower = prompt.lower()

        prompt = prompt.strip()

        logger.info(f"Processing collect trigger for chat {combined.chat_id}, prompt: '{prompt[:50] if prompt else 'none'}...'")

        # Run in background task to avoid blocking webhook
        async def run_collect():
            try:
                await _collect_go(update, context, prompt)
            except Exception as e:
                logger.error(f"Error in collect_go: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=f"Error processing collected items: {str(e)[:100]}"
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
