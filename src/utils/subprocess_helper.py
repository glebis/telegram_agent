"""
Secure Subprocess Helper

Provides secure subprocess execution that:
1. Passes data via stdin (not f-string interpolation) - prevents injection
2. Passes secrets via environment variables
3. Handles timeouts gracefully
4. Returns structured results
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.config import get_settings
from .retry import RetryableError, retry

logger = logging.getLogger(__name__)


@dataclass
class SubprocessResult:
    """Structured result from subprocess execution."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    error: Optional[str] = None


def run_python_script(
    script: str,
    input_data: Optional[Dict[str, Any]] = None,
    env_vars: Optional[Dict[str, str]] = None,
    timeout: int = 60,
    cwd: Optional[str] = None,
) -> SubprocessResult:
    """
    Run a Python script securely with data passed via stdin.

    Args:
        script: Python script code to execute
        input_data: Data to pass via stdin (will be JSON encoded)
        env_vars: Environment variables to set (for secrets)
        timeout: Timeout in seconds
        cwd: Working directory

    Returns:
        SubprocessResult with success status, stdout, stderr, etc.
    """
    settings = get_settings()
    python_path = settings.python_executable

    # Build environment
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    # Prepare stdin data (as string since text=True)
    stdin_data = None
    if input_data is not None:
        stdin_data = json.dumps(input_data)

    try:
        result = subprocess.run(
            [python_path, "-c", script],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )

        return SubprocessResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode,
            error=None if result.returncode == 0 else f"Exit code: {result.returncode}",
        )

    except subprocess.TimeoutExpired as e:
        logger.warning(f"Subprocess timeout after {timeout}s")
        return SubprocessResult(
            success=False,
            stdout=e.stdout.decode() if e.stdout else "",
            stderr=e.stderr.decode() if e.stderr else "",
            return_code=-1,
            error=f"Timeout after {timeout} seconds",
        )

    except Exception as e:
        logger.error(f"Subprocess error: {e}", exc_info=True)
        return SubprocessResult(
            success=False,
            stdout="",
            stderr=str(e),
            return_code=-1,
            error=str(e),
        )


def get_telegram_file_info(
    file_id: str,
    bot_token: str,
    timeout: int = 30,
) -> SubprocessResult:
    """
    Get file info from Telegram (size, path) without downloading.

    Args:
        file_id: Telegram file ID
        bot_token: Bot token (passed via env var, not interpolated)
        timeout: Timeout in seconds

    Returns:
        SubprocessResult with stdout containing JSON: {"file_size": int, "file_path": str}
    """
    script = """
import sys
import json
import os
import requests

# Read input from stdin
data = json.load(sys.stdin)
file_id = data["file_id"]

# Get token from environment
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

# Get file info (doesn't download)
r = requests.get(
    f"https://api.telegram.org/bot{bot_token}/getFile",
    params={"file_id": file_id},
    timeout=30
)
r.raise_for_status()
result = r.json()

if not result.get("ok"):
    print(f"ERROR: {result}", file=sys.stderr)
    sys.exit(1)

file_result = result["result"]
print(json.dumps({
    "file_path": file_result.get("file_path"),
    "file_size": file_result.get("file_size"),  # May be None
    "file_id": file_result.get("file_id")
}))
"""

    return run_python_script(
        script=script,
        input_data={"file_id": file_id},
        env_vars={"TELEGRAM_BOT_TOKEN": bot_token},
        timeout=timeout,
    )


def download_telegram_file(
    file_id: str,
    bot_token: str,
    output_path: Path,
    timeout: int = 120,
) -> SubprocessResult:
    """
    Download a file from Telegram using secure subprocess.

    Args:
        file_id: Telegram file ID
        bot_token: Bot token (passed via env var, not interpolated)
        output_path: Where to save the file
        timeout: Timeout in seconds

    Returns:
        SubprocessResult - check result.success and result.stdout for path
    """
    script = """
import sys
import json
import os
import requests

# Read input from stdin
data = json.load(sys.stdin)
file_id = data["file_id"]
output_path = data["output_path"]

# Get token from environment (not interpolated in script)
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

# Get file info
r = requests.get(
    f"https://api.telegram.org/bot{bot_token}/getFile",
    params={"file_id": file_id},
    timeout=30
)
r.raise_for_status()
result = r.json()

if not result.get("ok"):
    print(f"ERROR: {result}", file=sys.stderr)
    sys.exit(1)

file_path = result["result"]["file_path"]

# Download file
download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
r = requests.get(download_url, timeout=60)
r.raise_for_status()

# Save to output path
with open(output_path, "wb") as f:
    f.write(r.content)

print(json.dumps({"success": True, "path": output_path, "size": len(r.content)}))
"""

    return run_python_script(
        script=script,
        input_data={
            "file_id": file_id,
            "output_path": str(output_path),
        },
        env_vars={"TELEGRAM_BOT_TOKEN": bot_token},
        timeout=timeout,
    )


