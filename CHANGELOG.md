# Changelog

## [Unreleased]

### Added (Last 2 Weeks)
- **Design Skills Integration** (2025-01-20): Automatic UI/UX design guidance from Impeccable Style, UI Skills, and Rams.ai. Enhances Claude Code with best practices for typography, accessibility, visual hierarchy, and WCAG AA compliance. [DESIGN_SKILLS_INTEGRATION.md, docs/DESIGN_SKILLS.md]
- **Enhanced Reply Context** (2025-01-18): Extract full context from `reply_to_message` for all message types (text, images, videos, voice, documents). Fallback to extracted content when cache misses. [REPLY_CONTEXT_IMPLEMENTATION.md]
- **Transcript Correction** (2025-01-11): LLM-based transcript correction with configurable levels (off, light, moderate, aggressive) for voice/video messages [#12]
- **Auto-forward Voice to Claude** (2025-01-11): Automatically forward voice messages to Claude in locked mode, with new session trigger [#13, #14]
- **Model Settings UI** (2025-01-11): Toggle model button visibility and set default Claude model (haiku/sonnet/opus) via `/settings` [FEATURE_MODEL_SETTINGS.md]
- **Launchd Service Configuration** (2025-01-08): System service management with health monitoring and daily review scheduling
- **Worker Queue Service** (2025-01-05): Background job processing with queue management and control scripts
- **Conversation Analysis Scripts** (2025-01-07): Tools for analyzing chat patterns and message flows
- **Expanded Test Coverage** (2025-01-18): Comprehensive tests for services, utilities, and core modules

### Changed
- **Modular Handler Architecture** (2025-01-01): Split monolithic handlers into focused modules (core, claude, collect, note, mode commands)
- **Frontmatter Support** (2025-01-03): Enhanced Obsidian vault integration with frontmatter parsing and formatting
- **Simplified PDF Plugin** (2025-01-03): Refactored PDF generation plugin implementation

### Fixed
- **Duplicate Callback Processing** (2025-01-11): Prevent duplicate callback handler registration in Claude plugin
- **Webhook Endpoint Tests** (2025-01-11): Updated webhook tests to reflect current implementation

## [0.7.0] - 2024-12

### Major Features
- Claude Code SDK integration with session persistence
- Message buffering system for multi-part prompts
- Reply context tracking for conversation threading
- Collect mode for batch processing
- Obsidian vault integration with wikilink support
- Voice and video transcription via Groq Whisper
- Dynamic keyboard generation system
- Plugin architecture with claude_code and pdf plugins

### Core Components
- FastAPI backend with webhook support
- SQLAlchemy ORM with SQLite + vector search extensions
- Graceful shutdown with background task tracking
- Subprocess isolation for blocking operations
- Health monitoring with auto-recovery
- Structured logging with JSON output

### Bot Commands
- `/claude` - Interactive AI sessions with Claude Code SDK
- `/collect:start|go|stop|status|clear` - Batch processing mode
- `/note <name>` - View Obsidian vault notes
- `/settings` - User preferences and model selection
- `/mode` - Switch analysis modes

### Documentation
- ARCHITECTURE.md - System design and message flow
- CONTRIBUTING.md - Development guidelines and plugin creation
- REPLY_CONTEXT_IMPLEMENTATION.md - Reply context feature details
- FEATURE_MODEL_SETTINGS.md - Model settings feature details
- BUGFIX-stop-button-stuck.md - Stop button fix documentation

