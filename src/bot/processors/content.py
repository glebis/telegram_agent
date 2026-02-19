"""
Content processor mixin — video and document handling.

Methods:
- _process_with_videos: Download, extract audio, transcribe, and route videos
- _process_documents: Download and route documents to Claude

Extracted from combined_processor.py as part of #152.
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ...core.config import get_settings
from ...core.i18n import get_user_locale
from ...services.media_validator import validate_media
from ...services.message_buffer import CombinedMessage
from ...services.reply_context import ReplyContext
from ...services.stt_service import get_stt_service
from ...utils.subprocess_helper import (
    download_telegram_file,
    extract_audio_from_video,
)
from ...utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)


class ContentProcessorMixin:
    """Mixin for video, document, contact, and poll processing."""

    if TYPE_CHECKING:
        # Provided by CombinedMessageProcessor / TextProcessorMixin / MediaProcessorMixin
        reply_service: Any
        _mark_as_read_sync: Any
        _send_typing_sync: Any
        _send_message_sync: Any
        _handle_transcription_routing: Any

    async def _process_with_videos(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process video messages - extract audio, transcribe, and process like voice."""

        from ..handlers import execute_claude_prompt

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

                    # Prepare video path (used by both Bot API and Telethon downloads)
                    video_filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
                    video_path = temp_dir / video_filename

                    # Check file size first (prevents wasting time on >20MB files)
                    from ...utils.subprocess_helper import get_telegram_file_info

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
                                    logger.info(
                                        f"📥 Video is {size_mb:.2f}MB (>20MB). Using Telethon MTProto downloader..."
                                    )

                                    # Build Telegram URL from forward context
                                    forward_url = None
                                    if (
                                        video_msg.forward_from_chat_username
                                        and video_msg.forward_message_id
                                    ):
                                        forward_url = f"https://t.me/{video_msg.forward_from_chat_username}/{video_msg.forward_message_id}"

                                    if not forward_url:
                                        # Cannot download - no public URL
                                        await message.reply_text(
                                            f"⚠️ Cannot download this {size_mb:.1f}MB video: forwarded from private chat.\n\n"
                                            f"To process:\n"
                                            f"1️⃣ Download it to your device\n"
                                            f"2️⃣ Send it directly to me (not as forward)"
                                        )
                                        continue

                                    # Use Telethon to download large file
                                    from ...services.telethon_service import (
                                        get_telethon_service,
                                    )

                                    # video_path already initialized above
                                    # Show progress message to user
                                    await message.reply_text(
                                        f"📥 Downloading {size_mb:.1f}MB video via Telethon...\n"
                                        f"⏱️ This may take ~{int(size_mb * 2 / 60)} minutes"
                                    )

                                    try:
                                        telethon_service = get_telethon_service()
                                        telethon_result = (
                                            await telethon_service.download_from_url(
                                                url=forward_url,
                                                output_path=video_path,
                                                timeout=int(
                                                    (size_mb * 2) + 120
                                                ),  # 2s per MB + 2min buffer
                                            )
                                        )

                                        if not telethon_result["success"]:
                                            await message.reply_text(
                                                f"❌ Download failed: {telethon_result['error']}"
                                            )
                                            continue

                                        logger.info(
                                            f"✅ Downloaded {telethon_result['size_mb']:.1f}MB via Telethon"
                                        )

                                        # Continue with audio extraction (skip Bot API download)
                                        download_result = type(
                                            "obj", (object,), {"success": True}
                                        )()

                                    except Exception as e:
                                        logger.error(
                                            f"Telethon download failed: {e}",
                                            exc_info=True,
                                        )
                                        await message.reply_text(
                                            f"❌ Failed to download video: {e}\n\n"
                                            f"Try downloading manually and sending directly."
                                        )
                                        continue
                        except Exception as e:
                            logger.warning(f"Could not parse file info: {e}")

                    # Download video via Bot API (only if not already downloaded via Telethon)
                    # video_path already initialized above
                    if not video_path.exists():
                        download_result = download_telegram_file(
                            file_id=video_msg.file_id,
                            bot_token=bot_token,
                            output_path=video_path,
                            timeout=180,  # Videos can be large
                        )
                    else:
                        # Already downloaded via Telethon
                        download_result = type("obj", (object,), {"success": True})()

                    if not download_result.success:
                        logger.error(
                            f"Failed to download video: {download_result.error}"
                        )
                        # Clean up temp file on download failure
                        video_path.unlink(missing_ok=True)
                        continue

                    logger.info(f"Downloaded video to: {video_path}")

                    # Validate downloaded video file
                    from ...services.media_validator import validate_video

                    video_val = validate_video(video_path, video_path.name)
                    if not video_val.valid:
                        logger.warning("Video validation failed: %s", video_val.reason)
                        video_path.unlink(missing_ok=True)
                        continue

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
                    from ...services.keyboard_service import get_whisper_use_locale

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

        from ...services.keyboard_service import (
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
            from ...services.voice_service import get_voice_service

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

        from ..handlers import execute_claude_prompt

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

                # Get filename — sanitize to prevent path traversal
                original_name = "document"
                if doc_msg.message.document and doc_msg.message.document.file_name:
                    # Strip directory components to prevent traversal attacks
                    original_name = (
                        Path(doc_msg.message.document.file_name).name or "document"
                    )

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
