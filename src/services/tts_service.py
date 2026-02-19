"""
Multi-provider TTS service.

Supports Groq Orpheus and OpenAI TTS with per-user provider selection.
"""

import asyncio
import logging
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TTSResult:
    """Result of a TTS synthesis request."""

    success: bool
    audio_bytes: bytes = b""
    format: str = "wav"  # "wav" or "mp3"
    provider: str = ""
    error: str = ""


@dataclass
class ProviderCapabilities:
    """Capabilities of a TTS provider."""

    name: str
    voices: Dict[str, str]
    emotions: Dict[str, str]
    supports_emotion_tags: bool
    native_formats: List[str]
    max_chunk_size: int


# ---------------------------------------------------------------------------
# Provider voice/emotion catalogs
# ---------------------------------------------------------------------------

GROQ_VOICES = {
    "diana": "Warm, conversational female voice (recommended for check-ins)",
    "hannah": "Professional, clear female voice",
    "autumn": "Friendly, approachable female voice",
    "austin": "Supportive, friendly male voice (great for accountability)",
    "daniel": "Calm, reassuring male voice (gentle approach)",
    "troy": "Energetic, motivational male voice",
}

GROQ_EMOTIONS = {
    "cheerful": "Upbeat, positive tone",
    "neutral": "Standard delivery",
    "whisper": "Soft, quiet delivery",
}

OPENAI_VOICES = {
    "alloy": "Neutral, balanced voice",
    "ash": "Warm, conversational voice",
    "ballad": "Expressive, dramatic voice",
    "coral": "Clear, friendly voice",
    "echo": "Smooth, even-toned voice",
    "fable": "Distinctive, British-accented voice",
    "onyx": "Deep, authoritative voice",
    "nova": "Energetic, bright female voice",
    "sage": "Calm, measured voice",
    "shimmer": "Light, upbeat female voice",
}

OPENAI_EMOTIONS: Dict[str, str] = {}  # OpenAI TTS does not support emotion tags

# Cross-provider voice mapping (best-effort match by character)
_VOICE_MAP_GROQ_TO_OPENAI = {
    "diana": "coral",
    "hannah": "sage",
    "autumn": "shimmer",
    "austin": "ash",
    "daniel": "echo",
    "troy": "onyx",
}

_VOICE_MAP_OPENAI_TO_GROQ = {
    "alloy": "diana",
    "ash": "austin",
    "ballad": "diana",
    "coral": "diana",
    "echo": "daniel",
    "fable": "hannah",
    "onyx": "troy",
    "nova": "autumn",
    "sage": "hannah",
    "shimmer": "autumn",
}


# ---------------------------------------------------------------------------
# Helpers (extracted from voice_synthesis.py)
# ---------------------------------------------------------------------------


def _chunk_text(text: str, max_length: int = 200) -> List[str]:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining.strip())
            break

        chunk = remaining[:max_length]
        split_pos = -1
        for delimiter in [". ", "? ", "! ", ", ", " "]:
            pos = chunk.rfind(delimiter)
            if pos > max_length * 0.5:
                split_pos = pos + len(delimiter)
                break

        if split_pos == -1:
            split_pos = max_length

        chunks.append(remaining[:split_pos].strip())
        remaining = remaining[split_pos:].strip()

    return chunks