def transcribe_audio(
    audio_path: Path,
    api_key: str,
    model: str = "whisper-large-v3-turbo",
    language: str = "en",
    timeout: int = 90,
) -> SubprocessResult:
    """
    Transcribe audio using Groq Whisper API via secure subprocess.

    Args:
        audio_path: Path to audio file
        api_key: Groq API key (passed via env var)
        model: Whisper model to use
        language: Language code
        timeout: Timeout in seconds

    Returns:
        SubprocessResult - check result.stdout for transcription
    """
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

    return run_python_script(
        script=script,
        input_data={
            "audio_path": str(audio_path),
            "model": model,
            "language": language,
        },
        env_vars={"GROQ_API_KEY": api_key},
        timeout=timeout,
    )


def extract_audio_from_video(
    video_path: Path,
    output_path: Path,
    timeout: int = 120,
) -> SubprocessResult:
    """
    Extract audio from video file using ffmpeg.

    Args:
        video_path: Path to video file
        output_path: Where to save the audio (should be .ogg or .mp3)
        timeout: Timeout in seconds

    Returns:
        SubprocessResult - check result.success
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(video_path),
                "-vn",  # No video
                "-acodec",
                "libopus",  # Opus codec for .ogg
                "-b:a",
                "64k",  # Bitrate
                "-y",  # Overwrite output
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return SubprocessResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode,
            error=None if result.returncode == 0 else f"ffmpeg error: {result.stderr}",
        )

    except subprocess.TimeoutExpired:
        logger.warning(f"ffmpeg timeout after {timeout}s")
        return SubprocessResult(
            success=False,
            stdout="",
            stderr="",
            return_code=-1,
            error=f"Timeout after {timeout} seconds",
        )

    except FileNotFoundError:
        return SubprocessResult(
            success=False,
            stdout="",
            stderr="ffmpeg not found",
            return_code=-1,
            error="ffmpeg not installed",
        )

    except Exception as e:
        logger.error(f"Audio extraction error: {e}", exc_info=True)
        return SubprocessResult(
            success=False,
            stdout="",
            stderr=str(e),
            return_code=-1,
            error=str(e),
        )


@retry(max_attempts=3, base_delay=1.0, exceptions=(RetryableError,))
def send_telegram_message(
    chat_id: int,
    text: str,
    bot_token: str,
    parse_mode: str = "HTML",
    reply_to_message_id: Optional[int] = None,
    timeout: int = 30,
) -> SubprocessResult:
    """
    Send a Telegram message via secure subprocess.

    Args:
        chat_id: Telegram chat ID
        text: Message text
        bot_token: Bot token (passed via env var)
        parse_mode: HTML or Markdown
        reply_to_message_id: Optional message to reply to
        timeout: Timeout in seconds

    Returns:
        SubprocessResult with message info in stdout
    """
    script = """
import sys
import json
import os
import requests

# Read input from stdin
data = json.load(sys.stdin)
chat_id = data["chat_id"]
text = data["text"]
parse_mode = data["parse_mode"]
reply_to = data.get("reply_to_message_id")

# Get token from environment
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

payload = {
    "chat_id": chat_id,
    "text": text,
    "parse_mode": parse_mode,
}
if reply_to:
    payload["reply_to_message_id"] = reply_to

r = requests.post(
    f"https://api.telegram.org/bot{bot_token}/sendMessage",
    json=payload,
    timeout=30
)

result = r.json()
if result.get("ok"):
    print(json.dumps({"success": True, "message_id": result["result"]["message_id"]}))
else:
    print(json.dumps({"success": False, "error": result}), file=sys.stderr)
    sys.exit(1)
"""

    result = run_python_script(
        script=script,
        input_data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
        },
        env_vars={"TELEGRAM_BOT_TOKEN": bot_token},
        timeout=timeout,
    )

    if not result.success:
        # Try to parse error_code from stderr JSON
        try:
            import json as _json

            err_data = _json.loads(result.stderr)
            error_obj = err_data.get("error", {})
            error_code = (
                error_obj.get("error_code", 0) if isinstance(error_obj, dict) else 0
            )
            # Don't retry 4xx errors (except 429 rate limit)
            if error_code and 400 <= error_code < 500 and error_code != 429:
                return result
        except Exception:
            pass
        raise RetryableError(f"send_telegram_message failed: {result.error}")

    return result
