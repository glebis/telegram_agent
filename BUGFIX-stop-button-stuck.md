# Bug: Stop Button Stuck After Task Completion

## Issue
The Stop button remains visible and doesn't get replaced with the completion keyboard after Claude Code finishes a task.

## Root Cause
`BUTTON_DATA_INVALID` error from Telegram API when trying to edit the message with the completion keyboard.

### Error in Logs
```
2026-01-09 12:56:13,215 - src.bot.handlers.base - WARNING - _run_telegram_api_sync:91 - Telegram API editMessageText failed: {'ok': False, 'error_code': 400, 'description': 'Bad Request: BUTTON_DATA_INVALID'}
```

## Analysis

### Telegram's Callback Data Limit
Telegram has a **64-byte limit** for `callback_data` in inline keyboard buttons.

### Current Implementation
File: `src/bot/keyboard_utils.py`, lines 500-513

The code creates callback data using the full vault-relative path:
```python
callback_data = f"note:view:{note_path}"
```

### Examples of Problematic Paths
1. `note:view:ai-research/20260109-anthropic-claude-coding-plan-controversy.md` = **75 bytes** ❌
2. `note:view:ai-research/20260109-linkedin-jobs-rise-2026-relevant-roles.md` = **73 bytes** ❌

Both exceed the 64-byte limit, causing `BUTTON_DATA_INVALID`.

## Impact
- When vault notes are created with long filenames (especially dated research files)
- The completion keyboard fails to render
- The Stop button from the "in-progress" state remains visible
- User sees outdated UI state after task completion

## Affected Code Locations

### 1. Keyboard Creation
**File:** `src/bot/keyboard_utils.py:488-513`
- `create_claude_complete_keyboard()` method
- Creates note view buttons with `callback_data = f"note:view:{note_path}"`

### 2. Message Editing
**File:** `src/bot/handlers/claude_commands.py:798-804`
- `execute_claude_prompt()` function
- Tries to edit message with completion keyboard
- Fails silently when callback_data is invalid

### 3. Callback Handler
**File:** `src/bot/callback_handlers.py:1515-1524`
- Handles `note:view:*` callbacks
- Expects full path in callback data

## Solution Options

### Option 1: Hash-based Mapping (Recommended)
Store a mapping of short hashes to full paths and use hash in callback_data.

