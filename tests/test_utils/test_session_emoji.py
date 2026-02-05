"""
Tests for the Session Emoji utility.

Tests cover:
- Emoji generation from session IDs
- Deterministic behavior (same input = same output)
- Distribution across emoji sets
- Edge cases (empty strings, None-like values)
- Format function for session display
- Hash-based selection consistency
"""

import hashlib
from typing import Set

import pytest

from src.utils.session_emoji import (
    EMOJI_CIRCLES,
    EMOJI_SQUARES,
    format_session_id,
    get_session_emoji,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_session_ids():
    """Provide a set of sample session IDs for testing."""
    return [
        "abc123",
        "db5eesda3r",
        "550e8400-e29b-41d4-a716-446655440000",  # UUID format
        "session_1234567890",
        "a" * 100,  # Long session ID
        "x",  # Single character
        "12345",  # Numeric only
        "!@#$%^&*()",  # Special characters
    ]


@pytest.fixture
def uuid_session_ids():
    """Provide UUID-formatted session IDs."""
    return [
        "550e8400-e29b-41d4-a716-446655440000",
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    ]


# =============================================================================
# Get Session Emoji Tests
# =============================================================================


class TestGetSessionEmoji:
    """Tests for get_session_emoji function."""

    def test_returns_two_character_emoji_string(self, sample_session_ids):
        """Test that get_session_emoji returns exactly two emojis."""
        for session_id in sample_session_ids:
            result = get_session_emoji(session_id)

            # Should be two emojis (counting emoji characters, not bytes)
            # Each emoji is one character but multiple bytes
            assert len(result) == 2

    def test_first_emoji_is_from_circles(self, sample_session_ids):
        """Test that the first emoji is from EMOJI_CIRCLES set."""
        for session_id in sample_session_ids:
            result = get_session_emoji(session_id)
            first_emoji = result[0]

            assert (
                first_emoji in EMOJI_CIRCLES
            ), f"First emoji '{first_emoji}' not in EMOJI_CIRCLES for session '{session_id}'"

    def test_second_emoji_is_from_squares(self, sample_session_ids):
        """Test that the second emoji is from EMOJI_SQUARES set."""
        for session_id in sample_session_ids:
            result = get_session_emoji(session_id)
            second_emoji = result[1]

            assert (
                second_emoji in EMOJI_SQUARES
            ), f"Second emoji '{second_emoji}' not in EMOJI_SQUARES for session '{session_id}'"

    def test_deterministic_output(self, sample_session_ids):
        """Test that the same session ID always produces the same emoji pair."""
        for session_id in sample_session_ids:
            result1 = get_session_emoji(session_id)
            result2 = get_session_emoji(session_id)
            result3 = get_session_emoji(session_id)

            assert result1 == result2 == result3, (
                f"Non-deterministic results for session '{session_id}': "
                f"{result1}, {result2}, {result3}"
            )

    def test_different_sessions_can_have_different_emojis(self):
        """Test that different session IDs can produce different emoji pairs."""
        # Generate many session IDs to ensure we get variety
        unique_emojis: Set[str] = set()

        for i in range(1000):
            session_id = f"test_session_{i}"
            emoji = get_session_emoji(session_id)
            unique_emojis.add(emoji)

        # Should have multiple unique emoji combinations
        # With 9 circles x 9 squares = 81 possible combinations
        # 1000 samples should hit at least 20+ unique combinations
        assert (
            len(unique_emojis) > 20
        ), f"Expected significant variety in emojis, got only {len(unique_emojis)} unique pairs"

    def test_empty_string_returns_default(self):
        """Test that empty session ID returns default emoji pair."""
        result = get_session_emoji("")

        assert result == "\u2b1c\u2b1c"  # Two white squares

    def test_none_handled_gracefully(self):
        """Test that None input returns default emoji pair without error."""
        # The function checks 'if not session_id' which handles None
        result = get_session_emoji(None)

        assert result == "\u2b1c\u2b1c"  # Two white squares

    def test_whitespace_only_returns_default(self):
        """Test that whitespace-only session ID returns default."""
        # Empty string is falsy but whitespace is truthy
        # This tests what happens with whitespace
        result = get_session_emoji("   ")

        # Whitespace is truthy so it should hash and return emojis
        assert result != "\u2b1c\u2b1c"
        assert len(result) == 2

    def test_hash_based_selection(self):
        """Test that emoji selection matches expected hash-based algorithm."""
        session_id = "test_session"

        # Calculate expected result manually
        hash_bytes = hashlib.md5(session_id.encode()).digest()
        expected_circle_idx = hash_bytes[0] % len(EMOJI_CIRCLES)
        expected_square_idx = hash_bytes[1] % len(EMOJI_SQUARES)
        expected = (
            f"{EMOJI_CIRCLES[expected_circle_idx]}{EMOJI_SQUARES[expected_square_idx]}"
        )

        result = get_session_emoji(session_id)

        assert result == expected

    def test_uuid_format_sessions(self, uuid_session_ids):
        """Test emoji generation for UUID-formatted session IDs."""
        for session_id in uuid_session_ids:
            result = get_session_emoji(session_id)

            assert len(result) == 2
            assert result[0] in EMOJI_CIRCLES
            assert result[1] in EMOJI_SQUARES

    def test_special_characters_handled(self):
        """Test that session IDs with special characters work correctly."""
        special_ids = [
            "session/with/slashes",
            "session.with.dots",
            "session-with-dashes",
            "session_with_underscores",
            "session with spaces",
            "session\twith\ttabs",
            "session\nwith\nnewlines",
            "unicode_\u4e2d\u6587_session",  # Chinese characters
            "emoji_session",  # Emojis in session ID
        ]

        for session_id in special_ids:
            result = get_session_emoji(session_id)

            assert len(result) == 2, f"Failed for session: {repr(session_id)}"
            assert result[0] in EMOJI_CIRCLES
            assert result[1] in EMOJI_SQUARES


# =============================================================================
# Format Session ID Tests
# =============================================================================


class TestFormatSessionId:
    """Tests for format_session_id function."""

    def test_short_format_truncates_to_eight_chars(self):
        """Test that short format truncates session ID to 8 characters."""
        session_id = "1234567890abcdef"

        result = format_session_id(session_id, short=True)

        # Should contain emoji + space + first 8 chars
        assert "12345678" in result
        assert "90abcdef" not in result

    def test_long_format_shows_full_id(self):
        """Test that long format shows the complete session ID."""
        session_id = "1234567890abcdef"

        result = format_session_id(session_id, short=False)

        assert "1234567890abcdef" in result

    def test_default_is_short_format(self):
        """Test that short=True is the default behavior."""
        session_id = "1234567890abcdef"

        result_default = format_session_id(session_id)
        result_short = format_session_id(session_id, short=True)

        assert result_default == result_short

    def test_format_includes_emoji_prefix(self):
        """Test that formatted output includes emoji prefix."""
        session_id = "test_session_123"

        result = format_session_id(session_id)
        emoji = get_session_emoji(session_id)

        assert result.startswith(emoji)

    def test_format_includes_space_separator(self):
        """Test that emoji and ID are separated by space."""
        session_id = "test_session_123"

        result = format_session_id(session_id)
        emoji = get_session_emoji(session_id)

        expected_prefix = f"{emoji} "
        assert result.startswith(expected_prefix)

    def test_empty_string_returns_none_format(self):
        """Test that empty session ID returns '(none)' format."""
        result = format_session_id("")

        assert "(none)" in result
        assert "\u2b1c\u2b1c" in result  # Default emoji

    def test_none_returns_none_format(self):
        """Test that None session ID returns '(none)' format."""
        result = format_session_id(None)

        assert "(none)" in result
        assert "\u2b1c\u2b1c" in result  # Default emoji

    def test_short_session_id_not_truncated(self):
        """Test that session IDs shorter than 8 chars are not truncated."""
        short_id = "abc"

        result = format_session_id(short_id, short=True)

        assert "abc" in result

    def test_exactly_eight_char_session(self):
        """Test handling of exactly 8 character session ID."""
        session_id = "12345678"

        result = format_session_id(session_id, short=True)

        assert "12345678" in result


# =============================================================================
# Emoji Constants Tests
# =============================================================================


class TestEmojiConstants:
    """Tests for emoji constant definitions."""

    def test_emoji_circles_has_nine_elements(self):
        """Test that EMOJI_CIRCLES contains exactly 9 elements."""
        assert len(EMOJI_CIRCLES) == 9

    def test_emoji_squares_has_nine_elements(self):
        """Test that EMOJI_SQUARES contains exactly 9 elements."""
        assert len(EMOJI_SQUARES) == 9

    def test_emoji_circles_contains_expected_emojis(self):
        """Test that EMOJI_CIRCLES contains the expected circle emojis."""
        expected = {
            "\U0001f534",
            "\U0001f7e0",
            "\U0001f7e1",
            "\U0001f7e2",
            "\U0001f535",
            "\U0001f7e3",
            "\u26ab",
            "\u26aa",
            "\U0001f7e4",
        }

        assert set(EMOJI_CIRCLES) == expected

    def test_emoji_squares_contains_expected_emojis(self):
        """Test that EMOJI_SQUARES contains the expected square emojis."""
        expected = {
            "\U0001f7e5",
            "\U0001f7e7",
            "\U0001f7e8",
            "\U0001f7e9",
            "\U0001f7e6",
            "\U0001f7ea",
            "\u2b1b",
            "\u2b1c",
            "\U0001f7eb",
        }

        assert set(EMOJI_SQUARES) == expected

    def test_no_overlap_between_sets(self):
        """Test that circles and squares sets have no overlapping emojis."""
        circles_set = set(EMOJI_CIRCLES)
        squares_set = set(EMOJI_SQUARES)

        assert circles_set.isdisjoint(squares_set)

    def test_all_emojis_are_single_characters(self):
        """Test that each emoji is a single Unicode character."""
        for emoji in EMOJI_CIRCLES + EMOJI_SQUARES:
            assert len(emoji) == 1, f"Emoji '{emoji}' has length {len(emoji)}"


# =============================================================================
# Distribution Tests
# =============================================================================


class TestDistribution:
    """Tests for emoji distribution across session IDs."""

    def test_circle_distribution(self):
        """Test that all circle emojis can be selected."""
        seen_circles: Set[str] = set()

        # Try enough session IDs to likely see all circles
        for i in range(10000):
            session_id = f"dist_test_{i}"
            emoji_pair = get_session_emoji(session_id)
            seen_circles.add(emoji_pair[0])

            # Early exit if we've seen all
            if len(seen_circles) == len(EMOJI_CIRCLES):
                break

        assert seen_circles == set(
            EMOJI_CIRCLES
        ), f"Missing circles: {set(EMOJI_CIRCLES) - seen_circles}"

    def test_square_distribution(self):
        """Test that all square emojis can be selected."""
        seen_squares: Set[str] = set()

        # Try enough session IDs to likely see all squares
        for i in range(10000):
            session_id = f"dist_test_{i}"
            emoji_pair = get_session_emoji(session_id)
            seen_squares.add(emoji_pair[1])

            # Early exit if we've seen all
            if len(seen_squares) == len(EMOJI_SQUARES):
                break

        assert seen_squares == set(
            EMOJI_SQUARES
        ), f"Missing squares: {set(EMOJI_SQUARES) - seen_squares}"

    def test_all_combinations_possible(self):
        """Test that a significant number of combinations can be generated."""
        max_combinations = len(EMOJI_CIRCLES) * len(EMOJI_SQUARES)  # 81
        seen_combinations: Set[str] = set()

        # Try many session IDs
        for i in range(50000):
            session_id = f"combo_test_{i}"
            emoji_pair = get_session_emoji(session_id)
            seen_combinations.add(emoji_pair)

            # Early exit if we've seen all
            if len(seen_combinations) == max_combinations:
                break

        # Should see at least 75% of possible combinations
        expected_minimum = int(max_combinations * 0.75)
        assert len(seen_combinations) >= expected_minimum, (
            f"Expected at least {expected_minimum} combinations, "
            f"got {len(seen_combinations)}"
        )


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_session_id(self):
        """Test handling of very long session IDs."""
        long_id = "x" * 10000

        result = get_session_emoji(long_id)

        assert len(result) == 2
        assert result[0] in EMOJI_CIRCLES
        assert result[1] in EMOJI_SQUARES

    def test_single_character_session_id(self):
        """Test handling of single character session IDs."""
        for char in "abcdefghij0123456789":
            result = get_session_emoji(char)

            assert len(result) == 2
            assert result[0] in EMOJI_CIRCLES
            assert result[1] in EMOJI_SQUARES

    def test_binary_like_content(self):
        """Test session IDs that contain null bytes or binary-like content."""
        # Note: These are valid UTF-8 strings that might be edge cases
        binary_ids = [
            "\x00",  # Null byte
            "\x00\x01\x02",  # Multiple binary bytes
            "abc\x00def",  # Mixed with null
        ]

        for session_id in binary_ids:
            result = get_session_emoji(session_id)

            assert len(result) == 2
            assert result[0] in EMOJI_CIRCLES
            assert result[1] in EMOJI_SQUARES

    def test_unicode_session_ids(self):
        """Test session IDs with various Unicode characters."""
        unicode_ids = [
            "\u4e2d\u6587",  # Chinese
            "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",  # Russian
            "\u0627\u0644\u0639\u0631\u0628\u064a\u0629",  # Arabic
            "\U0001f600\U0001f601\U0001f602",  # Emojis as session ID
        ]

        for session_id in unicode_ids:
            result = get_session_emoji(session_id)

            assert len(result) == 2
            assert result[0] in EMOJI_CIRCLES
            assert result[1] in EMOJI_SQUARES

    def test_format_very_long_session_id(self):
        """Test format_session_id with very long session ID."""
        long_id = "x" * 10000

        result_short = format_session_id(long_id, short=True)
        result_long = format_session_id(long_id, short=False)

        # Short should be truncated to 8 chars + emoji + space
        assert len(result_short) < 20  # emoji(2) + space(1) + id(8) = 11 chars

        # Long should contain full ID
        assert "x" * 100 in result_long


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_format_uses_correct_emoji(self):
        """Test that format_session_id uses the correct emoji from get_session_emoji."""
        session_id = "integration_test_session"

        expected_emoji = get_session_emoji(session_id)
        formatted = format_session_id(session_id)

        assert formatted.startswith(expected_emoji)

    def test_empty_handling_consistency(self):
        """Test that empty session handling is consistent between functions."""
        empty_emoji = get_session_emoji("")
        empty_formatted = format_session_id("")

        # Both should use the default emoji
        assert empty_formatted.startswith(empty_emoji)

    def test_determinism_across_functions(self):
        """Test that multiple calls to both functions are deterministic."""
        session_id = "determinism_test"

        for _ in range(10):
            emoji1 = get_session_emoji(session_id)
            formatted1 = format_session_id(session_id)
            emoji2 = get_session_emoji(session_id)
            formatted2 = format_session_id(session_id)

            assert emoji1 == emoji2
            assert formatted1 == formatted2
