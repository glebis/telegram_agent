"""Tests for formatting module."""

from src.bot.handlers.formatting import (
    TELEGRAM_CODE_BLOCK_WIDTH,
    _parse_table_text,
    _reformat_code_block,
    escape_html,
    format_frontmatter_summary,
    markdown_to_telegram_html,
    parse_frontmatter,
    render_compact_table,
    split_message,
    split_message_html_safe,
    strip_telegram_html,
    validate_telegram_html,
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


class TestParseFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_no_frontmatter(self):
        """Content without frontmatter returns None and full content."""
        content = "# Just a heading\n\nSome text."
        fm, body = parse_frontmatter(content)
        assert fm is None
        assert body == content

    def test_basic_frontmatter(self):
        """Simple key-value frontmatter is parsed correctly."""
        content = """---
title: My Note
type: concept
---

# Content here"""
        fm, body = parse_frontmatter(content)
        assert fm is not None
        assert fm["title"] == "My Note"
        assert fm["type"] == "concept"
        assert body.strip().startswith("# Content")

    def test_inline_list(self):
        """Inline list format [a, b, c] is parsed."""
        content = """---
aliases: [PKM, second brain, zettelkasten]
---

Content"""
        fm, body = parse_frontmatter(content)
        assert fm["aliases"] == ["PKM", "second brain", "zettelkasten"]

    def test_multiline_list(self):
        """Multi-line list format with - items is parsed."""
        content = """---
tags:
  - claude-code
  - memory
  - context-management
---

Content"""
        fm, body = parse_frontmatter(content)
        assert fm["tags"] == ["claude-code", "memory", "context-management"]

    def test_empty_list(self):
        """Empty list [] is parsed as empty array."""
        content = """---
aliases: []
---

Content"""
        fm, body = parse_frontmatter(content)
        assert fm["aliases"] == []

    def test_quoted_values(self):
        """Values with quotes are unquoted."""
        content = """---
created_date: '📄 20260106'
title: "My Title"
---

Content"""
        fm, body = parse_frontmatter(content)
        assert fm["created_date"] == "📄 20260106"
        assert fm["title"] == "My Title"

    def test_wikilink_in_value(self):
        """Wikilinks in values are preserved."""
        content = """---
source: "[[Personal Assistant]]"
creation date: [[20210501]]
---

Content"""
        fm, body = parse_frontmatter(content)
        assert fm["source"] == "[[Personal Assistant]]"

    def test_unclosed_frontmatter(self):
        """Unclosed frontmatter returns None."""
        content = """---
title: Broken
type: oops

# No closing dashes"""
        fm, body = parse_frontmatter(content)
        assert fm is None
        assert body == content

    def test_empty_content(self):
        """Empty string returns None and empty body."""
        fm, body = parse_frontmatter("")
        assert fm is None
        assert body == ""

    def test_body_newlines_stripped(self):
        """Leading newlines after frontmatter are stripped."""
        content = """---
type: test
---


# Heading with space before"""
        fm, body = parse_frontmatter(content)
        assert body.startswith("# Heading")


class TestFormatFrontmatterSummary:
    """Tests for frontmatter summary formatting."""

    def test_empty_frontmatter(self):
        """Empty dict returns empty string."""
        assert format_frontmatter_summary({}) == ""
        assert format_frontmatter_summary(None) == ""

    def test_type_only(self):
        """Type field shown as [type]."""
        fm = {"type": "tool"}
        result = format_frontmatter_summary(fm)
        assert result == "[tool]"

    def test_type_and_status(self):
        """Type and status shown on same line."""
        fm = {"type": "agent-task", "status": "complete"}
        result = format_frontmatter_summary(fm)
        assert "[agent-task]" in result
        assert "• complete" in result

    def test_tags_shown(self):
        """Tags shown as hashtags."""
        fm = {"tags": ["claude-code", "memory", "ai"]}
        result = format_frontmatter_summary(fm)
        assert "#claude-code" in result
        assert "#memory" in result
        assert "#ai" in result

    def test_tags_limited_to_five(self):
        """Only first 5 tags shown."""
        fm = {"tags": ["a", "b", "c", "d", "e", "f", "g"]}
        result = format_frontmatter_summary(fm)
        assert "#e" in result
        assert "#f" not in result

    def test_url_shown(self):
        """URL shown with arrow."""
        fm = {"url": "https://github.com/example/repo"}
        result = format_frontmatter_summary(fm)
        assert "↩️" in result
        assert "github.com" in result

    def test_source_used_as_fallback(self):
        """Source field used if url not present."""
        fm = {"source": "fathom"}
        result = format_frontmatter_summary(fm)
        assert "↩️ fathom" in result

    def test_wikilink_source_cleaned(self):
        """Wikilink brackets removed from source."""
        fm = {"source": "[[Personal Assistant]]"}
        result = format_frontmatter_summary(fm)
        assert "[[" not in result
        assert "Personal Assistant" in result

    def test_long_url_truncated(self):
        """Long URLs show domain only."""
        fm = {"url": "https://github.com/very/long/path/to/something/deep"}
        result = format_frontmatter_summary(fm)
        assert "github.com..." in result

    def test_aliases_shown(self):
        """Non-empty aliases shown."""
        fm = {"aliases": ["PKM", "second brain"]}
        result = format_frontmatter_summary(fm)
        assert "aka:" in result
        assert "PKM" in result
        assert "second brain" in result

    def test_empty_aliases_not_shown(self):
        """Empty aliases list not shown."""
        fm = {"aliases": []}
        result = format_frontmatter_summary(fm)
        assert "aka:" not in result

    def test_minimal_frontmatter_empty(self):
        """Frontmatter with only dates/empty aliases returns empty."""
        fm = {
            "aliases": [],
            "creation date": ["[20210501]"],
            "modification date": ["[20241222]"],
        }
        result = format_frontmatter_summary(fm)
        assert result == ""

    def test_full_frontmatter(self):
        """Complete frontmatter formats correctly."""
        fm = {
            "type": "tool",
            "tags": ["claude-code", "memory"],
            "url": "https://github.com/example",
            "aliases": ["CC", "claude"],
        }
        result = format_frontmatter_summary(fm)
        lines = result.split("\n")
        assert len(lines) == 4
        assert "[tool]" in lines[0]
        assert "#claude-code" in lines[1]
        assert "↩️" in lines[2]
        assert "aka:" in lines[3]


class TestMarkdownToTelegramHtmlWithFrontmatter:
    """Tests for markdown conversion with frontmatter handling."""

    def test_frontmatter_stripped(self):
        """Frontmatter --- blocks are not in output."""
        content = """---
type: test
---

# Heading"""
        result = markdown_to_telegram_html(content)
        assert "---" not in result

    def test_frontmatter_summary_included(self):
        """Frontmatter summary prepended to output."""
        content = """---
type: tool
tags:
  - ai
---

# Tool Name"""
        result = markdown_to_telegram_html(content)
        assert "[tool]" in result
        assert "#ai" in result
        assert "<b>Tool Name</b>" in result

    def test_minimal_frontmatter_not_shown(self):
        """Frontmatter with only dates shows no summary."""
        content = """---
aliases: []
creation date: [[20210501]]
---

# Note"""
        result = markdown_to_telegram_html(content)
        # Should not have any frontmatter prefix, just the heading
        assert result.strip().startswith("<b>Note</b>")

    def test_frontmatter_disabled(self):
        """include_frontmatter=False skips summary."""
        content = """---
type: tool
---

# Content"""
        result = markdown_to_telegram_html(content, include_frontmatter=False)
        assert "[tool]" not in result
        assert "<b>Content</b>" in result

    def test_no_frontmatter_passthrough(self):
        """Content without frontmatter passes through unchanged."""
        content = "# Just a heading\n\nSome **bold** text."
        result = markdown_to_telegram_html(content)
        assert "<b>Just a heading</b>" in result
        assert "<b>bold</b>" in result


class TestTableConversion:
    """Tests for markdown table to compact format conversion."""

    def test_basic_table_conversion(self):
        """Simple markdown table converts to compact horizontal format."""
        content = """| Name | Age | City |
|---|---|---|
| Alice | 30 | NYC |
| Bob | 25 | LA |"""
        result = markdown_to_telegram_html(content, include_frontmatter=False)
        assert "<pre>" in result
        # Small table fits horizontally
        assert "Alice" in result
        assert "Bob" in result
        assert "Name" in result
        # Uses thin separator (─ not ═ or |---)
        assert "─" in result

    def test_table_fits_mobile_width(self):
        """All table output lines fit within TELEGRAM_CODE_BLOCK_WIDTH."""
        content = """| Feature | Status | Description |
|---|---|---|
| **Feature with a longer name** | ✅ Done | This is a long description that would wrap |"""
        result = markdown_to_telegram_html(content, include_frontmatter=False)
        import re

        pre_content = re.findall(r"<pre>(.*?)</pre>", result, re.DOTALL)
        assert len(pre_content) > 0
        lines = pre_content[0].split("\n")
        max_width = max(len(line) for line in lines)
        assert (
            max_width <= TELEGRAM_CODE_BLOCK_WIDTH
        ), f"Max line width {max_width} exceeds {TELEGRAM_CODE_BLOCK_WIDTH}"

    def test_table_with_bold_and_emojis(self):
        """Tables with bold text and emojis work correctly."""
        content = """| Idea | Priority |
|---|---|
| **Per-chat workspaces** | 🔴 P0 |
| **Task ledger** | 🔴 P0 |"""
        result = markdown_to_telegram_html(content, include_frontmatter=False)
        assert "**Per-chat workspaces**" in result
        assert "**Task ledger**" in result
        assert "🔴" in result

    def test_table_separator_variations(self):
        """Tables with different separator styles are handled."""
        variations = [
            "|---|---|",
            "| --- | --- |",
            "|:---|:---:|",
            "| :--- | :---: |",
        ]
        for sep in variations:
            content = f"""| A | B |
{sep}
| 1 | 2 |"""
            result = markdown_to_telegram_html(content, include_frontmatter=False)
            assert "1" in result, f"Failed with separator: {sep}"
            assert "2" in result

    def test_table_without_separator(self):
        """Tables without separator line still work (rare but valid)."""
        content = """| Name | Age |
| Alice | 30 |"""
        result = markdown_to_telegram_html(content, include_frontmatter=False)
        assert "Alice" in result
        assert "30" in result

    def test_multiple_tables_in_document(self):
        """Multiple tables in one document are all converted."""
        content = """## Table 1

| Name | Age |
|---|---|
| Alice | 30 |

## Table 2

| City | Country |
|---|---|
| NYC | USA |"""
        result = markdown_to_telegram_html(content, include_frontmatter=False)
        assert "Alice" in result
        assert "NYC" in result
        assert "Name" in result
        assert "City" in result


class TestCompactTableRenderer:
    """Tests for the render_compact_table function."""

    def test_small_table_horizontal(self):
        """Small table renders horizontally with ─ separator."""
        headers = ["Name", "Age"]
        rows = [["Alice", "30"], ["Bob", "25"]]
        result = render_compact_table(headers, rows)
        assert "Name" in result
        assert "Alice" in result
        assert "─" in result
        # Should be horizontal (no card-style indented labels)
        assert "  Age:" not in result

    def test_wide_table_uses_card_format(self):
        """Wide 4-column table falls back to readable card format."""
        headers = ["Service Type", "Pricing Model", "Cost per Minute", "Notes"]
        rows = [
            [
                "Basic Voice AI",
                "Per Minute",
                "$0.008-$0.01/min",
                "TTS, speech recognition",
            ],
            ["Mid-Range Voice AI", "Per Minute", "$0.10-$1.00/min", "Customer support"],
        ]
        result = render_compact_table(headers, rows)
        lines = result.split("\n")
        max_line = max(len(line) for line in lines)
        assert (
            max_line <= TELEGRAM_CODE_BLOCK_WIDTH
        ), f"Table line {max_line} exceeds {TELEGRAM_CODE_BLOCK_WIDTH}"
        # Card format: first column as title, rest as labelled values
        assert "Basic Voice AI" in result
        assert "Mid-Range Voice AI" in result
        assert "Pricing Model:" in result
        assert "Cost per Minute:" in result

    def test_very_wide_table_card_fallback(self):
        """Extremely wide table with many columns falls back to card format."""
        headers = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
        rows = [["value"] * 9]
        result = render_compact_table(headers, rows, max_width=35)
        lines = result.split("\n")
        max_line = max(len(line) for line in lines)
        assert max_line <= 35, f"Card line {max_line} exceeds 35"

    def test_truncation_with_ellipsis(self):
        """Long cell values get truncated with … ellipsis."""
        headers = ["A", "B"]
        rows = [["Short", "This is a very long cell value that should be truncated"]]
        result = render_compact_table(headers, rows, max_width=25)
        assert "…" in result

    def test_all_lines_within_width(self):
        """Every line respects max_width constraint."""
        headers = ["Column A", "Column B", "Column C"]
        rows = [
            ["value1", "value2", "value3"],
            ["longer value here", "another long val", "more text"],
        ]
        result = render_compact_table(headers, rows, max_width=35)
        for line in result.split("\n"):
            assert len(line) <= 35, f"Line exceeds 35 chars: '{line}' ({len(line)})"

    def test_empty_rows(self):
        """Table with no data rows just shows headers."""
        headers = ["A", "B", "C"]
        result = render_compact_table(headers, [])
        assert "A" in result

    def test_single_column_card(self):
        """Single-column table still works."""
        headers = ["Item"]
        rows = [["Apple"], ["Banana"]]
        result = render_compact_table(headers, rows)
        assert "Apple" in result
        assert "Banana" in result


class TestBoxDrawingTableDetection:
    """Tests for box-drawing table parsing and reformatting."""

    def test_parse_double_border_table(self):
        """Double-line box-drawing table is parsed correctly."""
        table = (
            "╔═══════════╦═══════╦═══════╗\n"
            "║ Name      ║ Age   ║ City  ║\n"
            "╠═══════════╬═══════╬═══════╣\n"
            "║ Alice     ║ 30    ║ NYC   ║\n"
            "║ Bob       ║ 25    ║ LA    ║\n"
            "╚═══════════╩═══════╩═══════╝"
        )
        parsed = _parse_table_text(table)
        assert parsed is not None
        headers, rows = parsed
        assert headers == ["Name", "Age", "City"]
        assert len(rows) == 2
        assert rows[0][0] == "Alice"

    def test_parse_single_border_table(self):
        """Single-line box-drawing table is parsed correctly."""
        table = (
            "┌──────┬─────┬──────┐\n"
            "│ Name │ Age │ City │\n"
            "├──────┼─────┼──────┤\n"
            "│ Alice│ 30  │ NYC  │\n"
            "└──────┴─────┴──────┘"
        )
        parsed = _parse_table_text(table)
        assert parsed is not None
        headers, rows = parsed
        assert "Name" in headers[0]
        assert len(rows) == 1

    def test_reformat_wide_box_table(self):
        """Wide box-drawing table in code block gets reformatted to fit."""
        wide_table = (
            "╔══════════════════╦════════════════╦══════════════════╗\n"
            "║ Service Type     ║ Pricing Model  ║ Cost per Minute  ║\n"
            "╠══════════════════╬════════════════╬══════════════════╣\n"
            "║ Basic Voice AI   ║ Per Minute     ║ $0.008-$0.01/min ║\n"
            "║ Mid-Range Voice  ║ Per Minute     ║ $0.10-$1.00/min  ║\n"
            "╚══════════════════╩════════════════╩══════════════════╝"
        )
        result = _reformat_code_block(wide_table)
        lines = result.split("\n")
        max_line = max(len(line) for line in lines)
        assert (
            max_line <= TELEGRAM_CODE_BLOCK_WIDTH
        ), f"Reformatted table line {max_line} exceeds {TELEGRAM_CODE_BLOCK_WIDTH}"
        # Data present (may be truncated with …)
        assert "Basic" in result
        assert "Mid-Range" in result or "Mid-Ran" in result

    def test_narrow_code_block_unchanged(self):
        """Code blocks that already fit are not modified."""
        narrow = "print('hello')\nx = 42"
        assert _reformat_code_block(narrow) == narrow

    def test_non_table_code_block_unchanged(self):
        """Wide code that isn't a table is left as-is."""
        code = "x = 'a very long string that exceeds the width limit but is not a table at all'"
        assert _reformat_code_block(code) == code

    def test_box_table_in_markdown_code_block(self):
        """Box-drawing table inside ```code``` gets reformatted during rendering."""
        content = (
            "Here is a table:\n"
            "```\n"
            "╔═══════════════╦══════════════╦═══════════════╗\n"
            "║ Name          ║ Department   ║ Location      ║\n"
            "╠═══════════════╬══════════════╬═══════════════╣\n"
            "║ Alice Smith   ║ Engineering  ║ San Francisco ║\n"
            "║ Bob Jones     ║ Marketing    ║ New York City ║\n"
            "╚═══════════════╩══════════════╩═══════════════╝\n"
            "```"
        )
        result = markdown_to_telegram_html(content, include_frontmatter=False)
        import re

        pre_content = re.findall(r"<pre>(.*?)</pre>", result, re.DOTALL)
        assert len(pre_content) > 0
        lines = pre_content[0].split("\n")
        max_line = max(len(line) for line in lines if line.strip())
        assert (
            max_line <= TELEGRAM_CODE_BLOCK_WIDTH
        ), f"Box table in code block: line {max_line} exceeds {TELEGRAM_CODE_BLOCK_WIDTH}"
        assert "Alice" in result


# ─── New tests for HTML-safety features ────────────────────────────────────────


class TestValidateTelegramHtml:
    """Tests for validate_telegram_html() — catches malformed HTML before sending."""

    def test_valid_simple_text(self):
        valid, err = validate_telegram_html("Hello world")
        assert valid is True
        assert err == ""

    def test_valid_bold_tag(self):
        valid, err = validate_telegram_html("<b>Hello</b>")
        assert valid is True

    def test_valid_pre_tag(self):
        valid, err = validate_telegram_html("<pre>some code</pre>")
        assert valid is True

    def test_valid_nested_tags(self):
        valid, err = validate_telegram_html("<b>bold <i>and italic</i></b>")
        assert valid is True

    def test_valid_multiple_pre_blocks(self):
        html = "<pre>block one</pre>\n\nsome text\n\n<pre>block two</pre>"
        valid, err = validate_telegram_html(html)
        assert valid is True

    def test_unclosed_pre_is_invalid(self):
        """Reproduces the actual Telegram error: unclosed <pre> tag."""
        html = "Some text <pre>start of code\nline 2\nline 3"  # no </pre>
        valid, err = validate_telegram_html(html)
        assert valid is False
        assert "pre" in err.lower() or "unclosed" in err.lower()

    def test_unexpected_closing_tag_is_invalid(self):
        """Reproduces: 'Unexpected end tag at byte offset N'."""
        html = "Normal text</pre> more text"
        valid, err = validate_telegram_html(html)
        assert valid is False

    def test_mismatched_tags_are_invalid(self):
        html = "<b>text <i>mixed</b></i>"
        valid, err = validate_telegram_html(html)
        assert valid is False

    def test_split_pre_chunk_is_invalid(self):
        """Simulates what split_message produces when it cuts inside a <pre> block."""
        # First chunk ends in the middle of a code block
        chunk = "Some text\n\n<pre>line 1\nline 2\nline 3"
        valid, err = validate_telegram_html(chunk)
        assert valid is False, "A chunk with unclosed <pre> must be flagged as invalid"

    def test_a_tag_with_href(self):
        """Anchor tags with attributes are valid."""
        html = '<a href="https://example.com">link</a>'
        valid, err = validate_telegram_html(html)
        assert valid is True

    def test_empty_string_is_valid(self):
        valid, err = validate_telegram_html("")
        assert valid is True


class TestStripTelegramHtml:
    """Tests for strip_telegram_html() — HTML → plain text fallback."""

    def test_removes_bold_tags(self):
        result = strip_telegram_html("<b>bold</b>")
        assert result == "bold"

    def test_removes_italic_tags(self):
        result = strip_telegram_html("<i>italic</i>")
        assert result == "italic"

    def test_removes_pre_tags(self):
        result = strip_telegram_html("<pre>code block</pre>")
        assert "code block" in result
        assert "<pre>" not in result

    def test_removes_code_tags(self):
        result = strip_telegram_html("<code>inline</code>")
        assert result == "inline"

    def test_unescapes_html_entities(self):
        result = strip_telegram_html("a &amp; b &lt;tag&gt;")
        assert result == "a & b <tag>"

    def test_mixed_html(self):
        result = strip_telegram_html("<b>Title</b>\n\n<pre>some code</pre>")
        assert "Title" in result
        assert "some code" in result
        assert "<b>" not in result
        assert "<pre>" not in result

    def test_plain_text_unchanged(self):
        result = strip_telegram_html("Just plain text")
        assert result == "Just plain text"

    def test_empty_string(self):
        result = strip_telegram_html("")
        assert result == ""


class TestSplitMessageHtmlSafe:
    """Tests for split_message_html_safe() — never cuts inside <pre> blocks."""

    def test_short_message_not_split(self):
        text = "Short message"
        result = split_message_html_safe(text)
        assert result == [text]

    def test_all_chunks_have_valid_html(self):
        """Every chunk produced must pass validate_telegram_html."""
        # Build a message with a large code block that forces splitting
        code_lines = "\n".join(f"line {i}: some code content here" for i in range(80))
        html = f"Intro text\n\n<pre>{code_lines}</pre>\n\nOutro text"
        chunks = split_message_html_safe(html, max_size=500)
        for i, chunk in enumerate(chunks):
            valid, err = validate_telegram_html(chunk)
            assert valid, f"Chunk {i} has invalid HTML: {err!r}\n---\n{chunk[:200]}"

    def test_pre_block_never_split_if_fits(self):
        """A <pre> block that fits within max_size must be kept whole."""
        inner = "\n".join(f"line {i}" for i in range(10))
        html = f"<pre>{inner}</pre>"
        chunks = split_message_html_safe(html, max_size=len(html) + 100)
        assert len(chunks) == 1
        assert "<pre>" in chunks[0]
        assert "</pre>" in chunks[0]

    def test_pre_block_not_split_across_chunks(self):
        """A <pre> block must appear complete in exactly one chunk (not span two chunks)."""
        inner = "\n".join(f"line {i}: code" for i in range(20))
        pre_block = f"<pre>{inner}</pre>"
        # Surround with text that forces splitting
        html = ("Before text\n\n" * 5) + pre_block + ("\n\nAfter text" * 5)
        chunks = split_message_html_safe(html, max_size=300)
        pre_chunks = [c for c in chunks if "<pre>" in c or "</pre>" in c]
        # The pre block should be entirely within a single chunk
        for chunk in pre_chunks:
            has_open = "<pre>" in chunk
            has_close = "</pre>" in chunk
            assert has_open == has_close, (
                "Found a chunk with <pre> but no </pre> (or vice versa): "
                f"{chunk[:200]!r}"
            )

    def test_regression_arseny_template(self):
        """
        Reproduces the actual bug: large markdown template response with a
        code block containing 200+ lines was rejected by Telegram with
        'Can't find end tag corresponding to start tag pre'.
        """
        # Simulate a big template inside a code block (like the all3-context-brief)
        template_lines = []
        for section in range(9):
            template_lines.append(f"## Section {section}")
            template_lines.append("")
            for q in range(8):
                template_lines.append(f"**Question {section}.{q}:**")
                template_lines.append("")
                template_lines.append("")
        inner = "\n".join(template_lines)

        # This is what markdown_to_telegram_html produces for a response with
        # a fenced code block containing the template
        html = (
            "<b>Proposal: Context Brief</b>\n\n"
            "Here is the framework:\n\n"
            f"<pre>{inner}</pre>\n\n"
            "Want me to create this as a vault note?"
        )

        chunks = split_message_html_safe(html, max_size=3800)
        for i, chunk in enumerate(chunks):
            valid, err = validate_telegram_html(chunk)
            assert valid, f"Chunk {i} would be rejected by Telegram: {err!r}"

    def test_large_pre_block_exceeding_max_size_is_truncated(self):
        """A single <pre> block larger than max_size must be truncated, not split."""
        inner = "x\n" * 500  # very large
        html = f"<pre>{inner}</pre>"
        chunks = split_message_html_safe(html, max_size=200)
        # Should produce exactly one chunk (truncated)
        assert len(chunks) == 1
        valid, err = validate_telegram_html(chunks[0])
        assert valid, f"Truncated chunk has invalid HTML: {err}"
        assert "<pre>" in chunks[0]
        assert "</pre>" in chunks[0]

    def test_multiple_pre_blocks_stay_whole(self):
        """Multiple pre blocks in a message are each kept intact."""
        blocks = [f"<pre>block {i}\ncontent</pre>" for i in range(3)]
        html = "\n\nSome text\n\n".join(blocks)
        chunks = split_message_html_safe(html, max_size=100)
        for i, chunk in enumerate(chunks):
            valid, err = validate_telegram_html(chunk)
            assert valid, f"Chunk {i} invalid: {err}"

    def test_text_only_still_splits_correctly(self):
        """Plain text without <pre> blocks still splits at natural boundaries."""
        text = ("word " * 100 + "\n\n") * 5
        chunks = split_message_html_safe(text, max_size=300)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 350  # allow slight overage at boundaries
            valid, _ = validate_telegram_html(chunk)
            assert valid
