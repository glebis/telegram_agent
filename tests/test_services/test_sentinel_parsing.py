"""Tests for sentinel marker output parsing in claude_subprocess."""

import json

import pytest

from src.services.claude_subprocess import (
    SENTINEL_END,
    SENTINEL_START,
    extract_between_sentinels,
)


class TestExtractBetweenSentinels:
    """Tests for the extract_between_sentinels function."""

    def test_valid_markers_extracts_content(self):
        """Content between valid sentinel markers is extracted and stripped."""
        raw = f"{SENTINEL_START}\nhello world\n{SENTINEL_END}"
        result = extract_between_sentinels(raw)
        assert result == "hello world"

    def test_returns_none_when_no_markers(self):
        """Returns None when neither sentinel marker is present."""
        raw = "just some regular output\nno markers here"
        result = extract_between_sentinels(raw)
        assert result is None

    def test_returns_none_with_only_start_marker(self):
        """Returns None when only the start marker is present."""
        raw = f"{SENTINEL_START}\nhello world"
        result = extract_between_sentinels(raw)
        assert result is None

    def test_returns_none_with_only_end_marker(self):
        """Returns None when only the end marker is present."""
        raw = f"hello world\n{SENTINEL_END}"
        result = extract_between_sentinels(raw)
        assert result is None

    def test_empty_content_between_markers(self):
        """Returns empty string when markers are adjacent (no content)."""
        raw = f"{SENTINEL_START}\n{SENTINEL_END}"
        result = extract_between_sentinels(raw)
        assert result == ""

    def test_strips_whitespace_from_content(self):
        """Whitespace around extracted content is stripped."""
        raw = f"{SENTINEL_START}\n  \n  hello  \n  \n{SENTINEL_END}"
        result = extract_between_sentinels(raw)
        assert result == "hello"

    def test_multiple_marker_pairs_extracts_first(self):
        """When multiple marker pairs exist, extracts from first start to first end."""
        raw = (
            f"{SENTINEL_START}\nfirst\n{SENTINEL_END}\n"
            f"{SENTINEL_START}\nsecond\n{SENTINEL_END}"
        )
        result = extract_between_sentinels(raw)
        assert result == "first"

    def test_interleaved_noise_between_markers(self):
        """Noise lines between markers are included in extraction."""
        json_line = json.dumps({"type": "text", "content": "hello"})
        raw = (
            f"DEBUG: starting up\n"
            f"WARNING: something\n"
            f"{SENTINEL_START}\n"
            f"{json_line}\n"
            f"stderr noise line\n"
            f"{SENTINEL_END}\n"
            f"DEBUG: shutting down"
        )
        result = extract_between_sentinels(raw)
        assert json_line in result
        assert "stderr noise line" in result

    def test_json_lines_between_markers(self):
        """JSON output lines between markers are extractable and parseable."""
        lines = [
            json.dumps({"type": "init", "session_id": "abc123"}),
            json.dumps({"type": "text", "content": "Hello"}),
            json.dumps({"type": "done", "session_id": "abc123", "cost": 0.01}),
        ]
        content = "\n".join(lines)
        raw = f"{SENTINEL_START}\n{content}\n{SENTINEL_END}"

        result = extract_between_sentinels(raw)
        assert result is not None

        # Each JSON line should be parseable
        extracted_lines = result.strip().split("\n")
        assert len(extracted_lines) == 3
        for line in extracted_lines:
            parsed = json.loads(line)
            assert "type" in parsed

    def test_markers_with_no_newlines(self):
        """Markers work even without newline separators."""
        raw = f"{SENTINEL_START}content{SENTINEL_END}"
        result = extract_between_sentinels(raw)
        assert result == "content"

    def test_empty_string_input(self):
        """Returns None for empty input."""
        result = extract_between_sentinels("")
        assert result is None

    def test_markers_embedded_in_other_text(self):
        """Markers are detected even when embedded in larger text."""
        raw = (
            f"prefix text {SENTINEL_START}\n"
            f"the payload\n"
            f"{SENTINEL_END} suffix text"
        )
        result = extract_between_sentinels(raw)
        assert result is not None
        assert "the payload" in result


class TestSentinelConstants:
    """Tests for sentinel marker constants."""

    def test_sentinel_start_is_string(self):
        assert isinstance(SENTINEL_START, str)

    def test_sentinel_end_is_string(self):
        assert isinstance(SENTINEL_END, str)

    def test_sentinels_are_distinct(self):
        assert SENTINEL_START != SENTINEL_END

    def test_sentinels_are_not_valid_json(self):
        """Sentinels should not be parseable as JSON to avoid confusion."""
        with pytest.raises(json.JSONDecodeError):
            json.loads(SENTINEL_START)
        with pytest.raises(json.JSONDecodeError):
            json.loads(SENTINEL_END)


class TestBackwardCompatibility:
    """Tests ensuring output without sentinels still works."""

    def test_no_sentinels_returns_none(self):
        """extract_between_sentinels returns None for legacy output."""
        legacy_output = "\n".join(
            [
                json.dumps({"type": "init", "session_id": "abc"}),
                json.dumps({"type": "text", "content": "Hello"}),
                json.dumps({"type": "done", "session_id": "abc", "cost": 0.0}),
            ]
        )
        result = extract_between_sentinels(legacy_output)
        assert result is None

    def test_legacy_json_lines_are_still_parseable(self):
        """Legacy output (no sentinels) can still be parsed line by line."""
        lines = [
            json.dumps({"type": "init", "session_id": "abc"}),
            json.dumps({"type": "text", "content": "Hello"}),
            json.dumps({"type": "done", "session_id": "abc", "cost": 0.0}),
        ]
        for line in lines:
            msg = json.loads(line)
            assert "type" in msg

    def test_fallback_pattern_with_extract(self):
        """Demonstrates the fallback pattern: try sentinels, then line-by-line."""
        legacy_output = json.dumps({"type": "text", "content": "Hello"})

        # Sentinel extraction returns None for legacy output
        sentinel_result = extract_between_sentinels(legacy_output)
        assert sentinel_result is None

        # Fallback: line-by-line JSON parsing still works
        msg = json.loads(legacy_output)
        assert msg["type"] == "text"
        assert msg["content"] == "Hello"
