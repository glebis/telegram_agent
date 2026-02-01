"""
Voice synthesis service using Groq Orpheus TTS.

Handles text-to-speech conversion with emotive controls and voice selection.
"""

import asyncio
import logging
import os
import struct
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional, List
import aiohttp

logger = logging.getLogger(__name__)

# Available voices and their characteristics
VOICES = {
    "diana": "Warm, conversational female voice (recommended for check-ins)",
    "hannah": "Professional, clear female voice",
    "autumn": "Friendly, approachable female voice",
    "austin": "Supportive, friendly male voice (great for accountability)",
    "daniel": "Calm, reassuring male voice (gentle approach)",
    "troy": "Energetic, motivational male voice",
}

# Emotion styles
EMOTIONS = {
    "cheerful": "Upbeat, positive tone",
    "neutral": "Standard delivery",
    "whisper": "Soft, quiet delivery",
}

# Max characters per Groq API request
MAX_CHUNK_SIZE = 200


class VoiceSynthesisError(Exception):
    """Exception raised for voice synthesis errors"""
    pass


async def synthesize_voice(
    text: str,
    voice: str = "diana",
    emotion: str = "cheerful",
    add_emotion_tag: bool = True,
) -> bytes:
    """
    Generate voice audio using Groq Orpheus TTS.

    Args:
        text: Text to synthesize (will be chunked if > 200 chars)
        voice: One of: diana, hannah, autumn, austin, daniel, troy
        emotion: One of: cheerful, neutral, whisper
        add_emotion_tag: Whether to wrap text with emotion brackets

    Returns:
        WAV audio bytes (24000 Hz, 16-bit mono)

    Raises:
        VoiceSynthesisError: If synthesis fails
    """
    if voice not in VOICES:
        logger.warning(f"Invalid voice '{voice}', falling back to diana")
        voice = "diana"

    if emotion not in EMOTIONS:
        logger.warning(f"Invalid emotion '{emotion}', falling back to cheerful")
        emotion = "cheerful"

    # Add emotion wrapper if requested
    if add_emotion_tag and emotion != "neutral":
        emotive_text = f"[{emotion}] {text}"
    else:
        emotive_text = text

    # Chunk text if necessary
    chunks = _chunk_text(emotive_text, max_length=MAX_CHUNK_SIZE)
    logger.info(f"Synthesizing {len(chunks)} chunks with voice={voice}, emotion={emotion}")

    # Synthesize each chunk
    audio_chunks = []
    for i, chunk in enumerate(chunks):
        try:
            audio = await _synthesize_chunk(chunk, voice)
            audio_chunks.append(audio)
            logger.debug(f"Chunk {i+1}/{len(chunks)} synthesized ({len(audio)} bytes)")
        except Exception as e:
            logger.error(f"Failed to synthesize chunk {i+1}: {e}")
            raise VoiceSynthesisError(f"Failed to synthesize chunk {i+1}: {e}")

    # Combine audio chunks if multiple
    if len(audio_chunks) == 1:
        return audio_chunks[0]
    else:
        return _combine_wav_files(audio_chunks)


async def _synthesize_chunk(text: str, voice: str) -> bytes:
    """Synthesize a single chunk of text using Groq API."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise VoiceSynthesisError("GROQ_API_KEY environment variable not set")

    url = "https://api.groq.com/openai/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "canopylabs/orpheus-v1-english",
        "input": text,
        "voice": voice,
        "response_format": "wav",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise VoiceSynthesisError(
                    f"Groq API returned {resp.status}: {error_text}"
                )

            return await resp.read()


def _chunk_text(text: str, max_length: int = 200) -> List[str]:
    """
    Split text into chunks at sentence boundaries, respecting max_length.

    Tries to split on:
    1. Period followed by space
    2. Question mark followed by space
    3. Exclamation mark followed by space
    4. Comma followed by space (if needed)
    5. Any space (as last resort)
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining.strip())
            break

        # Find best split point
        chunk = remaining[:max_length]

        # Try to split on sentence boundary
        split_pos = -1
        for delimiter in [". ", "? ", "! ", ", ", " "]:
            pos = chunk.rfind(delimiter)
            if pos > max_length * 0.5:  # Don't split too early
                split_pos = pos + len(delimiter)
                break

        if split_pos == -1:
            # No good split point, force split at max_length
            split_pos = max_length

        chunks.append(remaining[:split_pos].strip())
        remaining = remaining[split_pos:].strip()

    return chunks


