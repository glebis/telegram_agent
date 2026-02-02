"""
Bot command handlers package.

This package contains all Telegram bot command handlers, organized by functionality:
- base.py: Core utilities (Telegram API helpers, user/chat init, caches)
- formatting.py: Text formatting (HTML escaping, markdown conversion)
- core_commands.py: Basic commands (/start, /help, /menu, /settings, /gallery)
- mode_commands.py: Mode management (/mode, aliases)
- note_commands.py: Note viewing (/note)
- collect_commands.py: Batch input (/collect:*)
- claude_commands.py: Claude Code integration (/claude:*)

All handlers are re-exported here for backwards compatibility.
"""

# Base utilities
from .base import (
    initialize_user_chat,
    send_message_sync,
    edit_message_sync,
    get_claude_mode,
    set_claude_mode,
    init_claude_mode_cache,
    _claude_mode_cache,
    _run_telegram_api_sync,
)

# Formatting utilities
from .formatting import (
    escape_html,
    markdown_to_telegram_html,
    split_message,
)

# Core commands
from .core_commands import (
    start_command,
    help_command,
    menu_command,
    settings_command,
    gallery_command,
)

# Mode commands
from .mode_commands import (
    mode_command,
    show_mode_help,
    analyze_command,
    coach_command,
    creative_command,
    quick_command,
    formal_command,
    tags_command,
    coco_command,
)

# Note commands
from .note_commands import (
    note_command,
    view_note_command,
)

# Collect commands
from .collect_commands import (
    collect_command,
    _collect_start,
    _collect_stop,
    _collect_go,
    _collect_status,
    _collect_clear,
    _collect_exit,
    _collect_help,
)

# Claude commands
from .claude_commands import (
    claude_command,
    meta_command,
    execute_claude_prompt,
    _claude_new,
    _claude_sessions,
    _claude_lock,
    _claude_unlock,
    _claude_reset,
    _claude_help,
)

# Research commands
from .research_commands import (
    research_command,
    execute_research_prompt,
)

# Voice settings commands
from .voice_settings_commands import (
    voice_settings_command,
    handle_voice_settings_callback,
)

__all__ = [
    # Base
    "initialize_user_chat",
    "send_message_sync",
    "edit_message_sync",
    "get_claude_mode",
    "set_claude_mode",
    "init_claude_mode_cache",
    "_claude_mode_cache",
    "_run_telegram_api_sync",
    # Formatting
    "escape_html",
    "markdown_to_telegram_html",
    "split_message",
    # Core commands
    "start_command",
    "help_command",
    "menu_command",
    "settings_command",
    "gallery_command",
    # Mode commands
    "mode_command",
    "show_mode_help",
    "analyze_command",
    "coach_command",
    "creative_command",
    "quick_command",
    "formal_command",
    "tags_command",
    "coco_command",
    # Note commands
    "note_command",
    "view_note_command",
    # Collect commands
    "collect_command",
    "_collect_start",
    "_collect_stop",
    "_collect_go",
    "_collect_status",
    "_collect_clear",
    "_collect_exit",
    "_collect_help",
    # Claude commands
    "claude_command",
    "meta_command",
    "execute_claude_prompt",
    "_claude_new",
    "_claude_sessions",
    "_claude_lock",
    "_claude_unlock",
    "_claude_reset",
    "_claude_help",
    # Research commands
    "research_command",
    "execute_research_prompt",
    # Voice settings commands
    "voice_settings_command",
    "handle_voice_settings_callback",
]