def _combine_wav_files(chunks: List[bytes]) -> bytes:
    """Combine multiple WAV files into one with proper header."""
    if len(chunks) == 0:
        raise RuntimeError("No audio chunks to combine")
    if len(chunks) == 1:
        return _fix_wav_header(chunks[0])

    audio_data = bytearray()
    for chunk in chunks:
        audio_data += chunk[44:]

    sample_rate = 24000
    bits_per_sample = 16
    num_channels = 1
    byte_rate = sample_rate * num_channels * bits_per_sample // 8

    header = bytearray()
    header += b"RIFF"
    header += struct.pack("<I", 36 + len(audio_data))
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<I", 16)
    header += struct.pack("<H", 1)
    header += struct.pack("<H", num_channels)
    header += struct.pack("<I", sample_rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", num_channels * bits_per_sample // 8)
    header += struct.pack("<H", bits_per_sample)
    header += b"data"
    header += struct.pack("<I", len(audio_data))

    return bytes(header) + bytes(audio_data)


def _fix_wav_header(wav_bytes: bytes) -> bytes:
    """Fix WAV header to have proper size fields."""
    if len(wav_bytes) < 44:
        return wav_bytes

    audio_data = wav_bytes[44:]
    data_size = len(audio_data)
    file_size = 36 + data_size

    header = bytearray(wav_bytes[:44])
    header[4:8] = struct.pack("<I", file_size)
    header[40:44] = struct.pack("<I", data_size)

    return bytes(header) + audio_data


async def convert_to_mp3(
    wav_bytes: bytes, bitrate: str = "128k", quality: int = 2
) -> bytes:
    """Convert WAV audio to MP3 using ffmpeg."""
    with (
        tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file,
        tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file,
    ):
        wav_path = wav_file.name
        mp3_path = mp3_file.name

        try:
            wav_file.write(wav_bytes)
            wav_file.flush()

            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i",
                wav_path,
                "-codec:a",
                "libmp3lame",
                "-qscale:a",
                str(quality),
                "-y",
                mp3_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"ffmpeg conversion failed: {error_msg}")
                raise RuntimeError(f"MP3 conversion failed: {error_msg}")

            with open(mp3_path, "rb") as f:
                mp3_bytes = f.read()

            logger.info(
                f"Converted WAV ({len(wav_bytes)} bytes) "
                f"to MP3 ({len(mp3_bytes)} bytes)"
            )
            return mp3_bytes
        finally:
            Path(wav_path).unlink(missing_ok=True)
            Path(mp3_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TTSService
# ---------------------------------------------------------------------------


class TTSService:
    """Multi-provider TTS service."""

    def __init__(self, default_provider: str = "groq"):
        self._default_provider = default_provider

    # -- Factory --

    @classmethod
    def from_env(cls) -> "TTSService":
        """Create service from environment configuration."""
        provider = os.getenv("TTS_PROVIDER", "groq")
        return cls(default_provider=provider)

    # -- Provider resolution --

    def resolve_provider(self, user_override: str = "") -> str:
        """Resolve which provider to use. User pref > system default."""
        if user_override and user_override in ("groq", "openai"):
            return user_override
        return self._default_provider

    # -- Capabilities --

    def get_capabilities(self, provider: str) -> ProviderCapabilities:
        """Get capabilities for a provider."""
        if provider == "openai":
            return ProviderCapabilities(
                name="openai",
                voices=OPENAI_VOICES,
                emotions=OPENAI_EMOTIONS,
                supports_emotion_tags=False,
                native_formats=["mp3", "opus", "aac", "flac", "wav", "pcm"],
                max_chunk_size=4096,
            )
        # Default: groq
        return ProviderCapabilities(
            name="groq",
            voices=GROQ_VOICES,
            emotions=GROQ_EMOTIONS,
            supports_emotion_tags=True,
            native_formats=["wav"],
            max_chunk_size=200,
        )

    def get_voices(self, provider: str = "") -> Dict[str, str]:
        """Get available voices for a provider."""
        provider = provider or self._default_provider
        return dict(self.get_capabilities(provider).voices)

    def get_emotions(self, provider: str = "") -> Dict[str, str]:
        """Get available emotions for a provider."""
        provider = provider or self._default_provider
        return dict(self.get_capabilities(provider).emotions)

    def map_voice(self, voice: str, target_provider: str) -> str:
        """Map a voice name from one provider to another."""
        if target_provider == "openai":
            return _VOICE_MAP_GROQ_TO_OPENAI.get(voice, "coral")
        else:
            return _VOICE_MAP_OPENAI_TO_GROQ.get(voice, "diana")

    # -- Synthesis --

    async def synthesize(
        self,
        text: str,
        voice: str = "diana",
        emotion: str = "cheerful",
        provider: str = "",
        output_format: str = "",
        add_emotion_tag: bool = True,
    ) -> TTSResult:
        """Synthesize text to audio."""
        provider = self.resolve_provider(provider)
        caps = self.get_capabilities(provider)

        # Validate voice
        if voice not in caps.voices:
            mapped = self.map_voice(voice, provider)
            logger.info(f"Voice '{voice}' not in {provider}, mapped to '{mapped}'")
            voice = mapped

        try:
            if provider == "openai":
                return await self._synthesize_openai(text, voice, output_format)
            else:
                return await self._synthesize_groq(
                    text, voice, emotion, add_emotion_tag, caps
                )
        except Exception as e:
            logger.error(f"TTS synthesis failed ({provider}): {e}")
            return TTSResult(success=False, provider=provider, error=str(e))

    async def synthesize_mp3(
        self,
        text: str,
        voice: str = "diana",
        emotion: str = "cheerful",
        provider: str = "",
        add_emotion_tag: bool = True,
        quality: int = 2,
    ) -> bytes:
        """Synthesize text and return MP3 bytes.

        Skips ffmpeg conversion if provider returns MP3 natively.
        """
        provider = self.resolve_provider(provider)

        # OpenAI returns MP3 natively
        if provider == "openai":
            result = await self.synthesize(
                text,
                voice,
                emotion,
                provider,
                output_format="mp3",
                add_emotion_tag=add_emotion_tag,
            )
            if not result.success:
                raise RuntimeError(f"TTS failed: {result.error}")
            return result.audio_bytes

        # Groq returns WAV, needs conversion
        result = await self.synthesize(
            text,
            voice,
            emotion,
            provider,
            output_format="wav",
            add_emotion_tag=add_emotion_tag,
        )
        if not result.success:
            raise RuntimeError(f"TTS failed: {result.error}")

        return await convert_to_mp3(result.audio_bytes, quality=quality)

    # -- Groq provider --

    async def _synthesize_groq(
        self,
        text: str,
        voice: str,
        emotion: str,
        add_emotion_tag: bool,
        caps: ProviderCapabilities,
    ) -> TTSResult:
        """Synthesize using Groq Orpheus TTS."""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return TTSResult(
                success=False, provider="groq", error="GROQ_API_KEY not set"
            )

        # Add emotion wrapper
        if add_emotion_tag and emotion != "neutral" and emotion in GROQ_EMOTIONS:
            emotive_text = f"[{emotion}] {text}"
        else:
            emotive_text = text

        chunks = _chunk_text(emotive_text, max_length=caps.max_chunk_size)
        logger.info(
            f"Synthesizing {len(chunks)} chunks with "
            f"Groq voice={voice}, emotion={emotion}"
        )

        url = "https://api.groq.com/openai/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        audio_chunks = []
        async with aiohttp.ClientSession() as session:
            for i, chunk in enumerate(chunks):
                payload = {
                    "model": "canopylabs/orpheus-v1-english",
                    "input": chunk,
                    "voice": voice,
                    "response_format": "wav",
                }
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return TTSResult(
                            success=False,
                            provider="groq",
                            error=f"Groq API returned {resp.status}: {error_text}",
                        )
                    audio_chunks.append(await resp.read())
                    logger.debug(
                        f"Chunk {i + 1}/{len(chunks)} synthesized "
                        f"({len(audio_chunks[-1])} bytes)"
                    )

        if len(audio_chunks) == 1:
            wav_bytes = audio_chunks[0]
        else:
            wav_bytes = _combine_wav_files(audio_chunks)

        return TTSResult(
            success=True, audio_bytes=wav_bytes, format="wav", provider="groq"
        )

    # -- OpenAI provider --

    async def _synthesize_openai(
        self, text: str, voice: str, output_format: str = ""
    ) -> TTSResult:
        """Synthesize using OpenAI TTS API."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return TTSResult(
                success=False, provider="openai", error="OPENAI_API_KEY not set"
            )

        if voice not in OPENAI_VOICES:
            voice = "coral"

        fmt = output_format or "mp3"

        url = "https://api.openai.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice,
            "response_format": fmt,
        }

        logger.info(f"Synthesizing with OpenAI voice={voice}, format={fmt}")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return TTSResult(
                        success=False,
                        provider="openai",
                        error=f"OpenAI API returned {resp.status}: {error_text}",
                    )
                audio_bytes = await resp.read()

        logger.info(f"OpenAI TTS: {len(audio_bytes)} bytes ({fmt})")
        return TTSResult(
            success=True, audio_bytes=audio_bytes, format=fmt, provider="openai"
        )


# ---------------------------------------------------------------------------
def get_tts_service() -> TTSService:
    """Get the global TTS service instance (delegates to DI container)."""
    from ..core.services import Services, get_service

    return get_service(Services.TTS)
