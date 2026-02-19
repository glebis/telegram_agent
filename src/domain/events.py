"""Domain events for poll/accountability workflows.

Defines event types and a lightweight async EventBus for decoupled
communication between services.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


@dataclass
class PollAnswered:
    """Emitted after a poll response is persisted."""

    poll_id: str
    chat_id: int
    poll_type: str
    poll_category: Optional[str]
    selected_option_id: int
    selected_option_text: str
    question: str
    response_id: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MoodCaptured:
    """Emitted when a mood-related poll is answered."""

    poll_id: str
    chat_id: int
    mood_label: str
    poll_type: str
    response_id: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

# Type alias for an async event handler
EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """Simple in-process async event bus.

    Subscribers register for a specific event type. When that event is
    published, all registered handlers are invoked. A failing handler
    logs the error but does not prevent remaining handlers from running.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[Type, List[EventHandler]] = {}

    def subscribe(self, event_type: Type, handler: EventHandler) -> None:
        """Register *handler* for *event_type*."""
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Any) -> None:
        """Dispatch *event* to all registered handlers for its type."""
        handlers = self._subscribers.get(type(event), [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler %s failed for %s",
                    getattr(handler, "__name__", handler),
                    type(event).__name__,
                )


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Return the global EventBus singleton (create on first call)."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Replace the global EventBus (useful in tests)."""
    global _event_bus
    _event_bus = None
