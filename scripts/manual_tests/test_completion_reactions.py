#!/usr/bin/env python3
"""
Test script for completion reactions.

Usage:
    python scripts/test_completion_reactions.py --type emoji --value "🎉"
    python scripts/test_completion_reactions.py --type sticker --value "CAACAgIAAxk..."
    python scripts/test_completion_reactions.py --type animation --value "/path/to/file.gif"
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_reaction(reaction_type: str, reaction_value: str, chat_id: int):
    """Test sending a completion reaction."""
    from telegram import Bot
    from src.utils.completion_reactions import send_completion_reaction

    # Get bot token from environment
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    # Override config for testing
    os.environ["COMPLETION_REACTION_TYPE"] = reaction_type
    os.environ["COMPLETION_REACTION_VALUE"] = reaction_value
    os.environ["COMPLETION_REACTION_PROBABILITY"] = "1.0"

    # Create bot instance
    bot = Bot(token=token)

    logger.info(f"Testing {reaction_type} reaction: {reaction_value}")
    logger.info(f"Sending to chat: {chat_id}")

    try:
        success = await send_completion_reaction(
            bot=bot,
            chat_id=chat_id,
        )

        if success:
            print(f"✅ Successfully sent {reaction_type} reaction!")
        else:
            print(f"⚠️ Reaction was not sent (probability check or disabled)")

    except Exception as e:
        print(f"❌ Error sending reaction: {e}")
        logger.exception("Full error:")
        sys.exit(1)


async def test_all_types(chat_id: int):
    """Test all reaction types with examples."""
    tests = [
        ("emoji", "✅"),
        ("emoji", "🎉,✨,🚀"),  # Multiple
    ]

    print("\n=== Testing Completion Reactions ===\n")

    for reaction_type, reaction_value in tests:
        print(f"\nTesting {reaction_type}: {reaction_value}")
        print("-" * 50)
        await test_reaction(reaction_type, reaction_value, chat_id)
        await asyncio.sleep(2)  # Delay between tests

    print("\n=== Tests Complete ===\n")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test completion reactions")
    parser.add_argument(
        "--type",
        choices=["emoji", "sticker", "animation", "all"],
        default="emoji",
        help="Reaction type to test"
    )
    parser.add_argument(
        "--value",
        default="✅",
        help="Reaction value (emoji, file_id, or file path)"
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        help="Chat ID to send to (defaults to your user ID from env)"
    )

    args = parser.parse_args()

    # Get chat ID
    chat_id = args.chat_id
    if not chat_id:
        # Try to get from environment
        chat_id = os.environ.get("TEST_CHAT_ID")
        if not chat_id:
            print("❌ Please provide --chat-id or set TEST_CHAT_ID environment variable")
            print("   You can find your chat ID by messaging @userinfobot")
            sys.exit(1)
        chat_id = int(chat_id)

    # Run test
    if args.type == "all":
        asyncio.run(test_all_types(chat_id))
    else:
        asyncio.run(test_reaction(args.type, args.value, chat_id))


if __name__ == "__main__":
    main()
