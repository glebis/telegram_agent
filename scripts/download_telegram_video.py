#!/usr/bin/env python3
"""
Download large videos from Telegram using Telethon (bypasses 20MB Bot API limit).

Usage:
    python3 download_telegram_video.py https://t.me/ACT_Russia/3902 output.mp4
"""

import asyncio
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto


async def download_from_link(message_link: str, output_path: Path):
    """Download video from Telegram channel message."""

    # Parse link: https://t.me/ACT_Russia/3902 -> channel=ACT_Russia, msg_id=3902
    parts = message_link.rstrip('/').split('/')
    if len(parts) < 2:
        print(f"Invalid link format: {message_link}")
        return False

    channel_username = parts[-2]
    try:
        message_id = int(parts[-1])
    except ValueError:
        print(f"Invalid message ID in link: {parts[-1]}")
        return False

    print(f"📥 Downloading from @{channel_username}, message {message_id}")

    # TODO: Get credentials from env or config
    # For now, need API_ID and API_HASH from https://my.telegram.org
    api_id = input("Enter your API ID (from my.telegram.org): ").strip()
    api_hash = input("Enter your API HASH (from my.telegram.org): ").strip()

    if not api_id or not api_hash:
        print("❌ API credentials required")
        return False

    # Create client (will store session in current directory)
    client = TelegramClient('telegram_download_session', int(api_id), api_hash)

    try:
        await client.start()
        print(f"✅ Connected to Telegram")

        # Get the message
        entity = await client.get_entity(channel_username)
        message = await client.get_messages(entity, ids=message_id)

        if not message:
            print(f"❌ Message {message_id} not found in @{channel_username}")
            return False

        print(f"📋 Message found: {message.message[:100] if message.message else '(no text)'}...")

        # Check for media
        if not message.media:
            print("❌ No media in this message")
            return False

        # Download media with progress
        def progress_callback(current, total):
            percent = (current / total) * 100 if total > 0 else 0
            mb_current = current / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            print(f"\r📥 Downloading: {mb_current:.1f}/{mb_total:.1f} MB ({percent:.1f}%)", end='', flush=True)

        print(f"⏳ Starting download to {output_path}...")
        await client.download_media(
            message.media,
            file=str(output_path),
            progress_callback=progress_callback
        )
        print()  # New line after progress

        # Check file size
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"✅ Downloaded successfully: {size_mb:.1f} MB")
            return True
        else:
            print("❌ Download failed - file not created")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.disconnect()


async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 download_telegram_video.py <telegram_link> <output_file>")
        print("Example: python3 download_telegram_video.py https://t.me/ACT_Russia/3902 video.mp4")
        sys.exit(1)

    message_link = sys.argv[1]
    output_path = Path(sys.argv[2])

    success = await download_from_link(message_link, output_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
