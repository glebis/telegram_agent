"""
Virtual accountability partner service.

Provides personalized check-ins, milestone celebrations, and struggle support
with configurable personality levels.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from ..core.config import get_config_value
from ..core.database import get_db_session
from ..core.i18n import t
from ..models.tracker import CheckIn, Tracker
from ..models.user_settings import UserSettings
from .voice_synthesis import synthesize_voice_mp3

logger = logging.getLogger(__name__)

# Personality configuration loaded from defaults.yaml
PERSONALITY_CONFIG = get_config_value("accountability.personalities", {})


def _strip_voice_tags(text: str) -> str:
    """Remove voice/emotion markup tags for clean text display."""
    text = re.sub(r"\[.*?\]", "", text)  # [whisper], [cheerful], etc.
    text = re.sub(r"<\w+>", "", text)  # <sigh>, <chuckle>, etc.
    return text.strip()


class AccountabilityService:
    """Service for virtual accountability partner interactions."""

    @staticmethod
    async def get_user_settings(user_id: int) -> Optional[UserSettings]:
        """Get user settings for accountability partner."""
        async with get_db_session() as session:
            result = await session.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_active_trackers(user_id: int) -> List[Tracker]:
        """Get all active trackers for a user."""
        async with get_db_session() as session:
            result = await session.execute(
                select(Tracker).where(
                    Tracker.user_id == user_id, Tracker.active == True
                )
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_streak(user_id: int, tracker_id: int) -> int:
        """Calculate current streak for a tracker."""
        async with get_db_session() as session:
            # Get all check-ins for this tracker, ordered by date
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

            if not check_ins:
                return 0

            # Count consecutive days from today backwards
            streak = 0
            current_date = datetime.now().date()

            for check_in in check_ins:
                check_in_date = check_in.created_at.date()

                # If this check-in is from current_date, increment streak
                if check_in_date == current_date:
                    streak += 1
                    current_date -= timedelta(days=1)
                elif check_in_date < current_date:
                    # Gap in streak, stop counting
                    break

            return streak

    @staticmethod
    async def count_consecutive_misses(user_id: int, tracker_id: int) -> int:
        """Count consecutive days without check-ins."""
        async with get_db_session() as session:
            # Get tracker to check frequency
            result = await session.execute(
                select(Tracker).where(Tracker.id == tracker_id)
            )
            tracker = result.scalar_one_or_none()

            if not tracker or tracker.check_frequency != "daily":
                return 0

            # Get last check-in
            result = await session.execute(
                select(CheckIn)
                .where(CheckIn.user_id == user_id, CheckIn.tracker_id == tracker_id)
                .order_by(CheckIn.created_at.desc())
                .limit(1)
            )
            last_check_in = result.scalar_one_or_none()

            if not last_check_in:
                # No check-ins ever, not a "miss" yet
                return 0

            # Calculate days since last check-in
            days_since = (datetime.now() - last_check_in.created_at).days

            return max(0, days_since)

    @staticmethod
    def generate_check_in_message(
        personality: str,
        tracker_name: str,
        current_streak: int = 0,
        locale: str = "en",
    ) -> str:
        """Generate check-in message based on personality level."""
        if current_streak > 0:
            return t(
                f"accountability.voice.{personality}.checkin_streak",
                locale,
                name=tracker_name,
                streak=current_streak,
            )
        return t(
            f"accountability.voice.{personality}.checkin",
            locale,
            name=tracker_name,
        )

    @staticmethod
    def generate_celebration_message(
        personality: str,
        tracker_name: str,
        milestone: int,
        enthusiasm: float = 1.0,
        locale: str = "en",
    ) -> str:
        """Generate milestone celebration message."""
        message = t(
            f"accountability.voice.{personality}.celebration",
            locale,
            name=tracker_name,
            milestone=milestone,
            next_milestone=milestone * 2,
        )

        # Adjust enthusiasm (for celebration_style)
        if enthusiasm < 0.7:
            # Quiet style - remove emojis and excited tags
            message = (
                message.replace("🎉 ", "")
                .replace("!", ".")
                .replace("<laugh>", "")
                .replace("<chuckle>", "")
            )
        elif enthusiasm > 1.3:
            # Enthusiastic style - add extra energy
            message = message + " 🔥"

        return message

    @staticmethod
    def generate_struggle_message(
        personality: str,
        tracker_name: str,
        consecutive_misses: int,
        locale: str = "en",
    ) -> str:
        """Generate struggle support message."""
        return t(
            f"accountability.voice.{personality}.struggle",
            locale,
            name=tracker_name,
            misses=consecutive_misses,
        )

    @staticmethod
    async def send_check_in(
        user_id: int, tracker_id: int
    ) -> Optional[Tuple[str, bytes]]:
        """Generate check-in voice message.

        Returns:
            Tuple of (clean text, MP3 audio bytes) on success, None on failure.
        """
        try:
            settings = await AccountabilityService.get_user_settings(user_id)
            if not settings:
                logger.warning(f"No settings found for user {user_id}")
                return None

            async with get_db_session() as session:
                result = await session.execute(
                    select(Tracker).where(Tracker.id == tracker_id)
                )
                tracker = result.scalar_one_or_none()
                if not tracker:
                    logger.warning(f"Tracker {tracker_id} not found")
                    return None

            streak = await AccountabilityService.get_streak(user_id, tracker_id)

            message = AccountabilityService.generate_check_in_message(
                personality=settings.partner_personality,
                tracker_name=tracker.name,
                current_streak=streak,
            )

            personality_config = PERSONALITY_CONFIG.get(
                settings.partner_personality, PERSONALITY_CONFIG["supportive"]
            )
            voice = settings.partner_voice_override or personality_config["voice"]
            emotion = personality_config["emotion"]

            audio_bytes = await synthesize_voice_mp3(
                message, voice=voice, emotion=emotion
            )

            clean_text = _strip_voice_tags(message)
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
        """
        Check all trackers for consecutive misses.

        Returns:
            Dict mapping tracker_id to consecutive_misses count (only for struggling trackers)
        """
        struggles = {}

        settings = await AccountabilityService.get_user_settings(user_id)
        if not settings:
            return struggles

        trackers = await AccountabilityService.get_active_trackers(user_id)

        for tracker in trackers:
            consecutive_misses = await AccountabilityService.count_consecutive_misses(
                user_id, tracker.id
            )

            if consecutive_misses >= settings.struggle_threshold:
                struggles[tracker.id] = consecutive_misses

        return struggles

    @staticmethod
    async def send_struggle_alert(
        user_id: int, tracker_id: int, consecutive_misses: int
    ) -> Optional[Tuple[str, bytes]]:
        """Generate struggle support voice message.

        Returns:
            Tuple of (clean text, MP3 audio bytes) on success, None on failure.
        """
        try:
            settings = await AccountabilityService.get_user_settings(user_id)
            if not settings:
                return None

            async with get_db_session() as session:
                result = await session.execute(
                    select(Tracker).where(Tracker.id == tracker_id)
                )
                tracker = result.scalar_one_or_none()
                if not tracker:
                    return None

            message = AccountabilityService.generate_struggle_message(
                personality=settings.partner_personality,
                tracker_name=tracker.name,
                consecutive_misses=consecutive_misses,
            )

            personality_config = PERSONALITY_CONFIG.get(
                settings.partner_personality, PERSONALITY_CONFIG["supportive"]
            )
            voice = settings.partner_voice_override or personality_config["voice"]
            emotion = personality_config["emotion"]

            audio_bytes = await synthesize_voice_mp3(
                message, voice=voice, emotion=emotion
            )

            clean_text = _strip_voice_tags(message)
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
            settings = await AccountabilityService.get_user_settings(user_id)
            if not settings:
                return None

            async with get_db_session() as session:
                result = await session.execute(
                    select(Tracker).where(Tracker.id == tracker_id)
                )
                tracker = result.scalar_one_or_none()
                if not tracker:
                    return None

            enthusiasm_map = {
                "quiet": 0.5,
                "moderate": 1.0,
                "enthusiastic": 2.0,
            }
            enthusiasm = enthusiasm_map.get(settings.celebration_style, 1.0)

            message = AccountabilityService.generate_celebration_message(
                personality=settings.partner_personality,
                tracker_name=tracker.name,
                milestone=milestone,
                enthusiasm=enthusiasm,
            )

            personality_config = PERSONALITY_CONFIG.get(
                settings.partner_personality, PERSONALITY_CONFIG["supportive"]
            )
            voice = settings.partner_voice_override or personality_config["voice"]

            audio_bytes = await synthesize_voice_mp3(
                message, voice=voice, emotion="cheerful"
            )

            clean_text = _strip_voice_tags(message)
            logger.info(
                f"Generated celebration for user {user_id}, "
                f"tracker {tracker_id}, milestone {milestone}"
            )
            return (clean_text, audio_bytes)

        except Exception as e:
            logger.error(f"Failed to generate celebration: {e}")
            return None
