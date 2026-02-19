# Telethon Video Integration - Implementation Summary

**Date**: 2026-02-11
**Status**: ✅ Implemented, Ready for Testing

---

## What Was Done

### 1. Created Telethon Service
**File**: `src/services/telethon_service.py`

- Singleton service following bot's `get_X_service()` pattern
- Reuses existing config from `~/.telegram_dl/` (transcribe-telegram-video skill)
- Lazy import of Telethon (no startup overhead)
- Async download with timeout and progress callback support

**Key Features:**
- Downloads videos up to 2GB (no 20MB Bot API limit)
- Auto-calculates timeout: 2s per MB + 120s buffer
- File verification after download
- Thread-safe with asyncio.Lock
- Proper error handling and logging

### 2. Modified Video Processing Pipeline
**File**: `src/bot/combined_processor.py`

**Changes:**
- Line 1179-1184: Initialize video_path early (shared by both downloaders)
- Line 1202-1263: Added Telethon fallback for files >20MB
- Line 1267-1282: Skip Bot API download if file already exists (from Telethon)

**Flow:**
```
1. Get file info from Bot API (check size)
2. IF size > 20MB:
   - Extract forward URL from message context
   - Download via Telethon MTProto
   - Show progress to user
3. ELSE (size ≤ 20MB OR size unknown):
   - Download via Bot API (faster for small files)
4. Extract audio → Transcribe → Process with Claude
```

### 3. Updated Dependencies
**File**: `requirements.txt`

Added: `telethon>=1.34.0  # MTProto client for downloading large files (>20MB)`

---

## Why This Approach

### Bot API Limitation (Not a Bug)
- Telegram Bot API: **20MB hard limit** (server-side enforcement)
- Cannot be bypassed with any HTTP tricks
- Official Telegram limitation, documented

### MTProto = Standard Solution
- **Telethon** and **Pyrogram** are the two standard MTProto clients
- Used by all serious media-processing bots
- Same protocol as Telegram Desktop/Mobile
- Supports up to 2GB files

### Architecture Decisions

**✅ Reuse existing config**
- User already has Telethon configured at `~/.telegram_dl/`
- No additional setup needed
- Works immediately

**✅ Hybrid approach (Bot API + Telethon)**
- Bot API for <20MB (faster, simpler)
- Telethon for ≥20MB (only when needed)
- Best of both worlds

**✅ Singleton service pattern**
- Matches bot's existing patterns (`get_X_service()`)
- Maintains persistent connection
- Thread-safe with locks

**✅ Subprocess isolation preserved**
- Bot API download: subprocess (existing)
- Telethon download: async service (new)
- No blocking in webhook handlers

---

## Configuration

Uses existing Telethon session from transcribe-telegram-video skill:

```bash
~/.telegram_dl/config.json      # API credentials
~/.telegram_dl/user.session     # Active Telethon session
```

**Config contents:**
```json
{
    "api_id": 24339595,
    "api_hash": "40e6bdac2cf10ea546707f4a57a31580",
    "phone": "4917685278763"
}
```

**No additional setup needed** - already configured!

---

## Testing Plan

### 1. Test with Failed Video from Logs

**The video that failed** (session 11f01b54 at 19:16:50):
```
File ID: BAACAgIAAxkBAAIbRmmMv0MbgYQ2NKyiZqKPCma81ZuFAAIhlQ...
Error: "Failed to download video: Exit code: 1"
```

**Test:**
1. Forward the same video again
2. Should now download via Telethon
3. Should extract audio
4. Should transcribe
5. Should send to Claude Code

**Expected log output:**
```
19:XX:XX - INFO - Video file size: XX.XX MB
19:XX:XX - INFO - 📥 Video is XX.XXMB (>20MB). Using Telethon MTProto downloader...
19:XX:XX - INFO - Telethon client connected and authorized
19:XX:XX - INFO - Fetching message from @channel/msg_id...
19:XX:XX - INFO - Downloading XX.X MB from @channel/msg_id (timeout: XXXs)...
19:XX:XX - INFO - ✅ Downloaded XX.XMB via Telethon
19:XX:XX - INFO - Skipping Bot API download (already downloaded via Telethon)
19:XX:XX - INFO - Downloaded video to: /tmp/telegram_videos_XXXXX/video_XXXX.mp4
19:XX:XX - INFO - Extracted audio to: /tmp/telegram_videos_XXXXX/audio_XXXX.ogg
19:XX:XX - INFO - Transcribed video via groq
```

