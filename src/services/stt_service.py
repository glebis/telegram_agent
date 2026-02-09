"""
Speech-to-Text Service with provider fallback chain.

Supports multiple STT providers with automatic fallback:
- groq: Groq Whisper API (remote, fast)
- local_whisper: Local whisper CLI (mlx_whisper or whisper) via subprocess

Configure provider order via STT_PROVIDERS env var (comma-separated).
Default order: groq, local_whisper
"""

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..utils.retry import RetryableError, retry
from ..utils.subprocess_helper import run_python_script

logger = logging.getLogger(__name__)

# Default provider order
DEFAULT_PROVIDERS = ["groq", "local_whisper"]

# Known provider names
KNOWN_PROVIDERS = {"groq", "local_whisper"}

# Default whisper model and language (from config/defaults.yaml)
DEFAULT_WHISPER_MODEL = "whisper-large-v3-turbo"
DEFAULT_WHISPER_LANGUAGE = "en"


@dataclass
class STTResult:
    """Result from a speech-to-text transcription attempt."""

    success: bool
    text: str
    provider: str
    error: Optional[str] = None


@dataclass
class STTProvider:
    """Describes an STT provider."""

    name: str
    enabled: bool = True


class STTService:
    """
    Speech-to-Text service with configurable fallback chain.

    Tries providers in order. On failure, falls back to the next provider.
    """

    def __init__(self, providers: Optional[List[str]] = None):
        if providers is None:
            providers = list(DEFAULT_PROVIDERS)

        # Filter to known providers only
        filtered = [p for p in providers if p in KNOWN_PROVIDERS]

        # If nothing left after filtering, use defaults
        if not filtered:
            filtered = list(DEFAULT_PROVIDERS)

        self.providers = filtered

    @classmethod
    def from_env(cls) -> "STTService":
        """Create an STTService configured from environment variables."""
        env_providers = os.environ.get("STT_PROVIDERS", "")
        if env_providers.strip():
            providers = [p.strip() for p in env_providers.split(",") if p.strip()]
        else:
            providers = list(DEFAULT_PROVIDERS)
        return cls(providers=providers)

    def transcribe(
        self,
        audio_path: Path,
        model: str = DEFAULT_WHISPER_MODEL,
        language: str = DEFAULT_WHISPER_LANGUAGE,
    ) -> STTResult:
        """
        Transcribe audio using the configured provider chain.

        Tries each provider in order. Returns the first successful result,
        or an error result if all providers fail.

        Args:
            audio_path: Path to the audio file.
            model: Whisper model name (used by remote providers).
            language: Language code for transcription.

        Returns:
            STTResult with transcription text or error details.
        """
        # Validate file exists
        if not audio_path.exists():
            return STTResult(
                success=False,
                text="",
                provider="",
                error=f"Audio file not found: {audio_path}",
            )

        errors = []

        for provider_name in self.providers:
            try:
                method = self._get_provider_method(provider_name)
                if method is None:
                    continue

                logger.info(f"STT: trying provider '{provider_name}' for {audio_path}")
                result = method(audio_path, model, language)

                if result.success:
                    logger.info(
                        f"STT: provider '{provider_name}' succeeded, "
                        f"text_len={len(result.text)}"
                    )
                    return result

                # Provider returned failure
                logger.warning(
                    f"STT: provider '{provider_name}' failed: {result.error}"
                )
                errors.append(f"{provider_name}: {result.error}")

            except Exception as e:
                logger.warning(
                    f"STT: provider '{provider_name}' raised exception: {e}",
                    exc_info=True,
                )
                errors.append(f"{provider_name}: {str(e)}")

        # All providers failed
        error_summary = "; ".join(errors) if errors else "No providers configured"
        return STTResult(
            success=False,
            text="",
            provider="",
            error=f"All STT providers failed: {error_summary}",
        )

    def _get_provider_method(self, provider_name: str):
        """Map provider name to its transcription method."""
        mapping = {
            "groq": self._transcribe_groq,
            "local_whisper": self._transcribe_local_whisper,
        }
        return mapping.get(provider_name)

    # ------------------------------------------------------------------
    # Provider: Groq Whisper API
    # ------------------------------------------------------------------

    @retry(max_attempts=2, base_delay=1.0, exceptions=(RetryableError,))
    def _transcribe_groq(
        self,
        audio_path: Path,
        model: str = DEFAULT_WHISPER_MODEL,
        language: str = DEFAULT_WHISPER_LANGUAGE,
    ) -> STTResult:
        """
        Transcribe using Groq Whisper API via subprocess.

        Uses the same subprocess isolation pattern as the rest of the project.
        """
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return STTResult(
                success=False,
                text="",
                provider="groq",
                error="GROQ_API_KEY not set",
            )

        script = """
import sys
import json
import os
import httpx

# Read input from stdin
data = json.load(sys.stdin)
audio_path = data["audio_path"]
model = data["model"]
language = data["language"]

# Get API key from environment
api_key = os.environ["GROQ_API_KEY"]

with httpx.Client(timeout=60.0) as client:
    with open(audio_path, "rb") as audio_file:
        files = {"file": (audio_path.split("/")[-1], audio_file, "audio/ogg")}
        data = {"model": model, "language": language}

        response = client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
        )

        if response.status_code == 200:
            result = response.json()
            text = result.get("text", "").strip()
            print(json.dumps({"success": True, "text": text}))
        else:
            print(json.dumps({"success": False, "error": response.text}), file=sys.stderr)
            sys.exit(1)
"""

        result = run_python_script(
            script=script,
            input_data={
                "audio_path": str(audio_path),
                "model": model,
                "language": language,
            },
            env_vars={"GROQ_API_KEY": api_key},
            timeout=90,
        )

        if result.success:
            try:
                data = json.loads(result.stdout)
                text = data.get("text", "").strip()
                return STTResult(
                    success=True,
                    text=text,
                    provider="groq",
                )
            except json.JSONDecodeError:
                # Fall back to raw stdout
                text = result.stdout.strip()
                if text:
                    return STTResult(success=True, text=text, provider="groq")
                raise RetryableError("Failed to parse Groq response")
        else:
            raise RetryableError(
                result.error or result.stderr or "Groq transcription failed"
            )

    # ------------------------------------------------------------------
    # Provider: Local Whisper CLI (mlx_whisper or whisper)
    # ------------------------------------------------------------------

    def _transcribe_local_whisper(
        self,
        audio_path: Path,
        model: str = DEFAULT_WHISPER_MODEL,
        language: str = DEFAULT_WHISPER_LANGUAGE,
    ) -> STTResult:
        """
        Transcribe using local whisper CLI via subprocess.

        Prefers mlx_whisper (Apple Silicon optimized) if available,
        falls back to standard whisper CLI.

        Uses subprocess isolation to avoid blocking the event loop.
        No pip dependencies required -- just needs whisper CLI installed.
        """
        # Find the best available whisper command
        whisper_cmd = self._find_whisper_command()
        if whisper_cmd is None:
            return STTResult(
                success=False,
                text="",
                provider="local_whisper",
                error="Local whisper not installed (tried mlx_whisper, whisper)",
            )

        try:
            # Map remote model names to local model sizes
            local_model = self._map_model_to_local(model)

            # Build command
            cmd = [
                whisper_cmd,
                str(audio_path),
                "--language",
                language,
                "--model",
                local_model,
                "--output_format",
                "txt",
                "--output_dir",
                str(audio_path.parent),
            ]

            logger.info(f"STT local whisper: running {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                # whisper writes a .txt file; also check stdout
                txt_path = audio_path.with_suffix(".txt")
                if txt_path.exists():
                    text = txt_path.read_text().strip()
                    # Clean up the output file
                    try:
                        txt_path.unlink()
                    except Exception:
                        pass
                else:
                    # Some whisper versions output to stdout
                    text = result.stdout.strip()

                if text:
                    return STTResult(
                        success=True,
                        text=text,
                        provider="local_whisper",
                    )
                else:
                    return STTResult(
                        success=False,
                        text="",
                        provider="local_whisper",
                        error="Whisper produced empty output",
                    )
            else:
                return STTResult(
                    success=False,
                    text="",
                    provider="local_whisper",
                    error=f"Whisper exited with code {result.returncode}: {result.stderr[:200]}",
                )

        except FileNotFoundError:
            return STTResult(
                success=False,
                text="",
                provider="local_whisper",
                error="Whisper command not found",
            )
        except subprocess.TimeoutExpired:
            return STTResult(
                success=False,
                text="",
                provider="local_whisper",
                error="Local whisper timeout after 120 seconds",
            )
        except Exception as e:
            return STTResult(
                success=False,
                text="",
                provider="local_whisper",
                error=f"Local whisper error: {str(e)}",
            )

    def _find_whisper_command(self) -> Optional[str]:
        """Find the best available whisper command on this system."""
        # Prefer mlx_whisper (Apple Silicon optimized)
        for cmd in ["mlx_whisper", "whisper"]:
            if shutil.which(cmd) is not None:
                return cmd
        return None

    @staticmethod
    def _map_model_to_local(remote_model: str) -> str:
        """Map remote API model names to local whisper model sizes."""
        # Remote models like "whisper-large-v3-turbo" -> "turbo"
        model_lower = remote_model.lower()
        if "turbo" in model_lower:
            return "turbo"
        elif "large" in model_lower:
            return "large"
        elif "medium" in model_lower:
            return "medium"
        elif "small" in model_lower:
            return "small"
        elif "base" in model_lower:
            return "base"
        elif "tiny" in model_lower:
            return "tiny"
        # Default to base for local (faster, good enough for fallback)
        return "base"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_stt_service: Optional[STTService] = None


def get_stt_service() -> STTService:
    """Get or create the global STTService singleton."""
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService.from_env()
    return _stt_service
