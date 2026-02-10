"""
Voice Response Service - Synthesize text responses as voice messages.

This service determines when to synthesize responses based on user preferences
and sends voice messages to Telegram.
"""

import logging
from typing import Optional

from ..core.database import get_chat_by_telegram_id, get_db_session
from .tts_service import get_tts_service

logger = logging.getLogger(__name__)


class VoiceResponseService:
    """Service for synthesizing text responses as voice."""

    async def should_synthesize_voice(
        self, chat_id: int, text: str, context: str = "general"
    ) -> bool:
        """
        Determine if response should be synthesized as voice.

        Args:
            chat_id: Telegram chat ID
            text: Response text
            context: Response context (general, check_in, notification)

        Returns:
            True if voice should be synthesized, False otherwise
        """
        async with get_db_session() as session:
            chat_obj = await get_chat_by_telegram_id(session, chat_id)
            if not chat_obj:
                return False

            mode = chat_obj.voice_response_mode

            if mode in ("always_voice", "voice_only"):
                return True
            elif mode == "text_only":
                return False
            elif mode == "voice_on_request":
                # Only synthesize if explicitly requested in text
                return any(
                    keyword in text.lower()
                    for keyword in ["send as voice", "voice message", "read aloud"]
                )
            elif mode == "smart":
                # Smart mode logic
                return self._is_voice_appropriate(text, context)

            return False

    def _is_voice_appropriate(self, text: str, context: str) -> bool:
        """
        Smart mode logic - determine if voice is appropriate.

        Voice is appropriate for:
        - Short messages (< 500 chars)
        - Check-ins and notifications
        - Encouragement and feedback
        - Reminders

        Voice is NOT appropriate for:
        - Long technical content
        - Code snippets
        - Lists and tables
        - Complex formatting
        """
        # Context-based rules
        if context in ("check_in", "notification", "reminder"):
            return True

        # Length check
        if len(text) > 500:
            return False

        # Content-based rules
        has_code = "```" in text or "`" in text
        has_list = text.count("\n-") > 3 or text.count("\n•") > 3
        has_table = "|" in text and text.count("|") > 5

        if has_code or has_list or has_table:
            return False

        # Check for encouragement/feedback keywords
        voice_friendly_keywords = [
            "great",
            "nice",
            "good job",
            "well done",
            "congratulations",
            "keep it up",
            "reminder",
            "check in",
            "how are you",
            "feeling",
        ]

        text_lower = text.lower()
        if any(keyword in text_lower for keyword in voice_friendly_keywords):
            return True

        # Default for short, simple messages
        return len(text) < 200 and text.count("\n") < 3

    async def synthesize_and_send(
        self,
        chat_id: int,
        text: str,
        bot_token: str,
        context: str = "general",
        reply_to_message_id: Optional[int] = None,
    ) -> bool:
        """
        Synthesize text as voice and send to Telegram.

        Args:
            chat_id: Telegram chat ID
            text: Text to synthesize
            bot_token: Telegram bot token
            context: Response context
            reply_to_message_id: Optional message ID to reply to

        Returns:
            True if voice was sent, False otherwise
        """
        try:
            # Check if voice should be synthesized
            should_send = await self.should_synthesize_voice(chat_id, text, context)
            if not should_send:
                logger.debug(
                    f"Skipping voice synthesis for chat {chat_id} (mode check)"
                )
                return False

            # Get user's voice preferences
            async with get_db_session() as session:
                chat_obj = await get_chat_by_telegram_id(session, chat_id)
                if not chat_obj:
                    return False

                voice = chat_obj.voice_name
                emotion = chat_obj.voice_emotion
                verbosity = chat_obj.voice_verbosity or "full"
                tts_provider = chat_obj.tts_provider

            # Clean text for TTS (remove markdown, emojis handled by TTS)
            clean_text = self._clean_text_for_tts(text)

            if not clean_text:
                logger.warning("Text became empty after cleaning, skipping synthesis")
                return False

            # Summarize if needed (short/brief modes)
            if verbosity != "full" and len(clean_text) > 100:
                clean_text = await self._summarize_for_voice(clean_text, verbosity)
                if not clean_text:
                    logger.warning(
                        "Text became empty after summarization, using original"
                    )
                    clean_text = self._clean_text_for_tts(text)

            # Synthesize voice using user's TTS provider
            service = get_tts_service()
            logger.info(
                f"Synthesizing voice for chat {chat_id}: voice={voice}, "
                f"emotion={emotion}, provider={tts_provider or 'default'}, "
                f"length={len(clean_text)}"
            )
            audio_bytes = await service.synthesize_mp3(
                clean_text,
                voice=voice,
                emotion=emotion,
                provider=tts_provider,
                quality=2,
            )

            # Send via subprocess to avoid async blocking
            await self._send_voice_sync(
                chat_id, audio_bytes, bot_token, reply_to_message_id
            )

            logger.info(f"Voice message sent to chat {chat_id}")
            return True

        except Exception as e:
            logger.error(
                f"Error synthesizing voice for chat {chat_id}: {e}", exc_info=True
            )
            return False

    async def _summarize_for_voice(self, text: str, verbosity: str) -> str:
        """
        Summarize text based on verbosity level for voice synthesis.

        Args:
            text: Cleaned text (already stripped of markdown)
            verbosity: "full", "short", or "brief"

        Returns:
            Text appropriate for the verbosity level
        """
        if verbosity == "full":
            return text

        # Skip summarization for already-short text
        if len(text) < 100:
            logger.debug(f"Text too short ({len(text)} chars), skipping summarization")
            return text

        try:
            import litellm

            # System prompts for each level
            prompts = {
                "short": (
                    "You are a voice summary assistant. Condense the following text into a natural spoken summary "
                    "suitable for text-to-speech. Keep the key information and main points. For technical content, "
                    "highlight the main features and conclusions. Aim for 2-4 sentences. Write in a natural, "
                    "conversational tone - this will be read aloud. Do not use markdown, bullet points, or any "
                    "formatting. Output only the summary text, nothing else."
                ),
                "brief": (
                    "You are a voice summary assistant. Condense the following text into an extremely brief spoken "
                    "summary - ideally one short sentence, maximum two. Target approximately 40-50 words (about 15 "
                    "seconds of audio). Capture only the single most important point or conclusion. Write in a "
                    "natural, conversational tone - this will be read aloud. Do not use markdown, bullet points, or "
                    "any formatting. Output only the summary text, nothing else."
                ),
            }

            system_prompt = prompts.get(verbosity)
            if not system_prompt:
                logger.warning(f"Unknown verbosity level: {verbosity}, using full text")
                return text

            # Call LLM for summarization
            logger.info(
                f"Summarizing text ({len(text)} chars) with verbosity={verbosity}"
            )

            response = await litellm.acompletion(
                model="groq/llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                max_tokens=200 if verbosity == "short" else 80,
                temperature=0.3,
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"Summarization complete: {len(text)} → {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Error summarizing text for voice: {e}", exc_info=True)
            logger.warning("Falling back to full text due to summarization error")
            return text

    def _clean_text_for_tts(self, text: str) -> str:
        """
        Clean text for text-to-speech synthesis.

        Removes:
        - Markdown formatting
        - Code blocks
        - HTML tags
        - Multiple newlines

        Preserves:
        - Emojis (handled by TTS engine)
        - Punctuation
        - Basic structure
        """
        import re

        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]+`", "", text)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Remove markdown formatting
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # Bold
        text = re.sub(r"\*([^*]+)\*", r"\1", text)  # Italic
        text = re.sub(r"__([^_]+)__", r"\1", text)  # Bold
        text = re.sub(r"_([^_]+)_", r"\1", text)  # Italic

        # Remove links but keep text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

        # Clean up multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Clean up whitespace
        text = text.strip()

        return text

    async def _send_voice_sync(
        self,
        chat_id: int,
        audio_bytes: bytes,
        bot_token: str,
        reply_to_message_id: Optional[int] = None,
    ) -> None:
        """
        Send voice message via subprocess to avoid async blocking.

        This uses the subprocess pattern to avoid event loop blocking
        in the webhook context.
        """
        import base64
        import subprocess
        import tempfile
        from pathlib import Path

        # Save audio to temp file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
            f.write(audio_bytes)

        try:
            # Encode file path for safety
            encoded_path = base64.b64encode(temp_path.encode()).decode()

            reply_param = (
                f', "reply_to_message_id": {reply_to_message_id}'
                if reply_to_message_id
                else ""
            )

            script = f"""
import requests
import base64
import os
from pathlib import Path

temp_path = base64.b64decode("{encoded_path}").decode()
url = "https://api.telegram.org/bot{bot_token}/sendVoice"
with open(temp_path, "rb") as f:
    files = {{"voice": f}}
    data = {{"chat_id": {chat_id}{reply_param}}}
    response = requests.post(url, files=files, data=data, timeout=30)
    print("OK" if response.ok else f"FAIL: {{response.text}}")

# Cleanup temp file
os.unlink(temp_path)
"""

            from ..core.config import get_settings

            python_path = get_settings().python_executable

            # Run subprocess with timeout
            result = subprocess.run(
                [python_path, "-c", script],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if "OK" not in result.stdout:
                logger.error(f"Failed to send voice: {result.stdout}")
                # Manual cleanup if subprocess failed
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Error in voice send subprocess: {e}")
            # Cleanup on error
            Path(temp_path).unlink(missing_ok=True)
            raise


# Global instance
_voice_response_service: Optional[VoiceResponseService] = None


def get_voice_response_service() -> VoiceResponseService:
    """Get the global voice response service instance."""
    global _voice_response_service
    if _voice_response_service is None:
        _voice_response_service = VoiceResponseService()
    return _voice_response_service
