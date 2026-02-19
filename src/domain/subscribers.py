"""Event subscribers for poll/accountability workflows.

Subscribers react to domain events and perform side-effects such as
flipping processed_for_* flags on PollResponse rows and emitting
secondary events (e.g. MoodCaptured).
"""

import logging
from typing import Optional

from sqlalchemy import text

from ..core.database import get_db_session
from .events import EventBus, MoodCaptured, PollAnswered, get_event_bus

logger = logging.getLogger(__name__)


class PollResponseProcessor:
    """Listens for PollAnswered and flips processed_for flags.

    Also emits MoodCaptured when the poll_type is ``emotion``.
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus or get_event_bus()

    def register(self, bus: EventBus) -> None:
        """Subscribe to PollAnswered on the given bus."""
        bus.subscribe(PollAnswered, self.on_poll_answered)

    async def on_poll_answered(self, event: PollAnswered) -> None:
        """Process a PollAnswered event.

        1. Flip processed_for_trails, processed_for_todos, and
           processed_for_insights to 1 for the response row.
        2. If the poll is an emotion type, publish a MoodCaptured event.
        """
        async with get_db_session() as session:
            await session.execute(
                text(
                    "UPDATE poll_responses "
                    "SET processed_for_trails = 1, "
                    "    processed_for_todos = 1, "
                    "    processed_for_insights = 1 "
                    "WHERE id = :rid"
                ),
                {"rid": event.response_id},
            )
            await session.commit()

        logger.info(
            "Processed poll response %s (poll_id=%s): flags flipped",
            event.response_id,
            event.poll_id,
        )

        # Emit secondary event for mood tracking
        if event.poll_type == "emotion":
            await self._event_bus.publish(
                MoodCaptured(
                    poll_id=event.poll_id,
                    chat_id=event.chat_id,
                    mood_label=event.selected_option_text,
                    poll_type=event.poll_type,
                    response_id=event.response_id,
                    timestamp=event.timestamp,
                )
            )