def _combine_wav_files(chunks: List[bytes]) -> bytes:
    """
    Combine multiple WAV files into one with proper header.

    Creates a valid WAV file with correct RIFF header and size fields.
    """
    if len(chunks) == 0:
        raise VoiceSynthesisError("No audio chunks to combine")

    if len(chunks) == 1:
        return _fix_wav_header(chunks[0])

    # Combine all audio data (skip headers for subsequent chunks)
    audio_data = bytearray()
    for chunk in chunks:
        # Skip 44-byte WAV header
        audio_data += chunk[44:]

    # Create proper WAV header
    # WAV format: 24000 Hz, 16-bit, mono
    sample_rate = 24000
    bits_per_sample = 16
    num_channels = 1
    byte_rate = sample_rate * num_channels * bits_per_sample // 8

    # Build WAV header
    header = bytearray()

    # RIFF header
    header += b"RIFF"
    header += struct.pack("<I", 36 + len(audio_data))  # File size - 8
    header += b"WAVE"

    # fmt chunk
    header += b"fmt "
    header += struct.pack("<I", 16)  # fmt chunk size
    header += struct.pack("<H", 1)  # Audio format (1 = PCM)
    header += struct.pack("<H", num_channels)
    header += struct.pack("<I", sample_rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", num_channels * bits_per_sample // 8)  # Block align
    header += struct.pack("<H", bits_per_sample)

    # data chunk
    header += b"data"
    header += struct.pack("<I", len(audio_data))

    return bytes(header) + bytes(audio_data)


def _fix_wav_header(wav_bytes: bytes) -> bytes:
    """Fix WAV header to have proper size fields instead of 0xFFFFFFFF."""
    if len(wav_bytes) < 44:
        return wav_bytes

    # Get audio data size
    audio_data = wav_bytes[44:]
    data_size = len(audio_data)
    file_size = 36 + data_size

    # Build new header
    header = bytearray(wav_bytes[:44])

    # Update RIFF chunk size (bytes 4-7)
    header[4:8] = struct.pack("<I", file_size)

    # Update data chunk size (bytes 40-43)
    header[40:44] = struct.pack("<I", data_size)

    return bytes(header) + audio_data


def add_emotive_tags(text: str, tags: List[str]) -> str:
    """
    Add inline emotive tags to text.

    Available tags: laugh, chuckle, sigh, cough, sniffle, groan, yawn, gasp

    Example:
        add_emotive_tags("Hey there!", ["chuckle"])
        => "Hey there! <chuckle>"
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


def get_available_voices() -> dict:
    """Get dictionary of available voices and their descriptions."""
    return VOICES.copy()


def get_available_emotions() -> dict:
    """Get dictionary of available emotions and their descriptions."""
    return EMOTIONS.copy()


# Convenience functions for common use cases


async def synthesize_check_in(text: str, voice: str = "diana") -> bytes:
    """Synthesize a check-in message with cheerful tone."""
    return await synthesize_voice(text, voice=voice, emotion="cheerful")


async def synthesize_celebration(text: str, voice: str = "austin") -> bytes:
    """Synthesize a celebration message with enthusiastic tone."""
    # Add chuckle for extra warmth
    enhanced_text = add_emotive_tags(text, ["chuckle"])
    return await synthesize_voice(enhanced_text, voice=voice, emotion="cheerful")


async def synthesize_support(text: str, voice: str = "daniel") -> bytes:
    """Synthesize a supportive message with calm, gentle tone."""
    return await synthesize_voice(text, voice=voice, emotion="neutral")


async def synthesize_reminder(text: str, voice: str = "diana") -> bytes:
    """Synthesize a gentle reminder."""
    return await synthesize_voice(text, voice=voice, emotion="cheerful")


async def convert_to_mp3(
    wav_bytes: bytes, bitrate: str = "128k", quality: int = 2
) -> bytes:
    """
    Convert WAV audio to MP3 using ffmpeg.

    Args:
        wav_bytes: WAV audio bytes
        bitrate: MP3 bitrate (e.g., "128k", "192k", "256k")
        quality: VBR quality (0-9, where 0 is best, 2 is high quality default)

    Returns:
        MP3 audio bytes

    Note: Uses ffmpeg with libmp3lame encoder.
    Quality 2 (~190 kbps VBR) provides excellent quality with fast encoding.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False
    ) as wav_file, tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
        wav_path = wav_file.name
        mp3_path = mp3_file.name

        try:
            # Write WAV to temp file
            wav_file.write(wav_bytes)
            wav_file.flush()

            # Convert to MP3 using ffmpeg
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i",
                wav_path,
                "-codec:a",
                "libmp3lame",
                "-qscale:a",
                str(quality),  # VBR quality
                "-y",  # Overwrite output
                mp3_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"ffmpeg conversion failed: {error_msg}")
                raise VoiceSynthesisError(f"MP3 conversion failed: {error_msg}")

            # Read MP3 file
            with open(mp3_path, "rb") as f:
                mp3_bytes = f.read()

            logger.info(
                f"Converted WAV ({len(wav_bytes)} bytes) to MP3 ({len(mp3_bytes)} bytes)"
            )
            return mp3_bytes

        finally:
            # Cleanup temp files
            Path(wav_path).unlink(missing_ok=True)
            Path(mp3_path).unlink(missing_ok=True)


async def synthesize_voice_mp3(
    text: str,
    voice: str = "diana",
    emotion: str = "cheerful",
    add_emotion_tag: bool = True,
    bitrate: str = "128k",
    quality: int = 2,
) -> bytes:
    """
    Generate voice audio as MP3 (instead of WAV).

    Same parameters as synthesize_voice(), but returns MP3 bytes.
    Quality 2 provides ~190 kbps VBR, excellent quality with fast encoding.

    Returns:
        MP3 audio bytes
    """
    # Generate WAV
    wav_bytes = await synthesize_voice(text, voice, emotion, add_emotion_tag)

    # Convert to MP3
    mp3_bytes = await convert_to_mp3(wav_bytes, bitrate, quality)

    return mp3_bytes
