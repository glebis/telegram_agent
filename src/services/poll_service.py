"""
Poll Service - Manages poll scheduling, sending, and response tracking.

This service handles:
- Scheduling polls throughout the day
- Sending polls via Telegram bot
- Tracking sent polls for response handling
- Storing responses with embeddings
- Analyzing trends and generating insights
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from telegram import Bot

from ..core.database import get_db_session
from ..domain.interfaces import EmbeddingProvider
from ..models.poll_response import PollResponse, PollTemplate

logger = logging.getLogger(__name__)


def _default_embedding_provider() -> EmbeddingProvider:
    """Lazy import to avoid cross-context import at module level."""
    from ..services.embedding_service import EmbeddingService

    return EmbeddingService()


class PollService:
    """Service for managing polls and responses."""

    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        self._embedding_provider: EmbeddingProvider = (
            embedding_provider or _default_embedding_provider()
        )
        self._poll_tracker: Dict[str, Dict[str, Any]] = (
            {}
        )  # poll_id -> {template_id, chat_id, sent_at}

    async def send_poll(
        self,
        bot: Bot,
        chat_id: int,
        template: PollTemplate,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Send a poll to a user and track it for response handling.

        Args:
            bot: Telegram bot instance
            chat_id: Chat ID to send to
            template: Poll template to use
            context_data: Optional context metadata

        Returns:
            poll_id if successful, None otherwise
        """
        try:
            # Send the poll
            poll_message = await bot.send_poll(
                chat_id=chat_id,
                question=template.question,
                options=template.options,
                is_anonymous=False,
                allows_multiple_answers=False,
            )

            poll_id = poll_message.poll.id

            # Track the poll
            self._poll_tracker[poll_id] = {
                "template_id": template.id,
                "chat_id": chat_id,
                "sent_at": datetime.utcnow(),
                "question": template.question,
                "options": template.options,
                "poll_type": template.poll_type,
                "poll_category": template.poll_category,
                "message_id": poll_message.message_id,
                "context_data": context_data or {},
            }

            # Update template stats
            async with get_db_session() as session:
                template.last_sent_at = datetime.utcnow()
                template.times_sent += 1
                session.add(template)
                await session.commit()

            logger.info(
                f"Sent poll {poll_id} to chat {chat_id}: {template.question[:50]}..."
            )

            return poll_id

        except Exception as e:
            logger.error(f"Error sending poll: {e}", exc_info=True)
            return None

    async def handle_poll_answer(
        self, poll_id: str, user_id: int, selected_option_id: int
    ) -> bool:
        """
        Handle a poll answer and store it in the database.

        Args:
            poll_id: Telegram poll ID
            user_id: User who answered
            selected_option_id: Index of selected option

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get poll metadata from tracker
            if poll_id not in self._poll_tracker:
                logger.warning(f"Received answer for untracked poll: {poll_id}")
                return False

            poll_data = self._poll_tracker[poll_id]

            # Get selected option text
            selected_option_text = poll_data["options"][selected_option_id]

            # Calculate temporal context
            now = datetime.utcnow()
            day_of_week = now.weekday()
            hour_of_day = now.hour

            # Generate embedding for the response
            response_text = f"Q: {poll_data['question']}\nA: {selected_option_text}"
            embedding = await self._embedding_provider.generate_embedding(response_text)
            embedding_str = json.dumps(embedding) if embedding else None

            # Store response in database
            async with get_db_session() as session:
                response = PollResponse(
                    chat_id=poll_data["chat_id"],
                    poll_id=poll_id,
                    message_id=poll_data.get("message_id"),
                    question=poll_data["question"],
                    options=poll_data["options"],
                    selected_option_id=selected_option_id,
                    selected_option_text=selected_option_text,
                    poll_type=poll_data["poll_type"],
                    poll_category=poll_data.get("poll_category"),
                    created_at=poll_data["sent_at"],
                    day_of_week=day_of_week,
                    hour_of_day=hour_of_day,
                    context_metadata=poll_data.get("context_data"),
                    embedding=embedding_str,
                )

                session.add(response)
                await session.commit()

                logger.info(
                    f"Stored poll response: {poll_id}, type={poll_data['poll_type']}, "
                    f"answer='{selected_option_text}'"
                )

            return True

        except Exception as e:
            logger.error(f"Error handling poll answer: {e}", exc_info=True)
            return False

    async def get_next_poll(self, chat_id: int) -> Optional[PollTemplate]:
        """
        Get the next poll to send based on schedule and priority.

        Args:
            chat_id: Chat ID to send to

        Returns:
            PollTemplate or None
        """
        try:
            async with get_db_session() as session:
                now = datetime.utcnow()
                current_hour = now.hour
                current_day = now.weekday()

                # Get active templates
                result = await session.execute("""
                    SELECT * FROM poll_templates
                    WHERE is_active = 1
                    ORDER BY priority DESC, last_sent_at ASC NULLS FIRST
                    """)
                templates = result.fetchall()

                for template_row in templates:
                    template = PollTemplate(**dict(template_row))

                    # Check if template is due
                    if template.last_sent_at:
                        time_since_last = now - template.last_sent_at
                        if (
                            time_since_last.total_seconds()
                            < template.min_interval_hours * 3600
                        ):
                            continue  # Too soon

                    # Check schedule constraints
                    if template.schedule_days:
                        if current_day not in template.schedule_days:
                            continue  # Not scheduled for this day

                    if template.schedule_times:
                        # Check if current hour matches any scheduled time
                        matches_time = any(
                            current_hour == int(t.split(":")[0])
                            for t in template.schedule_times
                        )
                        if not matches_time:
                            continue  # Not scheduled for this hour

                    # This template is due
                    return template

                return None

        except Exception as e:
            logger.error(f"Error getting next poll: {e}", exc_info=True)
            return None

    async def get_responses(
        self,
        chat_id: int,
        poll_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[PollResponse]:
        """
        Get poll responses with optional filters.

        Args:
            chat_id: Chat ID
            poll_type: Optional filter by poll type
            since: Optional filter by date
            limit: Maximum number of responses

        Returns:
            List of PollResponse objects
        """
        try:
            async with get_db_session() as session:
                query = "SELECT * FROM poll_responses WHERE chat_id = ?"
                params = [chat_id]

                if poll_type:
                    query += " AND poll_type = ?"
                    params.append(poll_type)

                if since:
                    query += " AND created_at >= ?"
                    params.append(since)

                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                result = await session.execute(query, params)
                rows = result.fetchall()

                return [PollResponse(**dict(row)) for row in rows]

        except Exception as e:
            logger.error(f"Error getting responses: {e}", exc_info=True)
            return []

    async def analyze_trends(self, chat_id: int, days: int = 7) -> Dict[str, Any]:
        """
        Analyze poll response trends over a time period.

        Args:
            chat_id: Chat ID
            days: Number of days to analyze

        Returns:
            Dictionary with trend analysis
        """
        since = datetime.utcnow() - timedelta(days=days)
        responses = await self.get_responses(chat_id, since=since, limit=1000)

        if not responses:
            return {"error": "No responses found"}

        # Analyze by poll type
        type_counts = {}
        type_distributions = {}

        for response in responses:
            poll_type = response.poll_type
            if poll_type not in type_counts:
                type_counts[poll_type] = 0
                type_distributions[poll_type] = {}

            type_counts[poll_type] += 1

            # Track option distribution
            option_text = response.selected_option_text
            if option_text not in type_distributions[poll_type]:
                type_distributions[poll_type][option_text] = 0
            type_distributions[poll_type][option_text] += 1

        # Calculate most common responses by type
        top_responses = {}
        for poll_type, distribution in type_distributions.items():
            sorted_options = sorted(
                distribution.items(), key=lambda x: x[1], reverse=True
            )
            top_responses[poll_type] = sorted_options[:3]

        # Analyze temporal patterns
        hour_distribution = {}
        for response in responses:
            hour = response.hour_of_day
            if hour not in hour_distribution:
                hour_distribution[hour] = 0
            hour_distribution[hour] += 1

        return {
            "total_responses": len(responses),
            "days_analyzed": days,
            "type_counts": type_counts,
            "top_responses": top_responses,
            "hour_distribution": hour_distribution,
            "date_range": {
                "start": min(r.created_at for r in responses).isoformat(),
                "end": max(r.created_at for r in responses).isoformat(),
            },
        }


# Singleton instance
_poll_service: Optional[PollService] = None


def get_poll_service() -> PollService:
    """Get or create poll service singleton."""
    global _poll_service
    if _poll_service is None:
        _poll_service = PollService()
    return _poll_service
