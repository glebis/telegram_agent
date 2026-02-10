# Issue: Fix Large Video Download Limitation (>20MB) and Enhance Video Processing

> **TL;DR**: The bot already has complete video processing (extract audio → transcribe → process). The issue is Telegram Bot API's 20MB file size limit prevents downloading large videos from channels. Need to integrate Telethon for downloading files >20MB.

## Problem Statement

When forwarding messages from Telegram channels that contain videos, the bot currently:
1. May not detect video attachments in forwarded messages
2. Does not automatically extract audio from videos
3. Does not transcribe video audio content
4. Does not create structured notes with summaries and interlinking

### Current Behavior

**Example scenario:**
- User forwards a message from channel `@ACT_Russia/3902` containing a voice chat recording video
- Bot receives the forward with text: "Запись нашего войс-чата «Эволюционная психология и АСТ» с Александром Лозовским"
- Bot logs show: `videos=0` - no video detected
- No audio extraction or transcription occurs

## Root Cause Analysis

**Actual Issue Identified** (2026-02-10):
The bot **already has complete video processing** (`_process_with_videos` method) that:
✅ Detects videos in forwarded messages
✅ Downloads videos
✅ Extracts audio with ffmpeg
✅ Transcribes using Groq STT
✅ Routes to Claude

**The Real Problem**: Telegram Bot API has a **20MB file size limit** for direct downloads. When attempting to download large videos (like 1+ hour voice chats), the download fails with `Exit code: 1`.

Log evidence from 2026-02-10 14:45:38:
```
Processing video file_id: BAACAgIAAxkBAAIaQmmLE2Oe5kpfX5Km5GdjB4RqbPC8AAIWiw...
Failed to download video: Exit code: 1
```

The Telegram API's `getFile` endpoint returns an error for files >20MB.

## Proposed Solution

### Primary Fix: Handle Large Videos (>20MB)

Since the core video processing pipeline already exists, we need to:

**Option A: Use Telethon/MTProto Client** (Recommended)
- Telethon can download files of any size (up to 2GB+)
- Already have `telegram-telethon` skill in the repo
- Can download directly from channels without Bot API limits

**Option B: Request User to Re-send**
- Detect file size before download attempt
- If >20MB, ask user to forward the file directly (not from channel)
- Or ask user to provide a direct link where the video can be downloaded

**Option C: Use External Download Service**
- Instruct user to use a Telegram media downloader
- User uploads the downloaded file to the bot
- Bot processes the local file

### Secondary Enhancement: Structured Note Creation

Once videos can be downloaded, enhance post-processing to:
1. **Split large audio** into chunks for Whisper (currently processes as single file)
2. **Create structured notes** with summary and interlinking
3. **Add progress updates** for long-running transcriptions

## Definition of Done (DoD)

### Core Functionality
- [x] Bot detects video attachments in forwarded messages (**Already working**)
- [x] Bot detects videos in media groups (**Already working**)
- [x] Audio extraction from video files works for common formats (**Already working with ffmpeg**)
- [ ] **NEW**: Videos >20MB can be downloaded using Telethon
- [ ] **NEW**: File size check before attempting Bot API download
- [ ] **NEW**: User-friendly error message when file is too large
- [ ] Audio is split into chunks suitable for Whisper API (≤25MB, optimal length)
- [ ] Transcription pipeline processes all chunks sequentially
- [ ] Transcript segments are combined with timestamps

### Note Creation
- [ ] Structured note generated in vault with:
  - Title extracted from forwarded message or generated
  - Summary of key themes/topics
  - Full transcript with timestamps
  - Speaker identification (if detectable)
- [ ] Note is embedded in semantic search index
- [ ] Related notes are identified and linked (See also section)

### Code Quality
- [ ] All new code follows existing patterns (subprocess isolation for external tools)
- [ ] Error handling for missing dependencies (ffmpeg)
- [ ] Logging at appropriate levels (INFO for progress, ERROR for failures)
- [ ] Type hints on all functions
- [ ] Docstrings for public methods

### Testing
- [ ] Unit tests for audio extraction function
- [ ] Unit tests for audio chunking logic
- [ ] Integration test for full video→transcript→note pipeline
- [ ] Test with forwarded channel messages
- [ ] Test with media group videos
- [ ] Test with various video formats

### Documentation
- [ ] README updated with video processing capabilities
- [ ] Code comments explain video detection logic
- [ ] Example usage documented

## Acceptance Criteria

### Must Have
1. **Video Detection**: When a forwarded message contains a video, bot logs `videos=1` and captures `file_id`
2. **Audio Extraction**: Video is downloaded and audio extracted to temporary file
3. **Chunking**: Audio files >25MB are split into multiple chunks
4. **Transcription**: All chunks are transcribed via Groq STT service
5. **Note Creation**: Complete transcript saved to vault note with proper formatting

### Should Have
1. **Progress Updates**: User receives status updates during processing ("Extracting audio... Transcribing chunk 1/3...")
2. **Error Recovery**: If transcription fails mid-way, partial transcript is still saved
3. **Semantic Linking**: Note is linked to related psychology/ACT concepts in vault

### Nice to Have
1. **Speaker Diarization**: Identify different speakers in multi-person discussions
2. **Topic Segmentation**: Break transcript into sections by topic
3. **Key Quotes**: Extract and highlight impactful quotes
4. **Summary Generation**: LLM-generated summary of main points

