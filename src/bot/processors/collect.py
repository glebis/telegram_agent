"""
Collect processor mixin — collect mode queue and trigger handling.

Methods:
- _transcribe_voice_for_collect: Transcribe a single voice message
- _transcribe_video_for_collect: Transcribe a single video message
- _add_to_collect_queue: Add items to collect queue with reactions
- _process_collect_trigger: Process collected items on trigger keyword

Extracted from combined_processor.py as part of #152.
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ...core.i18n import get_user_locale
from ...services.message_buffer import BufferedMessage, CombinedMessage
from ...services.stt_service import get_stt_service
from ...utils.subprocess_helper import (
    download_telegram_file,
    extract_audio_from_video,
)
from ...utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)


class CollectProcessorMixin:
    """Mixin for collect mode queue and trigger handling."""

    if TYPE_CHECKING:
        # Provided by CombinedMessageProcessor / TextProcessorMixin
        _mark_as_read_sync: Any
        _send_message_sync: Any

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
            from ...services.keyboard_service import get_whisper_use_locale

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
            from ...services.keyboard_service import get_whisper_use_locale

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
        from ...services.collect_service import CollectItemType, get_collect_service

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
            duration: Optional[int] = None
            if voice.message:
                raw_dur = (
                    voice.message.voice.duration
                    if voice.message.voice
                    else voice.message.audio.duration if voice.message.audio else None
                )
                if raw_dur is not None:
                    from datetime import timedelta

                    duration = (
                        int(raw_dur.total_seconds())
                        if isinstance(raw_dur, timedelta)
                        else int(raw_dur)
                    )

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
                from ...services.keyboard_service import get_show_transcript as _get_st

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
            vid_duration: Optional[int] = None
            file_name = None
            if video.message and video.message.video:
                from datetime import timedelta

                raw_vd = video.message.video.duration
                vid_duration = (
                    int(raw_vd.total_seconds())
                    if isinstance(raw_vd, timedelta)
                    else int(raw_vd)
                )
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
                from ...services.keyboard_service import (
                    get_show_transcript as _get_st_v,
                )

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
                duration=vid_duration,
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
        from ...services.collect_service import TRIGGER_KEYWORDS
        from ..handlers import _collect_go

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
