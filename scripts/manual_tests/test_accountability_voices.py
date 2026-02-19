#!/usr/bin/env python3
"""
Test voice synthesis with all 5 accountability partner personalities.

Generates audio samples for:
- Check-in reminders
- Milestone celebrations
- Struggle alerts

Usage:
    python scripts/test_accountability_voices.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.accountability_service import AccountabilityService
from src.services.voice_synthesis import synthesize_voice
from src.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PERSONALITIES = ["gentle", "supportive", "direct", "assertive", "tough_love"]
OUTPUT_DIR = Path("/tmp/accountability_voice_tests")


async def test_personality_voices():
    """Generate voice samples for all personalities."""

    OUTPUT_DIR.mkdir(exist_ok=True)
    logger.info(f"Generating voice samples in {OUTPUT_DIR}")

    config = get_settings().accountability.personalities

    for personality in PERSONALITIES:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Testing personality: {personality.upper()}")
        logger.info(f"{'=' * 60}")

        personality_config = config.get(personality)
        voice = personality_config["voice"]
        emotion = personality_config["emotion"]

        # Test 1: Check-in message
        logger.info(f"\n1. Check-in (voice={voice}, emotion={emotion})")
        check_in_msg = AccountabilityService.generate_check_in_message(
            personality=personality,
            tracker_name="meditation",
            current_streak=4
        )
        logger.info(f"   Message: {check_in_msg}")

        try:
            audio = await synthesize_voice(check_in_msg, voice=voice, emotion=emotion)
            output_file = OUTPUT_DIR / f"{personality}_check_in.wav"
            with open(output_file, "wb") as f:
                f.write(audio)
            logger.info(f"   ✅ Saved: {output_file} ({len(audio)} bytes)")
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")

        # Test 2: Celebration message
        logger.info(f"\n2. Celebration (7-day streak)")
        celebration_msg = AccountabilityService.generate_celebration_message(
            personality=personality,
            tracker_name="meditation",
            milestone=7,
            enthusiasm=1.0
        )
        logger.info(f"   Message: {celebration_msg}")

        try:
            audio = await synthesize_voice(celebration_msg, voice=voice, emotion="cheerful")
            output_file = OUTPUT_DIR / f"{personality}_celebration.wav"
            with open(output_file, "wb") as f:
                f.write(audio)
            logger.info(f"   ✅ Saved: {output_file} ({len(audio)} bytes)")
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")

        # Test 3: Struggle message
        logger.info(f"\n3. Struggle alert (3 misses)")
        struggle_msg = AccountabilityService.generate_struggle_message(
            personality=personality,
            tracker_name="meditation",
            consecutive_misses=3
        )
        logger.info(f"   Message: {struggle_msg}")

        try:
            audio = await synthesize_voice(struggle_msg, voice=voice, emotion=emotion)
            output_file = OUTPUT_DIR / f"{personality}_struggle.wav"
            with open(output_file, "wb") as f:
                f.write(audio)
            logger.info(f"   ✅ Saved: {output_file} ({len(audio)} bytes)")
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")

    logger.info(f"\n{'=' * 60}")
    logger.info(f"✅ Voice samples generated in: {OUTPUT_DIR}")
    logger.info(f"{'=' * 60}")
    logger.info("\nSamples created:")
    for personality in PERSONALITIES:
        logger.info(f"\n  {personality.upper()}:")
        logger.info(f"    - {personality}_check_in.wav")
        logger.info(f"    - {personality}_celebration.wav")
        logger.info(f"    - {personality}_struggle.wav")

    logger.info(f"\nPlay a sample:")
    logger.info(f"  afplay {OUTPUT_DIR}/supportive_check_in.wav")
    logger.info("\n")


async def main():
    """Main test function."""
    try:
        await test_personality_voices()
        return 0
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
