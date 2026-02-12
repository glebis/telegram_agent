# Telethon Video Download Integration

**Research Date**: 2026-02-11
**Status**: Implementation Ready
**Priority**: High (fixes >20MB video download failures)

---

## TL;DR

The bot **already has** complete video processing (download → extract audio → transcribe → Claude). The **only missing piece** is downloading files >20MB, which Bot API can't handle. We have **two working Telethon solutions** already built and configured. Just need to wire them into `combined_processor.py` at line 1208.

---

## Current State

### ✅ What Works
- Video detection in forwarded messages (message_buffer.py:530)
- Forward URL extraction for channels (message_buffer.py:666-667)
- File size checking (combined_processor.py:1202)
- Audio extraction with ffmpeg (subprocess_helper.py)
- Transcription with Groq STT (stt_service)
- Claude processing pipeline

### ❌ What Fails
- **Bot API download fails** for files >20MB with `Exit code: 1`
- Code detects this (line 1202) and shows warning, but **doesn't handle it**

---

## The Problem: Telegram Bot API 20MB Limit

```python
# Current flow (src/bot/combined_processor.py:1224-1237)
download_result = download_telegram_file(
    file_id=video_msg.file_id,  # ← Bot API file_id
    bot_token=bot_token,
    output_path=video_path,
)

if not download_result.success:
    logger.error(f"Failed to download video: {download_result.error}")
    continue  # ← Skips processing, user gets nothing
```

**Why it fails:**
- Bot API `getFile` endpoint has hard 20MB limit
- For >20MB files, returns 400 error
- The subprocess gets exit code 1, no stderr captured
- Result: "Exit code: 1" logged, video skipped

---

## The Solution: Telethon MTProto Client

Telethon uses MTProto (same protocol as Telegram Desktop) → **no 20MB limit**, supports up to 2GB+.

### Available Options

#### Option 1: `transcribe-telegram-video` skill (Recommended)
**Location**: `/Users/server/.claude/skills/transcribe-telegram-video/`

**Features:**
- ✅ Specialized downloader for videos (`downloader.py`)
- ✅ Already configured with credentials at `~/.telegram_dl/config.json`
- ✅ Active session file at `~/.telegram_dl/user.session`
- ✅ Clean async API with progress callbacks
- ✅ Timeout auto-calculation (2s per MB + 60s base)
- ✅ File verification after download

**API:**
```python
from transcribe_telegram_video.downloader import TelegramDownloader

async with TelegramDownloader(
    session_path=Path("~/.telegram_dl/user.session"),
    api_id=24339595,
    api_hash="40e6bdac2cf10ea546707f4a57a31580"
) as downloader:
    result = await downloader.download_from_url(
        url="https://t.me/ACT_Russia/3902",
        output_path=Path("/tmp/video.mp4"),
        progress_callback=lambda cur, tot: print(f"{cur}/{tot}")
    )
    # Returns: {"success": True, "file_path": "...", "size_mb": 243.7}
```

#### Option 2: `telegram-telethon` skill
**Location**: `/Users/server/.claude/skills/telegram-telethon/`

**Features:**
- ✅ General-purpose media downloader (`media.py`)
- ✅ Handles all media types (voice, video, photo, document)
- ✅ Voice transcription built-in
- ⚠️ Requires separate config at `~/.config/telegram-telethon/`

**API:**
```python
from telegram_telethon.modules.media import download_media

downloaded = await download_media(
    client=client,  # TelegramClient instance
    chat_name="me",  # Saved Messages
    message_id=123,
    output_dir="/tmp"
)
```

---

## Integration Architecture

### Current Bot Design Patterns

1. **Subprocess Isolation** - All external I/O in webhook context runs in subprocesses
   - Example: `download_telegram_file()` spawns subprocess with Python script
   - Reason: Keeps webhook handlers non-blocking, prevents timeouts

2. **Service Singletons** - `get_X_service()` pattern with module-level cache
   - Example: `get_stt_service()`, `get_claude_code_service()`
   - Reason: Share resources across handlers

3. **Sync subprocess helpers** - Fast I/O ops run via `run_python_script()`
   - Example: `send_message_sync()`, `edit_message_sync()`
   - Reason: Bot API calls from webhook handlers without blocking

### Integration Decision: **Hybrid Approach**

**Why NOT pure subprocess?**
- Telethon maintains WebSocket connection (MTProto)
- Session state needs to persist across downloads
- Subprocess overhead for each download would be slow

**Why NOT pure async service?**
- Risk of blocking webhook handler on large downloads
- Bot's existing pattern uses subprocess isolation

**Recommended: Subprocess with long-lived client**

