"""
Message Buffer Service

Buffers incoming messages for a short window to combine split messages,
media groups, and rapid-fire inputs into a single processing unit.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from telegram import Message, Update
from telegram.ext import ContextTypes

from src.services.media_validator import validate_upload_mime_type
from src.utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)


@dataclass
class BufferedMessage:
    """A single buffered message with metadata."""

    message_id: int
    message: Message
    update: Update
    context: ContextTypes.DEFAULT_TYPE
    timestamp: datetime
    message_type: (
        str  # "text", "photo", "voice", "document", "contact", "claude_command"
    )
    media_group_id: Optional[str] = None

    # Extracted content
    text: Optional[str] = None
    caption: Optional[str] = None
    file_id: Optional[str] = None
    file_path: Optional[str] = None  # For downloaded files

    # Command flags - indicate this is a /claude, /meta, or /dev prompt
    is_claude_command: bool = False
    is_meta_command: bool = False
    is_dev_command: bool = False
    command_type: Optional[str] = None  # "claude", "meta", or "dev"

    # Poll data (optional)
    poll_question: Optional[str] = None
    poll_options: Optional[List[str]] = None
    poll_type: Optional[str] = None  # "regular" or "quiz"
    poll_is_anonymous: Optional[bool] = None
    poll_total_voter_count: Optional[int] = None
    poll_id: Optional[str] = None

    # Forward info (optional)
    forward_from_username: Optional[str] = None
    forward_from_first_name: Optional[str] = None
    forward_sender_name: Optional[str] = None  # Privacy-protected forwards
    forward_from_chat_title: Optional[str] = None  # Channel forwards
    forward_from_chat_username: Optional[str] = None  # Channel username for URL
    forward_message_id: Optional[int] = None  # Original message ID for URL
    is_forwarded: bool = False


@dataclass
class CombinedMessage:
    """Combined message ready for processing."""

    chat_id: int
    user_id: int
    messages: List[BufferedMessage]

    # Combined content
    combined_text: str = ""
    images: List[BufferedMessage] = field(default_factory=list)
    voices: List[BufferedMessage] = field(default_factory=list)
    videos: List[BufferedMessage] = field(default_factory=list)
    documents: List[BufferedMessage] = field(default_factory=list)
    contacts: List[BufferedMessage] = field(default_factory=list)
    polls: List[BufferedMessage] = field(default_factory=list)

    # Link + comment pair detection
    link_comment_pair: Optional[Dict[str, str]] = None

    # Reply context
    reply_to_message_id: Optional[int] = None
    reply_to_message_text: Optional[str] = None  # Text/caption from replied message
    reply_to_message_type: Optional[str] = (
        None  # Type of replied message (text, voice, photo, etc.)
    )
    reply_to_message_from_bot: bool = False  # Whether replied message is from bot
    reply_to_message_date: Optional["datetime"] = None  # Timestamp of replied message

    # Use first message's update/context for processing
    @property
    def primary_update(self) -> Update:
        return self.messages[0].update

    @property
    def primary_context(self) -> ContextTypes.DEFAULT_TYPE:
        return self.messages[0].context

    @property
    def primary_message(self) -> Message:
        return self.messages[0].message

    def has_images(self) -> bool:
        return len(self.images) > 0

    def has_voice(self) -> bool:
        return len(self.voices) > 0

    def has_documents(self) -> bool:
        return len(self.documents) > 0

    def has_videos(self) -> bool:
        return len(self.videos) > 0

    def has_polls(self) -> bool:
        return len(self.polls) > 0

    def has_text_only(self) -> bool:
        return (
            len(self.combined_text) > 0
            and not self.has_images()
            and not self.has_voice()
            and not self.has_documents()
            and not self.has_polls()
        )

    def has_claude_command(self) -> bool:
        """Check if any message in the buffer is a /claude command."""
        return any(m.is_claude_command for m in self.messages)

    def has_meta_command(self) -> bool:
        """Check if any message in the buffer is a /meta command."""
        return any(m.is_meta_command for m in self.messages)

    def has_dev_command(self) -> bool:
        """Check if any message in the buffer is a /dev command."""
        return any(m.is_dev_command for m in self.messages)

    def has_command(self) -> bool:
        """Check if any message in the buffer is a /claude, /meta, or /dev command."""
        return any(
            m.is_claude_command or m.is_meta_command or m.is_dev_command
            for m in self.messages
        )

    def get_claude_command_message(self) -> Optional["BufferedMessage"]:
        """Get the /claude command message if present."""
        for m in self.messages:
            if m.is_claude_command:
                return m
        return None

    def get_command_message(self) -> Optional["BufferedMessage"]:
        """Get the command message (/claude, /meta, or /dev) if present."""
        for m in self.messages:
            if m.is_claude_command or m.is_meta_command or m.is_dev_command:
                return m
        return None

    def has_forwarded_messages(self) -> bool:
        """Check if any message is forwarded."""
        return any(m.is_forwarded for m in self.messages)

    def get_forward_context(self) -> Optional[str]:
        """Build forward context string for first forwarded message."""
        from .vault_user_service import build_forward_context

        for msg in self.messages:
            if msg.is_forwarded:
                forward_info = {
                    "forward_from_username": msg.forward_from_username,
                    "forward_from_first_name": msg.forward_from_first_name,
                    "forward_sender_name": msg.forward_sender_name,
                    "forward_from_chat_title": msg.forward_from_chat_title,
                    "forward_from_chat_username": msg.forward_from_chat_username,
                    "forward_message_id": msg.forward_message_id,
                }
                return build_forward_context(forward_info)
        return None

    def get_link_comment_context(self) -> Optional[str]:
        """Build semantic context string for link + comment pairs."""
        if not self.link_comment_pair:
            return None
        link_text = self.link_comment_pair["link_text"]
        comment = self.link_comment_pair["comment"]
        return f"User shared link: {link_text}\n\nComment: {comment}"


# URL pattern for link-comment detection (same as message_handlers.URL_PATTERN)
_URL_PATTERN = re.compile(
    r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*", re.IGNORECASE
)


def _detect_link_comment_pair(
    messages: List[BufferedMessage],
) -> Optional[Dict[str, str]]:
    """
    Detect when 2 buffered messages form a link + comment pair.

    Returns {"link_text": ..., "comment": ...} if:
    - Exactly 2 messages, both text, neither is a reply
    - First message is link-dominant (URL chars >70% or text ≤100 chars with a URL)
    - Second message is commentary (no URLs, or URL chars <30%)
    - Neither starts with / (not a command)
    """
    if len(messages) != 2:
        return None

    first, second = messages

    # Both must be text messages
    if first.message_type != "text" or second.message_type != "text":
        return None

    # Neither should have text that is None
    if not first.text or not second.text:
        return None

    # Neither should be a reply
    if first.message.reply_to_message or second.message.reply_to_message:
        return None

    # Neither should be a command
    if first.text.startswith("/") or second.text.startswith("/"):
        return None

    # First message: link-dominant check
    first_urls = _URL_PATTERN.findall(first.text)
    if not first_urls:
        return None

    first_url_chars = sum(len(u) for u in first_urls)
    first_total_chars = len(first.text.strip())

    if first_total_chars == 0:
        return None

    is_link_dominant = (
        first_url_chars / first_total_chars > 0.7 or first_total_chars <= 100
    )
    if not is_link_dominant:
        return None

    # Second message: commentary check (no URLs or URL chars < 30%)
    second_urls = _URL_PATTERN.findall(second.text)
    if second_urls:
        second_url_chars = sum(len(u) for u in second_urls)
        second_total_chars = len(second.text.strip())
        if second_total_chars > 0 and second_url_chars / second_total_chars >= 0.3:
            return None

    return {"link_text": first.text, "comment": second.text}


@dataclass
class BufferEntry:
    """Buffer entry for a specific (chat_id, user_id) pair."""

    messages: List[BufferedMessage] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None
    first_message_time: Optional[datetime] = None
    media_group_ids: set = field(default_factory=set)


# Type alias for the processing callback
ProcessCallback = Callable[[CombinedMessage], Coroutine[Any, Any, None]]


class MessageBufferService:
    """
    Buffers messages and combines them before processing.

    Features:
    - Groups messages by (chat_id, user_id)
    - Waits for buffer_timeout seconds after last message
    - Automatically groups Telegram media groups
    - Combines text, images, voice, documents
    - Respects max_messages and max_wait limits
    """

    def __init__(
        self,
        buffer_timeout: float = 2.5,  # Seconds to wait after last message
        max_messages: int = 20,  # Max messages before forced flush
        max_wait: float = 30.0,  # Max seconds to buffer
    ):
        self.buffer_timeout = buffer_timeout
        self.max_messages = max_messages
        self.max_wait = max_wait

        # Buffer storage: (chat_id, user_id) -> BufferEntry
        self._buffers: Dict[Tuple[int, int], BufferEntry] = {}

        # Lock to prevent race conditions when accessing _buffers
        self._buffer_lock = asyncio.Lock()

        # Processing callback
        self._process_callback: Optional[ProcessCallback] = None

        # Commands that bypass buffering (processed immediately)
        self._bypass_commands = {
            "/help",
            "/start",
            "/mode",
            "/cancel",
            "/gallery",
            "/note",
        }

        logger.info(
            f"MessageBuffer initialized: timeout={buffer_timeout}s, "
            f"max_messages={max_messages}, max_wait={max_wait}s"
        )

    def set_process_callback(self, callback: ProcessCallback) -> None:
        """Set the callback for processing combined messages."""
        self._process_callback = callback

    def _get_buffer_key(self, chat_id: int, user_id: int) -> Tuple[int, int]:
        """Get buffer key for a chat/user pair."""
        return (chat_id, user_id)

    async def add_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> bool:
        """
        Add a message to the buffer.

        Returns True if message was buffered, False if it should be processed immediately.
        """
        message = update.message
        if not message:
            return False

        chat = update.effective_chat
        user = update.effective_user

        if not chat or not user:
            return False

        chat_id = chat.id
        user_id = user.id

        # Check if this is a command that bypasses buffering
        if message.text and message.text.startswith("/"):
            cmd = message.text.split()[0].split("@")[0].lower()
            if cmd in self._bypass_commands:
                logger.debug(f"Command {cmd} bypasses buffer")
                return False

        # Determine message type and extract content
        buffered, rejection_reason = self._create_buffered_message(
            update, context, message
        )
        if not buffered:
            if rejection_reason:
                # MIME type validation failed — notify the user
                try:
                    await message.reply_text(rejection_reason)
                except Exception as e:
                    logger.error("Failed to send MIME rejection message: %s", e)
            return False

        # Get or create buffer entry (protected by lock)
        key = self._get_buffer_key(chat_id, user_id)

        async with self._buffer_lock:
            if key not in self._buffers:
                self._buffers[key] = BufferEntry()

            entry = self._buffers[key]

            # Track first message time
            if entry.first_message_time is None:
                entry.first_message_time = buffered.timestamp

            # Drop if buffer already at capacity (prevent unbounded growth)
            if len(entry.messages) >= self.max_messages:
                logger.warning(
                    f"Buffer at capacity ({self.max_messages}) for "
                    f"({chat_id}, {user_id}), dropping message"
                )
                return True  # Silently consumed

            # Add to buffer
            entry.messages.append(buffered)

            # Track media group
            if buffered.media_group_id:
                entry.media_group_ids.add(buffered.media_group_id)

            buffer_size = len(entry.messages)
            first_msg_time = entry.first_message_time

            logger.info(
                f"Buffered message {buffered.message_id} for ({chat_id}, {user_id}), "
                f"type={buffered.message_type}, buffer_size={buffer_size}"
            )

            # Check if we should force flush
            should_flush = False

            if buffer_size >= self.max_messages:
                logger.info(f"Buffer full ({self.max_messages}), forcing flush")
                should_flush = True

            if first_msg_time:
                elapsed = (datetime.now() - first_msg_time).total_seconds()
                if elapsed >= self.max_wait:
                    logger.info(
                        f"Max wait time reached ({self.max_wait}s), forcing flush"
                    )
                    should_flush = True

        # Flush or reset timer (outside lock to avoid deadlock)
        if should_flush:
            await self._flush_buffer(key)
        else:
            # Reset/start timer
            self._reset_timer(key)

        return True

    def _create_buffered_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        message: Message,
    ) -> Tuple[Optional[BufferedMessage], Optional[str]]:
        """Create a BufferedMessage from a Telegram message.

        Returns:
            Tuple of (buffered_message, rejection_reason).
            If the message is rejected, buffered_message is None and
            rejection_reason contains a user-facing explanation.
        """

        msg_type = None
        text = None
        caption = message.caption
        file_id = None
        media_group_id = getattr(message, "media_group_id", None)
        is_claude_command = False
        is_meta_command = False
        is_dev_command = False
        command_type = None

        # Check if caption contains /claude, /meta, or /dev command
        # (for images with captions)
        if caption:
            caption_stripped = caption.strip()
            detected_command = None

            if caption_stripped.startswith("/claude"):
                is_claude_command = True
                detected_command = "claude"
            elif caption_stripped.startswith("/meta"):
                is_meta_command = True
                detected_command = "meta"
            elif caption_stripped.startswith("/dev"):
                is_dev_command = True
                detected_command = "dev"

            if detected_command:
                command_type = detected_command
                # Extract the command text (everything after /<command>)
                parts = caption.split(None, 1)  # Split on first whitespace
                if len(parts) > 1:
                    text = parts[1]  # Command text after command
                else:
                    text = ""  # Just /<command> with no text
                preview = text[:50] if text else "(empty)"
                logger.info(
                    f"Detected /{detected_command} command in caption: " f"{preview}..."
                )

        if message.text:
            msg_type = "text"
            text = message.text
        elif message.photo:
            msg_type = "photo"
            file_id = message.photo[-1].file_id  # Largest photo
        elif message.voice:
            msg_type = "voice"
            file_id = message.voice.file_id
        elif message.audio:
            # Treat audio files (mp3, etc.) as voice messages for transcription
            msg_type = "voice"
            file_id = message.audio.file_id
            logger.info(f"Audio file treated as voice: {message.audio.mime_type}")
        elif message.video:
            msg_type = "video"
            file_id = message.video.file_id
        elif message.video_note:
            msg_type = "video"  # Treat video notes (circles) as videos
            file_id = message.video_note.file_id
        elif message.document:
            msg_type = "document"
            file_id = message.document.file_id
            # Check if it's an image document
            if message.document.mime_type and message.document.mime_type.startswith(
                "image/"
            ):
                msg_type = "photo"  # Treat as photo
            # Check if it's an audio document (mp3, ogg, etc.)
            elif message.document.mime_type and message.document.mime_type.startswith(
                "audio/"
            ):
                msg_type = "voice"  # Treat as voice for transcription
                logger.info(
                    f"Audio document treated as voice: {message.document.mime_type}"
                )
        elif message.contact:
            msg_type = "contact"
        elif message.poll:
            msg_type = "poll"
            # Extract poll data for downstream processing
            poll = message.poll
            poll_question = poll.question
            poll_options = [opt.text for opt in poll.options]
            poll_type_val = poll.type  # "regular" or "quiz"
            poll_is_anonymous = poll.is_anonymous
            poll_total_voter_count = poll.total_voter_count
            poll_id_val = poll.id
            logger.info(
                f"Poll message detected: '{poll_question[:50]}...', "
                f"options={len(poll_options)}, type={poll_type_val}"
            )
        else:
            # Log all message attributes for debugging
            attrs = []
            for attr in [
                "text",
                "caption",
                "photo",
                "video",
                "video_note",
                "audio",
                "voice",
                "document",
                "sticker",
                "animation",
                "forward_origin",
            ]:
                val = getattr(message, attr, None)
                if val:
                    attrs.append(f"{attr}={type(val).__name__}")
            logger.info(f"Unknown message type, skipping buffer. Attrs: {attrs}")
            return None, None

        # -------------------------------------------------------------------
        # MIME type validation for file uploads (pre-download check)
        # -------------------------------------------------------------------
        if msg_type in ("voice", "photo", "video", "document") and file_id:
            declared_mime = None
            declared_file_name = None

            if message.voice:
                declared_mime = message.voice.mime_type
            elif message.audio:
                declared_mime = message.audio.mime_type
                declared_file_name = message.audio.file_name
            elif message.video:
                declared_mime = message.video.mime_type
                declared_file_name = getattr(message.video, "file_name", None)
            elif message.document:
                declared_mime = message.document.mime_type
                declared_file_name = message.document.file_name

            mime_result = validate_upload_mime_type(
                mime_type=declared_mime,
                file_name=declared_file_name,
                handler=msg_type,
            )
            if not mime_result.valid:
                logger.warning(
                    "Rejected file upload: chat_id=%s, handler=%s, "
                    "mime_type=%r, file_name=%r, reason=%s",
                    getattr(message.chat, "id", "?"),
                    msg_type,
                    declared_mime,
                    declared_file_name,
                    mime_result.reason,
                )
                return None, (
                    f"Unsupported file type: {declared_mime or 'unknown'}. "
                    f"This file cannot be processed as {msg_type}."
                )

        # Extract forward info (using new API: message.forward_origin)
        forward_from_username = None
        forward_from_first_name = None
        forward_sender_name = None
        forward_from_chat_title = None
        forward_from_chat_username = None
        forward_message_id = None
        is_forwarded = False

        # Use getattr for forward_origin (added in python-telegram-bot v21.0)
        # For older versions, fall back to deprecated forward_* attributes
        forward_origin = getattr(message, "forward_origin", None)
        if forward_origin:
            is_forwarded = True
            origin = forward_origin
            origin_type = getattr(origin, "type", None)
            logger.info(f"Forward origin detected: type={origin_type}")

            if origin_type == "user":
                # MessageOriginUser - user allowed linking
                sender = getattr(origin, "sender_user", None)
                if sender:
                    forward_from_username = sender.username
                    forward_from_first_name = sender.first_name
                    logger.info(
                        f"Forward detected: from @{forward_from_username or forward_from_first_name}"
                    )
            elif origin_type == "hidden_user":
                # MessageOriginHiddenUser - privacy-protected
                forward_sender_name = getattr(origin, "sender_user_name", None)
                logger.info(f"Forward detected (privacy): from {forward_sender_name}")
            elif origin_type == "channel":
                # MessageOriginChannel
                chat = getattr(origin, "chat", None)
                if chat:
                    forward_from_chat_title = chat.title
                    forward_from_chat_username = getattr(chat, "username", None)
                forward_message_id = getattr(origin, "message_id", None)
                url_part = ""
                if forward_from_chat_username and forward_message_id:
                    url_part = f" (https://t.me/{forward_from_chat_username}/{forward_message_id})"
                logger.info(
                    f"Forward detected (channel): from {forward_from_chat_title}{url_part}"
                )
            elif origin_type == "chat":
                # MessageOriginChat
                chat = getattr(origin, "sender_chat", None)
                if chat:
                    forward_from_chat_title = chat.title
                logger.info(f"Forward detected (chat): from {forward_from_chat_title}")
        else:
            # Fallback for python-telegram-bot < 21.0 (deprecated attributes)
            forward_from = getattr(message, "forward_from", None)
            forward_from_chat = getattr(message, "forward_from_chat", None)
            forward_sender_name_attr = getattr(message, "forward_sender_name", None)

            if forward_from:
                is_forwarded = True
                forward_from_username = forward_from.username
                forward_from_first_name = forward_from.first_name
                logger.info(
                    f"Forward detected (legacy): from @{forward_from_username or forward_from_first_name}"
                )
            elif forward_from_chat:
                is_forwarded = True
                forward_from_chat_title = forward_from_chat.title
                forward_from_chat_username = getattr(
                    forward_from_chat, "username", None
                )
                forward_message_id = getattr(message, "forward_from_message_id", None)
                logger.info(
                    f"Forward detected (legacy channel): from {forward_from_chat_title}"
                )
            elif forward_sender_name_attr:
                is_forwarded = True
                forward_sender_name = forward_sender_name_attr
                logger.info(
                    f"Forward detected (legacy hidden): from {forward_sender_name}"
                )

        # Build poll kwargs if this is a poll message
        poll_kwargs = {}
        if msg_type == "poll":
            poll_kwargs = {
                "poll_question": poll_question,
                "poll_options": poll_options,
                "poll_type": poll_type_val,
                "poll_is_anonymous": poll_is_anonymous,
                "poll_total_voter_count": poll_total_voter_count,
                "poll_id": poll_id_val,
            }

        return (
            BufferedMessage(
                message_id=message.message_id,
                message=message,
                update=update,
                context=context,
                timestamp=datetime.now(),
                message_type=msg_type,
                media_group_id=media_group_id,
                text=text,
                caption=caption,
                file_id=file_id,
                is_claude_command=is_claude_command,
                is_meta_command=is_meta_command,
                is_dev_command=is_dev_command,
                command_type=command_type,
                forward_from_username=forward_from_username,
                forward_from_first_name=forward_from_first_name,
                forward_sender_name=forward_sender_name,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_chat_username=forward_from_chat_username,
                forward_message_id=forward_message_id,
                is_forwarded=is_forwarded,
                **poll_kwargs,
            ),
            None,
        )

    def _reset_timer(self, key: Tuple[int, int]) -> None:
        """Reset the flush timer for a buffer."""
        entry = self._buffers.get(key)
        if not entry:
            return

        # Cancel existing timer
        if entry.timer_task and not entry.timer_task.done():
            entry.timer_task.cancel()

        # Start new timer
        entry.timer_task = create_tracked_task(
            self._timer_callback(key), name=f"buffer_timer_{key}"
        )

    async def _timer_callback(self, key: Tuple[int, int]) -> None:
        """Timer callback - flush buffer after timeout."""
        try:
            await asyncio.sleep(self.buffer_timeout)
            await self._flush_buffer(key)
        except asyncio.CancelledError:
            # Timer was cancelled (new message arrived)
            pass
        except Exception as e:
            logger.error(f"Error in timer callback: {e}", exc_info=True)

    async def _flush_buffer(self, key: Tuple[int, int]) -> None:
        """Flush buffer and process combined message."""
        # Use lock to prevent race with add_message and timer_callback
        async with self._buffer_lock:
            entry = self._buffers.pop(key, None)
            if not entry or not entry.messages:
                return

            # Cancel timer if running
            if entry.timer_task and not entry.timer_task.done():
                entry.timer_task.cancel()

        chat_id, user_id = key

        # Sort messages by message_id (handles out-of-order arrival)
        entry.messages.sort(key=lambda m: m.message_id)

        # Combine messages
        combined = self._combine_messages(chat_id, user_id, entry.messages)

        logger.info(
            f"Flushing buffer for ({chat_id}, {user_id}): "
            f"{len(entry.messages)} messages, "
            f"text_len={len(combined.combined_text)}, "
            f"images={len(combined.images)}, "
            f"voices={len(combined.voices)}, "
            f"videos={len(combined.videos)}, "
            f"docs={len(combined.documents)}, "
            f"contacts={len(combined.contacts)}, "
            f"polls={len(combined.polls)}"
        )

        # Process
        if self._process_callback:
            try:
                await self._process_callback(combined)
            except Exception as e:
                logger.error(f"Error processing combined message: {e}", exc_info=True)
        else:
            logger.warning("No process callback set for MessageBuffer")

    def _combine_messages(
        self,
        chat_id: int,
        user_id: int,
        messages: List[BufferedMessage],
    ) -> CombinedMessage:
        """Combine buffered messages into a single CombinedMessage."""

        combined = CombinedMessage(
            chat_id=chat_id,
            user_id=user_id,
            messages=messages,
        )

        text_parts = []

        for msg in messages:
            # Check for reply context (use first reply found)
            if combined.reply_to_message_id is None:
                reply_to = msg.message.reply_to_message
                if reply_to:
                    combined.reply_to_message_id = reply_to.message_id
                    combined.reply_to_message_date = reply_to.date  # Extract timestamp

                    # Check if replied message is from a bot
                    if reply_to.from_user:
                        combined.reply_to_message_from_bot = reply_to.from_user.is_bot

                    # Extract content from the replied-to message
                    if reply_to.text:
                        combined.reply_to_message_text = reply_to.text
                        combined.reply_to_message_type = "text"
                    elif reply_to.caption:
                        combined.reply_to_message_text = reply_to.caption
                        if reply_to.photo:
                            combined.reply_to_message_type = "photo"
                        elif reply_to.video:
                            combined.reply_to_message_type = "video"
                        elif reply_to.document:
                            combined.reply_to_message_type = "document"
                    elif reply_to.voice:
                        combined.reply_to_message_type = "voice"
                        # Voice messages don't have text initially, will be in cache
                    elif reply_to.video_note:
                        combined.reply_to_message_type = "video_note"

            # Collect by type
            if msg.message_type == "text":
                if msg.text:
                    text_parts.append(msg.text)

            elif msg.message_type == "claude_command":
                # /claude command prompt - add to text parts
                if msg.text:
                    text_parts.append(msg.text)

            elif msg.message_type == "photo":
                combined.images.append(msg)
                if msg.caption:
                    text_parts.append(msg.caption)

            elif msg.message_type == "video":
                combined.videos.append(msg)
                if msg.caption:
                    text_parts.append(msg.caption)

            elif msg.message_type == "voice":
                combined.voices.append(msg)

            elif msg.message_type == "document":
                combined.documents.append(msg)
                if msg.caption:
                    text_parts.append(msg.caption)

            elif msg.message_type == "contact":
                combined.contacts.append(msg)

            elif msg.message_type == "poll":
                combined.polls.append(msg)

        # Combine text with newlines
        combined.combined_text = "\n".join(text_parts)

        # Detect link + comment pairs
        combined.link_comment_pair = _detect_link_comment_pair(messages)
        if combined.link_comment_pair:
            logger.info("Detected link + comment pair in buffered messages")

        return combined

    async def add_claude_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        prompt: str,
    ) -> None:
        """
        Add a /claude command to the buffer.

        This buffers the prompt and waits for potential follow-up messages
        before executing. After the buffer timeout, the combined message
        will be routed to Claude.
        """
        message = update.message
        if not message:
            return

        chat = update.effective_chat
        user = update.effective_user

        if not chat or not user:
            return

        chat_id = chat.id
        user_id = user.id

        # Create a buffered message for the /claude command
        buffered = BufferedMessage(
            message_id=message.message_id,
            message=message,
            update=update,
            context=context,
            timestamp=datetime.now(),
            message_type="claude_command",
            text=prompt,
            is_claude_command=True,
        )

        # Get or create buffer entry (protected by lock)
        key = self._get_buffer_key(chat_id, user_id)

        async with self._buffer_lock:
            if key not in self._buffers:
                self._buffers[key] = BufferEntry()

            entry = self._buffers[key]

            # Track first message time
            if entry.first_message_time is None:
                entry.first_message_time = buffered.timestamp

            # Add to buffer (at the beginning to preserve order)
            entry.messages.insert(0, buffered)

            buffer_size = len(entry.messages)

        logger.info(
            f"Buffered /claude command for ({chat_id}, {user_id}), "
            f"prompt_len={len(prompt)}, buffer_size={buffer_size}"
        )

        # Start/reset timer to wait for follow-up messages (outside lock)
        self._reset_timer(key)

    async def cancel_buffer(self, chat_id: int, user_id: int) -> bool:
        """Cancel and clear buffer without processing."""
        key = self._get_buffer_key(chat_id, user_id)
        async with self._buffer_lock:
            entry = self._buffers.pop(key, None)

        if entry:
            if entry.timer_task and not entry.timer_task.done():
                entry.timer_task.cancel()
            logger.info(f"Cancelled buffer for ({chat_id}, {user_id})")
            return True

        return False

    async def get_buffer_status(self, chat_id: int, user_id: int) -> Optional[dict]:
        """Get current buffer status for debugging."""
        key = self._get_buffer_key(chat_id, user_id)
        async with self._buffer_lock:
            entry = self._buffers.get(key)

            if not entry:
                return None

            return {
                "message_count": len(entry.messages),
                "first_message_time": entry.first_message_time,
                "media_groups": list(entry.media_group_ids),
                "message_types": [m.message_type for m in entry.messages],
            }


# Global instance
_buffer_service: Optional[MessageBufferService] = None


def get_message_buffer() -> MessageBufferService:
    """Get the global message buffer instance."""
    global _buffer_service
    if _buffer_service is None:
        _buffer_service = MessageBufferService()
    return _buffer_service


def init_message_buffer(
    buffer_timeout: float = 2.5,
    max_messages: int = 10,
    max_wait: float = 30.0,
) -> MessageBufferService:
    """Initialize the message buffer with custom settings."""
    global _buffer_service
    _buffer_service = MessageBufferService(
        buffer_timeout=buffer_timeout,
        max_messages=max_messages,
        max_wait=max_wait,
    )
    return _buffer_service
