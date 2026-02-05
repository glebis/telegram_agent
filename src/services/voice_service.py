"""
Voice message service using Groq Whisper API
Transcribes audio and detects intent for routing
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx
import yaml

logger = logging.getLogger(__name__)


class VoiceService:
    """Service for voice message transcription and processing"""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.base_url = "https://api.groq.com/openai/v1"
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load routing configuration"""
        config_path = Path(__file__).parent.parent.parent / "config" / "routing.yaml"
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading routing config: {e}")
            return self._default_config()

    def _default_config(self) -> Dict:
        """Default configuration"""
        return {
            "voice": {
                "service": "groq_whisper",
                "intents": {
                    "task": {
                        "keywords": [
                            "todo",
                            "task",
                            "remind",
                            "need to",
                            "don't forget",
                        ],
                        "destination": "daily",
                        "format": "task",
                    },
                    "note": {
                        "keywords": ["note", "remember", "idea", "thought"],
                        "destination": "inbox",
                    },
                    "quick": {
                        "keywords": [],
                        "destination": "daily",
                        "section": "log",
                    },
                },
            }
        }

    async def transcribe(self, audio_path: str) -> Tuple[bool, Dict]:
        """
        Transcribe audio using Groq Whisper API

        Args:
            audio_path: Path to audio file (ogg, mp3, wav, etc)

        Returns:
            Tuple of (success, result_dict with text or error)
        """
        if not self.api_key:
            logger.error("GROQ_API_KEY not configured")
            return False, {"error": "Groq API key not configured"}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(audio_path, "rb") as audio_file:
                    files = {"file": (Path(audio_path).name, audio_file, "audio/ogg")}
                    data = {"model": "whisper-large-v3-turbo", "language": "en"}

                    response = await client.post(
                        f"{self.base_url}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files=files,
                        data=data,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        text = result.get("text", "").strip()
                        logger.info(f"Transcription successful: {text[:100]}...")
                        return True, {"text": text}
                    else:
                        error = (
                            f"Groq API error {response.status_code}: {response.text}"
                        )
                        logger.error(error)
                        return False, {"error": error}

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return False, {"error": str(e)}

    def detect_intent(self, text: str) -> Dict:
        """
        Detect intent from transcribed text for routing

        Returns:
            Dict with intent, destination, format
        """
        text_lower = text.lower()
        intents = self.config.get("voice", {}).get("intents", {})

        # Check each intent's keywords
        for intent_name, intent_config in intents.items():
            keywords = intent_config.get("keywords", [])
            for keyword in keywords:
                if keyword in text_lower:
                    return {
                        "intent": intent_name,
                        "destination": intent_config.get("destination", "inbox"),
                        "format": intent_config.get("format"),
                        "section": intent_config.get("section"),
                        "matched_keyword": keyword,
                    }

        # Default to quick/log
        quick_config = intents.get("quick", {})
        return {
            "intent": "quick",
            "destination": quick_config.get("destination", "daily"),
            "format": quick_config.get("format"),
            "section": quick_config.get("section", "log"),
        }

    def format_for_obsidian(
        self, text: str, intent_info: Dict, timestamp: Optional[datetime] = None
    ) -> str:
        """
        Format transcribed text for Obsidian based on intent

        Args:
            text: Transcribed text
            intent_info: Result from detect_intent
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Formatted markdown string
        """
        ts = timestamp or datetime.now()
        time_str = ts.strftime("%H:%M")

        format_type = intent_info.get("format")

        if format_type == "task":
            # Format as task
            return f"- [ ] {text}"
        else:
            # Format as log entry
            return f"- {time_str} {text}"

    async def process_voice_message(self, audio_path: str) -> Tuple[bool, Dict]:
        """
        Full workflow: transcribe and prepare for routing

        Returns:
            Tuple of (success, result with text, intent, formatted_text)
        """
        # Transcribe
        success, transcribe_result = await self.transcribe(audio_path)
        if not success:
            return False, transcribe_result

        text = transcribe_result["text"]

        # Detect intent
        intent_info = self.detect_intent(text)

        # Format for Obsidian
        formatted = self.format_for_obsidian(text, intent_info)

        return True, {
            "text": text,
            "intent": intent_info,
            "formatted_text": formatted,
            "destination": intent_info.get("destination", "daily"),
        }


# Global service instance
_voice_service: Optional[VoiceService] = None


def get_voice_service() -> VoiceService:
    """Get the global voice service instance"""
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service
