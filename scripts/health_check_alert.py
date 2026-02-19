import json
import logging
import time
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "failure_count": 0,
    "last_alert_time": None,
    "first_failure_time": None,
}


def load_state(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return dict(_DEFAULTS)
    except json.JSONDecodeError:
        logger.warning("Corrupt or invalid state file: %s", path)
        return dict(_DEFAULTS)


def save_state(state: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(state, f)


def _format_duration(seconds: float) -> str:
    total_minutes = int(seconds) // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts.append(f"{int(seconds)} seconds")
    return " ".join(parts)


def format_failure_alert(
    failure_type: str,
    action_taken: str,
    failure_count: int,
    first_failure_time: float,
) -> str:
    ts = datetime.fromtimestamp(first_failure_time).strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"Alert: {failure_type} failure (count: {failure_count}). "
        f"Action taken: {action_taken}. Since: {ts}"
    )


def format_recovery_message(
    first_failure_time: float, failure_count: int, now: float = None
) -> str:
    if now is None:
        now = time.time()
    duration_secs = now - first_failure_time
    duration_str = _format_duration(duration_secs)
    return (
        f"Recovered after {failure_count} failure{'s' if failure_count != 1 else ''}. "
        f"Downtime: {duration_str}"
    )


def record_failure(failure_type: str, action_taken: str, state_path: str) -> None:
    state = load_state(state_path)
    state["failure_count"] += 1
    if state["first_failure_time"] is None:
        state["first_failure_time"] = time.time()
    save_state(state, state_path)


def should_alert(state_path: str, now: float = None) -> bool:
    state = load_state(state_path)
    if state["failure_count"] < 2:
        return False
    if now is None:
        now = time.time()
    if state["last_alert_time"] is None:
        return True
    return now - state["last_alert_time"] >= 600


def record_success(state_path: str) -> tuple:
    state = load_state(state_path)
    was_failing = state["failure_count"] > 0
    prev_count = state["failure_count"]
    first_failure_time = state["first_failure_time"]
    state["failure_count"] = 0
    state["first_failure_time"] = None
    save_state(state, state_path)
    return (was_failing, prev_count, first_failure_time)


def send_telegram_alert(message: str, bot_token: str, chat_id: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as exc:
        logger.error("Failed to send Telegram alert: %s", exc)
        return False


def main() -> None:
    """CLI entry point for bash integration."""
    import argparse
    import os
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Health check alerting")
    parser.add_argument(
        "--state-path",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "data",
            "health_check_state.json",
        ),
    )
    sub = parser.add_subparsers(dest="command")

    fail_p = sub.add_parser("failure")
    fail_p.add_argument("failure_type")
    fail_p.add_argument("action_taken")

    sub.add_parser("success")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    state_path = os.path.abspath(args.state_path)
    os.makedirs(os.path.dirname(state_path), exist_ok=True)

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    admin_ids = os.environ.get("ADMIN_USER_IDS", "")

    if not bot_token or not admin_ids:
        logger.warning("TELEGRAM_BOT_TOKEN or ADMIN_USER_IDS not set, skipping alert")
        sys.exit(0)

    chat_id = admin_ids.split(",")[0].strip()

    if args.command == "failure":
        record_failure(args.failure_type, args.action_taken, state_path)
        if should_alert(state_path):
            state = load_state(state_path)
            msg = format_failure_alert(
                args.failure_type,
                args.action_taken,
                state["failure_count"],
                state["first_failure_time"],
            )
            send_telegram_alert(msg, bot_token, chat_id)
            state["last_alert_time"] = time.time()
            save_state(state, state_path)

    elif args.command == "success":
        was_failing, prev_count, first_failure_time = record_success(state_path)
        if was_failing and first_failure_time is not None:
            msg = format_recovery_message(first_failure_time, prev_count)
            send_telegram_alert(msg, bot_token, chat_id)


if __name__ == "__main__":
    main()
