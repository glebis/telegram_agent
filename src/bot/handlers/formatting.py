"""
Text formatting utilities for Telegram messages.

Contains:
- HTML escaping
- Markdown to Telegram HTML conversion
- Frontmatter parsing and formatting
- Message splitting for long content
"""

import logging
import re
import uuid
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, any]], str]:
    """
    Extract YAML frontmatter from markdown content.

    Returns:
        (frontmatter_dict, body_content) - frontmatter is None if not present
    """
    if not content.startswith("---"):
        return None, content

    # Find closing ---
    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return None, content

    yaml_content = content[4:end_idx]  # Skip opening ---\n
    body = content[end_idx + 4 :].lstrip("\n")  # Skip closing ---\n

    result = {}
    current_key = None
    current_list = None

    for line in yaml_content.split("\n"):
        # Check for list item (starts with -)
        if line.strip().startswith("- ") and current_key:
            item = line.strip()[2:].strip()
            if current_list is None:
                current_list = []
            current_list.append(item)
            result[current_key] = current_list
        elif ":" in line and not line.strip().startswith("-"):
            # Save previous list if any
            current_list = None

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            current_key = key

            # Handle inline lists like [item1, item2]
            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                result[key] = [i.strip().strip("'\"") for i in items if i.strip()]
            elif value:
                # Strip quotes
                value = value.strip("'\"")
                result[key] = value
            else:
                result[key] = None  # Key with no value (list follows)

    return result, body


def format_frontmatter_summary(frontmatter: Dict[str, any]) -> str:
    """
    Format frontmatter as a concise 1-3 line summary for Telegram.

    Priority fields (in order):
    - type: shown as [type]
    - tags: shown as #tag1 #tag2
    - url/source: shown as link
    - status: shown for tasks
    - aliases: only if non-empty and useful
    """
    if not frontmatter:
        return ""

    parts = []

    # Line 1: Type + Status (if present)
    line1_parts = []
    if frontmatter.get("type"):
        line1_parts.append(f"[{frontmatter['type']}]")
    if frontmatter.get("status"):
        line1_parts.append(f"• {frontmatter['status']}")

    if line1_parts:
        parts.append(" ".join(line1_parts))

    # Line 2: Tags
    tags = frontmatter.get("tags", [])
    if isinstance(tags, list) and tags:
        tag_str = " ".join(f"#{t}" for t in tags[:5])  # Max 5 tags
        parts.append(tag_str)

    # Line 3: URL/Source
    url = frontmatter.get("url") or frontmatter.get("source")
    if url:
        # Clean up wikilink format if present
        if url.startswith("[[") and url.endswith("]]"):
            url = url[2:-2]
        # Truncate long URLs
        if len(url) > 50 and url.startswith("http"):
            # Show domain only
            import urllib.parse

            parsed = urllib.parse.urlparse(url)
            url = f"{parsed.netloc}..."
        parts.append(f"↩️ {url}")

    # Aliases (only if non-empty and different from common patterns)
    aliases = frontmatter.get("aliases", [])
    if isinstance(aliases, list) and aliases:
        alias_str = ", ".join(aliases[:3])  # Max 3 aliases
        parts.append(f"aka: {alias_str}")

    return "\n".join(parts)


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
            remaining = remaining[break_point + 2 :]
            continue

        # Look for single newline
        break_point = chunk.rfind("\n")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 1 :]
            continue

        # Look for space
        break_point = chunk.rfind(" ")
        if break_point > max_size // 2:
            chunks.append(remaining[:break_point])
            remaining = remaining[break_point + 1 :]
            continue

        # No good break point, just cut at max_size
        chunks.append(remaining[:max_size])
        remaining = remaining[max_size:]

    return chunks


