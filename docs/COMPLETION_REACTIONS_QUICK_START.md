# Completion Reactions - Quick Start

Add celebratory reactions when the agent completes tasks! 🎉

## 5-Second Setup

Add to your `.env`:

```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=✅
COMPLETION_REACTION_PROBABILITY=1.0
```

Restart the bot. Done! ✨

## Popular Presets

### 1. Simple Checkmark (Professional)
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=✅
COMPLETION_REACTION_PROBABILITY=1.0
```

### 2. Random Celebration (Fun)
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=🎉,✨,🚀,💪,🔥,🌟
COMPLETION_REACTION_PROBABILITY=1.0
```

### 3. Occasional Surprise (Subtle)
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=✨,👍
COMPLETION_REACTION_PROBABILITY=0.3
```

### 4. Robot Theme (Branded)
```bash
COMPLETION_REACTION_TYPE=emoji
COMPLETION_REACTION_VALUE=🤖,🧠,💡,⚡
COMPLETION_REACTION_PROBABILITY=0.8
```

### 5. No Reactions (Silent)
```bash
COMPLETION_REACTION_TYPE=none
```

## Using Custom Stickers

1. Send your sticker to [@userinfobot](https://t.me/userinfobot)
2. Copy the `file_id` from the response
3. Add to `.env`:

```bash
COMPLETION_REACTION_TYPE=sticker
COMPLETION_REACTION_VALUE=CAACAgIAAxkBAAID...
COMPLETION_REACTION_PROBABILITY=1.0
```

## Using GIFs

Same as stickers, but with animations:

```bash
COMPLETION_REACTION_TYPE=animation
COMPLETION_REACTION_VALUE=CgACAgIAAxkBAAID...
COMPLETION_REACTION_PROBABILITY=1.0
```

## Pro Tips

- **Multiple options**: Separate with commas for random selection
  ```bash
  COMPLETION_REACTION_VALUE=🎉,✨,🚀,💪
  ```

- **Adjust frequency**: Use probability to control how often reactions appear
  ```bash
  COMPLETION_REACTION_PROBABILITY=0.5  # 50% of the time
  ```

- **Test it**: Set probability to 1.0 when testing, then adjust to taste

## Full Documentation

See [COMPLETION_REACTIONS.md](../COMPLETION_REACTIONS.md) for complete documentation.

## Emoji Ideas

**Celebration:**
🎉 🎊 🎈 🥳 🍾 🎆 ✨ 🌟 ⭐

**Approval:**
✅ ✔️ 👍 👌 🙌 💯 🏆 🥇

**Tech/Smart:**
🤖 🧠 💡 ⚡ 🔧 ⚙️ 🛠️

**Power/Energy:**
💪 🔥 🚀 ⚡ 💥 ⭐

**Positive:**
😊 😎 🤗 👏 🙏 💚 💙

Mix and match to create your perfect vibe!
