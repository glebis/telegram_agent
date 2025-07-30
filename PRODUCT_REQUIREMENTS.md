# Telegram Agent - Product Requirements v0.3

## Overview
A Telegram bot with image processing capabilities, vision AI analysis, and web admin interface. Supports multiple analysis modes, vector similarity search, and MCP tool integration.

## Core Features

### 1. Vision Pipeline (Image Processing)
- **Download**: Grab highest-resolution image from Telegram, save original to `/data/raw/`
- **Compress**: Resize to max 1024px, save to `/data/img/` (≤300 kB)
- **Analyze**: LiteLLM → GPT-4o-mini vision with mode-specific prompts
- **Embed**: (Artistic mode only) Generate 768-D vectors for similarity search
- **Store**: SQLite storage with metadata and analysis JSON
- **Reply**: Send analysis + similar images (if artistic mode)

### 2. Mode System
- **Default Mode**: 
  - Describe image in ≤40 words
  - Extract visible text verbatim
  - No embedding generation
- **Artistic Mode**:
  - Presets: "Critic" (composition analysis), "Photo-coach" (improvement advice)
  - Generate embeddings for similarity search
  - Show "Ähnliche Bilder" with inline buttons

### 3. User Management & Admin
- **Bot Interface**: Primary image browsing interface
- **Web Admin**: User management, chat monitoring, statistics
- **User Actions**: Ban users, delete chats, manual messaging, group assignment
- **Real-time Monitoring**: Live chat observation and intervention

### 4. MCP Integration
- Auto-discovery of available MCP servers/tools using `mcp` Python package
- Tool calling from LLM responses
- Support for claudemind approach to MCP discovery

## Technical Stack

### Backend
- **Framework**: FastAPI for web API and admin interface
- **Bot**: python-telegram-bot for Telegram integration
- **Database**: SQLite with sqlite-vss for vector search
- **LLM**: LiteLLM (default: GPT-4o-mini)
- **Image Processing**: Pillow for resizing/compression
- **Background Jobs**: Async task processing for image analysis
- **MCP**: `mcp` Python package for tool integration

### Configuration
- **Mode Config**: YAML files for prompts and presets
- **Environment**: .env.local, .env, environment variables for API keys
- **Settings**: YAML-based configuration management

### Development
- **Testing**: Mock APIs initially, switch to production
- **Quality**: Always lint and fix errors before building
- **Local Dev**: ngrok for webhook testing
- **Deployment**: TBD (focus on local development first)

## Database Schema

### Tables
```sql
-- Existing
CREATE TABLE chats (
  id INTEGER PRIMARY KEY,
  chat_id INTEGER UNIQUE,
  mode TEXT DEFAULT 'default',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- New
CREATE TABLE images (
  id INTEGER PRIMARY KEY,
  chat_id INTEGER REFERENCES chats(id),
  file_id TEXT,
  path TEXT,
  width INT,
  height INT,
  embed BLOB,
  analysis JSON,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  user_id INTEGER UNIQUE,
  username TEXT,
  banned BOOLEAN DEFAULT FALSE,
  user_group TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Vector Search
- sqlite-vss index on images.embed column
- Similarity search returns top K≈5 matches

## Dependencies
```
python-telegram-bot~=20.7
fastapi~=0.104
litellm~=1.40
pillow~=10.3
sqlite-vss~=0.3
opencv-python-headless~=4.8
pytesseract~=3.10
mcp~=1.0
pydantic~=2.5
uvicorn~=0.24
pytest~=7.4
pytest-asyncio~=0.21
```

## Project Structure
```
telegram_agent/
├── src/
│   ├── bot/                 # Telegram bot handlers
│   ├── api/                 # FastAPI endpoints
│   ├── core/                # Business logic
│   ├── models/              # Database models
│   ├── services/            # External service integrations
│   └── utils/               # Utilities
├── config/                  # YAML configurations
├── data/                    # Image storage (raw/, img/)
├── tests/                   # Test suite
├── requirements.txt
├── .env.example
├── docker-compose.yml
└── CLAUDE.md
```

---

## Open Questions & Decisions Needed

### 1. Background Job Processing
**Question**: Which background job system to use?
**Options**: 
- Celery with Redis broker (full-featured)
- FastAPI BackgroundTasks (simple, in-process)
- Custom async task queue with SQLite
**Decision Needed**: Balance between simplicity and scalability

### 2. Image Storage Strategy
**Question**: Long-term storage approach for images?
**Considerations**:
- Disk space management for originals vs compressed
- Retention policy (delete after N days?)
- Backup strategy for user images
**Decision Needed**: Storage limits and cleanup policies

### 3. Similarity Search UI
**Question**: How to display similar images?
**Options**:
- Telegram inline gallery with thumbnails
- Link back to web app for browsing
- Hybrid approach (thumbnails + web links)
**Decision Needed**: User experience preference

### 4. Error Handling & Resilience
**Question**: How to handle API failures gracefully?
**Considerations**:
- LLM API rate limits and failures
- Telegram API interruptions
- Image processing errors
**Decision Needed**: Retry policies and fallback strategies

### 5. Multi-language Support
**Question**: Should the bot support multiple languages?
**Considerations**:
- UI language selection
- Response language based on user preference
- Prompt translation for different languages
**Decision Needed**: Scope of internationalization

### 6. Performance & Scaling
**Question**: Expected load and performance requirements?
**Considerations**:
- Concurrent users and image processing
- Database query optimization
- Caching strategies for embeddings
**Decision Needed**: Performance benchmarks and optimization priorities

### 7. Security & Privacy
**Question**: Data privacy and security measures?
**Considerations**:
- Image data encryption at rest
- User data retention policies
- Admin access controls
**Decision Needed**: Security requirements and compliance needs

### 8. Testing Strategy Details
**Question**: Testing approach for external integrations?
**Considerations**:
- Mock vs real API testing
- Test data management
- Automated testing in CI/CD
**Decision Needed**: Testing depth and automation level

### 9. Configuration Management
**Question**: How to handle different deployment environments?
**Considerations**:
- Development vs production configs
- Feature flags for experimental features
- Dynamic configuration updates
**Decision Needed**: Configuration flexibility requirements

### 10. Monitoring & Observability
**Question**: What metrics and monitoring are needed?
**Considerations**:
- Bot usage statistics
- API response times and errors
- Image processing success rates
**Decision Needed**: Monitoring scope and tools