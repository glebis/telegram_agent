# Claude Timeout Fixes - Implementation Summary

## Overview
Fixed critical issues with Claude Code session timeout handling that prevented proper session resumption after timeouts.

## Problem Analysis
The original issue occurred when a Claude session timed out:
1. **Pending session not cleaned up**: When subprocess was killed at timeout, the pending session flag was never cleared, causing subsequent messages to wait 30s unnecessarily
2. **Force-killed session loses context**: `process.kill()` used SIGKILL, interrupting mid-tool-use and causing context loss
3. **No timeout notification context**: Resume prompts had no indication that previous session timed out

## Changes Made

### 1. Configurable Timeout (30 min default)
**File**: `src/core/config.py`
- Added `claude_session_timeout_seconds: int = 1800` (30 minutes)

**File**: `src/services/claude_subprocess.py`
- Changed from hardcoded 600s (10 min) to configurable timeout via `get_session_timeout()`
- Function loads from settings with fallback to 1800s

### 2. Pending Session Cleanup on Timeout
**File**: `src/services/claude_code_service.py`
- Added `_timeout_sessions: Dict[int, Dict[str, Any]]` to track timed-out sessions
- Added cleanup callback parameter to `execute_claude_subprocess()`
- Added cleanup in `finally` block of `execute_prompt()` to ensure pending sessions are cleared
- Fixed `wait_for_pending_session()` to clean up state on timeout (lines 291-302)

**File**: `src/services/claude_subprocess.py`
- Added `cleanup_callback` parameter to `execute_claude_subprocess()`
- Calls cleanup callback in all timeout/error paths

### 3. Graceful Shutdown with SIGTERM before SIGKILL
**File**: `src/services/claude_subprocess.py`
- Added `_graceful_shutdown()` helper function (lines 17-46)
- Tries `terminate()` (SIGTERM) first, waits 5s for graceful exit
- Falls back to `kill()` (SIGKILL) only if graceful exit times out
- Updated all timeout handlers to use `_graceful_shutdown()`

### 4. Timeout Context in Resume Prompts
**File**: `src/services/claude_code_service.py`
- Tracks timeout info in `_timeout_sessions` dict (session_id, last_prompt, timeout_at)
- On resume, checks if resuming timed-out session and prepends context:
  ```
  [CONTEXT: The previous session timed out N minutes ago
  while working on: 'original prompt'. The user is now continuing.]
  ```
- Clears timeout state on successful completion (line 461)

## Tests Added
**File**: `tests/test_services/test_claude_timeout_fixes.py` (NEW - 12 tests, all passing)

### TestPendingSessionCleanup (3 tests)
- `test_timeout_cleans_up_pending_session` - Verifies pending session cleanup on timeout error
- `test_subprocess_cleanup_cancels_pending_session` - Verifies cleanup callback integration
- `test_wait_for_pending_clears_state_after_timeout` - Verifies wait timeout cleanup

### TestConfigurableTimeout (3 tests)
- `test_timeout_loaded_from_settings` - Verifies config has 1800s default
- `test_custom_timeout_used_in_subprocess` - Verifies subprocess uses config value
- `test_per_message_timeout_separate_from_session_timeout` - Verifies 300s vs 1800s separation

### TestTimeoutContext (2 tests)
- `test_timeout_info_stored_in_session_metadata` - Verifies timeout tracking
- `test_resume_prompt_includes_timeout_context` - Verifies context prepending

### TestGracefulShutdown (2 tests)
- `test_subprocess_uses_terminate_before_kill` - Verifies SIGTERM before SIGKILL
- `test_timeout_uses_graceful_shutdown` - Verifies timeout handler uses graceful shutdown

### TestTimeoutIntegration (2 tests)
- `test_full_timeout_flow_with_cleanup` - End-to-end timeout flow
- `test_resume_after_timeout_has_context` - Verifies resume context works

## Tests Updated
**File**: `tests/test_services/test_claude_subprocess.py` (2 tests updated)
- `test_execute_timeout_handling` - Changed from `kill()` to `terminate()` assertion
- `test_execute_stop_check` - Changed from `kill()` to `terminate()` assertion

## Test Results
```
91 tests passed (17 services, 62 subprocess, 12 timeout fixes)
0 tests failed
```

## Key Benefits
1. **Better user experience**: Sessions resume with context after timeout instead of appearing like new sessions
2. **No more stuck pending sessions**: Timeout properly cleans up state, preventing 30s waits on next message
3. **Graceful shutdown**: Gives Claude SDK chance to save state before force-kill
4. **Configurable timeout**: Easy to adjust for different deployment scenarios (default 30 min)
5. **Full test coverage**: Comprehensive tests ensure timeout behavior works correctly

## Files Changed
- `src/core/config.py` (+1 line)
- `src/services/claude_subprocess.py` (+76 lines, ~35 modified)
- `src/services/claude_code_service.py` (+44 lines, ~15 modified)
- `tests/test_services/test_claude_timeout_fixes.py` (+370 lines, NEW)
- `tests/test_services/test_claude_subprocess.py` (~8 lines modified)

## Backward Compatibility
✅ All changes are backward compatible:
- Config has sensible default (30 min)
- Cleanup callback is optional parameter
- Timeout context only added when resuming timed-out session
- Graceful shutdown is internal implementation detail

## Performance Impact
- Minimal: Graceful shutdown adds 5s timeout before force-kill (only on timeout/error)
- Cleanup callback execution: negligible (~1ms)
- Timeout context string prepending: negligible (~1ms)

## Deployment Notes
1. No migration needed - timeout setting has default value
2. To customize timeout, set `CLAUDE_SESSION_TIMEOUT_SECONDS` env var or in config
3. All existing tests continue to pass
4. New tests validate timeout behavior

## Related Issues
- Fixes: Session timeout behavior not cleaning up pending state
- Fixes: "go on" after timeout creating new session instead of resuming
- Fixes: No context provided to Claude when resuming after timeout