### 2. Test Edge Cases

**A. Small video (<20MB)**
- Should use Bot API (existing flow)
- Telethon should NOT be triggered

**B. Large video from private chat**
- No forward_from_chat_username
- Should show error: "Cannot download: forwarded from private chat"

**C. Large video - network failure**
- Telethon download times out
- Should show error: "Download timed out after XXXs"

**D. Expired Telethon session**
- Session not authorized
- Should show error: "Telethon session expired. Run setup..."

### 3. Performance Test

**Expected times** (for 100MB video):
```
Download:       ~20s  (5 MB/s via MTProto)
Audio extract:  ~5s   (ffmpeg)
Transcription:  ~60s  (Groq Whisper, depends on audio length)
Total:          ~90s
```

---

## Rollback Plan

If issues occur:

### 1. Revert combined_processor.py
```bash
git diff src/bot/combined_processor.py
git checkout HEAD -- src/bot/combined_processor.py
```

### 2. Remove telethon_service.py
```bash
rm src/services/telethon_service.py
```

### 3. Revert requirements.txt
```bash
git diff requirements.txt
git checkout HEAD -- requirements.txt
```

**Bot will return to previous behavior** (show "20MB limit" warning)

---

## Next Steps

### Phase 1: Test (Now)
1. ✅ Implementation complete
2. ⏳ Test with failed video
3. ⏳ Verify audio extraction works
4. ⏳ Verify Claude processing works
5. ⏳ Check logs for any errors

### Phase 2: Monitor (Week 1)
1. Track Telethon vs Bot API usage
2. Monitor download success rate
3. Check session health (re-auth needed?)
4. User feedback on download times

### Phase 3: Enhance (Optional)
1. Live progress updates to user
2. Chunked audio transcription (>1hr videos)
3. Structured vault notes with summary
4. Semantic interlinking (See also)

---

## Troubleshooting

### "Telethon not installed"
```bash
/opt/homebrew/bin/python3.11 -m pip install telethon
```

### "Config not found"
```bash
# Check if config exists
ls -la ~/.telegram_dl/
# If missing, run setup:
python3 ~/.claude/skills/telegram-telethon/scripts/tg.py setup
```

### "Session expired"
```bash
# Re-authenticate
python3 ~/.claude/skills/telegram-telethon/scripts/tg.py setup
```

### "Cannot download: forwarded from private chat"
- User needs to download manually
- Or send video directly (not as forward)
- Cannot be fixed (privacy protection)

---

## Files Changed

### New Files
- `src/services/telethon_service.py` (240 lines)
- `docs/TELETHON_VIDEO_INTEGRATION.md` (comprehensive research doc)
- `docs/TELETHON_INTEGRATION_SUMMARY.md` (this file)

### Modified Files
- `src/bot/combined_processor.py`:
  - Line 1179-1184: Initialize video_path early
  - Line 1202-1263: Telethon fallback logic
  - Line 1267-1282: Skip duplicate download
- `requirements.txt`:
  - Added `telethon>=1.34.0`

### Dependency Changes
- Added: `telethon>=1.34.0` (already installed)

---

## Metrics to Track

Post-deployment, monitor:

1. **Download success rate**
   - Before: 0% for >20MB (all failed)
   - Target: >95% for >20MB

2. **Download method breakdown**
   - Bot API: <20MB videos
   - Telethon: ≥20MB videos

3. **Average download times**
   - 50MB: ~10s
   - 100MB: ~20s
   - 200MB: ~40s

4. **Error rate**
   - Session expiration
   - Timeout errors
   - Private forward errors

---

**Status**: ✅ Ready to test with real video

**Next**: Forward a >20MB video and verify it downloads + processes correctly
