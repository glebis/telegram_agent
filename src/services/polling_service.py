"""
Polling Service - Manages poll delivery, responses, and analysis.

Features:
- Smart scheduling with time windows and frequency control
- Response tracking with embeddings
- Trend analysis and insights
- Trail/todo integration
"""

import json
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import yaml
from sqlalchemy import and_, func, select

from ..core.database import get_db_session
from ..models.poll_response import PollResponse, PollTemplate
from ..services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class PollingService:
    """Manages poll scheduling, delivery, and analysis."""

    def __init__(self):
        self.templates: List[Dict] = []
        self.config: Dict = {}
        self.embedding_service = EmbeddingService()
        self._load_templates()

    def _load_templates(self):
        """Load poll templates from YAML config."""
        try:
            with open("config/poll_templates.yaml", "r") as f:
                data = yaml.safe_load(f)
                self.templates = data.get("templates", [])
                self.config = data.get("scheduling", {})
                logger.info(f"Loaded {len(self.templates)} poll templates")
        except Exception as e:
            logger.error(f"Error loading poll templates: {e}")
            self.templates = []
            self.config = {}

    def reload_templates(self):
        """Reload templates from disk (for dynamic updates)."""
        self._load_templates()

    def _parse_frequency(self, freq: str) -> Tuple[float, float]:
        """Parse frequency string like '3-4' or '0.5-1' into (min, max)."""
        freq_map = {
            "high": (3, 4),
            "medium": (1, 2),
            "low": (0.5, 1),
        }

        if freq in freq_map:
            return freq_map[freq]

        try:
            if "-" in freq:
                parts = freq.split("-")
                return (float(parts[0]), float(parts[1]))
            return (float(freq), float(freq))
        except Exception:
            return (1, 1)

    def _is_in_time_window(self, template: Dict, current_hour: int) -> bool:
        """Check if current hour is in template's preferred time windows."""
        time_windows = template.get("time_windows", [])

        if not time_windows:
            return True

        # Allow 1 hour flexibility around each window
        for window_hour in time_windows:
            if abs(current_hour - window_hour) <= 1:
                return True

        return False

    def _is_in_quiet_hours(self, current_hour: int) -> bool:
        """Check if current time is in quiet hours."""
        quiet = self.config.get("quiet_hours", {})
        start = quiet.get("start", 23)
        end = quiet.get("end", 8)

        if start > end:  # Crosses midnight
            return current_hour >= start or current_hour < end
        return start <= current_hour < end

    async def get_recent_poll_count(self, chat_id: int, hours: int = 1) -> int:
        """Count polls sent to chat in last N hours."""
        async with get_db_session() as session:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            result = await session.execute(
                select(func.count(PollResponse.id)).where(
                    and_(
                        PollResponse.chat_id == chat_id,
                        PollResponse.created_at >= cutoff,
                    )
                )
            )
            return result.scalar() or 0

    async def get_sent_templates_today(self, chat_id: int) -> set:
        """Get set of template IDs already sent today."""
        async with get_db_session() as session:
            today_start = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            result = await session.execute(
                select(PollResponse.context_metadata).where(
                    and_(
                        PollResponse.chat_id == chat_id,
                        PollResponse.created_at >= today_start,
                    )
                )
            )
            sent_ids = set()
            for (metadata,) in result:
                if metadata and "template_id" in metadata:
                    sent_ids.add(metadata["template_id"])
            return sent_ids

    async def get_next_poll(self, chat_id: int) -> Optional[Dict]:
        """
        Get next poll to send based on smart scheduling.

        Returns poll dict or None if no poll should be sent now.
        """
        current_time = datetime.utcnow()
        current_hour = current_time.hour

        # Check quiet hours
        if self._is_in_quiet_hours(current_hour):
            logger.info("In quiet hours, not sending poll")
            return None

        # Check max per hour
        max_per_hour = self.config.get("max_per_hour", 2)
        recent_count = await self.get_recent_poll_count(chat_id, hours=1)
        if recent_count >= max_per_hour:
            logger.info(f"Max polls per hour reached ({recent_count}/{max_per_hour})")
            return None

        # Check min gap -- use actual send time, not answer time
        from .poll_lifecycle import get_poll_lifecycle_tracker

        tracker = get_poll_lifecycle_tracker()
        min_gap = self.config.get("rules", {}).get("min_gap_minutes", 75)
        last_sent = tracker.get_last_sent_time(chat_id)
        if last_sent:
            minutes_since = (current_time - last_sent).total_seconds() / 60
            if minutes_since < min_gap:
                logger.info(
                    f"Too soon since last poll sent ({minutes_since:.1f} < {min_gap} min)"
                )
                return None

        # Get templates already sent today
        sent_today = await self.get_sent_templates_today(chat_id)

        # Filter eligible templates
        eligible = []
        for template in self.templates:
            template_id = template["id"]

            # Skip if sent today and duplicates not allowed
            if self.config.get("rules", {}).get("avoid_duplicates", True):
                if template_id in sent_today:
                    continue

            # Check time window
            if self.config.get("rules", {}).get("respect_time_windows", True):
                if not self._is_in_time_window(template, current_hour):
                    continue

            eligible.append(template)

        if not eligible:
            logger.info("No eligible templates at this time")
            return None

        # Weight by frequency (high frequency templates more likely)
        weights = []
        for template in eligible:
            freq = template.get("frequency", "medium")
            min_freq, max_freq = self._parse_frequency(freq)
            weight = (min_freq + max_freq) / 2
            weights.append(weight)

        # Random selection weighted by frequency
        selected = random.choices(eligible, weights=weights, k=1)[0]

        logger.info(
            f"Selected poll: {selected['id']} (type={selected['type']}, "
            f"category={selected.get('category')}, "
            f"question='{selected['question'][:50]}...')"
        )

        return selected

    def _find_template_by_question(self, question: str) -> Optional[Dict]:
        """Find a YAML template dict by its question text."""
        for t in self.templates:
            if t.get("question") == question:
                return t
        return None

    async def increment_send_count(self, question: str) -> None:
        """
        Increment the times_sent counter for a poll template in the database.

        Looks up the PollTemplate row by question text.  If found, increments
        times_sent and updates last_sent_at.  If no row exists yet (templates
        come from YAML and may not have been persisted), creates a new record
        with times_sent=1.

        Args:
            question: The poll question text used to identify the template.
        """
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(PollTemplate).where(PollTemplate.question == question)
                )
                template = result.scalar_one_or_none()

                if template:
                    template.times_sent += 1
                    template.last_sent_at = datetime.utcnow()
                else:
                    # Look up metadata from YAML templates
                    yaml_data = self._find_template_by_question(question)
                    template = PollTemplate(
                        question=question,
                        options=yaml_data.get("options", []) if yaml_data else [],
                        poll_type=(
                            yaml_data.get("type", "unknown") if yaml_data else "unknown"
                        ),
                        poll_category=yaml_data.get("category") if yaml_data else None,
                        times_sent=1,
                        last_sent_at=datetime.utcnow(),
                    )
                    session.add(template)

                await session.commit()
                logger.info(
                    f"Updated send count for poll: '{question[:50]}...' "
                    f"(times_sent={template.times_sent})"
                )
        except Exception as e:
            logger.error(f"Error updating poll send count: {e}", exc_info=True)

    async def _get_last_poll_time(self, chat_id: int) -> Optional[datetime]:
        """Get timestamp of last poll sent to chat."""
        async with get_db_session() as session:
            result = await session.execute(
                select(PollResponse.created_at)
                .where(PollResponse.chat_id == chat_id)
                .order_by(PollResponse.created_at.desc())
                .limit(1)
            )
            row = result.first()
            return row[0] if row else None

    async def save_response(
        self,
        chat_id: int,
        poll_id: str,
        message_id: int,
        question: str,
        options: List[str],
        selected_option_id: int,
        selected_option_text: str,
        poll_type: str,
        poll_category: Optional[str] = None,
        context_metadata: Optional[Dict] = None,
    ) -> PollResponse:
        """
        Save poll response to database with embedding.

        Args:
            chat_id: Telegram chat ID
            poll_id: Telegram poll ID
            message_id: Message ID containing the poll
            question: Poll question text
            options: List of all option texts
            selected_option_id: Index of selected option
            selected_option_text: Text of selected option
            poll_type: Type of poll (emotion, decision, activity, etc)
            poll_category: Category (work, personal, health, etc)
            context_metadata: Additional context (template_id, current_trail, etc)

        Returns:
            Saved PollResponse object
        """
        now = datetime.utcnow()

        # Generate embedding for semantic search
        embedding_text = f"{question}\n{selected_option_text}"
        embedding_vector = await self.embedding_service.generate_embedding(
            embedding_text
        )
        embedding_json = json.dumps(embedding_vector) if embedding_vector else None

        # Create response object
        response = PollResponse(
            chat_id=chat_id,
            poll_id=poll_id,
            message_id=message_id,
            question=question,
            options=options,
            selected_option_id=selected_option_id,
            selected_option_text=selected_option_text,
            poll_type=poll_type,
            poll_category=poll_category,
            created_at=now,
            day_of_week=now.weekday(),
            hour_of_day=now.hour,
            context_metadata=context_metadata or {},
            embedding=embedding_json,
        )

        async with get_db_session() as session:
            session.add(response)
            await session.commit()
            await session.refresh(response)

        logger.info(
            f"Saved poll response: {response.id} "
            f"(type={poll_type}, answer='{selected_option_text}')"
        )

        return response

    async def get_responses(
        self,
        chat_id: int,
        days: int = 7,
        poll_type: Optional[str] = None,
        poll_category: Optional[str] = None,
    ) -> List[PollResponse]:
        """Get poll responses for a chat, optionally filtered."""
        async with get_db_session() as session:
            cutoff = datetime.utcnow() - timedelta(days=days)

            conditions = [
                PollResponse.chat_id == chat_id,
                PollResponse.created_at >= cutoff,
            ]

            if poll_type:
                conditions.append(PollResponse.poll_type == poll_type)

            if poll_category:
                conditions.append(PollResponse.poll_category == poll_category)

            result = await session.execute(
                select(PollResponse)
                .where(and_(*conditions))
                .order_by(PollResponse.created_at.desc())
            )

            return list(result.scalars().all())

    async def get_statistics(self, chat_id: int, days: int = 7) -> Dict:
        """
        Get statistics and trends from poll responses.

        Returns dict with:
        - total_responses
        - by_type: counts by poll_type
        - by_category: counts by poll_category
        - by_hour: distribution by hour of day
        - by_day: distribution by day of week
        - recent_trends: patterns in recent responses
        """
        responses = await self.get_responses(chat_id, days=days)

        if not responses:
            return {
                "total_responses": 0,
                "days_analyzed": days,
                "message": "No poll responses in time range",
            }

        # Count by type
        by_type = {}
        for r in responses:
            by_type[r.poll_type] = by_type.get(r.poll_type, 0) + 1

        # Count by category
        by_category = {}
        for r in responses:
            if r.poll_category:
                by_category[r.poll_category] = by_category.get(r.poll_category, 0) + 1

        # Distribution by hour
        by_hour = {}
        for r in responses:
            if r.hour_of_day is not None:
                by_hour[r.hour_of_day] = by_hour.get(r.hour_of_day, 0) + 1

        # Distribution by day of week
        by_day = {}
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for r in responses:
            if r.day_of_week is not None:
                day_name = day_names[r.day_of_week]
                by_day[day_name] = by_day.get(day_name, 0) + 1

        return {
            "total_responses": len(responses),
            "days_analyzed": days,
            "by_type": by_type,
            "by_category": by_category,
            "by_hour": sorted(by_hour.items()),
            "by_day": by_day,
            "avg_per_day": len(responses) / days,
        }


def get_polling_service() -> PollingService:
    """Get or create polling service singleton (delegates to DI container)."""
    from ..core.services import Services, get_service

    return get_service(Services.POLLING)
