"""
Telegram Bot API utilities — subprocess-isolated sync callers.

Moved from src/bot/handlers/base.py so that service-layer code can call
Telegram without importing upward from the handler layer.

Functions:
- _run_telegram_api_sync(method, payload) — core HTTP caller via subprocess
- send_message_sync(chat_id, text, ...)   — send a message
- edit_message_sync(chat_id, message_id, text, ...) — edit a message
- send_photo_sync(chat_id, photo_path, ...) — send a photo
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from .retry import RetryableError, retry
from .subprocess_helper import run_python_script

logger = logging.getLogger(__name__)


@retry(max_attempts=3, base_delay=1.0, exceptions=(RetryableError,))
def _run_telegram_api_sync(method: str, payload: dict) -> Optional[dict]:
    """Call Telegram Bot API using secure subprocess (bypasses async blocking)."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    try:
        script = """
import sys
import json
import os
import requests

# Read payload from stdin
data = json.load(sys.stdin)
method = data["method"]
payload = data["payload"]

# Get token from environment (not interpolated in script)
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

r = requests.post(
    f"https://api.telegram.org/bot{bot_token}/{method}",
    json=payload,
    timeout=30
)
result = r.json()
if result.get("ok"):
    print(json.dumps({"success": True, "result": result["result"]}))
else:
    print(json.dumps({"success": False, "error": result}))
"""
        result = run_python_script(
            script=script,
            input_data={"method": method, "payload": payload},
            env_vars={"TELEGRAM_BOT_TOKEN": bot_token},
            timeout=60,
        )

        if result.success:
            response = json.loads(result.stdout)
            if response.get("success"):
                return response.get("result")
            else:
                error = response.get("error", {})
                error_code = (
                    error.get("error_code", 0) if isinstance(error, dict) else 0
                )
                if error_code == 429 or error_code >= 500:
                    raise RetryableError(
                        f"Telegram API {method}: retryable error {error_code}"
                    )
                logger.warning(f"Telegram API {method} failed: {response.get('error')}")
                return None
        else:
            raise RetryableError(
                f"Telegram API {method} subprocess failed: {result.error}"
            )
    except RetryableError:
        raise
    except Exception as e:
        logger.error(f"Error calling Telegram API {method}: {e}")
        return None


def send_message_sync(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_to: int = None,
    reply_markup: dict = None,
) -> Optional[dict]:
    """
    Send a message using the Telegram HTTP API via subprocess.

    Bypasses async blocking issues.

    If ``parse_mode="HTML"`` and Telegram rejects the message with a
    *parse entities* error (HTTP 400), the function automatically retries
    with the HTML stripped to plain text.  This prevents messages from being
    silently dropped when the HTML formatter produces malformed markup (e.g.
    unclosed ``<pre>`` tags from naive message splitting).
    """
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if reply_markup:
        payload["reply_markup"] = reply_markup

    result = _run_telegram_api_sync("sendMessage", payload)
    if result is not None:
        return result

    # If we sent HTML and it failed, check whether it was a parse-entities
    # error by inspecting the last warning logged (the low-level function
    # already logged the 400 detail).  We retry unconditionally when
    # parse_mode is HTML and the first attempt returned None, so we don't
    # need to parse the error message here — a second attempt with plain
    # text is always safe.
    if parse_mode == "HTML":
        from src.bot.handlers.formatting import strip_telegram_html

        plain_text = strip_telegram_html(text)
        logger.warning(
            "send_message_sync: HTML rejected by Telegram, retrying as plain text "
            f"(chat={chat_id}, original_len={len(text)}, plain_len={len(plain_text)})"
        )
        fallback_payload = {"chat_id": chat_id, "text": plain_text}
        if reply_to:
            fallback_payload["reply_to_message_id"] = reply_to
        if reply_markup:
            fallback_payload["reply_markup"] = reply_markup
        return _run_telegram_api_sync("sendMessage", fallback_payload)

    return None


def edit_message_sync(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict = None,
) -> Optional[dict]:
    """
    Edit a message using the Telegram HTTP API via subprocess.

    Bypasses async blocking issues.
    """
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _run_telegram_api_sync("editMessageText", payload)


def send_photo_sync(
    chat_id: int,
    photo_path: str,
    caption: str = None,
    parse_mode: str = "HTML",
) -> Optional[dict]:
    """
    Send a photo using the Telegram HTTP API via subprocess.

    Bypasses async blocking issues.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    # Validate photo_path against allowed directories
    from src.services.media_validator import validate_outbound_path

    if not validate_outbound_path(Path(photo_path)):
        logger.error(f"Photo path rejected by outbound validation: {photo_path}")
        return None

    # Use curl with multipart/form-data
    cmd = [
        "curl",
        "-s",
        "-X",
        "POST",
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        "-F",
        f"chat_id={chat_id}",
        "-F",
        f"photo=@{photo_path}",
    ]

    if caption:
        cmd.extend(["--form-string", f"caption={caption}"])
    if parse_mode:
        cmd.extend(["--form-string", f"parse_mode={parse_mode}"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            logger.error(f"Telegram API sendPhoto failed: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Error sending photo via Telegram API: {e}")
        return None
