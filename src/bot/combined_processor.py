"""
Combined Message Processor

Processes combined messages from the MessageBuffer.
Handles reply context injection and routes to appropriate handlers.
"""

import logging
import tempfile
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..services.message_buffer import CombinedMessage, BufferedMessage
from ..services.reply_context import (
    get_reply_context_service,
    ReplyContext,
    MessageType,
)

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
            f"voices={len(combined.voices)}, text_len={len(combined.combined_text)}"
        )

        # Check for /claude command first - this takes priority
        if combined.has_claude_command():
            await self._process_claude_command(combined)
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

        # Route based on content
        try:
            if combined.has_images():
                await self._process_with_images(combined, reply_context, is_claude_mode)
            elif combined.has_voice():
                await self._process_with_voice(combined, reply_context, is_claude_mode)
            elif combined.contacts:
                await self._process_contacts(combined)
            elif combined.has_documents():
                await self._process_documents(combined, reply_context, is_claude_mode)
            elif combined.combined_text:
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
        from pathlib import Path
        import uuid

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        # Download images to temp location
        image_paths = []

        for img_msg in combined.images:
            try:
                if not img_msg.file_id:
                    continue

                # Create temp directory
                temp_dir = Path.home() / "Research" / "vault" / "temp_images"
                temp_dir.mkdir(parents=True, exist_ok=True)

                # Download
                bot = context.bot
                file = await bot.get_file(img_msg.file_id)

                # Generate filename
                ext = ".jpg"
                if img_msg.message.document and img_msg.message.document.file_name:
                    ext = Path(img_msg.message.document.file_name).suffix or ".jpg"

                image_filename = f"telegram_{uuid.uuid4().hex[:8]}{ext}"
                image_path = temp_dir / image_filename

                await file.download_to_drive(str(image_path))
                image_paths.append(str(image_path))
                logger.info(f"Downloaded image for Claude: {image_path}")

            except Exception as e:
                logger.error(f"Error downloading image: {e}", exc_info=True)

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

        # Send to Claude
        await execute_claude_prompt(update, context, full_prompt)

    async def _process_with_voice(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process message with voice."""
        from .handlers import execute_claude_prompt
        from ..services.voice_service import get_voice_service

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        voice_service = get_voice_service()

        # Transcribe all voice messages
        transcriptions = []

        for voice_msg in combined.voices:
            try:
                if not voice_msg.file_id:
                    continue

                # Download voice file
                bot = context.bot
                file = await bot.get_file(voice_msg.file_id)

                with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                    await file.download_to_drive(tmp.name)
                    audio_path = tmp.name

                # Transcribe
                success, result = await voice_service.transcribe(audio_path)

                import os
                os.unlink(audio_path)

                if success:
                    transcriptions.append(result["text"])
                else:
                    logger.error(f"Transcription failed: {result.get('error')}")

            except Exception as e:
                logger.error(f"Error processing voice: {e}", exc_info=True)

        if not transcriptions:
            await message.reply_text("Failed to transcribe voice messages.")
            return

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

        if is_claude_mode:
            # Send to Claude
            await execute_claude_prompt(update, context, full_text)
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

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        if not is_claude_mode:
            # For non-Claude mode, just acknowledge
            await message.reply_text(
                "Documents received. Enable Claude mode to analyze them."
            )
            return

        # Download documents for Claude
        doc_paths = []

        for doc_msg in combined.documents:
            try:
                if not doc_msg.file_id:
                    continue

                # Create temp directory
                temp_dir = Path.home() / "Research" / "vault" / "temp_docs"
                temp_dir.mkdir(parents=True, exist_ok=True)

                # Download
                bot = context.bot
                file = await bot.get_file(doc_msg.file_id)

                # Get filename
                original_name = "document"
                if doc_msg.message.document and doc_msg.message.document.file_name:
                    original_name = doc_msg.message.document.file_name

                doc_filename = f"{uuid.uuid4().hex[:8]}_{original_name}"
                doc_path = temp_dir / doc_filename

                await file.download_to_drive(str(doc_path))
                doc_paths.append(str(doc_path))
                logger.info(f"Downloaded document for Claude: {doc_path}")

            except Exception as e:
                logger.error(f"Error downloading document: {e}", exc_info=True)

        if not doc_paths:
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
        asyncio.create_task(run_claude())

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

        if is_claude_mode:
            await execute_claude_prompt(update, context, full_prompt)
        else:
            # Use existing text handler
            await handle_text_message(update, context)


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
