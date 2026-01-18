"""
Demo script showing how reply context extraction works.

This demonstrates the new feature that extracts content from messages being replied to.
"""

from dataclasses import dataclass, field
from typing import Optional, List


# Simplified mock classes
@dataclass
class MockReplyToMessage:
    """Simulates Telegram's reply_to_message object."""
    message_id: int
    text: Optional[str] = None
    caption: Optional[str] = None
    photo: Optional[list] = None
    video: Optional[dict] = None
    voice: Optional[dict] = None
    video_note: Optional[dict] = None
    document: Optional[dict] = None


@dataclass
class CombinedMessage:
    """Simplified CombinedMessage showing new fields."""
    reply_to_message_id: Optional[int] = None
    reply_to_message_text: Optional[str] = None
    reply_to_message_type: Optional[str] = None


def extract_reply_context(reply_to: MockReplyToMessage) -> CombinedMessage:
    """Simulates the extraction logic from message_buffer.py"""
    combined = CombinedMessage()

    if reply_to:
        combined.reply_to_message_id = reply_to.message_id

        # Extract content from the replied-to message
        if reply_to.text:
            combined.reply_to_message_text = reply_to.text
            combined.reply_to_message_type = "text"
        elif reply_to.caption:
            combined.reply_to_message_text = reply_to.caption
            if reply_to.photo:
                combined.reply_to_message_type = "photo"
            elif reply_to.video:
                combined.reply_to_message_type = "video"
            elif reply_to.document:
                combined.reply_to_message_type = "document"
        elif reply_to.voice:
            combined.reply_to_message_type = "voice"
        elif reply_to.video_note:
            combined.reply_to_message_type = "video_note"

    return combined


def demo():
    """Run demo scenarios."""
    print("=" * 60)
    print("REPLY CONTEXT EXTRACTION DEMO")
    print("=" * 60)

    # Scenario 1: Reply to text message
    print("\n1. Replying to a text message:")
    print("   User sends: 'What's the weather?'")
    print("   You reply to it with: 'Tell me more'")
    reply_to = MockReplyToMessage(message_id=123, text="What's the weather?")
    result = extract_reply_context(reply_to)
    print(f"   ✓ Extracted: type={result.reply_to_message_type}, text='{result.reply_to_message_text}'")

    # Scenario 2: Reply to voice transcription
    print("\n2. Replying to a voice message transcription:")
    print("   Transcript says: 'Hey Claude, can you help me?'")
    print("   You reply with: 'Yes'")
    reply_to = MockReplyToMessage(message_id=456, text="📝 Transcript:\n\nHey Claude, can you help me?")
    result = extract_reply_context(reply_to)
    print(f"   ✓ Extracted: type={result.reply_to_message_type}, text='{result.reply_to_message_text[:50]}...'")

    # Scenario 3: Reply to image with caption
    print("\n3. Replying to an image with caption:")
    print("   Image caption: 'Check out this diagram'")
    print("   You reply with: 'Analyze this'")
    reply_to = MockReplyToMessage(message_id=789, caption="Check out this diagram", photo=[{}])
    result = extract_reply_context(reply_to)
    print(f"   ✓ Extracted: type={result.reply_to_message_type}, text='{result.reply_to_message_text}'")

    # Scenario 4: Reply to video with caption
    print("\n4. Replying to a video with caption:")
    print("   Video caption: 'Tutorial on Python'")
    print("   You reply with: 'Summarize this'")
    reply_to = MockReplyToMessage(message_id=101, caption="Tutorial on Python", video={"file_id": "xyz"})
    result = extract_reply_context(reply_to)
    print(f"   ✓ Extracted: type={result.reply_to_message_type}, text='{result.reply_to_message_text}'")

    # Scenario 5: Reply to voice message (no text yet)
    print("\n5. Replying to a voice message (before transcription):")
    print("   Voice message (not transcribed yet)")
    print("   You send text reply immediately")
    reply_to = MockReplyToMessage(message_id=202, voice={})
    result = extract_reply_context(reply_to)
    print(f"   ✓ Extracted: type={result.reply_to_message_type}, text={result.reply_to_message_text}")
    print(f"   Note: Text is None, will fall back to cache lookup")

    print("\n" + "=" * 60)
    print("WHAT HAPPENS NEXT:")
    print("=" * 60)
    print("""
When Claude receives your reply:
1. First, it checks the in-memory cache for context
2. If cache misses but reply_to_message_text exists:
   - Creates a ReplyContext from the extracted content
   - Adds it to cache for future replies
3. Uses ReplyContext to build a prompt like:

   [Replying to previous message]
   Original: What's the weather?

   Response: Tell me more

This gives Claude full context of what you're replying to!
    """)


if __name__ == "__main__":
    demo()
