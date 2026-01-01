"""
Text formatting utilities for Telegram messages.

Contains:
- HTML escaping
- Markdown to Telegram HTML conversion
- Message splitting for long content
"""

import logging
import re
import uuid
from typing import List

logger = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def split_message(text: str, max_size: int = 3800) -> List[str]:
    """Split a long message into chunks, trying to break at natural boundaries."""
    if len(text) <= max_size:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_size:
            chunks.append(remaining)
            break

        chunk = remaining[:max_size]

        # Look for paragraph break (double newline)
        break_point = chunk.rfind("\n\n")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 2:]
            continue

        # Look for single newline
        break_point = chunk.rfind("\n")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 1:]
            continue

        # Look for space
        break_point = chunk.rfind(" ")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 1:]
            continue

        # No good break point, just cut at max_size
        chunks.append(remaining[:max_size])
        remaining = remaining[max_size:]

    return chunks


def markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram-compatible HTML."""
    # Generate unique placeholder prefix
    placeholder = f"CODEBLOCK{uuid.uuid4().hex[:8]}"

    # First escape HTML entities
    text = escape_html(text)

    # Process code blocks first (```code```) - preserve them
    code_blocks = []

    def save_code_block(match):
        code_blocks.append(match.group(1))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    text = re.sub(r'```(?:\w+)?\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

    # Detect and convert markdown tables to ASCII tables
    def convert_table(match):
        try:
            from tabulate import tabulate
            table_text = match.group(0)
            lines = [l.strip() for l in table_text.strip().split('\n') if l.strip()]

            rows = []
            for line in lines:
                if re.match(r'^\|[\s\-:]+\|$', line):
                    continue
                cells = [c.strip() for c in line.split('|')]
                cells = [c for c in cells if c]
                if cells:
                    rows.append(cells)

            if len(rows) >= 1:
                headers = rows[0]
                data = rows[1:] if len(rows) > 1 else []
                ascii_table = tabulate(data, headers=headers, tablefmt="simple")
                code_blocks.append(ascii_table)
                return f"{placeholder}{len(code_blocks) - 1}{placeholder}"
        except Exception as e:
            logger.warning(f"Table conversion failed: {e}")
        code_blocks.append(match.group(0))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    table_pattern = r'(?:^\|.+\|$\n?)+'
    text = re.sub(table_pattern, convert_table, text, flags=re.MULTILINE)

    # Inline code (`code`)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Bold (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic (*text* or _text_)
    text = re.sub(r'(?<![a-zA-Z0-9])\*([^*]+)\*(?![a-zA-Z0-9])', r'<i>\1</i>', text)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)

    # Headers (# Header) -> bold
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Markdown links [text](url) -> <a href="url">text</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Wikilinks [[Note Name]] -> clickable deep link
    def format_wikilink(match):
        import urllib.parse
        note_name = match.group(1)
        display_name = note_name.lstrip('@')
        encoded_name = urllib.parse.quote(display_name, safe='')
        deep_link = f'https://t.me/toolbuildingape_bot?start=note_{encoded_name}'
        return f'<a href="{deep_link}">📄 {display_name}</a>'

    text = re.sub(r'\[\[([^\]]+)\]\]', format_wikilink, text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"{placeholder}{i}{placeholder}", f"<pre>{block}</pre>")

    return text


# Aliases for backwards compatibility
_escape_html = escape_html
_split_message = split_message
_markdown_to_telegram_html = markdown_to_telegram_html
