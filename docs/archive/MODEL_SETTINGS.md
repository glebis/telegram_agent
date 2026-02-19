# Model Selection Settings Feature

## Overview
Added two new settings to control Claude model selection behavior:
1. **Show Model Buttons** - Toggle display of model selection buttons in completion keyboards (default: OFF)
2. **Default Model** - Choose default Claude model (haiku/sonnet/opus, default: sonnet)

## Changes

### Database Schema
- Added `show_model_buttons` column to `chats` table (Boolean, default: False)
- Existing `claude_model` column already present for storing default model preference

### Settings UI
- `/settings` command now displays both new settings
- New toggle button: "Model Buttons: ON/OFF"
- New cycle button: "Default Model: ⚡ Haiku / 🎵 Sonnet / 🎭 Opus"

### Keyboard Behavior
- Model selection buttons in completion keyboard now only appear when `show_model_buttons` is enabled
- When disabled (default), completion keyboard shows only:
  - Retry, More, New buttons
  - Lock/Unlock button
  - Voice continuation (if available)
  - Note view buttons (if applicable)

### Callback Handlers
Added two new callback actions in `settings:*` namespace:
- `settings:toggle_model_buttons` - Toggle model buttons display
- `settings:cycle_default_model` - Cycle through haiku → sonnet → opus

### Files Modified

1. **src/models/chat.py**
   - Added `show_model_buttons` field

2. **src/bot/keyboard_utils.py**
   - Updated `create_settings_keyboard()` with new parameters
   - Updated `create_claude_complete_keyboard()` to conditionally show model buttons

3. **src/bot/handlers/core_commands.py**
   - Updated `settings_command()` to fetch and display new settings

4. **src/bot/callback_handlers.py**
   - Refactored `handle_settings_callback()` with helper functions
   - Added handlers for `toggle_model_buttons` and `cycle_default_model`
   - Updated all settings display logic to use new helper function
   - Updated Claude model selection callback to respect show_model_buttons

5. **src/bot/handlers/claude_commands.py**
   - Updated `execute_claude_prompt()` to fetch show_model_buttons setting
   - Pass setting to completion keyboard creation

## Migration

The database migration happens automatically via SQLAlchemy's `create_all()` when the bot starts.

For manual migration (optional):
```bash
python3 scripts/migrate_add_model_buttons.py
```

## Usage

1. Open `/settings` in the bot
2. Tap "Model Buttons: OFF" to enable model selection buttons
3. Tap "Default Model: 🎵 Sonnet" to cycle through models
4. Model buttons will now appear in Claude completion keyboards

## Default Behavior

By default (for all existing and new users):
- Model buttons are hidden (cleaner interface)
- Default model is Sonnet (balanced performance)
- Users can enable model buttons if they frequently switch models
