# Claude Session CWD Issue - Analysis & Solutions

## Problem Summary

When a Claude Code session is created in one working directory and later resumed from a different directory, the session cannot be found, causing the error:

```
No conversation found with session ID: 558a260f-89dd-4aa9-a817-f951bbbff7f2
```

## Root Cause

Claude Code SDK stores session data in **project-specific directories** based on the `cwd` parameter:

```
~/.claude/projects/-Users-server-ai-projects-telegram-agent/
~/.claude/projects/-Users-server-Research-vault/
```

Each session's conversation history (`.jsonl` file) is stored in the directory corresponding to its creation CWD. When you try to resume a session with a different CWD, the SDK cannot find the session file.

### Example Timeline

1. **17:45:49** - Session `558a260f` created with `cwd=/Users/server/ai_projects/telegram_agent`
   - Session file created: `~/.claude/projects/-Users-server-ai-projects-telegram-agent/558a260f-89dd-4aa9-a817-f951bbbff7f2.jsonl`
2. **17:47:47** - Resume attempted with `cwd=/Users/server/Research/vault`
   - SDK looks in: `~/.claude/projects/-Users-server-Research-vault/`
   - Session not found → Error
3. **17:48:13** - Retry with correct `cwd=/Users/server/ai_projects/telegram_agent`
   - Session found → Success

## Current Database Schema

The `claude_sessions` table does NOT store the CWD:

```sql
CREATE TABLE claude_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    name VARCHAR(255),
    is_active BOOLEAN NOT NULL,
    last_prompt TEXT,
    last_used DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
);
```

## Solution Options

### Option 1: Store CWD in Database ⭐ RECOMMENDED

**Pros:**
- Proper tracking of session metadata
- Enables session migration/recovery
- Future-proof for multi-project support

**Cons:**
- Requires database migration
- Slightly more complex

**Implementation:**
1. Add `cwd` column to `claude_sessions` table
2. Store CWD when saving session
3. Retrieve CWD when resuming session
4. Validate CWD before resume

### Option 2: Search Multiple Directories

**Pros:**
- No database changes needed
- Works with existing sessions
- Handles sessions created before fix

**Cons:**
- Slower (multiple directory checks)
- Doesn't prevent the underlying issue
- May find wrong session if IDs collide across projects

**Implementation:**
1. When session not found in expected directory
2. Search known project directories for session file
3. If found, use that directory for resume
4. Optionally update database with discovered CWD

### Option 3: Always Use Single CWD

**Pros:**
- Simplest implementation
- No database changes
- Guaranteed session availability

**Cons:**
- Loses context-aware working directory
- May confuse Claude about file locations
- Not flexible for multi-project use

**Implementation:**
1. Remove `cwd` parameter from all calls
2. Always use `/Users/server/ai_projects/telegram_agent`
3. Sessions work everywhere but lose project context

### Option 4: Hybrid Approach ⭐⭐ BEST SOLUTION

Combine Option 1 and Option 2:

1. **Add CWD to database** (Option 1)
2. **Fallback search** for legacy sessions (Option 2)
3. **Migrate found sessions** to database

**Benefits:**
- Handles existing sessions gracefully
- Proper tracking going forward
- Self-healing for legacy data

## Recommended Implementation

### Phase 1: Database Migration

```python
# Migration script
async def add_cwd_column():
    async with get_db_session() as session:
        await session.execute(text("""
            ALTER TABLE claude_sessions
            ADD COLUMN cwd VARCHAR(512) DEFAULT '/Users/server/ai_projects/telegram_agent'
        """))
        await session.commit()
```

### Phase 2: Session Discovery Helper

```python
def find_session_file(session_id: str) -> Optional[str]:
    """Search for session file across known project directories.

    Returns the CWD where the session was found, or None.
    """
    from pathlib import Path

    known_projects = [
        "-Users-server-ai-projects-telegram-agent",
        "-Users-server-Research-vault",
        "-Users-server-Research-vault-Research-daily",
    ]

    claude_dir = Path.home() / ".claude" / "projects"

    for project in known_projects:
        session_file = claude_dir / project / f"{session_id}.jsonl"
        if session_file.exists():
            # Convert project directory name back to actual path
            # "-Users-server-ai-projects-telegram-agent" -> "/Users/server/ai_projects/telegram_agent"
            cwd = "/" + project.lstrip("-").replace("-", "/")
            logger.info(f"Found session {session_id[:8]} in project {cwd}")
            return cwd

    return None
```

### Phase 3: Update Save/Resume Logic

```python
async def _save_session(
    self,
    chat_id: int,
    user_id: int,
    session_id: str,
    last_prompt: str,
    cwd: str,  # NEW parameter
):
    """Save session with CWD."""
    # ... existing code ...
    stmt = text("""
        INSERT INTO claude_sessions
        (user_id, chat_id, session_id, last_prompt, is_active, cwd, last_used)
        VALUES (:user_id, :chat_id, :session_id, :last_prompt, 1, :cwd, :last_used)
        ON CONFLICT (session_id) DO UPDATE SET
            last_prompt = :last_prompt,
            last_used = :last_used,
            cwd = :cwd
    """)
    # ...

async def get_session_cwd(self, session_id: str) -> Optional[str]:
    """Get CWD for a session, with fallback search."""
    # Try database first
    async with get_db_session() as session:
        result = await session.execute(
            text("SELECT cwd FROM claude_sessions WHERE session_id = :sid"),
            {"sid": session_id}
        )
        row = result.first()
        if row and row[0]:
            return row[0]

    # Fallback: search filesystem
    discovered_cwd = find_session_file(session_id)
    if discovered_cwd:
        logger.info(f"Discovered session CWD via filesystem search: {discovered_cwd}")
        # Update database for future use
        async with get_db_session() as session:
            await session.execute(
                text("UPDATE claude_sessions SET cwd = :cwd WHERE session_id = :sid"),
                {"cwd": discovered_cwd, "sid": session_id}
            )
            await session.commit()
        return discovered_cwd

    return None
```

## Testing Plan

1. **Test session creation**: Verify CWD is stored
2. **Test session resume**: Verify correct CWD is used
3. **Test legacy sessions**: Verify fallback search works
4. **Test cross-directory resume**: Ensure proper error handling
5. **Test migration**: Verify existing sessions get CWD populated

## Migration Strategy

1. Deploy database migration (add `cwd` column with default)
2. Deploy code with hybrid approach
3. Monitor logs for "Discovered session CWD" messages
4. Verify all active sessions have CWD populated
5. (Optional) Remove fallback search after migration complete

## Files to Modify

1. `src/models/claude_session.py` - Add `cwd` field to model
2. `src/services/claude_code_service.py` - Update save/resume logic
3. `src/services/claude_subprocess.py` - Add session discovery helper
4. `alembic/versions/xxx_add_session_cwd.py` - Migration script
5. `tests/test_services/test_claude_code_service.py` - Add tests

## Estimated Impact

- **Development time**: 2-3 hours
- **Risk level**: Low (backwards compatible)
- **User impact**: Eliminates session resume errors
- **Performance impact**: Negligible (one extra DB column)
