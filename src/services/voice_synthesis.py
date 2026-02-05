"""
Voice synthesis service — backward-compatible shim.

All TTS logic now lives in tts_service.py. This module preserves the original
public API so existing callers (voice_response_service, accountability,
voice_settings_commands, tests) continue to work unchanged.
"""

import logging
from typing import Dict, List

from .tts_service import (
    GROQ_EMOTIONS,
    GROQ_VOICES,
    get_tts_service,
)

logger = logging.getLogger(__name__)

# Re-export constants for any code that reads them directly
VOICES = GROQ_VOICES
EMOTIONS = GROQ_EMOTIONS
MAX_CHUNK_SIZE = 200


class VoiceSynthesisError(Exception):
    """Exception raised for voice synthesis errors."""

    pass


# ---------------------------------------------------------------------------
# Public API — delegates to TTSService
# ---------------------------------------------------------------------------


async def synthesize_voice(
    text: str,
    voice: str = "diana",
    emotion: str = "cheerful",
    add_emotion_tag: bool = True,
) -> bytes:
    """Generate voice audio (WAV). Delegates to TTSService (Groq provider)."""
    service = get_tts_service()
    result = await service.synthesize(
        text,
        voice=voice,
        emotion=emotion,
        provider="groq",
        add_emotion_tag=add_emotion_tag,
    )
    if not result.success:
        raise VoiceSynthesisError(result.error)
    return result.audio_bytes


async def synthesize_voice_mp3(
    text: str,
    voice: str = "diana",
    emotion: str = "cheerful",
    add_emotion_tag: bool = True,
    bitrate: str = "128k",
    quality: int = 2,
) -> bytes:
    """Generate voice audio as MP3. Delegates to TTSService (Groq provider)."""
    service = get_tts_service()
    try:
        return await service.synthesize_mp3(
            text,
            voice=voice,
            emotion=emotion,
            provider="groq",
            add_emotion_tag=add_emotion_tag,
            quality=quality,
        )
    except RuntimeError as e:
        raise VoiceSynthesisError(str(e)) from e


def get_available_voices() -> Dict[str, str]:
    """Get dictionary of available voices and their descriptions."""
    return dict(VOICES)


def get_available_emotions() -> Dict[str, str]:
    """Get dictionary of available emotions and their descriptions."""
    return dict(EMOTIONS)


# ---------------------------------------------------------------------------
# Emotive tags (Groq-specific, kept here for convenience callers)
# ---------------------------------------------------------------------------


def add_emotive_tags(text: str, tags: List[str]) -> str:
    """Add inline emotive tags to text.

    Available tags: laugh, chuckle, sigh, cough, sniffle, groan, yawn, gasp
    """
    valid_tags = {
        "laugh",
        "chuckle",
        "sigh",
        "cough",
        "sniffle",
        "groan",
        "yawn",
        "gasp",
    }
    tag_string = " ".join(f"<{tag}>" for tag in tags if tag in valid_tags)
    if tag_string:
        return f"{text} {tag_string}"
    return text


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


async def synthesize_check_in(text: str, voice: str = "diana") -> bytes:
    """Synthesize a check-in message with cheerful tone."""
    return await synthesize_voice(text, voice=voice, emotion="cheerful")


async def synthesize_celebration(text: str, voice: str = "austin") -> bytes:
    """Synthesize a celebration message with enthusiastic tone."""
    enhanced_text = add_emotive_tags(text, ["chuckle"])
    return await synthesize_voice(enhanced_text, voice=voice, emotion="cheerful")


async def synthesize_support(text: str, voice: str = "daniel") -> bytes:
    """Synthesize a supportive message with calm, gentle tone."""
    return await synthesize_voice(text, voice=voice, emotion="neutral")


async def synthesize_reminder(text: str, voice: str = "diana") -> bytes:
    """Synthesize a gentle reminder."""
    return await synthesize_voice(text, voice=voice, emotion="cheerful")
