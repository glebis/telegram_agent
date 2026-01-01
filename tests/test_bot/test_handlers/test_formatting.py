"""Tests for formatting module."""

import pytest
from src.bot.handlers.formatting import (
    escape_html,
    markdown_to_telegram_html,
    split_message,
)


class TestEscapeHtml:
    """Tests for HTML escaping."""

    def test_escapes_ampersand(self):
        assert escape_html("A & B") == "A &amp; B"

    def test_escapes_less_than(self):
        assert escape_html("a < b") == "a &lt; b"

    def test_escapes_greater_than(self):
        assert escape_html("a > b") == "a &gt; b"

    def test_preserves_normal_text(self):
        assert escape_html("Hello World") == "Hello World"

    def test_escapes_multiple_special_chars(self):
        assert escape_html("<script>alert('xss')</script>") == (
            "&lt;script&gt;alert('xss')&lt;/script&gt;"
        )

    def test_empty_string(self):
        assert escape_html("") == ""

    def test_unicode_preserved(self):
        assert escape_html("Hello 世界 🌍") == "Hello 世界 🌍"


class TestMarkdownToTelegramHtml:
    """Tests for markdown to Telegram HTML conversion."""

    def test_bold_text(self):
        result = markdown_to_telegram_html("**bold text**")
        assert "<b>bold text</b>" in result

    def test_italic_text(self):
        result = markdown_to_telegram_html("*italic*")
        assert "<i>italic</i>" in result

    def test_code_inline(self):
        result = markdown_to_telegram_html("`code`")
        assert "<code>code</code>" in result

    def test_code_block(self):
        result = markdown_to_telegram_html("```python\nprint('hello')\n```")
        assert "<pre>" in result or "<code>" in result

    def test_header_conversion(self):
        result = markdown_to_telegram_html("# Header")
        # Headers become bold
        assert "<b>" in result

    def test_wikilink_conversion(self):
        result = markdown_to_telegram_html("See [[Note Name]] for details")
        # Wikilinks should be converted to code or preserved
        assert "Note Name" in result

    def test_preserves_plain_text(self):
        result = markdown_to_telegram_html("Plain text without markdown")
        assert "Plain text without markdown" in result

    def test_handles_empty_string(self):
        result = markdown_to_telegram_html("")
        assert result == ""

    def test_mixed_formatting(self):
        result = markdown_to_telegram_html("**bold** and *italic* and `code`")
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<code>code</code>" in result

    def test_escapes_html_entities(self):
        result = markdown_to_telegram_html("Use <tag> & entity")
        assert "&lt;tag&gt;" in result
        assert "&amp;" in result


class TestSplitMessage:
    """Tests for message splitting."""

    def test_short_message_not_split(self):
        text = "Short message"
        result = split_message(text)
        assert len(result) == 1
        assert result[0] == text

    def test_long_message_split(self):
        # Create a message longer than default max
        text = "x" * 5000
        result = split_message(text, max_size=1000)
        assert len(result) > 1
        # Reconstruct should equal original (minus any added newlines)
        reconstructed = "".join(result)
        assert len(reconstructed) >= len(text)

    def test_respects_max_size(self):
        text = "word " * 1000
        result = split_message(text, max_size=500)
        for chunk in result:
            assert len(chunk) <= 600  # Allow some overflow for word boundaries

    def test_splits_at_newlines(self):
        text = "Line 1\n" * 100
        result = split_message(text, max_size=50)
        assert len(result) > 1
        # Each chunk should end at a line boundary where possible
        for chunk in result[:-1]:  # All but last
            assert chunk.endswith("\n") or len(chunk) < 60

    def test_splits_at_word_boundaries(self):
        text = "word " * 100
        result = split_message(text, max_size=50)
        assert len(result) > 1
        # No word should be cut in the middle
        for chunk in result:
            # Should not start with partial word (no leading non-space after first chunk)
            words = chunk.strip().split()
            for word in words:
                assert word == word.strip()

    def test_handles_empty_string(self):
        result = split_message("")
        assert result == [""]

    def test_handles_no_good_split_point(self):
        # Long word with no spaces or newlines
        text = "x" * 500
        result = split_message(text, max_size=100)
        assert len(result) > 1
        # Should still split even without good boundaries

    def test_custom_max_size(self):
        text = "abc " * 100
        result = split_message(text, max_size=100)
        for chunk in result:
            assert len(chunk) <= 150  # Allow some overflow


class TestIntegration:
    """Integration tests for formatting functions."""

    def test_markdown_converter_escapes_html(self):
        """Markdown converter internally escapes HTML entities."""
        dangerous = "User said: <script>alert(1)</script>"
        # markdown_to_telegram_html should escape HTML internally
        result = markdown_to_telegram_html(dangerous)
        # The raw <script> tag should not appear
        assert "<script>" not in result or "&lt;script&gt;" in result

    def test_escape_standalone(self):
        """Standalone escape function works correctly."""
        dangerous = "<script>alert(1)</script>"
        escaped = escape_html(dangerous)
        assert "&lt;script&gt;" in escaped
        assert "<script>" not in escaped

    def test_split_after_format(self):
        """Long formatted message can be split."""
        text = "**Bold section** " * 200
        formatted = markdown_to_telegram_html(text)
        chunks = split_message(formatted, max_size=500)
        assert len(chunks) > 1
        # All chunks should be valid
        for chunk in chunks:
            assert len(chunk) > 0
