"""
Text formatting utilities for Telegram messages.

This module re-exports all formatting helpers from ``src.utils.formatting``,
which is the canonical location.  Kept here for backward compatibility so
existing ``from .formatting import ...`` imports in the bot layer continue
to work unchanged.
"""

from src.utils.formatting import (  # noqa: F401
    TELEGRAM_CODE_BLOCK_WIDTH,
    _escape_html,
    _markdown_to_telegram_html,
    _parse_table_text,
    _reformat_code_block,
    _split_message,
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
