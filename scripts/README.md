# Development Scripts

This directory contains development scripts and conversation analysis tools for the Telegram Agent project.

## Table of Contents
1. [Directory Structure](#directory-structure)
2. [Development Scripts](#development-scripts-1)
3. [Deployment Scripts](#deployment-scripts)
4. [Integration Tests](#integration-tests)
5. [Conversation Analysis Tools](#conversation-analysis-tools)

---

## Directory Structure

```
scripts/
├── start_dev.py          # Main development startup script
├── start.sh              # Railway/production deployment script
├── setup_webhook.py      # Webhook management utility
├── check_port.py         # Port checking utility
├── tests/                # Integration test scripts
│   └── test_locked_mode.sh
├── proactive_tasks/      # Scheduled task framework
├── setup/                # Setup utilities
└── *.py, *.sh           # Various utility scripts
```

---

# Development Scripts

## Enhanced Start Script (`start_dev.py`)

The main development startup script with improved error handling and port management.

### New Features

- **Automatic Port Detection**: Automatically finds free ports when the default port is in use
- **Process Management**: Can kill existing processes on ports
- **Better Error Handling**: Detailed error messages and recovery suggestions
- **Health Checks**: Verifies that FastAPI server starts correctly
- **Enhanced Logging**: More detailed startup information

### Usage

```bash
# Basic start (with auto-port selection)
python scripts/start_dev.py start

# Start with specific options
python scripts/start_dev.py start --port 8000 --auto-port --kill-existing

# Skip ngrok/webhook for local development only
python scripts/start_dev.py start --skip-ngrok --skip-webhook

# Stop all services
python scripts/start_dev.py stop

# Stop specific port
python scripts/start_dev.py stop --port 8001

# Check service status
python scripts/start_dev.py status
```

### Options

- `--port`: Port to run FastAPI server on (default: 8000)
- `--auto-port`: Automatically find free port if specified port is in use (default: True)
- `--kill-existing`: Kill existing processes on the port (default: False)
- `--skip-ngrok`: Skip ngrok tunnel setup (default: False)
- `--skip-webhook`: Skip webhook setup (default: False)
- `--env-file`: Environment file to load (default: .env.local)

## Port Checker (`check_port.py`)

Utility script for checking and managing ports.

### Usage

```bash
# Check specific port
python scripts/check_port.py check 8000

# Kill processes on specific port
python scripts/check_port.py kill 8000

# Scan port range
python scripts/check_port.py scan 8000 8010
```

## Error Resolution

### "Address already in use" Error

When you see this error, you have several options:

1. **Automatic port selection** (recommended):
   ```bash
   python scripts/start_dev.py start --auto-port
   ```

2. **Kill existing processes**:
   ```bash
   python scripts/start_dev.py start --kill-existing
   ```

3. **Use different port**:
   ```bash
   python scripts/start_dev.py start --port 8002
   ```

4. **Check what's using the port**:
   ```bash
   python scripts/check_port.py check 8000
   ```

5. **Stop all services and restart**:
   ```bash
   python scripts/start_dev.py stop
   python scripts/start_dev.py start
   ```

### FastAPI Health Check Failures

If the FastAPI server starts but health checks fail:

1. Check if the server is actually running: `curl http://localhost:PORT/health`
2. Check server logs for errors
3. Verify database connectivity
4. Check environment variables

### Common Issues

- **Missing dependencies**: Run `pip install -r requirements.txt`
- **Database not running**: Start your database service
- **Environment variables**: Check `.env.local` file exists and has required variables
- **Port conflicts**: Use `--auto-port` or `--kill-existing` flags

## Development Workflow

1. **Start development environment**:
   ```bash
   python scripts/start_dev.py start
   ```

2. **Check status**:
   ```bash
   python scripts/start_dev.py status
   ```

3. **Stop when done**:
   ```bash
   python scripts/start_dev.py stop
   ```

## Troubleshooting

- Use `python scripts/check_port.py scan 8000 8010` to find available ports
- Use `python scripts/start_dev.py status` to check service health
- Check logs in the terminal output for detailed error messages
- Use `--skip-ngrok --skip-webhook` for local-only development

---

# Deployment Scripts

## Production Startup (`start.sh`)

Simple startup script for Railway and other cloud deployment platforms.

**Usage:**
```bash
# Uses PORT environment variable or defaults to 8000
./scripts/start.sh
```

The script runs uvicorn with the correct host binding for container environments.

---

# Integration Tests

Located in `scripts/tests/`, these are shell-based integration tests that verify end-to-end functionality.

## Auto-Lock Mode Test (`tests/test_locked_mode.sh`)

Tests that locked mode is automatically enabled when a Claude session is created.

**Usage:**
```bash
./scripts/tests/test_locked_mode.sh
```

**What it tests:**
- Creates test database entries
- Verifies session save triggers auto-lock
- Cleans up test data

**Note:** For unit tests, see `tests/` directory (pytest-based).

---

# Conversation Analysis Tools

Tools for analyzing Claude Code sessions from the Telegram bot to identify usage patterns, common use cases, and improvement opportunities.

## Scripts

### 1. `analyze_conversations.py`
Comprehensive analysis of conversation patterns and usage statistics.

**Usage:**
```bash
# Run full analysis
python3 scripts/analyze_conversations.py

# Save to file
python3 scripts/analyze_conversations.py -o analysis.json

# Quiet mode (no console output)
python3 scripts/analyze_conversations.py -o analysis.json --quiet

# Specify paths
python3 scripts/analyze_conversations.py \
  --db ~/path/to/telegram_agent.db \
  --log ~/path/to/app.log \
  --days 30
```

**Output includes:**
- Session statistics (total, active, reuse rate)
- Usage by date and user
- Tool usage patterns
- Model preferences
- Common errors
- Recommendations for improvements

### 2. `query_conversations.py`
Interactive tool for querying conversation database.

**Usage:**
```bash
# Search prompts by keyword
python3 scripts/query_conversations.py search "youtube"
python3 scripts/query_conversations.py search "create note" --limit 10

# Get sessions by date range
python3 scripts/query_conversations.py date-range 2026-01-01 2026-01-05

# Get longest-running sessions
python3 scripts/query_conversations.py longest --limit 5

# Get sessions by user
python3 scripts/query_conversations.py by-user
python3 scripts/query_conversations.py by-user --username glebkalinin

# Analyze prompt patterns
python3 scripts/query_conversations.py patterns

# Export data for training/analysis
python3 scripts/query_conversations.py export output.json --limit 100
```

### 3. `suggest_features.py`
AI-powered feature suggestion based on usage patterns.

**Usage:**
```bash
# Generate suggestions
python3 scripts/suggest_features.py

# Use existing analysis
python3 scripts/suggest_features.py \
  --analysis analysis.json \
  --output suggestions.json

# Quiet mode
python3 scripts/suggest_features.py -o suggestions.json --quiet
```

**Identifies:**
- Repeated patterns that could be automated
- Tool usage optimizations
- UX improvement opportunities
- Workflow automation candidates
- High-priority feature requests

## Automated Analysis Workflow

### Quick Weekly Analysis
```bash
#!/bin/bash
# Save as: scripts/run_weekly_analysis.sh
cd ~/ai_projects/telegram_agent

DATE=$(date +%Y%m%d)
OUTPUT_DIR=~/Research/vault/ai-research

python3 scripts/analyze_conversations.py \
  --output "$OUTPUT_DIR/${DATE}-telegram-analysis.json"

python3 scripts/suggest_features.py \
  --analysis "$OUTPUT_DIR/${DATE}-telegram-analysis.json" \
  --output "$OUTPUT_DIR/${DATE}-feature-suggestions.json"

echo "✅ Analysis complete: $OUTPUT_DIR/${DATE}-*"
```

Make executable: `chmod +x scripts/run_weekly_analysis.sh`

## Future Roadmap

### Phase 1: Enhanced Analysis (✅ Current)
- ✅ Database queries for session metadata
- ✅ Log parsing for tool usage
- ✅ Pattern identification
- ✅ Feature suggestions

### Phase 2: ML Integration
- [ ] Prompt clustering with embeddings
- [ ] Session similarity scoring
- [ ] Predictive session suggestions
- [ ] Anomaly detection for errors

### Phase 3: Automated Feature Development
- [ ] Auto-generate GitHub issues from suggestions
- [ ] Create feature branch with skeleton code
- [ ] Generate tests based on usage patterns
- [ ] Automated PR creation for high-confidence features

### Phase 4: Full Conversation Analysis
- [ ] Store full conversation transcripts
- [ ] Multi-turn conversation analysis
- [ ] Success/failure pattern detection
- [ ] User satisfaction metrics
