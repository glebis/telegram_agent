"""
Text formatting utilities for Telegram messages.

Canonical location for formatting helpers used across layers (services,
utils, bot handlers).  The original ``src/bot/handlers/formatting`` module
re-exports everything from here for backward compatibility.

Contains:
- HTML escaping
- Markdown to Telegram HTML conversion
- Frontmatter parsing and formatting
- Message splitting for long content
- Compact table rendering for mobile Telegram
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# === Telegram mobile display constraints ===
# Safe monospace char width for <pre> blocks on mobile phones.
# iPhone SE/standard ~ 33-35 chars, Plus/Max ~ 40+, Android similar.
TELEGRAM_CODE_BLOCK_WIDTH = 35

# Box-drawing characters used in fancy/double-grid tables
_BOX_H = set("\u2500\u2501\u2550\u2504\u2505\u2508\u2509\u254c\u254d\u257c\u257e")
_BOX_V = set("\u2502\u2503\u2551\u2506\u2507\u250a\u250b\u254e\u254f\u257d\u257f")
_BOX_J = set(
    "\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"
    "\u250f\u2513\u2517\u251b\u2523\u252b\u2533\u253b\u254b"
    "\u2554\u2557\u255a\u255d\u2560\u2563\u2566\u2569\u256c"
    "\u256d\u256e\u256f\u2570"
)
_BOX_ALL = _BOX_H | _BOX_V | _BOX_J


def _is_table_separator(line: str) -> bool:
    """Check if a line is a table separator (horizontal border, dashes, etc.)."""
    stripped = line.strip()
    if not stripped:
        return False
    non_space = stripped.replace(" ", "")
    if non_space and all(c in _BOX_ALL for c in non_space):
        return True
    if re.match(r"^[\|\+\-:= ]+$", stripped) and "-" in stripped:
        return True
    return False


def _split_table_row(line: str) -> List[str]:
    """Split a table row into cell values, handling box-drawing and pipe delimiters."""
    for ch in _BOX_V:
        line = line.replace(ch, "|")
    cells = [c.strip() for c in line.split("|")]
    return [c for c in cells if c]


def _parse_table_text(text: str) -> Optional[Tuple[List[str], List[List[str]]]]:
    """
    Parse a table (box-drawing or pipe-delimited) into (headers, data_rows).
    Returns None if the text is not a recognisable table.
    """
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return None

    data_lines: List[Tuple[int, List[str]]] = []
    separator_indices: List[int] = []

    for i, line in enumerate(lines):
        if _is_table_separator(line):
            separator_indices.append(i)
        else:
            cells = _split_table_row(line)
            if cells:
                data_lines.append((i, cells))

    if len(data_lines) < 2:
        return None

    if separator_indices:
        first_sep = separator_indices[0]
        header_rows = [(idx, c) for idx, c in data_lines if idx < first_sep]
        rest_rows = [(idx, c) for idx, c in data_lines if idx > first_sep]
        if header_rows:
            headers = header_rows[0][1]
        elif rest_rows:
            headers = rest_rows[0][1]
            rest_rows = rest_rows[1:]
        else:
            return None
    else:
        headers = data_lines[0][1]
        rest_rows = data_lines[1:]

    rows = [cells for _, cells in rest_rows]
    return headers, rows


def _truncate(s: str, width: int) -> str:
    """Truncate string to width with ellipsis."""
    if len(s) <= width:
        return s
    return s[: width - 1] + "\u2026" if width > 1 else s[:width]


def render_compact_table(
    headers: List[str],
    rows: List[List[str]],
    max_width: int = TELEGRAM_CODE_BLOCK_WIDTH,
) -> str:
    """
    Render a table in the most compact format that fits *max_width*.

    1. Try a slim horizontal table (no borders, thin \u2500 header underline).
    2. If too wide even with truncation, fall back to card format.
    """
    num_cols = len(headers)
    if not rows:
        return "  ".join(headers)

    # --- Attempt: horizontal table ---
    if num_cols >= 2:
        col_w = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < num_cols:
                    col_w[i] = max(col_w[i], len(cell))

        gap = 1
        total = sum(col_w) + (num_cols - 1) * gap

        if total <= max_width:
            sep = " " * gap
            out = []
            out.append(
                sep.join(h.ljust(col_w[i]) for i, h in enumerate(headers)).rstrip()
            )
            out.append(sep.join("\u2500" * col_w[i] for i in range(num_cols)))
            for row in rows:
                parts = [
                    (row[i] if i < len(row) else "").ljust(col_w[i])
                    for i in range(num_cols)
                ]
                out.append(sep.join(parts).rstrip())
            return "\n".join(out)

        # Try proportional truncation
        avail = max_width - (num_cols - 1) * gap
        min_col = 4
        # Minimum useful column width -- below this, truncation destroys readability
        min_useful = 8
        if avail >= num_cols * min_col:
            total_natural = max(sum(col_w), 1)
            tw = [max(min_col, int(w / total_natural * avail)) for w in col_w]
            while sum(tw) + (num_cols - 1) * gap > max_width:
                tw[tw.index(max(tw))] -= 1

            # If too many columns are squeezed below useful width, skip to card
            cramped = sum(
                1 for i, w in enumerate(tw) if w < min_useful and col_w[i] > w
            )
            if cramped <= 1:
                sep = " " * gap
                out = []
                out.append(
                    sep.join(
                        _truncate(h, tw[i]).ljust(tw[i]) for i, h in enumerate(headers)
                    ).rstrip()
                )
                out.append(sep.join("\u2500" * tw[i] for i in range(num_cols)))
                for row in rows:
                    parts = [
                        _truncate(row[i] if i < len(row) else "", tw[i]).ljust(tw[i])
                        for i in range(num_cols)
                    ]
                    out.append(sep.join(parts).rstrip())

                result = "\n".join(out)
                if max(len(line) for line in result.split("\n")) <= max_width:
                    return result

    # --- Fallback: card format ---
    cards = []
    for row in rows:
        card_lines = []
        for i, cell in enumerate(row):
            if i >= len(headers):
                break
            if i == 0:
                card_lines.append(_truncate(cell, max_width))
            else:
                prefix = f"  {headers[i]}: "
                budget = max_width - len(prefix)
                if budget < 4:
                    card_lines.append(_truncate(f"  {headers[i]}: {cell}", max_width))
                else:
                    card_lines.append(f"{prefix}{_truncate(cell, budget)}")
        cards.append("\n".join(card_lines))

    return "\n\n".join(cards)


def _reformat_code_block(text: str, max_width: int = TELEGRAM_CODE_BLOCK_WIDTH) -> str:
    """
    If a code block contains a wide table, reformat it to fit max_width.
    Non-table code blocks are returned unchanged.
    """
    lines = text.split("\n")
    max_line = max((len(line) for line in lines), default=0)
    if max_line <= max_width:
        return text

    has_box = any(c in _BOX_ALL for c in text)
    pipe_lines = sum(1 for line in lines if "|" in line and line.count("|") >= 2)

    if has_box or pipe_lines >= 2:
        parsed = _parse_table_text(text)
        if parsed:
            headers, rows = parsed
            if rows:
                return render_compact_table(headers, rows, max_width)

    return text


def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, Any]], str]:
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

    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[List[str]] = None

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

            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            current_key = key

            # Handle inline lists like [item1, item2]
            if val.startswith("[") and val.endswith("]"):
                items = val[1:-1].split(",")
                result[key] = [i.strip().strip("'\"") for i in items if i.strip()]
            elif val:
                # Strip quotes
                result[key] = val.strip("'\"")
            else:
                result[key] = None  # Key with no value (list follows)

    return result, body


def format_frontmatter_summary(frontmatter: Dict[str, Any]) -> str:
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
    line1_parts: List[str] = []
    if frontmatter.get("type"):
        line1_parts.append(f"[{frontmatter['type']}]")
    if frontmatter.get("status"):
        line1_parts.append(f"\u2022 {frontmatter['status']}")

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
        parts.append(f"\u21a9\ufe0f {url}")

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

    # Detect and convert markdown tables using compact renderer
    def convert_table(match):
        try:
            parsed = _parse_table_text(match.group(0))
            if parsed:
                headers, data = parsed
                compact = render_compact_table(headers, data)
                code_blocks.append(compact)
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

        from src.core.config import get_config_value

        note_name = match.group(1)
        display_name = note_name.lstrip("@")
        encoded_name = urllib.parse.quote(display_name, safe="")
        bot_username = get_config_value("bot.bot_username", "toolbuildingape_bot")
        deep_link = f"https://t.me/{bot_username}?start=note_{encoded_name}"
        return f'<a href="{deep_link}">\U0001f4c4 {display_name}</a>'

    text = re.sub(r"\[\[([^\]]+)\]\]", format_wikilink, text)

    # Restore code blocks (reformat wide tables to fit mobile)
    for i, block in enumerate(code_blocks):
        block = _reformat_code_block(block)
        text = text.replace(f"{placeholder}{i}{placeholder}", f"<pre>{block}</pre>")

    # Prepend frontmatter summary if present
    if frontmatter_summary:
        text = frontmatter_summary + text

    return text


def validate_telegram_html(text: str) -> tuple:
    """
    Check whether *text* is valid Telegram HTML (balanced, properly nested tags).

    Telegram supports only a small subset of HTML tags:
    ``b``, ``i``, ``u``, ``s``, ``a``, ``code``, ``pre``, ``tg-spoiler``.

    Returns:
        (True, "")           -- HTML is well-formed
        (False, error_msg)   -- HTML is malformed, with a human-readable reason
    """
    ALLOWED_TAGS = {"b", "i", "u", "s", "a", "code", "pre", "tg-spoiler"}
    stack = []
    # Match opening/closing HTML tags (ignore self-closing / unknown tags)
    for match in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^>]*)?>", text):
        is_closing = match.group(1) == "/"
        tag_name = match.group(2).lower()
        if tag_name not in ALLOWED_TAGS:
            continue
        if not is_closing:
            stack.append(tag_name)
        else:
            if not stack:
                return False, f"Unexpected closing tag </{tag_name}>"
            if stack[-1] != tag_name:
                return (
                    False,
                    f"Mismatched tags: expected </{stack[-1]}>, got </{tag_name}>",
                )
            stack.pop()
    if stack:
        return False, f"Unclosed tags: {stack}"
    return True, ""


def strip_telegram_html(text: str) -> str:
    """
    Strip all Telegram HTML tags and unescape HTML entities.

    Used as a plain-text fallback when Telegram rejects a message due to
    malformed HTML.
    """
    # Remove all HTML tags
    stripped = re.sub(r"<[^>]+>", "", text)
    # Unescape HTML entities
    stripped = (
        stripped.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return stripped


def split_message_html_safe(text: str, max_size: int = 3800) -> List[str]:
    """
    Split *text* into Telegram-sendable chunks without ever breaking inside a
    ``<pre>`` block.

    The standard :func:`split_message` splits on ``\\n\\n`` boundaries which
    can land inside a ``<pre>...</pre>`` block, producing an unclosed tag that
    Telegram rejects with *"Can't find end tag corresponding to start tag pre"*.

    Strategy
    --------
    1. Tokenise the text into alternating **text segments** and **<pre> blocks**.
    2. Greedily pack tokens into chunks up to *max_size*.
    3. Text segments that overflow are sub-split with the original
       :func:`split_message` logic.
    4. A single ``<pre>`` block that on its own exceeds *max_size* is
       **truncated** (with a ``[... truncated ...]`` notice) rather than split,
       so every chunk still has balanced tags.
    """
    if len(text) <= max_size:
        return [text]

    # Split into alternating [text, <pre>...</pre>, text, ...] segments.
    # re.split with a capturing group keeps the matched delimiter in the list.
    segments = re.split(r"(<pre>.*?</pre>)", text, flags=re.DOTALL)

    chunks: List[str] = []
    current: str = ""

    for segment in segments:
        if not segment:
            continue

        is_pre = segment.startswith("<pre>")

        if len(current) + len(segment) <= max_size:
            # Fits in the current chunk -- just append.
            current += segment
            continue

        # Doesn't fit.
        if is_pre:
            if len(segment) <= max_size:
                # The block fits alone -- flush current chunk first.
                if current:
                    chunks.append(current)
                    current = ""
                current = segment
            else:
                # Block is too large even on its own -- truncate it.
                if current:
                    chunks.append(current)
                    current = ""
                inner = segment[5:-6]  # strip <pre> and </pre>
                keep = max_size - len("<pre>[... truncated ...]</pre>")
                truncated = f"<pre>{inner[:keep]}[... truncated ...]</pre>"
                chunks.append(truncated)
                current = ""
        else:
            # Plain text segment -- flush current chunk, then sub-split.
            if current:
                chunks.append(current)
                current = ""
            sub = split_message(segment, max_size)
            for piece in sub[:-1]:
                chunks.append(piece)
            current = sub[-1] if sub else ""

    if current:
        chunks.append(current)

    return chunks or [""]


# Aliases for backwards compatibility
_escape_html = escape_html
_split_message = split_message
_markdown_to_telegram_html = markdown_to_telegram_html
