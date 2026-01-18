# Fix: Claude Session CWD Conflict

## Problem

When a Claude Code session was created in one working directory (e.g., `telegram_agent`) and later resumed from a different directory (e.g., `vault`), the session could not be found:

```
Error: No conversation found with session ID: 558a260f-89dd-4aa9-a817-f951bbbff7f2
```

## Root Cause

Claude Code SDK stores session files in project-specific directories:
```
~/.claude/projects/-Users-server-ai-projects-telegram-agent/558a260f-....jsonl
~/.claude/projects/-Users-server-Research-vault/
```

When resuming with a different `cwd`, the SDK looks in the wrong directory.

## Solution Implemented

Added automatic session discovery in `src/services/claude_subprocess.py`:

### 1. New Function: `find_session_cwd()`

Searches all Claude project directories for a session file and returns its original CWD.

**Features:**
- Scans `~/.claude/projects/` for session files
- Maps Claude's encoded directory names back to actual paths
- Handles known projects: `telegram_agent`, `vault`, `vault/Research/daily`
- Fallback for unknown projects with warning

**Encoding Logic:**
```python
# Claude encodes paths by replacing "/" and "_" with "-"
/Users/server/ai_projects/telegram_agent
  → -Users-server-ai-projects-telegram-agent

# We decode using a project map for known paths
project_map = {
    "-Users-server-ai-projects-telegram-agent": "/Users/server/ai_projects/telegram_agent",
    "-Users-server-Research-vault": "/Users/server/Research/vault",
    ...
}
```

### 2. Auto-Correction in `execute_claude_subprocess()`

When resuming a session:
1. Search for the session's original CWD
2. If found and different from requested CWD, use the original
3. Log a warning about the CWD switch
4. Proceed with correct CWD

**Example Log:**
```
WARNING: Session 558a260f... was created in /Users/server/ai_projects/telegram_agent,
         but requested CWD is /Users/server/Research/vault.
         Using original CWD to ensure session can be found.
```

## Testing

```bash
# Test session discovery
python3 -c "
from src.services.claude_subprocess import find_session_cwd
cwd = find_session_cwd('558a260f-89dd-4aa9-a817-f951bbbff7f2')
print(f'Found: {cwd}')
"
```

**Expected output:**
```
INFO:...:Found session 558a260f... in project: /Users/server/ai_projects/telegram_agent
Found: /Users/server/ai_projects/telegram_agent
```

## Impact

### Before Fix
- ❌ Session resume fails with CWD mismatch
- ❌ User sees error message
- ❌ Requires manual `/claude:new` to start fresh

### After Fix
- ✅ Session automatically discovered
- ✅ CWD auto-corrected with warning
- ✅ Seamless session continuation
- ✅ No user intervention needed

## Future Enhancements

For a more robust solution, consider:

1. **Database Storage** (Phase 2)
   - Add `cwd` column to `claude_sessions` table
   - Store CWD when creating session
   - Retrieve CWD when resuming

2. **Migration Script** (Phase 2)
   - Scan all existing sessions in database
   - Populate CWD column using `find_session_cwd()`
   - Provide fallback for sessions not found

3. **Telemetry** (Optional)
   - Track CWD switching frequency
   - Identify common patterns
   - Optimize project mapping

See `docs/SESSION_CWD_ISSUE_ANALYSIS.md` for complete analysis.

## Deployment

```bash
# Restart bot to apply fix
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.bot.plist && \
launchctl load ~/Library/LaunchAgents/com.telegram-agent.bot.plist

# Verify
tail -20 logs/app.log
```

## Files Changed

- `src/services/claude_subprocess.py`
  - Added `find_session_cwd()` function
  - Modified `execute_claude_subprocess()` to use auto-discovery
  - Added project mapping for path decoding

## Commit Message

```
fix: auto-discover Claude session CWD to prevent resume errors

When resuming a Claude session from a different working directory,
the session file cannot be found. This adds automatic session
discovery that scans ~/.claude/projects/ and corrects the CWD
to match the session's original location.

- Add find_session_cwd() to search for sessions across projects
- Auto-correct CWD when resuming sessions
- Map Claude's encoded directory names to actual paths
- Log warnings when CWD is switched for transparency

Fixes: Session resume errors with "No conversation found" message
```

## Verification

After restart, test by:
1. Creating a session in `telegram_agent` directory
2. Attempting to resume from `vault` directory
3. Should see warning log and successful resume
4. No error message to user

Expected log:
```
WARNING: Session xxx... was created in /Users/server/ai_projects/telegram_agent,
         but requested CWD is /Users/server/Research/vault.
         Using original CWD to ensure session can be found.
INFO: Starting Claude subprocess with model=sonnet, cwd=/Users/server/ai_projects/telegram_agent, resuming=xxx...
INFO: Claude session initialized: xxx...
```
