"""
Application-layer accountability service.

Orchestrates domain logic (AccountabilityDomainService) with infrastructure
(SQLAlchemy repos, TTS synthesis). Extracted from AccountabilityService to
separate concerns (issue #226).
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from ..core.config import get_config_value
from ..core.database import get_db_session
from ..core.i18n import t
from ..models.tracker import CheckIn, Tracker
from ..models.user_settings import UserSettings
from .accountability_domain import (
    AccountabilityDomainService,
    strip_voice_tags,
)
from .voice_synthesis import synthesize_voice_mp3

logger = logging.getLogger(__name__)

PERSONALITY_CONFIG = get_config_value("accountability.personalities", {})


class AccountabilityAppService:
    """Application service wiring domain logic with DB and TTS."""

    # -- Infrastructure helpers (DB) --

    @staticmethod
    async def _get_user_settings(user_id: int) -> Optional[UserSettings]:
        async with get_db_session() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def _get_tracker(tracker_id: int) -> Optional[Tracker]:
        async with get_db_session() as session:
            result = await session.execute(
                select(Tracker).where(Tracker.id == tracker_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def _get_active_trackers(user_id: int) -> List[Tracker]:
        async with get_db_session() as session:
            result = await session.execute(
                select(Tracker).where(
                    Tracker.user_id == user_id, Tracker.active == True
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def _get_streak_from_db(user_id: int, tracker_id: int) -> int:
        """Fetch check-in dates from DB, delegate streak math to domain."""
        async with get_db_session() as session:
            result = await session.execute(
                select(CheckIn)
                .where(
                    CheckIn.user_id == user_id,
                    CheckIn.tracker_id == tracker_id,
                    CheckIn.status.in_(["completed", "partial"]),
                )
                .order_by(CheckIn.created_at.desc())
            )
            check_ins = list(result.scalars().all())

        dates = [ci.created_at for ci in check_ins]
        return AccountabilityDomainService.calculate_streak(dates, datetime.now())

    @staticmethod
    async def _count_misses_from_db(user_id: int, tracker_id: int) -> int:
        """Fetch last check-in from DB, delegate miss counting to domain."""
        async with get_db_session() as session:
            tracker_result = await session.execute(
                select(Tracker).where(Tracker.id == tracker_id)
            )
            tracker = tracker_result.scalar_one_or_none()

            if not tracker or tracker.check_frequency != "daily":
                return 0

            result = await session.execute(
                select(CheckIn)
                .where(CheckIn.user_id == user_id, CheckIn.tracker_id == tracker_id)
                .order_by(CheckIn.created_at.desc())
                .limit(1)
            )
            last_checkin = result.scalar_one_or_none()

        last_dt = last_checkin.created_at if last_checkin else None
        return AccountabilityDomainService.count_consecutive_misses(
            last_dt, datetime.now()
        )

    # -- Infrastructure helpers (TTS) --

    @staticmethod
    async def _synthesize_voice(message: str, voice: str, emotion: str) -> bytes:
        return await synthesize_voice_mp3(message, voice=voice, emotion=emotion)

    # -- Message generation (thin wrappers around i18n + domain) --

    @staticmethod
    def _generate_message_text(
        personality: str,
        tracker_name: str,
        streak: int = 0,
        locale: str = "en",
    ) -> str:
        """Generate check-in message using i18n templates."""
        from .accountability_service import _time_greeting

        greeting = _time_greeting(locale=locale)
        if streak > 0:
            return t(
                f"accountability.voice.{personality}.checkin_streak",
                locale,
                name=tracker_name,
                streak=streak,
                greeting=greeting,
            )
        return t(
            f"accountability.voice.{personality}.checkin",
            locale,
            name=tracker_name,
            greeting=greeting,
        )

    @staticmethod
    def _generate_struggle_text(
        personality: str,
        tracker_name: str,
        consecutive_misses: int,
        locale: str = "en",
    ) -> str:
        return t(
            f"accountability.voice.{personality}.struggle",
            locale,
            name=tracker_name,
            misses=consecutive_misses,
        )

    @staticmethod
    def _generate_celebration_text(
        personality: str,
        tracker_name: str,
        milestone: int,
        enthusiasm: float = 1.0,
        locale: str = "en",
    ) -> str:
        message = t(
            f"accountability.voice.{personality}.celebration",
            locale,
            name=tracker_name,
            milestone=milestone,
            next_milestone=milestone * 2,
        )
        return AccountabilityDomainService.adjust_celebration_enthusiasm(
            message, enthusiasm
        )

    @staticmethod
    def _resolve_voice(settings: UserSettings, personality_config: dict) -> str:
        return settings.partner_voice_override or personality_config["voice"]

    @staticmethod
    def _get_personality_config(personality: str) -> dict:
        return PERSONALITY_CONFIG.get(
            personality, PERSONALITY_CONFIG.get("supportive", {})
        )

    # -- Public orchestration methods --

    @staticmethod
    async def send_check_in(
        user_id: int, tracker_id: int
    ) -> Optional[Tuple[str, bytes]]:
        """Generate check-in voice message.

        Returns:
            Tuple of (clean text, MP3 audio bytes) on success, None on failure.
        """
        try:
            settings = await AccountabilityAppService._get_user_settings(user_id)
            if not settings:
                logger.warning(f"No settings found for user {user_id}")
                return None

            tracker = await AccountabilityAppService._get_tracker(tracker_id)
            if not tracker:
                logger.warning(f"Tracker {tracker_id} not found")
                return None

            streak = await AccountabilityAppService._get_streak_from_db(
                user_id, tracker_id
            )

            message = AccountabilityAppService._generate_message_text(
                personality=settings.partner_personality,
                tracker_name=tracker.name,
                current_streak=streak,
            )

            pc = AccountabilityAppService._get_personality_config(
                settings.partner_personality
            )
            voice = AccountabilityAppService._resolve_voice(settings, pc)
            emotion = pc.get("emotion", "neutral")

            audio_bytes = await AccountabilityAppService._synthesize_voice(
                message, voice=voice, emotion=emotion
            )

            clean_text = strip_voice_tags(message)
            logger.info(
                f"Generated check-in audio for user {user_id}, "
                f"tracker {tracker_id} ({len(audio_bytes)} bytes)"
            )
            return (clean_text, audio_bytes)

        except Exception as e:
            logger.error(f"Failed to generate check-in: {e}")
            return None

    @staticmethod
    async def check_for_struggles(user_id: int) -> Dict[int, int]:
        """Check all trackers for consecutive misses.

        Returns:
            Dict mapping tracker_id -> consecutive_misses (only for struggling).
        """
        struggles: Dict[int, int] = {}

        settings = await AccountabilityAppService._get_user_settings(user_id)
        if not settings:
            return struggles

        trackers = await AccountabilityAppService._get_active_trackers(user_id)

        miss_counts: Dict[int, int] = {}
        for tracker in trackers:
            misses = await AccountabilityAppService._count_misses_from_db(
                user_id, tracker.id
            )
            miss_counts[tracker.id] = misses

        return AccountabilityDomainService.detect_struggles(
            miss_counts, settings.struggle_threshold
        )

    @staticmethod
    async def send_struggle_alert(
        user_id: int, tracker_id: int, consecutive_misses: int
    ) -> Optional[Tuple[str, bytes]]:
        """Generate struggle support voice message.

        Returns:
            Tuple of (clean text, MP3 audio bytes) on success, None on failure.
        """
        try:
            settings = await AccountabilityAppService._get_user_settings(user_id)
            if not settings:
                return None

            tracker = await AccountabilityAppService._get_tracker(tracker_id)
            if not tracker:
                return None

            message = AccountabilityAppService._generate_struggle_text(
                personality=settings.partner_personality,
                tracker_name=tracker.name,
                consecutive_misses=consecutive_misses,
            )

            pc = AccountabilityAppService._get_personality_config(
                settings.partner_personality
            )
            voice = AccountabilityAppService._resolve_voice(settings, pc)
            emotion = pc.get("emotion", "neutral")

            audio_bytes = await AccountabilityAppService._synthesize_voice(
                message, voice=voice, emotion=emotion
            )

            clean_text = strip_voice_tags(message)
            logger.info(
                f"Generated struggle alert for user {user_id}, tracker {tracker_id}"
            )
            return (clean_text, audio_bytes)

        except Exception as e:
            logger.error(f"Failed to generate struggle alert: {e}")
            return None

    @staticmethod
    async def celebrate_milestone(
        user_id: int, tracker_id: int, milestone: int
    ) -> Optional[Tuple[str, bytes]]:
        """Generate milestone celebration voice message.

        Returns:
            Tuple of (clean text, MP3 audio bytes) on success, None on failure.
        """
        try:
            settings = await AccountabilityAppService._get_user_settings(user_id)
            if not settings:
                return None

            tracker = await AccountabilityAppService._get_tracker(tracker_id)
            if not tracker:
                return None

            enthusiasm = AccountabilityDomainService.get_enthusiasm_value(
                settings.celebration_style
            )

            message = AccountabilityAppService._generate_celebration_text(
                personality=settings.partner_personality,
                tracker_name=tracker.name,
                milestone=milestone,
                enthusiasm=enthusiasm,
            )

            pc = AccountabilityAppService._get_personality_config(
                settings.partner_personality
            )
            voice = AccountabilityAppService._resolve_voice(settings, pc)

            audio_bytes = await AccountabilityAppService._synthesize_voice(
                message, voice=voice, emotion="cheerful"
            )

            clean_text = strip_voice_tags(message)
            logger.info(
                f"Generated celebration for user {user_id}, "
                f"tracker {tracker_id}, milestone {milestone}"
            )
            return (clean_text, audio_bytes)

        except Exception as e:
            logger.error(f"Failed to generate celebration: {e}")
            return None
