# Reply Context Implementation

## Overview
Enhanced the Telegram bot to capture and provide context when you reply to messages (voice, text, images, videos). This ensures Claude receives the full context of what you're responding to.

## What Was Changed

### 1. Enhanced Message Buffer (`src/services/message_buffer.py`)

#### Added new fields to `CombinedMessage`:
```python
reply_to_message_text: Optional[str] = None  # Text/caption from replied message
reply_to_message_type: Optional[str] = None  # Type of replied message
```

#### Enhanced reply extraction (lines 503-526):
Now extracts the **full content** from `reply_to_message` object:
- **Text messages**: Captures `reply_to.text`
- **Images**: Captures `reply_to.caption` + type = "photo"
- **Videos**: Captures `reply_to.caption` + type = "video"
- **Documents**: Captures `reply_to.caption` + type = "document"
- **Voice**: Sets type = "voice" (transcription in cache)
- **Video notes**: Sets type = "video_note"

### 2. Enhanced Combined Processor (`src/bot/combined_processor.py`)

#### Added fallback for cache misses (lines 189-206):
When replying to a message:
1. **First**: Check in-memory cache for ReplyContext
2. **If cache miss**: Create ReplyContext from extracted `reply_to_message_text`
3. Store new context in cache for future replies

This ensures you can reply to **any** message, even if it wasn't previously tracked.

## How It Works

### Scenario: User replies to their own voice message

```
1. User sends voice message
   └─> Bot transcribes: "What's the weather like?"
   └─> Sends transcript back to user

2. User replies to transcript with: "Tell me more"
   └─> Telegram provides reply_to_message object
   └─> Bot extracts: reply_to_message.text = "📝 Transcript:\n\nWhat's the weather like?"

3. Bot builds context for Claude:
   [Replying to previous message]
   Original: 📝 Transcript:

   What's the weather like?

   Response: Tell me more

4. Claude receives full context and can respond appropriately
```

### Scenario: User replies to their own text message

```
1. User sends: "I need help with Python"
   └─> Message not processed by bot (no command/voice)

2. User replies to their message with: "Can you help?"
   └─> Bot extracts: reply_to_message.text = "I need help with Python"
   └─> Creates ReplyContext on-the-fly

3. Claude receives:
   [Replying to previous message]
   Original: I need help with Python

   Response: Can you help?
```

### Scenario: User replies to an image they sent

```
1. User sends image with caption: "Check this diagram"
   └─> Bot processes image (if in Claude mode)
   └─> Stores image analysis in cache

2. User replies to image with: "What does this mean?"
   └─> Bot extracts: reply_to_message.caption = "Check this diagram"
   └─> Looks up image analysis from cache

3. Claude receives:
   [Replying to image analysis]
   Image: /path/to/image.jpg
   Description: [AI analysis of diagram...]

   Follow-up about this image: What does this mean?
```

## Benefits

1. **Full context preservation**: Claude always knows what you're replying to
2. **Works for all message types**: text, voice, images, videos, documents
3. **Cache fallback**: Even works for messages that weren't previously tracked
4. **No user action needed**: Automatic - just use Telegram's reply feature

## Testing

Run the demo to see extraction in action:
```bash
cd /Users/server/ai_projects/telegram_agent
python3 test_reply_context_demo.py
```

## Technical Details

- **Cache**: In-memory LRU cache with 24-hour TTL
- **Extraction**: Happens in `MessageBuffer._build_combined_message()`
- **Context creation**: Happens in `CombinedMessageProcessor.process_combined()`
- **Prompt building**: Uses existing `ReplyContextService.build_reply_prompt()`

## Files Modified

1. `src/services/message_buffer.py` - Extract reply content
2. `src/bot/combined_processor.py` - Create context on cache miss

## No Breaking Changes

- All existing functionality preserved
- Backward compatible with existing reply context cache
- Falls back gracefully when content unavailable
