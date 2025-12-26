# Completion Reactions

Configure the bot to send celebratory reactions when tasks complete!

## Configuration

Add these environment variables to your `.env` file:

### Basic Settings

```bash
# Type of reaction: emoji, sticker, animation, or none
COMPLETION_REACTION_TYPE=emoji

# The reaction to send (depends on type - see below)
COMPLETION_REACTION_VALUE=✅

# Probability of sending (0.0 to 1.0, where 1.0 = always)
COMPLETION_REACTION_PROBABILITY=1.0
```

## Reaction Types

### 1. Emoji Reactions

Send emoji as reactions or text messages.

**Single emoji:**
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=✅
```

**Random selection from multiple:**
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=✨,🎉,👍,🚀,💪,🔥
```

Popular emoji options:
- ✅ ✔️ (checkmarks)
- 🎉 🎊 🎈 (celebration)
- ✨ ⭐ 🌟 (sparkles)
- 👍 👌 🙌 (approval)
- 🚀 💪 🔥 (energy)
- 🤖 🧠 💡 (tech/smart)

### 2. Sticker Reactions

Send Telegram stickers (custom or from packs).

**Using Telegram file_id:**
```bash
COMPLETION_REACTION_TYPE=sticker
COMPLETION_REACTION_VALUE=CAACAgIAAxkBAAID...
```

**Using local file:**
```bash
COMPLETION_REACTION_TYPE=sticker
COMPLETION_REACTION_VALUE=/path/to/sticker.webp
```

**Random selection:**
```bash
COMPLETION_REACTION_TYPE=sticker
COMPLETION_REACTION_VALUE=CAACAgIAAxkBAAID...,CAACAgIAAxkBAAIE...,CAACAgIAAxkBAAIF...
```

#### How to Get Sticker file_id

1. Forward a sticker to [@userinfobot](https://t.me/userinfobot)
2. It will reply with the file_id
3. Copy and paste into `COMPLETION_REACTION_VALUE`

Or use [@RawDataBot](https://t.me/RawDataBot) to get the full JSON.

### 3. Animation/GIF Reactions

Send animated GIFs or MP4s.

**Using Telegram file_id:**
```bash
COMPLETION_REACTION_TYPE=animation
COMPLETION_REACTION_VALUE=CgACAgIAAxkBAAID...
```

**Using local file:**
```bash
COMPLETION_REACTION_TYPE=animation
COMPLETION_REACTION_VALUE=/path/to/celebration.gif
```

**Random selection:**
```bash
COMPLETION_REACTION_TYPE=animation
COMPLETION_REACTION_VALUE=CgACAgIAAxkBAAID...,CgACAgIAAxkBAAIE...
```

#### How to Get Animation file_id

Same as stickers - forward to [@userinfobot](https://t.me/userinfobot) or [@RawDataBot](https://t.me/RawDataBot).

### 4. Disable Reactions

```bash
COMPLETION_REACTION_TYPE=none
```

## Advanced Configuration

### Probability Control

Make reactions less frequent for a subtler experience:

```bash
# 50% chance
COMPLETION_REACTION_PROBABILITY=0.5

# 25% chance (occasional surprise)
COMPLETION_REACTION_PROBABILITY=0.25

# Always send
COMPLETION_REACTION_PROBABILITY=1.0
```

### Context-Aware Ideas

You can create different reaction sets for different contexts:

**Professional/Minimal:**
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=✅
COMPLETION_REACTION_PROBABILITY=1.0
```

**Enthusiastic:**
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=🎉,✨,🚀,💪,🔥,🌟
COMPLETION_REACTION_PROBABILITY=0.8
```

**Quiet (rare celebrations):**
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=👍
COMPLETION_REACTION_PROBABILITY=0.2
```

## Examples in Action

### Example 1: Simple Checkmark
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=✅
COMPLETION_REACTION_PROBABILITY=1.0
```
Result: Every task completion gets a ✅ reaction

### Example 2: Random Celebration
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=🎉,✨,🎊,🌟,🚀
COMPLETION_REACTION_PROBABILITY=0.7
```
Result: 70% of completions get a random celebration emoji

### Example 3: Custom Sticker Pack
```bash
COMPLETION_REACTION_TYPE=sticker
COMPLETION_REACTION_VALUE=CAACAgIAAxkBAAID1...,CAACAgIAAxkBAAID2...,CAACAgIAAxkBAAID3...
COMPLETION_REACTION_PROBABILITY=1.0
```
Result: Every completion gets a random sticker from your custom set

### Example 4: GIF Party
```bash
COMPLETION_REACTION_TYPE=animation
COMPLETION_REACTION_VALUE=/app/assets/celebration.gif,/app/assets/success.gif
COMPLETION_REACTION_PROBABILITY=0.5
```
Result: 50% of completions get a celebratory GIF

## Troubleshooting

### Reactions not showing
- Check that `COMPLETION_REACTION_TYPE` is not set to `none`
- Verify `COMPLETION_REACTION_PROBABILITY` is > 0
- Check logs for errors

### Invalid file_id errors
- Make sure you copied the complete file_id
- Test by sending the sticker/animation manually first
- Use [@RawDataBot](https://t.me/RawDataBot) to verify the file_id

### File not found errors
- Verify the file path is absolute
- Ensure file exists in the Docker container (if using Docker)
- Check file permissions

## Technical Details

- Reactions are sent after task completion and file delivery
- Emoji reactions use Telegram's reaction API when replying to a message
- Stickers and animations are sent as separate messages
- Random selection happens per completion (not cached)
- Failures are logged but don't interrupt the main flow
