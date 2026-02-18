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

# Accountability commands
from .accountability_commands import (
    handle_track_callback,
    register_accountability_handlers,
    streak_command,
    track_command,
)

# Base utilities
from .base import (
    _claude_mode_cache,
    _run_telegram_api_sync,
    edit_message_sync,
    get_claude_mode,
    init_claude_mode_cache,
    initialize_user_chat,
    send_message_sync,
    set_claude_mode,
)

# Claude commands
from .claude_commands import (
    _claude_help,
    _claude_lock,
    _claude_new,
    _claude_reset,
    _claude_sessions,
    _claude_unlock,
    claude_command,
    clean_command,
    execute_claude_prompt,
    meta_command,
)

# Collect commands
from .collect_commands import (
    _collect_clear,
    _collect_exit,
    _collect_go,
    _collect_help,
    _collect_start,
    _collect_status,
    _collect_stop,
    collect_command,
)

# Core commands
from .core_commands import (
    gallery_command,
    help_command,
    menu_command,
    settings_command,
    start_command,
)

# Formatting utilities
from .formatting import (
    escape_html,
    markdown_to_telegram_html,
    split_message,
)

# Heartbeat commands
from .heartbeat_commands import heartbeat_command

# Life weeks settings commands
from .life_weeks_settings import (
    STATE_AWAITING_CUSTOM_PATH,
    STATE_AWAITING_DOB,
    STATE_AWAITING_TIME,
    cancel_conversation,
    handle_custom_path_input,
    handle_dob_input,
    handle_life_weeks_callback,
    handle_time_input,
    life_weeks_settings_command,
)

# Memory commands
from .memory_commands import memory_command

# Mode commands
from .mode_commands import (
    analyze_command,
    coach_command,
    coco_command,
    creative_command,
    formal_command,
    mode_command,
    quick_command,
    show_mode_help,
    tags_command,
)

# Note commands
from .note_commands import (
    note_command,
    view_note_command,
)

# OpenCode commands
from .opencode_commands import opencode_command

# Research commands
from .research_commands import (
    execute_research_prompt,
    research_command,
)

# Save commands
from .save_commands import save_command

# Status commands
from .status_commands import status_command

# Task ledger commands
from .task_commands import (
    register_task_handlers,
    tasks_command,
)

# Voice settings commands
from .voice_settings_commands import (
    handle_tracker_name_message,
    handle_voice_settings_callback,
    partner_settings_command,
    voice_settings_command,
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
    "clean_command",
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
    "handle_tracker_name_message",
    "partner_settings_command",
    # Life weeks settings commands
    "life_weeks_settings_command",
    "handle_life_weeks_callback",
    "handle_dob_input",
    "handle_time_input",
    "handle_custom_path_input",
    "cancel_conversation",
    "STATE_AWAITING_DOB",
    "STATE_AWAITING_TIME",
    "STATE_AWAITING_CUSTOM_PATH",
    # Heartbeat commands
    "heartbeat_command",
    # Accountability commands
    "track_command",
    "streak_command",
    "handle_track_callback",
    "register_accountability_handlers",
    # Memory commands
    "memory_command",
    # OpenCode commands
    "opencode_command",
    # Task ledger commands
    "tasks_command",
    "register_task_handlers",
    # Save commands
    "save_command",
    # Status commands
    "status_command",
]
