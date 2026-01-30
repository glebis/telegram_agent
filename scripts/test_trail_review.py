#!/usr/bin/env python3
"""
Test script for trail review system.

Verifies that:
1. Trail files can be discovered
2. Frontmatter can be parsed
3. Poll sequences can be generated
4. Trail selection logic works
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.trail_review_service import TrailReviewService


def test_trail_discovery():
    """Test trail file discovery."""
    print("=" * 80)
    print("TEST 1: Trail Discovery")
    print("=" * 80)

    service = TrailReviewService()
    trails = service.get_trails_for_review()

    print(f"\n✅ Found {len(trails)} trails")

    if trails:
        print("\nTrails:")
        for trail in trails:
            print(f"\n  • {trail['name']}")
            print(f"    Status: {trail['status']}")
            print(f"    Velocity: {trail['velocity']}")
            print(f"    Urgency: {trail['urgency']} days")
            if trail['next_review']:
                print(f"    Next review: {trail['next_review']}")
    else:
        print("\n⚠️  No trails found. Make sure:")
        print("    - Trails exist in ~/Research/vault/Trails/")
        print("    - Trail files have type: trail in frontmatter")
        print("    - Trail files are named 'Trail - *.md'")

    return len(trails) > 0


def test_poll_generation():
    """Test poll sequence generation."""
    print("\n" + "=" * 80)
    print("TEST 2: Poll Generation")
    print("=" * 80)

    service = TrailReviewService()
    trails = service.get_trails_for_review()

    if not trails:
        print("\n❌ Skipped (no trails found)")
        return False

    trail = trails[0]
    print(f"\nGenerating polls for: {trail['name']}")

    sequence = service.get_poll_sequence(trail)
    print(f"\n✅ Generated {len(sequence)} polls:")

    for i, poll in enumerate(sequence, 1):
        print(f"\n  Poll {i}: {poll['field']}")
        print(f"  Question: {poll['question']}")
        print(f"  Options ({len(poll['options'])}):")
        for opt in poll['options']:
            print(f"    - {opt}")

    return len(sequence) == 4


def test_trail_selection():
    """Test smart trail selection."""
    print("\n" + "=" * 80)
    print("TEST 3: Trail Selection")
    print("=" * 80)

    service = TrailReviewService()

    # Test prioritization
    trails = service.get_trails_for_review()
    if trails:
        print(f"\n✅ Most urgent trail: {trails[0]['name']}")
        print(f"   Urgency: {trails[0]['urgency']} days overdue")

    # Test random active trail
    random_trail = service.get_random_active_trail()
    if random_trail:
        print(f"\n✅ Random trail selected: {random_trail['name']}")
    else:
        print("\n⚠️  No trails available for random selection")

    return random_trail is not None


def test_poll_state_management():
    """Test poll state tracking."""
    print("\n" + "=" * 80)
    print("TEST 4: Poll State Management")
    print("=" * 80)

    service = TrailReviewService()
    trails = service.get_trails_for_review()

    if not trails:
        print("\n❌ Skipped (no trails found)")
        return False

    trail = trails[0]
    chat_id = 123456789  # Test chat ID

    # Start sequence
    first_poll = service.start_poll_sequence(chat_id, trail)

    if first_poll:
        print(f"\n✅ Started poll sequence")
        print(f"   First question: {first_poll['question']}")

        # Simulate answering
        test_answer = first_poll['options'][0]
        next_poll, is_complete = service.get_next_poll(
            chat_id, trail['path'], test_answer
        )

        if next_poll:
            print(f"\n✅ Recorded answer and got next poll")
            print(f"   Next question: {next_poll['question']}")
        else:
            print(f"\n⚠️  Sequence complete after 1 answer")

        return True
    else:
        print("\n❌ Failed to start poll sequence")
        return False


def main():
    """Run all tests."""
    print("\n🧪 Trail Review System Tests\n")

    results = []

    try:
        results.append(("Trail Discovery", test_trail_discovery()))
        results.append(("Poll Generation", test_poll_generation()))
        results.append(("Trail Selection", test_trail_selection()))
        results.append(("Poll State Management", test_poll_state_management()))
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed! Trail review system is ready.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
