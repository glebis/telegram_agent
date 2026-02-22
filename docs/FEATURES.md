# Verity - Feature Documentation

Comprehensive documentation for all bot features. For quick start and command reference, see [README.md](README.md).

## Table of Contents
- [Spaced Repetition System (SRS)](#spaced-repetition-system-srs)
- [Claude Code Integration](#claude-code-integration)
- [Design Skills Integration](#design-skills-integration)
- [Session Management](#session-management)
- [Reply Context System](#reply-context-system)
- [Collect Mode (Batch Processing)](#collect-mode-batch-processing)
- [Plugin System](#plugin-system)
- [Voice & Video Transcription](#voice--video-transcription)
- [Obsidian Integration](#obsidian-integration)
- [Message Buffering](#message-buffering)
- [Image Analysis](#image-analysis)
- [Proactive Task Framework](#proactive-task-framework)

---

## Spaced Repetition System (SRS)

Review ideas from your Obsidian vault using the SM-2 spaced repetition algorithm for optimal learning retention.

### What is SRS?

The Spaced Repetition System helps you review and retain knowledge by scheduling reviews at optimal intervals. The bot uses the SM-2 algorithm (SuperMemo 2) which adjusts intervals based on your recall performance.

### Setup

1. **Configure vault paths** in `.env`:
   ```bash
   OBSIDIAN_VAULT_PATH=/path/to/your/vault
   SRS_VAULT_PATHS=/path/to/your/vault/Ideas,/path/to/your/vault/Research
   ```

2. **Sync vault to SRS database**:
   ```bash
   python src/services/srs/srs_sync.py -v
   ```

3. **Install launchd services** for automatic sync and daily batches:
   ```bash
   ~/ai_projects/telegram_agent/scripts/srs_service.sh install
   ~/ai_projects/telegram_agent/scripts/srs_service.sh start
   ```

### Card Format

SRS cards are extracted from Obsidian notes using the following format:

```markdown
## Card Title

Card content here. This will be the front of the card.

### Answer (optional)

Answer content. This will be the back of the card.

### Tags (optional)

#tag1 #tag2 #tag3
```

**Requirements:**
- Cards must be level 2 headings (`##`)
- Optional level 3 heading (`###`) for answer section
- Tags can appear anywhere in the card content
- Cards without explicit answers use the full content

### Commands

- `/review` - Get next 5 cards due for review
- `/review <count>` - Get specific number of cards (e.g., `/review 10`)
- `/srs_stats` - View review statistics

### Rating Cards

After reviewing a card, rate your recall:

| Rating | Meaning | Next Review |
|--------|---------|-------------|
| **0 (Complete blackout)** | No recall | 1 minute |
| **1 (Incorrect response)** | Wrong answer | 1 minute |
| **2 (Incorrect response; correct one seemed easy)** | Partial recall | 1 minute |
| **3 (Correct response recalled with difficulty)** | Hard | ~1 day |
| **4 (Correct response after hesitation)** | Good | ~3 days |
| **5 (Perfect response)** | Easy | ~1 week+ |

### SM-2 Algorithm

The bot uses the SuperMemo 2 algorithm which:
- Adjusts intervals based on your performance
- Increases intervals for cards you know well (ratings 3-5)
- Resets intervals for cards you struggle with (ratings 0-2)
- Uses an "easiness factor" that adapts to each card

**Interval calculation:**
- First review (quality ≥ 3): 1 day
- Second review (quality ≥ 3): 6 days
- Subsequent reviews: previous interval × easiness factor
- Failed cards (quality < 3): restart from 1 minute

### Scheduled Batches

The bot automatically sends review batches at scheduled times:

- **Morning batch**: 9:00 AM (configurable)
- **Automatic sync**: Every hour (updates vault changes)

### Statistics

View your review statistics with `/srs_stats`:
- Total cards in system
- Cards due today
- Cards reviewed in last 7/30 days
- Average recall quality
- Mastery levels (new, learning, mature)

### Technical Details

For implementation details, database schema, and API reference, see [docs/SRS_INTEGRATION.md](docs/SRS_INTEGRATION.md).

---

## Claude Code Integration

Interactive AI sessions with full Claude Code SDK integration, streaming responses, and session persistence.

### Starting a Session

**Basic usage:**
```
/claude <prompt>
```

**New session:**
```
/claude:new <prompt>
```

**Multi-part prompts** (send within 2.5 seconds):
```
/claude Analyze this code
<paste code here>
Also check for security issues
```

All messages are combined into one prompt before Claude executes.

### Session Controls

Inline keyboard buttons for session management:

| Button | Action |
|--------|--------|
| **Reset** | End session and start fresh |
| **Continue** | Resume with a follow-up prompt |
| **Lock/Unlock** | Toggle continuous conversation mode |
| **Haiku/Sonnet/Opus** | Switch between Claude models |

### Locked Mode

Enable continuous conversation mode where all messages route to Claude without the `/claude` prefix.

**Enable:**
```
/claude:lock
```

**In locked mode:**
- All text messages route to Claude
- All voice messages are transcribed and sent to Claude
- All images are sent to Claude
- All videos are transcribed and sent to Claude
- Reply to continue in specific sessions

**Disable:**
```
/claude:unlock
```

### Session Persistence

- Sessions persist for 60 minutes of inactivity
- Sessions are stored in database and can be resumed
- In-memory session cache for fast lookups
- View past sessions with `/claude:sessions`

### Auto-Naming

Sessions are automatically named after the first response using AI:
- Concise, descriptive names (3-5 words)
- Generated from the prompt context
- Visible in session list

### Session Management

**Show current session:**
```
/session
```

**Rename session:**
```
/session rename <new name>
```

**List all sessions:**
```
/session list
```

**Delete session:**
- Use inline button in session list

### Tool Display

See real-time display of Claude's actions:

| Tool | Description |
|------|-------------|
| **Read/Write/Edit** | File operations |
| **Bash** | Shell commands |
| **Skill** | Claude skills execution |
| **Task** | Background agent tasks |
| **WebFetch/WebSearch** | Web operations |
| **Glob/Grep** | File search operations |

### Auto-Send Files

Generated files are automatically sent to you:
- PDFs
- Images (PNG, JPG, SVG)
- Audio files (MP3, WAV)
- Video files (MP4, MOV)

### Model Selection

**Default model:**
Set in `/settings` or per-session with inline buttons.

**Available models:**
- **Haiku** - Fast, cost-effective (best for simple tasks)
- **Sonnet** - Balanced performance (default)
- **Opus** - Most capable (best for complex tasks)

### Long Message Handling

Responses exceeding Telegram's 4096 character limit are automatically split into multiple messages with continuation indicators.

### Meta Command (Bot Development)

Use `/meta` to execute Claude prompts in the telegram_agent directory:

```
/meta check for TODO comments in the codebase
```

This is useful for bot development and debugging.

---

## Design Skills Integration

Automatic UI/UX guidance from industry-leading design resources when Claude detects design-related prompts.

### Included Design Systems

#### 1. Impeccable Style
Source: https://impeccable.style/

Design fluency principles for AI coding tools:
- Visual hierarchy and layout
- Typography best practices
- Color theory and accessibility
- Spacing rhythm and consistency
- Responsive design patterns

#### 2. UI Skills
Source: http://ui-skills.com

Opinionated constraints for better interfaces:
- **Avoid disabled buttons** - Use validation messages instead
- **Meaningful labels** - Not generic "Submit" or "OK"
- **Inline validation** - Validate on blur, not on submit
- **Loading states** - Show progress for async operations
- **Error recovery** - Guide users to fix issues
- **Mobile-first design** - Start with smallest screens
- **Touch targets** - Minimum 44x44px for touch
- **Focus indicators** - Clear keyboard navigation

#### 3. Rams.ai
Source: https://www.rams.ai/

Design engineer for coding agents:
- Accessibility review checklist (WCAG AA)
- Visual consistency checks
- UI polish recommendations
- Auto-review on completion
- Offers to fix identified issues

### How It Works

**Automatic detection:**
Claude detects UI/design keywords in prompts:
- UI, interface, form, button, layout
- Design, style, visual, appearance
- Component, widget, dialog, modal

**Enhanced system prompt:**
When detected, Claude's system prompt includes relevant design guidance from all enabled skills.

**Auto-review:**
After completing design tasks, Claude can offer to review the output for:
- Accessibility issues
- Visual consistency
- Best practice violations

### Configuration

**View current configuration:**
```bash
python scripts/manage_design_skills.py show
```

**Test if skills apply to a prompt:**
```bash
python scripts/manage_design_skills.py test "build a login form"
```

**Enable/disable specific skills:**
```bash
python scripts/manage_design_skills.py enable impeccable_style
python scripts/manage_design_skills.py disable ui_skills
```

**Get design review checklist:**
```bash
python scripts/manage_design_skills.py review
```

### Example Usage

```
/claude Create a login form with email and password fields

[Claude responds with form implementation using design best practices]
- Meaningful labels ("Email address" not "Username")
- Inline validation on blur
- Accessible error messages
- Proper focus indicators
- Touch-friendly button sizes
```

### Technical Details

For implementation details and API reference, see [docs/DESIGN_SKILLS.md](docs/DESIGN_SKILLS.md).

---

## Session Management

AI-powered session naming and controls for organizing your Claude conversations.

### Auto-Naming

Sessions are automatically named after the first response:
- **AI-generated** from prompt context
- **Concise** (3-5 words)
- **Descriptive** of the conversation topic
- **Visible** in session list

**Example:**
```
Prompt: "Help me refactor this authentication module"
Auto-name: "Refactor Auth Module"
```

### Session Commands

**Show current session info:**
```
/session
```
Displays:
- Session ID
- Name (auto-generated or custom)
- Active status
- Last used timestamp
- Model in use

**Rename current session:**
```
/session rename <new name>
```

**List all past sessions:**
```
/session list
```
Shows paginated list with:
- Session names
- Last used dates
- Inline buttons to resume or delete

### Session Lifecycle

1. **Creation**: When you first use `/claude` or `/claude:new`
2. **Auto-naming**: After first Claude response
3. **Persistence**: Stored in database with full state
4. **Resumption**: Automatically resumed when you continue
5. **Expiration**: After 60 minutes of inactivity

### Resuming Sessions

**From session list:**
Click "Resume" button in `/session list`

**From reply:**
Reply to any Claude message to continue that session

**Automatic:**
In locked mode, continues current session

---

## Reply Context System

Enables seamless conversation threading by tracking message origins and extracting context from replies.

### How It Works

When you reply to a message:
1. **Extract context** from the original message
2. **Check cache** for existing context
3. **Create context** if cache miss
4. **Build enhanced prompt** with original message + your reply
5. **Send to Claude** with full context

### Supported Message Types

Reply context works for all message types:
- **Text messages** - Extracts full text
- **Voice messages** - Includes transcription
- **Images** - Includes caption and analysis
- **Videos** - Includes caption and transcription
- **Documents** - Includes file name and description

### Context Cache

- **24-hour TTL** - Context expires after 24 hours
- **LRU eviction** - Oldest entries removed when cache is full
- **In-memory** - Fast lookups, no database overhead

### Use Cases

**Continue Claude conversation:**
```
[Claude responds to your prompt]
You: [Reply to Claude's message]
Bot: [Continues in same session with context]
```

**Reference transcriptions:**
```
[You send voice message]
Bot: [Transcribes to text]
You: [Reply to transcription with follow-up]
Bot: [Includes original transcription in context]
```

**Discuss images:**
```
[You send image]
Bot: [Analyzes image]
You: [Reply with question about image]
Bot: [Includes image analysis in context]
```

### Technical Details

For implementation details, see [REPLY_CONTEXT_IMPLEMENTATION.md](REPLY_CONTEXT_IMPLEMENTATION.md).

---

## Collect Mode (Batch Processing)

Accumulate multiple items before processing them together with Claude for comprehensive analysis.

### Workflow

1. **Start collecting:**
   ```
   /collect:start
   ```

2. **Send items in any order:**
   - Text messages
   - Images
   - Voice messages
   - Videos
   - Documents

3. **Check what's collected:**
   ```
   /collect:status
   ```

4. **Process with Claude:**
   ```
   /collect:go
   ```

5. **Or cancel without processing:**
   ```
   /collect:stop
   ```

### Commands

| Command | Description |
|---------|-------------|
| `/collect:start` | Start collecting items |
| `/collect:go` | Process collected items with Claude |
| `/collect:stop` | Stop collecting without processing |
| `/collect:status` | Show what's been collected |
| `/collect:clear` | Clear queue but stay in collect mode |
| `/collect:help` | Show collect command help |

### Use Cases

**Batch analyze photos:**
```
/collect:start
[Send 5 vacation photos]
/collect:go "Compare these photos and suggest the best one for social media"
```

**Transcribe voice memos:**
```
/collect:start
[Send 3 voice memos from meetings]
/collect:go "Summarize action items from these meeting recordings"
```

**Combined analysis:**
```
/collect:start
[Send text notes]
[Send related images]
[Send voice memo with context]
/collect:go "Create a comprehensive report from these materials"
```

### Queue Management

- **Persistent** - Queue survives bot restarts
- **Per-user** - Each user has their own queue
- **Status display** - Shows count of each item type
- **Clear option** - Remove items without exiting collect mode

---

## Plugin System

Extensible architecture for adding new bot capabilities without modifying core code.

### Architecture

**Plugin lifecycle:**
1. **Discovery** - Scan `plugins/` directory
2. **Loading** - Import plugin module and metadata
3. **Activation** - Call plugin lifecycle hooks
4. **Runtime** - Register handlers and services
5. **Deactivation** - Clean up resources

### Built-in Plugins

#### claude_code
Full Claude Code SDK integration with streaming responses, session persistence, and tool display.

**Location:** `plugins/claude_code/`

**Features:**
- Claude session management
- Real-time tool execution display
- Auto-send generated files
- Model selection

#### pdf
PDF generation and manipulation capabilities.

**Location:** `plugins/pdf/`

**Features:**
- Generate PDFs from text
- Extract text from PDFs
- Merge/split PDF files

### Creating a Plugin

**1. Create plugin directory:**
```
plugins/my_plugin/
├── plugin.yaml       # Metadata
├── plugin.py         # Main plugin class
├── services/         # Business logic
└── handlers/         # Command handlers
```

**2. Define metadata (plugin.yaml):**
```yaml
name: my_plugin
version: 1.0.0
description: My custom plugin
author: Your Name
dependencies:
  - claude_code  # Optional plugin dependencies
```

**3. Implement plugin class (plugin.py):**
```python
from src.plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    async def on_load(self):
        """Called when plugin is loaded"""
        self.logger.info("Plugin loaded")

    async def on_activate(self):
        """Called when plugin is activated"""
        self.logger.info("Plugin activated")

    def get_command_handlers(self):
        """Return dict of command handlers"""
        return {
            "mycommand": self.handle_my_command
        }

    async def handle_my_command(self, update, context):
        """Handle /mycommand"""
        await update.message.reply_text("Hello from my plugin!")
```

**4. Register plugin:**
Plugins in `plugins/` directory are automatically discovered.

### Plugin Development

For complete plugin development guide, see [docs/PLUGINS.md](docs/PLUGINS.md) and [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

---

## Voice & Video Transcription

Automatic transcription of voice messages and videos using Groq Whisper with optional LLM-based correction.

### Transcription Pipeline

1. **Download** audio/video file via subprocess
2. **Extract audio** (for video files)
3. **Transcribe** using Groq Whisper API
4. **Correct** transcription with LLM (optional)
5. **Send** transcription to user
6. **Auto-forward** to Claude (in locked mode)

### Correction Levels

Configure transcription correction in settings:

| Level | Description | Use Case |
|-------|-------------|----------|
| **Off** | No correction | Clean audio, technical terms |
| **Light** | Fix obvious typos only | Good quality audio |
| **Moderate** | Fix grammar and structure | Normal conversation |
| **Aggressive** | Full rewrite for clarity | Poor quality audio, heavy accent |

**Configure:**
```
/settings
→ Transcription Correction: [Off/Light/Moderate/Aggressive]
```

### Auto-Forward to Claude

In locked mode, transcriptions are automatically sent to Claude:

1. Voice message received
2. Transcription generated
3. Correction applied (if configured)
4. Automatically forwarded to Claude Code
5. Claude responds in context

### Supported Formats

**Voice:**
- OGG (Telegram default)
- MP3
- WAV
- M4A

**Video:**
- MP4
- MOV
- AVI
- MKV

### Technical Details

**Services:**
- `src/services/voice_service.py` - Transcription via Groq
- `src/services/transcript_corrector.py` - LLM-based correction
- `src/bot/combined_processor.py` - Audio extraction and routing

**Subprocess isolation:**
All transcription operations use subprocess to avoid async blocking in the webhook context.

---

## Obsidian Integration

Read, search, and edit Obsidian vault notes through Telegram with clickable wikilinks and deep link navigation.

### Features

- **View notes** in Telegram
- **Clickable wikilinks** with deep link navigation
- **Vault operations** through Claude sessions
- **Auto-linking** of vault paths in Claude responses

### Commands

**View a note:**
```
/note <note name>
```

**Examples:**
```
/note Index
/note Projects/MyProject
/note Daily/20250122
```

### Wikilink Support

Notes containing wikilinks are automatically made clickable:

```markdown
See [[Index]] for overview.
Related: [[Projects/MyProject]]
```

Clicking a wikilink:
1. Opens note in Telegram (if available)
2. Or opens in Obsidian app via deep link

### Deep Links

Deep links use Obsidian URI scheme:
```
obsidian://open?vault=YourVault&file=Path/To/Note
```

**Generated for:**
- Wikilinks in messages
- Note references in Claude responses
- Full vault paths mentioned by Claude

### Vault Operations via Claude

**Read notes:**
```
/claude Show me my Index note
```

**Search vault:**
```
/claude Search my vault for "project ideas"
```

**Edit notes:**
```
/claude Add a new section to my Index note about recent projects
```

**Create notes:**
```
/claude Create a new note called "Meeting Notes 2025-01-22"
```

### Auto-Linking

Claude Code automatically converts full vault paths to clickable Obsidian links:

```
Created note: /Users/name/vault/Research/Notes/Idea.md
                    ↓
Created note: [[Research/Notes/Idea]] (clickable)
```

### Configuration

Set in `.env`:
```bash
OBSIDIAN_VAULT_PATH=/path/to/your/vault
OBSIDIAN_VAULT_NAME=vault
```

### Technical Details

**Services:**
- `src/services/vault_user_service.py` - Vault operations
- `src/services/link_service.py` - Wikilink parsing and deep links
- `src/bot/handlers/note_commands.py` - Note command handler

---

## Message Buffering

Combine multi-part messages into a single prompt before processing with Claude.

### How It Works

1. **Detection**: First message starts the buffer
2. **Collection**: Subsequent messages added to buffer
3. **Timeout**: 2.5 seconds after last message
4. **Flush**: All messages combined and processed together

### Supported Content

- Text messages
- Images with captions
- Voice messages (transcribed)
- Videos (transcribed)
- Documents with descriptions
- Contacts

### Use Cases

**Multi-part prompts:**
```
/claude Analyze this code
<paste code snippet>
<paste more code>
Focus on security issues
```

**Image + description:**
```
/claude
<send image>
What's the architectural style of this building?
```

**Multiple images:**
```
/claude Compare these photos
<send image 1>
<send image 2>
<send image 3>
```

### Configuration

**Buffer timeout:** 2.5 seconds (hard-coded)

**Special handling:**
- `/claude` commands start immediate buffering
- Voice messages in locked mode are buffered
- Reply context is preserved during buffering

### Technical Details

**Services:**
- `src/services/message_buffer.py` - Message buffering logic
- `src/bot/combined_processor.py` - Message routing and processing

---

## Image Analysis

AI-powered image analysis with multiple modes and vector similarity search.

### Modes

#### Default Mode
Quick description in ≤40 words:
```
/mode default
<send image>
```

#### Artistic Mode
In-depth analysis with specialized presets:
```
/mode artistic Critic
<send image>
```

**Available presets:**
- **Critic** - Composition, color theory, technique analysis
- **Photo-coach** - Constructive feedback for improvement
- **Historian** - Historical context and art movements
- **Technical** - Camera settings, lighting, post-processing

### Quick Commands

```
/analyze        # Artistic Critic mode
/coach          # Artistic Photo-coach mode
```

### Vector Similarity Search

In artistic mode, the bot:
1. Generates embedding for the image analysis
2. Stores in vector database (sqlite-vss)
3. Finds similar images from your history
4. Shows top 3 similar images with similarity scores

### Analysis Pipeline

1. **Download** image from Telegram
2. **Compress** to optimize API costs
3. **Analyze** using OpenAI Vision API
4. **Generate embedding** (artistic mode only)
5. **Store** results in database
6. **Find similar** images (if available)
7. **Reply** with analysis and similar images

### Configuration

**Mode configuration:**
Edit `config/modes.yaml`:

```yaml
modes:
  default:
    prompt: "Describe the image in ≤40 words..."
    embed: false
  artistic:
    embed: true
    presets:
      - name: "Critic"
        prompt: "Analyze composition, color theory..."
      - name: "Photo-coach"
        prompt: "Provide constructive feedback..."
```

### Technical Details

**Services:**
- `src/core/image_processor.py` - Image processing pipeline
- `src/services/llm_service.py` - Image analysis
- `src/services/embedding_service.py` - Vector embeddings
- `src/core/mode_manager.py` - Mode management

---

## Proactive Task Framework

Schedule and run background AI tasks that execute automatically at specified times.

**Environment prerequisites (fail-fast):**
- `GOOGLE_API_KEY` and `GOOGLE_SEARCH_CX` for web/image enrichment
- `FIRECRAWL_API_KEY` for link crawling (if tasks request Firecrawl)
- Toggle tasks via `enabled: true/false` in `scripts/proactive_tasks/task_registry.yaml`

### Built-in Tasks

#### daily-research
Fetch and summarize AI research papers, send to Obsidian daily note.

**Schedule:** 10:00 AM daily

**Configuration:** `scripts/proactive_tasks/task_registry.yaml`

**Output:**
- Summary of recent papers
- Key findings and highlights
- Links to full papers
- Saved to daily note

### Task Management

**List all registered tasks:**
```bash
python -m scripts.proactive_tasks.task_runner list
```

**Run task manually:**
```bash
python -m scripts.proactive_tasks.task_runner run daily-research
```

**Dry-run (preview without executing):**
```bash
python -m scripts.proactive_tasks.task_runner run daily-research --dry-run
```

**Generate launchd plist:**
```bash
python -m scripts.proactive_tasks.task_runner generate-plist daily-research --install
```

**Activate task schedule:**
```bash
launchctl load ~/Library/LaunchAgents/com.telegram-agent.daily-research.plist
```

### Creating Custom Tasks

**1. Define task in registry (`scripts/proactive_tasks/task_registry.yaml`):**
```yaml
tasks:
  my-task:
    name: "My Custom Task"
    description: "Does something useful"
    schedule: "0 9 * * *"  # Cron format: 9:00 AM daily
    enabled: true
    topics:
      - "Topic to research"
    output:
      format: "markdown"
      destination: "telegram"
      chat_ids: [12345]  # Your chat ID
```

**2. Create task class (`scripts/proactive_tasks/tasks/my_task.py`):**
```python
from scripts.proactive_tasks.base_task import BaseTask

class MyTask(BaseTask):
    async def execute(self):
        """Execute the task"""
        self.logger.info("Running my task")

        # Do something useful
        result = await self.do_research()

        # Send to configured destination
        await self.send_output(result)

        return {"status": "success"}
```

**3. Register task class:**
Add import in `scripts/proactive_tasks/task_runner.py`.

### Task Configuration

**Task registry:** `scripts/proactive_tasks/task_registry.yaml`

**Options:**
- `schedule` - Cron expression for scheduling
- `enabled` - Enable/disable task
- `topics` - List of topics for research tasks
- `output.format` - Output format (markdown, json, plain)
- `output.destination` - Where to send (telegram, file, obsidian)
- `output.chat_ids` - Telegram chat IDs to send to

### Launchd Integration

Each task can have a launchd plist for macOS scheduling:

**Location:** `~/Library/LaunchAgents/com.telegram-agent.<task-name>.plist`

**Management:**
```bash
# Load (activate)
launchctl load ~/Library/LaunchAgents/com.telegram-agent.daily-research.plist

# Unload (deactivate)
launchctl unload ~/Library/LaunchAgents/com.telegram-agent.daily-research.plist

# Check status
launchctl list | grep telegram-agent

# View logs
cat logs/launchd_daily_research.log
```

---

## Additional Resources

### Documentation

- [README.md](README.md) - Quick start and command reference
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) - Development guide
- [docs/PLUGINS.md](docs/PLUGINS.md) - Plugin development
- [docs/SRS_INTEGRATION.md](docs/SRS_INTEGRATION.md) - SRS technical details
- [docs/DESIGN_SKILLS.md](docs/DESIGN_SKILLS.md) - Design skills guide
- [CLAUDE.md](CLAUDE.md) - Developer instructions
- [CHANGELOG.md](CHANGELOG.md) - Recent changes

### Configuration Files

- `config/modes.yaml` - Image analysis modes
- `config/settings.yaml` - Application settings
- `config/design_skills.yaml` - Design skills configuration
- `scripts/proactive_tasks/task_registry.yaml` - Proactive task definitions
- `.env` / `.env.local` - Environment variables

### Database

- `data/telegram_agent.db` - Main SQLite database
- `data/srs/schedule.db` - SRS card schedule database

### Logs

- `logs/app.log` - Main application log
- `logs/errors.log` - Error-only log
- `logs/launchd_*.log` - Launchd service logs
