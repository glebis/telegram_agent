"""
Reply Context Service

Tracks message context for reply-aware routing.
When a user replies to a bot message, this service provides
the context needed to continue that conversation appropriately.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from collections import OrderedDict

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages we track context for."""
    CLAUDE_RESPONSE = "claude_response"
    IMAGE_ANALYSIS = "image_analysis"
    VOICE_TRANSCRIPTION = "voice_transcription"
    LINK_CAPTURE = "link_capture"
    USER_TEXT = "user_text"
    BOT_ERROR = "bot_error"
    BOT_INFO = "bot_info"


@dataclass
class ReplyContext:
    """Context for a tracked message."""

    message_id: int
    chat_id: int
    user_id: int  # User who triggered the original message
    message_type: MessageType
    created_at: datetime = field(default_factory=datetime.now)

    # Claude-specific
    session_id: Optional[str] = None
    prompt: Optional[str] = None  # Original prompt that generated this response

    # Image-specific
    image_path: Optional[str] = None
    image_file_id: Optional[str] = None
    image_analysis: Optional[dict] = None

    # Voice-specific
    transcription: Optional[str] = None
    voice_file_id: Optional[str] = None

    # Link-specific
    url: Optional[str] = None
    link_title: Optional[str] = None
    link_path: Optional[str] = None  # Path in vault

    # General
    original_text: Optional[str] = None  # Original user message
    response_text: Optional[str] = None  # Bot's response text
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if this context has expired."""
        return datetime.now() - self.created_at > timedelta(hours=ttl_hours)

    def get_context_summary(self) -> str:
        """Get a brief summary of this context for prompts."""
        if self.message_type == MessageType.CLAUDE_RESPONSE:
            return f"[Previous Claude response to: {self.prompt[:100] if self.prompt else 'unknown'}]"
        elif self.message_type == MessageType.IMAGE_ANALYSIS:
            return f"[Image analysis: {self.image_path or 'unknown'}]"
        elif self.message_type == MessageType.VOICE_TRANSCRIPTION:
            return f"[Voice transcription: {self.transcription[:100] if self.transcription else 'unknown'}...]"
        elif self.message_type == MessageType.LINK_CAPTURE:
            return f"[Link capture: {self.link_title or self.url or 'unknown'}]"
        elif self.message_type == MessageType.USER_TEXT:
            return f"[User message: {self.original_text[:100] if self.original_text else 'unknown'}]"
        else:
            return f"[{self.message_type.value}]"


class LRUCache(OrderedDict):
    """Simple LRU cache with max size."""

    def __init__(self, max_size: int = 1000):
        super().__init__()
        self.max_size = max_size

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.max_size:
            oldest = next(iter(self))
            del self[oldest]

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


class ReplyContextService:
    """
    Service for tracking and retrieving message context.

    Features:
    - LRU cache with configurable max size
    - TTL-based expiration
    - Lookup by message_id
    - Context injection for reply handling
    """

    def __init__(
        self,
        max_cache_size: int = 1000,
        ttl_hours: int = 24,
    ):
        self.max_cache_size = max_cache_size
        self.ttl_hours = ttl_hours

        # Cache: (chat_id, message_id) -> ReplyContext
        self._cache: LRUCache = LRUCache(max_size=max_cache_size)

        # Secondary index: session_id -> list of message_ids
        # Useful for finding all messages in a Claude session
        self._session_messages: Dict[str, List[int]] = {}

        logger.info(
            f"ReplyContextService initialized: max_size={max_cache_size}, ttl={ttl_hours}h"
        )

    def _make_key(self, chat_id: int, message_id: int) -> tuple:
        """Create cache key."""
        return (chat_id, message_id)

    def track_message(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        message_type: MessageType,
        **kwargs,
    ) -> ReplyContext:
        """
        Track a message for future reply context.

        Args:
            message_id: The bot's response message ID
            chat_id: Chat where message was sent
            user_id: User who triggered this message
            message_type: Type of message
            **kwargs: Additional context fields

        Returns:
            The created ReplyContext
        """
        context = ReplyContext(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_type=message_type,
            **kwargs,
        )

        key = self._make_key(chat_id, message_id)
        self._cache[key] = context

        # Track session messages
        if context.session_id:
            if context.session_id not in self._session_messages:
                self._session_messages[context.session_id] = []
            self._session_messages[context.session_id].append(message_id)

        logger.debug(
            f"Tracked message {message_id} in chat {chat_id}: "
            f"type={message_type.value}"
        )

        return context

    def get_context(
        self,
        chat_id: int,
        message_id: int,
        check_expiry: bool = True,
    ) -> Optional[ReplyContext]:
        """
        Get context for a message.

        Args:
            chat_id: Chat ID
            message_id: Message ID to look up
            check_expiry: If True, return None for expired contexts

        Returns:
            ReplyContext if found and not expired, else None
        """
        key = self._make_key(chat_id, message_id)
        context = self._cache.get(key)

        if context is None:
            return None

        if check_expiry and context.is_expired(self.ttl_hours):
            logger.debug(f"Context for message {message_id} has expired")
            return None

        return context

    def get_session_context(self, session_id: str) -> Optional[ReplyContext]:
        """
        Get the most recent context for a Claude session.

        Args:
            session_id: Claude session ID

        Returns:
            Most recent ReplyContext for this session, or None
        """
        message_ids = self._session_messages.get(session_id, [])
        if not message_ids:
            return None

        # Get most recent (last in list)
        for msg_id in reversed(message_ids):
            # We need chat_id to look up, but we don't have it here
            # This is a limitation - we'd need to iterate the cache
            # For now, return None and use message-based lookup instead
            pass

        return None

    def track_claude_response(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        session_id: str,
        prompt: str,
        response_text: Optional[str] = None,
    ) -> ReplyContext:
        """Convenience method to track a Claude response."""
        return self.track_message(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_type=MessageType.CLAUDE_RESPONSE,
            session_id=session_id,
            prompt=prompt,
            response_text=response_text,
        )

    def track_image_analysis(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        image_path: Optional[str] = None,
        image_file_id: Optional[str] = None,
        analysis: Optional[dict] = None,
    ) -> ReplyContext:
        """Convenience method to track an image analysis."""
        return self.track_message(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_type=MessageType.IMAGE_ANALYSIS,
            image_path=image_path,
            image_file_id=image_file_id,
            image_analysis=analysis,
        )

    def track_voice_transcription(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        transcription: str,
        voice_file_id: Optional[str] = None,
    ) -> ReplyContext:
        """Convenience method to track a voice transcription."""
        return self.track_message(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_type=MessageType.VOICE_TRANSCRIPTION,
            transcription=transcription,
            voice_file_id=voice_file_id,
        )

    def track_link_capture(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        url: str,
        title: Optional[str] = None,
        path: Optional[str] = None,
    ) -> ReplyContext:
        """Convenience method to track a link capture."""
        return self.track_message(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_type=MessageType.LINK_CAPTURE,
            url=url,
            link_title=title,
            link_path=path,
        )

    def track_user_message(
        self,
        message_id: int,
        chat_id: int,
        user_id: int,
        text: str,
    ) -> ReplyContext:
        """Track a user's message for potential quote/reference."""
        return self.track_message(
            message_id=message_id,
            chat_id=chat_id,
            user_id=user_id,
            message_type=MessageType.USER_TEXT,
            original_text=text,
        )

    def build_reply_prompt(
        self,
        context: ReplyContext,
        new_message: str,
        include_original: bool = True,
    ) -> str:
        """
        Build a prompt that includes reply context.

        Args:
            context: The context being replied to
            new_message: The new message from the user
            include_original: Whether to include original content

        Returns:
            Combined prompt with context
        """
        parts = []

        if context.message_type == MessageType.CLAUDE_RESPONSE:
            # Session is resumed, Claude already has the context - just pass the message
            parts.append(new_message)

        elif context.message_type == MessageType.IMAGE_ANALYSIS:
            parts.append(f"[Replying to image analysis]")
            if context.image_path:
                parts.append(f"Image: {context.image_path}")
            if context.image_analysis:
                # Include key analysis points
                analysis = context.image_analysis
                if "description" in analysis:
                    parts.append(f"Description: {analysis['description'][:200]}")
            parts.append("")
            parts.append(f"Follow-up about this image: {new_message}")

        elif context.message_type == MessageType.VOICE_TRANSCRIPTION:
            parts.append(f"[Replying to voice transcription]")
            if context.transcription:
                parts.append(f"Transcription: {context.transcription}")
            parts.append("")
            parts.append(f"Follow-up: {new_message}")

        elif context.message_type == MessageType.LINK_CAPTURE:
            parts.append(f"[Replying to captured link]")
            if context.url:
                parts.append(f"URL: {context.url}")
            if context.link_title:
                parts.append(f"Title: {context.link_title}")
            if context.link_path:
                parts.append(f"Saved to: {context.link_path}")
            parts.append("")
            parts.append(f"Follow-up: {new_message}")

        elif context.message_type == MessageType.USER_TEXT:
            parts.append(f"[Replying to previous message]")
            if context.original_text:
                parts.append(f"Original: {context.original_text}")
            parts.append("")
            parts.append(f"Response: {new_message}")

        else:
            # Generic fallback
            parts.append(f"[Replying to: {context.get_context_summary()}]")
            parts.append("")
            parts.append(new_message)

        return "\n".join(parts)

    def cleanup_expired(self) -> int:
        """Remove expired contexts. Returns count of removed items."""
        expired_keys = []

        for key, context in list(self._cache.items()):
            if context.is_expired(self.ttl_hours):
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired contexts")

        return len(expired_keys)

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "max_size": self.max_cache_size,
            "sessions_tracked": len(self._session_messages),
            "ttl_hours": self.ttl_hours,
        }


# Global instance
_reply_context_service: Optional[ReplyContextService] = None


def get_reply_context_service() -> ReplyContextService:
    """Get the global reply context service instance."""
    global _reply_context_service
    if _reply_context_service is None:
        _reply_context_service = ReplyContextService()
    return _reply_context_service


def init_reply_context_service(
    max_cache_size: int = 1000,
    ttl_hours: int = 24,
) -> ReplyContextService:
    """Initialize the reply context service with custom settings."""
    global _reply_context_service
    _reply_context_service = ReplyContextService(
        max_cache_size=max_cache_size,
        ttl_hours=ttl_hours,
    )
    return _reply_context_service