def markdown_to_telegram_html(text: str, include_frontmatter: bool = True) -> str:
    """
    Convert markdown to Telegram-compatible HTML.

    Args:
        text: Markdown content (may include YAML frontmatter)
        include_frontmatter: If True, prepend formatted frontmatter summary
    """
    # Parse and remove frontmatter
    frontmatter, body = parse_frontmatter(text)

    # Format frontmatter summary if present and requested
    frontmatter_summary = ""
    if frontmatter and include_frontmatter:
        summary = format_frontmatter_summary(frontmatter)
        if summary:
            frontmatter_summary = f"{summary}\n\n"

    # Generate unique placeholder prefix
    placeholder = f"CODEBLOCK{uuid.uuid4().hex[:8]}"

    # First escape HTML entities
    text = escape_html(body)

    # Process code blocks first (```code```) - preserve them
    code_blocks = []

    def save_code_block(match):
        code_blocks.append(match.group(1))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    text = re.sub(r"```(?:\w+)?\n?(.*?)```", save_code_block, text, flags=re.DOTALL)

    # Detect and convert markdown tables to mobile-friendly card format
    def convert_table(match):
        try:
            table_text = match.group(0)
            lines = [
                line.strip() for line in table_text.strip().split("\n") if line.strip()
            ]

            rows = []
            separator_found = False
            for line in lines:
                # Skip separator line (e.g., |---|---|---|)
                if re.match(r"^\|[\s\-:|]+\|$", line):
                    separator_found = True
                    continue
                cells = [c.strip() for c in line.split("|")]
                cells = [c for c in cells if c]
                if cells:
                    rows.append(cells)

            # If we found a separator, first row is headers
            if separator_found and len(rows) >= 2:
                headers = rows[0]
                data = rows[1:]
            elif len(rows) >= 1:
                # No separator, treat first row as headers
                headers = rows[0]
                data = rows[1:] if len(rows) > 1 else []
            else:
                # No valid table
                code_blocks.append(match.group(0))
                return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

            # Mobile-friendly card format (vertical layout per row)
            # Better for narrow Telegram screens than wide ASCII tables
            cards = []
            for row in data:
                card_lines = []
                for i, cell in enumerate(row):
                    if i < len(headers):
                        # First column: use as title (bold, no label)
                        if i == 0:
                            card_lines.append(cell)
                        else:
                            # Other columns: label + value
                            card_lines.append(f"  {headers[i]}: {cell}")
                cards.append("\n".join(card_lines))

            mobile_table = "\n\n".join(cards)
            code_blocks.append(mobile_table)
            return f"{placeholder}{len(code_blocks) - 1}{placeholder}"
        except Exception as e:
            logger.warning(f"Table conversion failed: {e}")
        code_blocks.append(match.group(0))
        return f"{placeholder}{len(code_blocks) - 1}{placeholder}"

    table_pattern = r"(?:^\|.+\|$\n?)+"
    text = re.sub(table_pattern, convert_table, text, flags=re.MULTILINE)

    # Inline code (`code`)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bold (**text** or __text__)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Italic (*text* or _text_)
    text = re.sub(r"(?<![a-zA-Z0-9])\*([^*]+)\*(?![a-zA-Z0-9])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)

    # Headers (# Header) -> bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Markdown links [text](url) -> <a href="url">text</a>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Wikilinks [[Note Name]] -> clickable deep link
    def format_wikilink(match):
        import urllib.parse

        from ...core.config import get_config_value

        note_name = match.group(1)
        display_name = note_name.lstrip("@")
        encoded_name = urllib.parse.quote(display_name, safe="")
        bot_username = get_config_value("bot.bot_username", "toolbuildingape_bot")
        deep_link = f"https://t.me/{bot_username}?start=note_{encoded_name}"
        return f'<a href="{deep_link}">📄 {display_name}</a>'

    text = re.sub(r"\[\[([^\]]+)\]\]", format_wikilink, text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"{placeholder}{i}{placeholder}", f"<pre>{block}</pre>")

    # Prepend frontmatter summary if present
    if frontmatter_summary:
        text = frontmatter_summary + text

    return text


# Aliases for backwards compatibility
_escape_html = escape_html
_split_message = split_message
_markdown_to_telegram_html = markdown_to_telegram_html
