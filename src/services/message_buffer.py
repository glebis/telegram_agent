"""
Message Buffer Service

Buffers incoming messages for a short window to combine split messages,
media groups, and rapid-fire inputs into a single processing unit.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from telegram import Message, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


@dataclass
class BufferedMessage:
    """A single buffered message with metadata."""

    message_id: int
    message: Message
    update: Update
    context: ContextTypes.DEFAULT_TYPE
    timestamp: datetime
    message_type: str  # "text", "photo", "voice", "document", "contact", "claude_command"
    media_group_id: Optional[str] = None

    # Extracted content
    text: Optional[str] = None
    caption: Optional[str] = None
    file_id: Optional[str] = None
    file_path: Optional[str] = None  # For downloaded files

    # Claude command flag - indicates this is a /claude prompt
    is_claude_command: bool = False

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

    # Reply context
    reply_to_message_id: Optional[int] = None

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

    def has_text_only(self) -> bool:
        return (
            len(self.combined_text) > 0
            and not self.has_images()
            and not self.has_voice()
            and not self.has_documents()
        )

    def has_claude_command(self) -> bool:
        """Check if any message in the buffer is a /claude command."""
        return any(m.is_claude_command for m in self.messages)

    def get_claude_command_message(self) -> Optional["BufferedMessage"]:
        """Get the /claude command message if present."""
        for m in self.messages:
            if m.is_claude_command:
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
        max_messages: int = 10,       # Max messages before forced flush
        max_wait: float = 30.0,       # Max seconds to buffer
    ):
        self.buffer_timeout = buffer_timeout
        self.max_messages = max_messages
        self.max_wait = max_wait

        # Buffer storage: (chat_id, user_id) -> BufferEntry
        self._buffers: Dict[Tuple[int, int], BufferEntry] = {}

        # Processing callback
        self._process_callback: Optional[ProcessCallback] = None

        # Commands that bypass buffering (processed immediately)
        self._bypass_commands = {
            "/help", "/start", "/mode", "/cancel", "/gallery", "/note",
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
        buffered = self._create_buffered_message(update, context, message)
        if not buffered:
            return False

        # Get or create buffer entry
        key = self._get_buffer_key(chat_id, user_id)

        if key not in self._buffers:
            self._buffers[key] = BufferEntry()

        entry = self._buffers[key]

        # Track first message time
        if entry.first_message_time is None:
            entry.first_message_time = buffered.timestamp

        # Add to buffer
        entry.messages.append(buffered)

        # Track media group
        if buffered.media_group_id:
            entry.media_group_ids.add(buffered.media_group_id)

        logger.debug(
            f"Buffered message {buffered.message_id} for ({chat_id}, {user_id}), "
            f"type={buffered.message_type}, buffer_size={len(entry.messages)}"
        )

        # Check if we should force flush
        should_flush = False

        if len(entry.messages) >= self.max_messages:
            logger.info(f"Buffer full ({self.max_messages}), forcing flush")
            should_flush = True

        if entry.first_message_time:
            elapsed = (datetime.now() - entry.first_message_time).total_seconds()
            if elapsed >= self.max_wait:
                logger.info(f"Max wait time reached ({self.max_wait}s), forcing flush")
                should_flush = True

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
    ) -> Optional[BufferedMessage]:
        """Create a BufferedMessage from a Telegram message."""

        msg_type = None
        text = None
        caption = message.caption
        file_id = None
        media_group_id = getattr(message, "media_group_id", None)

        if message.text:
            msg_type = "text"
            text = message.text
        elif message.photo:
            msg_type = "photo"
            file_id = message.photo[-1].file_id  # Largest photo
        elif message.voice:
            msg_type = "voice"
            file_id = message.voice.file_id
        elif message.video:
            msg_type = "video"
            file_id = message.video.file_id
        elif message.document:
            msg_type = "document"
            file_id = message.document.file_id
            # Check if it's an image document
            if message.document.mime_type and message.document.mime_type.startswith("image/"):
                msg_type = "photo"  # Treat as photo
        elif message.contact:
            msg_type = "contact"
        else:
            # Log all message attributes for debugging
            attrs = []
            for attr in ['text', 'caption', 'photo', 'video', 'audio', 'voice', 'document', 'sticker', 'animation', 'forward_origin']:
                val = getattr(message, attr, None)
                if val:
                    attrs.append(f"{attr}={type(val).__name__}")
            logger.info(f"Unknown message type, skipping buffer. Attrs: {attrs}")
            return None

        # Extract forward info (using new API: message.forward_origin)
        forward_from_username = None
        forward_from_first_name = None
        forward_sender_name = None
        forward_from_chat_title = None
        forward_from_chat_username = None
        forward_message_id = None
        is_forwarded = False

        if message.forward_origin:
            is_forwarded = True
            origin = message.forward_origin
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
                logger.info(f"Forward detected (channel): from {forward_from_chat_title}{url_part}")
            elif origin_type == "chat":
                # MessageOriginChat
                chat = getattr(origin, "sender_chat", None)
                if chat:
                    forward_from_chat_title = chat.title
                logger.info(f"Forward detected (chat): from {forward_from_chat_title}")

        return BufferedMessage(
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
            forward_from_username=forward_from_username,
            forward_from_first_name=forward_from_first_name,
            forward_sender_name=forward_sender_name,
            forward_from_chat_title=forward_from_chat_title,
            forward_from_chat_username=forward_from_chat_username,
            forward_message_id=forward_message_id,
            is_forwarded=is_forwarded,
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
        entry.timer_task = asyncio.create_task(
            self._timer_callback(key)
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
            f"videos={len(combined.videos)}"
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

        # Combine text with newlines
        combined.combined_text = "\n".join(text_parts)

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

        # Get or create buffer entry
        key = self._get_buffer_key(chat_id, user_id)

        if key not in self._buffers:
            self._buffers[key] = BufferEntry()

        entry = self._buffers[key]

        # Track first message time
        if entry.first_message_time is None:
            entry.first_message_time = buffered.timestamp

        # Add to buffer (at the beginning to preserve order)
        entry.messages.insert(0, buffered)

        logger.info(
            f"Buffered /claude command for ({chat_id}, {user_id}), "
            f"prompt_len={len(prompt)}, buffer_size={len(entry.messages)}"
        )

        # Start/reset timer to wait for follow-up messages
        self._reset_timer(key)

    async def cancel_buffer(self, chat_id: int, user_id: int) -> bool:
        """Cancel and clear buffer without processing."""
        key = self._get_buffer_key(chat_id, user_id)
        entry = self._buffers.pop(key, None)

        if entry:
            if entry.timer_task and not entry.timer_task.done():
                entry.timer_task.cancel()
            logger.info(f"Cancelled buffer for ({chat_id}, {user_id})")
            return True

        return False

    def get_buffer_status(self, chat_id: int, user_id: int) -> Optional[dict]:
        """Get current buffer status for debugging."""
        key = self._get_buffer_key(chat_id, user_id)
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
