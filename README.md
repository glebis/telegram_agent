# Telegram Agent v0.3

A Telegram bot with advanced image processing capabilities, vision AI analysis, and web admin interface. Supports multiple analysis modes, vector similarity search, and MCP (Model Context Protocol) integration.

## Features

- **Image Processing Pipeline**: Download, compress, analyze, and store images with AI-powered analysis
- **Multiple Analysis Modes**: Default (quick description) and Artistic (in-depth analysis with presets)
- **Vector Similarity Search**: Find similar images using embeddings (artistic mode)
- **Web Admin Interface**: User management, chat monitoring, and bot statistics
- **MCP Integration**: Auto-discovery and execution of MCP tools
- **Background Processing**: Async image analysis and embedding generation

## Quick Start

### Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key (or other LLM provider)
- ngrok (for local webhook development)

### Installation

1. Clone and setup:
```bash
git clone <repository-url>
cd telegram_agent
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env.local
# Edit .env.local with your API keys and settings
```

3. Initialize database:
```bash
python -m src.core.database init
```

4. Start the application:
```bash
# In one terminal - start the FastAPI server
python -m uvicorn src.main:app --reload --port 8000

# In another terminal - start ngrok tunnel
ngrok http 8000

# Copy the ngrok URL and update TELEGRAM_WEBHOOK_URL in .env.local
# Then set the webhook:
python -m src.bot.setup_webhook
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

Key variables:
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `OPENAI_API_KEY`: OpenAI API key for vision analysis
- `DATABASE_URL`: SQLite database path
- `TELEGRAM_WEBHOOK_URL`: ngrok URL for webhook

### Mode Configuration

Edit `config/modes.yaml` to customize analysis modes and presets:

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
```

## Usage

### Bot Commands

- `/start` - Initialize chat and show welcome message
- `/mode default` - Switch to default analysis mode
- `/mode artistic Critic` - Switch to artistic mode with Critic preset
- `/analyze` - Alias for artistic Critic mode
- `/coach` - Alias for artistic Photo-coach mode
- `/help` - Show available commands

### Image Analysis

1. Send any image to the bot
2. Bot will automatically:
   - Download and compress the image
   - Analyze using the current mode
   - Generate embeddings (if artistic mode)
   - Store results in database
   - Reply with analysis and similar images (if available)

### Web Admin Interface

Access the admin interface at `http://localhost:8000/admin`:

- User management (ban, unban, group assignment)
- Chat monitoring and message sending
- Bot statistics and analytics
- Real-time chat observation

## Development

### Project Structure

```
telegram_agent/
├── src/
│   ├── bot/          # Telegram bot handlers
│   ├── api/          # FastAPI admin endpoints  
│   ├── core/         # Business logic
│   ├── models/       # Database models
│   ├── services/     # External integrations
│   └── utils/        # Utilities
├── config/           # YAML configurations
├── data/             # Image storage and database
├── tests/            # Test suite
└── logs/             # Application logs
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests
pytest -m unit

# Run only integration tests  
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Code Quality

```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/

# Pre-commit hooks (recommended)
pre-commit install
pre-commit run --all-files
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Check current version
alembic current
```

## Deployment

### Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f telegram-agent

# Stop services
docker-compose down
```

### Production Considerations

- Use PostgreSQL instead of SQLite for production
- Configure proper logging and monitoring
- Set up SSL/TLS for webhook endpoints
- Implement rate limiting and security measures
- Use cloud storage for images (S3, etc.)
- Set up backup strategies for database and images

## API Documentation

Once running, visit:
- API docs: `http://localhost:8000/docs`
- Alternative docs: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

## MCP Integration

The bot supports MCP (Model Context Protocol) for extending capabilities:

1. Configure MCP servers in `config/mcp_servers.json`
2. Available tools are auto-discovered
3. LLM can call tools during image analysis
4. Results are incorporated into responses

## Troubleshooting

### Common Issues

1. **Webhook not receiving updates**:
   - Check ngrok is running and URL is correct
   - Verify bot token is valid
   - Check webhook status: `curl -X GET "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`

2. **Image processing fails**:
   - Verify OpenAI API key and credits
   - Check network connectivity
   - Review logs in `logs/app.log`

3. **Database errors**:
   - Check database file permissions
   - Run `alembic upgrade head` to apply migrations
   - Verify DATABASE_URL is correct

4. **Mode switching not working**:
   - Validate `config/modes.yaml` syntax
   - Check chat exists in database
   - Review mode configuration

### Debug Commands

```bash
# Check database content
sqlite3 data/telegram_agent.db ".tables"
sqlite3 data/telegram_agent.db "SELECT * FROM chats LIMIT 5;"

# Test image processing
python -c "from src.core.image_processor import process_image; print(process_image('tests/fixtures/test.jpg'))"

# Validate configuration
python -c "from src.core.config import get_settings; print(get_settings())"
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run quality checks: `black`, `flake8`, `mypy`, `pytest`
5. Submit a pull request

## License

[MIT License](LICENSE)

## Support

- Create an issue for bug reports
- Check existing issues for solutions
- Review `CLAUDE.md` for development guidelines