```python
# New: src/services/telethon_service.py
class TelethonService:
    """Singleton service managing Telethon client for large file downloads."""

    def __init__(self):
        self._client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()
        # Load credentials from ~/.telegram_dl/config.json or env vars

    async def download_large_video(
        self,
        url: str,  # https://t.me/channel/msg_id
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Download video >20MB using Telethon MTProto."""
        async with self._lock:
            if not self._client:
                await self._connect()

            # Use TelegramDownloader from transcribe-telegram-video
            # ...

_service: Optional[TelethonService] = None

def get_telethon_service() -> TelethonService:
    global _service
    if _service is None:
        _service = TelethonService()
    return _service
```

---

## Implementation Plan

### Phase 1: Minimal Integration (1-2 hours)

**Goal:** Fix >20MB video downloads without changing architecture

**Changes:**

1. **Add Telethon credentials to config**
   ```bash
   # .env
   TELEGRAM_API_ID=24339595
   TELEGRAM_API_HASH=40e6bdac2cf10ea546707f4a57a31580
   TELETHON_SESSION_PATH=~/.telegram_dl/user.session
   ```

2. **Create telethon_service.py** (new file)
   - Singleton service with lazy client init
   - `download_from_url(url, output_path)` method
   - Reuses existing session from transcribe skill

3. **Modify combined_processor.py:1208-1216**
   ```python
   if file_size > 20 * 1024 * 1024:  # >20MB
       logger.info(f"Video is {size_mb:.2f}MB, using Telethon downloader...")

       # Extract URL from forward context
       forward_link = self._extract_forward_url(video_msg)
       if not forward_link:
           await message.reply_text("⚠️ Cannot download: forwarded video has no public URL")
           continue

       # Use Telethon downloader
       telethon_service = get_telethon_service()
       result = await telethon_service.download_from_url(
           url=forward_link,
           output_path=video_path
       )

       if not result["success"]:
           await message.reply_text(f"❌ Download failed: {result['error']}")
           continue

       logger.info(f"✅ Downloaded {result['size_mb']:.1f}MB via Telethon")
       # Continue with existing audio extraction...
   ```

4. **Add helper method to extract forward URL**
   ```python
   def _extract_forward_url(self, video_msg: BufferedMessage) -> Optional[str]:
       """Build t.me URL from forwarded message."""
       if not video_msg.forward_from_chat_username or not video_msg.forward_message_id:
           return None
       return f"https://t.me/{video_msg.forward_from_chat_username}/{video_msg.forward_message_id}"
   ```

**Testing:**
- Forward the failed video from logs (BAACAgIAAxkBAAIbRmmMv0MbgYQ2NKyiZqKPCma81ZuFAAIhlQ...)
- Should now download via Telethon → extract audio → transcribe → Claude

---

### Phase 2: Enhanced Features (optional, 4-6 hours)

1. **Progress updates** - Send live download progress to user
   ```python
   progress_msg = await message.reply_text("📥 Downloading 243.7 MB video...")

   async def update_progress(current, total):
       percent = (current / total) * 100
       await edit_message_sync(
           chat_id=chat_id,
           message_id=progress_msg.message_id,
           text=f"📥 Downloading: {current/(1024**2):.1f}/{total/(1024**2):.1f} MB ({percent:.1f}%)"
       )
   ```

2. **Chunked audio transcription** - Use transcribe skill's chunking
   - Current: passes full audio file to Groq (may hit 25MB limit)
   - Enhanced: chunk large audio into 15-min segments
   - Already implemented in `transcribe_telegram_video/audio_processor.py`

3. **Structured vault notes** - Create rich notes with summary
   - Use transcribe skill's `note_creator.py`
   - Add semantic interlinking (See also section)

---

## Configuration Strategy

### Option A: Reuse existing config (Recommended)
**Pros:**
- No new config needed
- Already authenticated
- Works immediately

**Cons:**
- Couples bot to skill's config location

```python
# src/services/telethon_service.py
CONFIG_PATH = Path.home() / ".telegram_dl" / "config.json"
SESSION_PATH = Path.home() / ".telegram_dl" / "user.session"

def load_telethon_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)
```

### Option B: Add to bot's .env
**Pros:**
- Centralized bot config
- Follows existing patterns
- Can use different credentials

**Cons:**
- Need to duplicate session file
- Extra setup step

```bash
# .env
TELEGRAM_API_ID=24339595
TELEGRAM_API_HASH=40e6bdac2cf10ea546707f4a57a31580
TELETHON_SESSION_NAME=telegram_agent_bot
```

**Recommendation:** Start with Option A (reuse), move to Option B if needed.

---

## Edge Cases & Gotchas

### 1. **Forwarded videos without public URL**
**Problem:** Privacy-protected forwards don't have `forward_from_chat_username`
**Solution:** Ask user to re-send directly (not forwarded)

```python
if not forward_link:
    await message.reply_text(
        "⚠️ Cannot download this video: forwarded from private chat.\n\n"
        "To process:\n"
        "1️⃣ Download to your device\n"
        "2️⃣ Send directly to me (not as forward)"
    )
```