## Technical Implementation Notes

### Current Implementation (Already Complete)

**Video Detection** ✅ Working
```python
# src/services/message_buffer.py:528-530
elif message.video:
    msg_type = "video"
    file_id = message.video.file_id
```

**Download, Extract, Transcribe** ✅ Working (for files <20MB)
```python
# src/bot/combined_processor.py:_process_with_videos (lines 1130-1280)
# - Downloads video with download_telegram_file()
# - Extracts audio with extract_audio_from_video()
# - Transcribes with stt_service.transcribe()
# - Routes to Claude for processing
```

### New Implementation: Telethon Download (for files >20MB)

```python
# src/utils/telethon_downloader.py (NEW)
from telethon import TelegramClient
from pathlib import Path

async def download_large_video(
    message_link: str,  # e.g., "https://t.me/ACT_Russia/3902"
    output_path: Path,
    progress_callback=None
) -> bool:
    """Download video using Telethon MTProto client (no 20MB limit)."""
    client = TelegramClient('bot_session', api_id, api_hash)
    await client.start()

    # Parse channel and message_id from link
    channel, msg_id = parse_telegram_link(message_link)

    # Get message
    message = await client.get_messages(channel, ids=msg_id)

    # Download video
    if message.video:
        await client.download_media(
            message.video,
            file=str(output_path),
            progress_callback=progress_callback
        )
        return True
    return False
```

### Audio Chunking Strategy
- Use pydub or ffmpeg to split by duration
- Target chunk size: 20MB (leaves buffer below 25MB limit)
- Target duration: 15 minutes per chunk
- Overlap: 1 second between chunks to avoid cutting words

### Transcription Service
```python
# Use existing stt_service
stt_service = get_stt_service()
for chunk_path in audio_chunks:
    result = stt_service.transcribe(
        audio_path=chunk_path,
        model="whisper-large-v3-turbo",
        language="auto"  # Detect language
    )
    transcriptions.append(result.text)
```

### Note Template
```markdown
# [Title from Forwarded Message]

**Source**: [Channel Name](https://t.me/channel/msgid)
**Date**: YYYY-MM-DD
**Duration**: XX minutes
**Speakers**: [Auto-detected or Unknown]

## Summary

[LLM-generated summary of key themes]

## Transcript

### [00:00] Introduction
[Transcribed content from chunk 1...]

### [15:00] Topic 2
[Transcribed content from chunk 2...]

## See also

- [[Related Note 1]]
- [[Related Note 2]]
```

## Test Plan

### Test Case 1: Small Forwarded Video (<20MB)
**Setup**: Forward a message containing a small video file
**Expected**: Bot detects video, downloads via Bot API, extracts audio, transcribes
**Verify**: Check logs show `videos=1`, download succeeds, transcript is accurate

### Test Case 1b: Large Forwarded Video (>20MB) - **CURRENTLY FAILING**
**Setup**: Forward message from `@ACT_Russia/3902` (voice chat recording, likely >20MB)
**Current Behavior**: `Failed to download video: Exit code: 1`
**Expected After Fix**: Bot detects >20MB, uses Telethon download, succeeds
**Verify**: Log shows "File >20MB, using Telethon download", transcript created

### Test Case 2: Media Group with Videos
**Setup**: Forward multiple videos sent as album
**Expected**: All videos detected, processed together or separately
**Verify**: Multiple notes created or single note with multiple sections

### Test Case 3: Large Video (>1 hour)
**Setup**: Send 90-minute video recording
**Expected**: Audio split into ~6 chunks, all transcribed
**Verify**: Full transcript with timestamps, no missing sections

### Test Case 4: Video Without Audio
**Setup**: Forward a video with no audio track
**Expected**: Bot detects this, sends user message "Video has no audio track"
**Verify**: No transcription attempted, no empty note created

### Test Case 5: Unsupported Video Format
**Setup**: Send video in rare codec (e.g., .flv)
**Expected**: Error message sent to user, fallback to download and convert
**Verify**: Either successful processing or clear error message

## Implementation Phases

### Phase 1: Detection & Download (MVP)
- Verify forwarded videos are detected
- Download video file to temp location
- Log video metadata (duration, size, codec)

### Phase 2: Audio Extraction
- Extract audio track from video
- Handle videos without audio gracefully
- Clean up temp files properly

### Phase 3: Chunking & Transcription
- Split large audio files
- Send chunks to STT service
- Combine transcripts with timestamps

### Phase 4: Note Generation
- Create structured note in vault
- Embed note for semantic search
- Find and link related notes

### Phase 5: Polish & Testing
- Add progress updates for user
- Comprehensive error handling
- Full test suite

## Related Issues

- #XXX - Voice message transcription (existing feature to build upon)
- #XXX - Media group handling (may need enhancement)

## References

- [Telegram Bot API - Message](https://core.telegram.org/bots/api#message)
- [python-telegram-bot - Media Groups Discussion](https://github.com/python-telegram-bot/python-telegram-bot/discussions/3561)
- [Groq Whisper API Documentation](https://console.groq.com/docs/speech-text)
- Existing code: `src/bot/combined_processor.py` - `_process_with_videos()` method
- Existing code: `src/utils/subprocess_helper.py` - `extract_audio_from_video()` function

---

**Labels**: enhancement, feature, video-processing, transcription
**Priority**: Medium
**Effort**: Large (3-5 days)
**Dependencies**: ffmpeg, Groq API
