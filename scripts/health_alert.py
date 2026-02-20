#!/usr/bin/env python3
"""Health alert entry point — called by health_check.sh.

Usage:
    python3 health_alert.py --failure "reason text"
    python3 health_alert.py --success
"""

import argparse
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.health_alert_service import process_health_result

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Health check alerting")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--failure", type=str, help="Record a failure with reason")
    group.add_argument(
        "--success", action="store_true", help="Record a successful check"
    )
    parser.add_argument(
        "--state-file",
        default="/tmp/telegram_agent_health_state.json",
        help="Path to state file",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Consecutive failures before alerting",
    )
    args = parser.parse_args()

    # Get admin chat ID from env
    admin_ids = os.environ.get("ADMIN_USER_IDS", "")
    if not admin_ids:
        # Try owner_user_id as fallback
        admin_ids = os.environ.get("OWNER_USER_ID", "")
    if not admin_ids:
        sys.exit(0)  # No admin to alert

    admin_chat_id = int(admin_ids.split(",")[0].strip())

    process_health_result(
        success=args.success,
        reason=args.failure or "",
        state_file=args.state_file,
        admin_chat_id=admin_chat_id,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
