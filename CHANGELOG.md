# Changelog

## [Unreleased]

### Added
- **Opus 4.6 Support** (2025-02): Integrated Claude Opus 4.6 with adaptive thinking effort settings (low/medium/high/max), changed default model to Opus for better quality at competitive pricing ($5/$25 per MTok, 3x cheaper than Opus 4), 128K output token support
- **Interactive Setup Wizard** (2025-02): Questionary-based CLI wizard for guided first-time setup with idempotent .env.local management (46 tests)
- **Deep Research Command** (2025-01): `/research <topic>` - 4-stage pipeline (plan → search → synthesize → report) with PDF generation and Obsidian vault integration
- **Data Retention Service** (2025-01): Per-user GDPR-compliant data lifecycle enforcement (1 month / 6 months / 1 year / forever) with correct dual-ID-space handling
- **Accountability & Wellness** (2025-01): Tracker model (habits, medication, values), CheckIn model with scheduling, PollResponse with sentiment analysis
- **Voice Synthesis** (2025-01): Groq Orpheus TTS with 6 voices, 3 emotion styles, automatic text chunking
- **CI/CD Pipeline** (2025-01): GitHub Actions workflow with ruff, mypy, pytest, detect-secrets, pip-audit
- **Systemd Deployment** (2025-01): Cross-platform deployment via Docker Compose systemd service unit
- **Security Hardening** (2025-01): HMAC-SHA256 webhook validation, timing-safe comparison, image/payload size limits, rate limiting
- **Poll Reply Context** (2025-01): Track and forward poll responses to Claude for contextual analysis
- **Design Skills Integration** (2025-01-20): Automatic UI/UX design guidance from Impeccable Style, UI Skills, and Rams.ai. [docs/DESIGN_SKILLS.md]
- **Enhanced Reply Context** (2025-01-18): Extract full context from `reply_to_message` for all message types. [docs/REPLY_CONTEXT.md]
- **Transcript Correction** (2025-01-11): LLM-based transcript correction with configurable levels
- **Auto-forward Voice to Claude** (2025-01-11): Automatically forward voice messages to Claude in locked mode
- **Model Settings UI** (2025-01-11): Toggle model button visibility and set default Claude model via `/settings`
- **Launchd Service Configuration** (2025-01-08): System service management with health monitoring
- **Worker Queue Service** (2025-01-05): Background job processing with queue management
- **Conversation Analysis Scripts** (2025-01-07): Tools for analyzing chat patterns and message flows
- **Expanded Test Coverage**: 2400+ tests across services, utilities, and core modules

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
All documentation is in the `docs/` folder:
- ARCHITECTURE.md - System design and message flow
- CONTRIBUTING.md - Development guidelines and plugin creation
- DESIGN_SKILLS.md - UI/UX design guidance integration
- MODEL_SETTINGS.md - Model settings feature details
- QUICKREF.md - Quick reference guide
- REPLY_CONTEXT.md - Reply context feature details
- SRS_INTEGRATION.md - Spaced repetition system
- UX.md - User experience guidelines