**Pros:**
- Works for paths of any length
- Maintains backward compatibility
- Secure (hashes don't reveal structure)

**Cons:**
- Requires state management (cache/database)
- Need to handle hash collisions
- Need to clean up old mappings

**Implementation:**
```python
# In keyboard_utils.py
def _create_note_hash(note_path: str, chat_id: int) -> str:
    """Create short hash for note path."""
    import hashlib
    data = f"{chat_id}:{note_path}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]

# Store mapping in cache/database
note_hash = _create_note_hash(note_path, chat_id)
store_note_mapping(chat_id, note_hash, note_path)
callback_data = f"note:view:{note_hash}"
```

### Option 2: Truncate Path with Database Lookup
Store full paths in database, use shortened identifier.

**Pros:**
- Reliable for all path lengths
- Can track note view analytics

**Cons:**
- Database overhead
- More complex implementation

### Option 3: URL-safe Encoding + Abbreviation
Compress path using intelligent abbreviation.

**Example:**
```python
def abbreviate_path(path: str) -> str:
    """Abbreviate vault path for callback data."""
    # ai-research/20260109-anthropic... -> ai-r/260109-anthr...
    parts = path.split('/')
    folder = parts[0][:4] if len(parts) > 1 else ""
    filename = parts[-1] if len(parts) > 1 else parts[0]

    # Remove date prefix, take first 20 chars
    if filename.startswith('202'):
        filename = filename[9:]  # Skip YYYYMMDD-

    abbreviated = f"{folder}/{filename[:20]}" if folder else filename[:25]
    return abbreviated
```

**Pros:**
- Stateless
- Simple implementation

**Cons:**
- May have collisions
- Not guaranteed to fit in 64 bytes
- Loses exact path information

### Option 4: Sequential Note IDs (Best for MVP)
Use sequential IDs for notes in current session.

**Implementation:**
```python
# In execute_claude_prompt, before creating keyboard
note_ids = {}
for idx, note_path in enumerate(vault_notes):
    note_id = f"{session_id[:8]}-{idx}"  # e.g., "4810f84d-0"
    note_ids[note_id] = note_path
    store_temp_mapping(chat_id, note_id, note_path, ttl=3600)

# In keyboard creation
callback_data = f"note:view:{note_id}"  # e.g., "note:view:4810f84d-0"
```

**Callback data:** `note:view:4810f84d-0` = **22 bytes** ✅

**Pros:**
- Simple and reliable
- Always fits in 64 bytes
- Session-scoped (auto cleanup)
- Easy to debug

**Cons:**
- Requires temporary storage
- IDs expire after session

## Recommended Fix

**Use Option 4 (Sequential Note IDs)** for immediate fix:

1. Store note ID → path mapping when creating keyboard
2. Use short session-scoped IDs in callback_data
3. Look up path when handling callback
4. Auto-expire mappings after 1 hour

### Changes Required

**File 1:** `src/bot/handlers/claude_commands.py`
```python
# Before line 782 (creating keyboard)
note_id_map = {}
if vault_notes:
    for idx, note_path in enumerate(vault_notes):
        note_id = f"{session_id[:8]}-{idx}"
        note_id_map[note_id] = note_path
        # Store in cache/temp storage with 1hr TTL
        await cache.set(f"note:{chat_id}:{note_id}", note_path, ttl=3600)

# Pass note_ids instead of note_paths
complete_keyboard = keyboard_utils.create_claude_complete_keyboard(
    is_locked=is_locked,
    current_model=selected_model,
    voice_url=voice_url,
    note_ids=note_id_map.keys(),  # Changed from note_paths
)
```

**File 2:** `src/bot/keyboard_utils.py`
```python
# Update signature at line 491
def create_claude_complete_keyboard(
    self, has_session: bool = True, is_locked: bool = False,
    current_model: str = "sonnet", session_id: Optional[str] = None,
    voice_url: Optional[str] = None,
    note_ids: Optional[List[str]] = None  # Changed from note_paths
) -> InlineKeyboardMarkup:
    """Create keyboard shown after Claude Code completion.

    Args:
        note_ids: List of short note IDs (not full paths)
    """
    # Lines 501-513
    if note_ids:
        for note_id in note_ids[:3]:
            # Get display name from note_id
            # For now, just use the note_id as button text
            # Or fetch from cache to get filename
            callback_data = f"note:view:{note_id}"  # Always <64 bytes
            buttons.append([
                InlineKeyboardButton(f"👁 Note {note_id[-1]}", callback_data=callback_data)
            ])
```

**File 3:** `src/bot/callback_handlers.py`
```python
# Update handler at line 1515
if action == "view":
    note_id = ":".join(params[1:])
    logger.info(f"Note view callback: {note_id}")

    # Look up full path from cache
    cache_key = f"note:{chat_id}:{note_id}"
    relative_path = await cache.get(cache_key)

    if not relative_path:
        await query.message.reply_text("Note not found (session expired)")
        return

    # Continue with existing path validation and reading logic...
```

## Testing

After implementing fix:

1. Create a file with a long name:
   ```bash
   echo "test" > ai-research/20260109-very-long-filename-that-exceeds-limits.md
   ```

2. Reference it in Claude response

3. Verify callback_data length:
   ```python
   assert len(f"note:view:{note_id}") <= 64
   ```

4. Check that keyboard renders correctly

5. Verify note view button works

## Related Issues

- This affects any inline keyboard buttons that use dynamic data
- Consider auditing all callback_data usage for length limits
- May want to add validation middleware to catch this earlier

## Priority

**High** - Affects user experience on every Claude Code completion that creates vault notes.

## Files to Modify

1. `src/bot/handlers/claude_commands.py` - Add note ID mapping
2. `src/bot/keyboard_utils.py` - Use note IDs instead of paths
3. `src/bot/callback_handlers.py` - Look up path from note ID
4. `src/core/cache.py` (or similar) - Add temp storage for mappings

## Estimated Effort

- **Development:** 2-3 hours
- **Testing:** 1 hour
- **Total:** 3-4 hours