### 2. **Session expiration**
**Problem:** Telethon session may expire after months
**Solution:** Catch auth error, guide user to re-authenticate

```python
try:
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon session expired")
except Exception as e:
    logger.error(f"Telethon auth failed: {e}")
    await message.reply_text(
        "⚠️ Telegram session expired. Run: python3 scripts/tg.py setup"
    )
```

### 3. **Rate limiting**
**Problem:** Telegram may rate-limit MTProto downloads
**Solution:** Already handled by Telethon (auto-backoff)

### 4. **Concurrent downloads**
**Problem:** Multiple users downloading simultaneously
**Solution:** Use asyncio.Lock in service (already in design)

---

## Dependencies

### Already Installed (via skills)
```bash
# From telegram-telethon skill
telethon>=1.34.0

# From transcribe-telegram-video skill
(uses telegram-telethon's telethon)
```

### Need to Add to Bot
```toml
# pyproject.toml or requirements.txt
telethon>=1.34.0  # MTProto client for large file downloads
```

**Installation:**
```bash
cd /Users/server/ai_projects/telegram_agent
pip install telethon
```

---

## Testing Checklist

### Unit Tests
- [ ] `test_telethon_service.py` - service initialization
- [ ] `test_telethon_download_url()` - URL download flow
- [ ] `test_telethon_auth_failure()` - expired session handling

### Integration Tests
- [ ] Forward video <20MB → should use Bot API
- [ ] Forward video >20MB from channel → should use Telethon
- [ ] Forward video >20MB from private chat → should show error
- [ ] Multiple concurrent downloads → should queue correctly

### Manual Tests
- [ ] Forward the failed video from logs (session 11f01b54)
- [ ] Should download via Telethon
- [ ] Should extract audio
- [ ] Should transcribe
- [ ] Should route to Claude Code

---

## Performance Estimates

| File Size | Bot API (fails) | Telethon MTProto | Speedup |
|-----------|----------------|------------------|---------|
| 20 MB     | ✅ ~4s         | ~4s              | 1x      |
| 50 MB     | ❌ Fails       | ~10s             | ∞       |
| 100 MB    | ❌ Fails       | ~20s             | ∞       |
| 250 MB    | ❌ Fails       | ~50s (+ 2 min transcribe) | ∞ |

**Network:** ~5 MB/s via MTProto (depends on Telegram's CDN)

---

## Migration Path

### Week 1: Quick Fix
1. Add telethon_service.py
2. Modify combined_processor.py fallback
3. Test with failed video from logs
4. Deploy to production

### Week 2: Polish
1. Add progress updates
2. Handle edge cases (no URL, expired session)
3. Add monitoring (track Telethon vs Bot API usage)

### Week 3: Enhanced Features
1. Audio chunking for >1hr videos
2. Structured vault notes with summary
3. Semantic interlinking

---

## Open Questions

1. **Should we always use Telethon?**
   - Pro: Consistent behavior for all videos
   - Con: Bot API is faster for small files
   - **Decision:** Use Bot API for <20MB (existing), Telethon for ≥20MB (new)

2. **How to handle private forwards?**
   - Option A: Error message, ask to re-send
   - Option B: Detect if user is in source chat, download via chat ID
   - **Decision:** Start with Option A (simpler)

3. **Where to store session file?**
   - Option A: Reuse ~/.telegram_dl/ (skill location)
   - Option B: Create ~/ai_projects/telegram_agent/data/telethon.session
   - **Decision:** Option A for now (already configured)

---

## Related Files

### To Modify
- `src/bot/combined_processor.py:1208` - Add Telethon fallback
- `src/bot/combined_processor.py` - Add `_extract_forward_url()` method

### To Create
- `src/services/telethon_service.py` - New service singleton
- `tests/test_services/test_telethon_service.py` - Unit tests

### To Reference
- `/Users/server/.claude/skills/transcribe-telegram-video/src/transcribe_telegram_video/downloader.py` - Telethon downloader implementation
- `/Users/server/.claude/skills/telegram-telethon/src/telegram_telethon/modules/media.py` - General media download
- `src/services/message_buffer.py:666` - Forward URL extraction logic

---

## Next Steps

1. **Implement Phase 1** (minimal fix)
   - Create `telethon_service.py`
   - Modify `combined_processor.py`
   - Test with failed video

2. **Write tests**
   - Unit tests for service
   - Integration test for >20MB flow

3. **Deploy & Monitor**
   - Track success rate of Telethon downloads
   - Monitor session health

4. **Iterate** (Phase 2 features)
   - Progress updates
   - Chunked transcription
   - Vault notes with summary

---

**Ready to implement?** Start with `src/services/telethon_service.py` and the 5-line change to `combined_processor.py:1208`.
