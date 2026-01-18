#!/usr/bin/env python3
"""Test script for session naming functionality."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from services.session_naming import generate_session_name


async def test_session_naming():
    """Test session name generation with various prompts."""

    test_cases = [
        ("Can you help me analyze this YouTube video about AI?", "youtube-ai-analysis"),
        ("Create a note about design thinking experiments", "design-thinking"),
        ("Fix the telegram agent error in logs", "telegram-agent"),
        ("What are the open issues in the repo?", "github-issues"),
        ("Transcribe this audio file", "audio"),
        ("Review my notes from this week", "notes-review"),
        ("Research AI-powered session naming", "research-ai"),
        ("Let's look for solutions. as an option, we can just look for session in other folders", "session-search"),
    ]

    print("🧪 Testing Session Naming\n")

    for i, (prompt, expected_pattern) in enumerate(test_cases, 1):
        print(f"Test {i}:")
        print(f"  Prompt: {prompt[:60]}...")

        try:
            name = await generate_session_name(prompt)
            print(f"  Generated: '{name}'")

            # Basic validation
            assert name, "Generated name should not be empty"
            assert len(name) <= 50, f"Name too long: {len(name)} chars"
            assert name.replace("-", "").isalnum(), "Name should be alphanumeric with hyphens"

            # Check it's somewhat relevant (basic check)
            words = name.split("-")
            assert 1 <= len(words) <= 4, f"Should have 1-4 words, got {len(words)}"

            print(f"  ✅ Valid\n")

        except Exception as e:
            print(f"  ❌ Error: {e}\n")
            raise

    print("✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_session_naming())
