# Telegram Agent - Railway Deployment Guide

## 🚀 Quick Deploy to Railway

### Prerequisites
- Railway account (sign up at [railway.app](https://railway.app))
- GitHub repository with this code
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))
- OpenAI API Key

### Deployment Steps

1. **Connect Repository to Railway**
   - Go to [railway.app](https://railway.app)
   - Click "Deploy from GitHub repo"
   - Select this repository

2. **Configure Environment Variables**
   Set these in Railway's environment variables:
   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   OPENAI_API_KEY=your_openai_key_here
   TELEGRAM_WEBHOOK_SECRET=your_webhook_secret_here
   DATABASE_URL=sqlite+aiosqlite:///./data/telegram_agent.db
   DEBUG=false
   LOG_LEVEL=INFO
   ```

3. **Deploy**
   - Railway will automatically detect the `Dockerfile`
   - Uses `requirements-simple.txt` (lightweight production dependencies)
   - No heavy ML libraries (PyTorch, OpenCV) for faster builds

### 🔧 Architecture

**Production (Railway):**
- ✅ FastAPI + Uvicorn web server
- ✅ Telegram Bot integration  
- ✅ Image processing with PIL
- ✅ LLM analysis (OpenAI GPT-4o-mini)
- ✅ SQLite database
- ✅ Structured logging
- ❌ Vector similarity search (fallback mode)
- ❌ ML embeddings (deterministic fallback)

**Local Development:**
- ✅ All production features
- ✅ PyTorch + sentence-transformers
- ✅ OpenCV image processing
- ✅ Full vector similarity search
- ✅ ML-based embeddings

### 📝 Files Overview

| File | Purpose |
|------|---------|
| `Dockerfile` | Railway deployment container |
| `railway.toml` | Railway platform configuration |
| `requirements-simple.txt` | Lightweight production dependencies |
| `requirements.txt` | Full development dependencies |

### 🔍 Health Check

After deployment, your bot will be available at:
- Health endpoint: `https://your-app.railway.app/health`
- Admin interface: `https://your-app.railway.app/admin`

### 🐛 Troubleshooting

**Build Issues:**
- Check Railway build logs for dependency conflicts
- Ensure all environment variables are set
- Verify Telegram bot token is valid

**Runtime Issues:**
- Check Railway deployment logs
- Verify webhook URL is set correctly in Telegram
- Test health endpoint

### 📊 Logging

All image processing errors are logged to structured JSON format:
- Application logs: Available in Railway dashboard
- Comprehensive error tracking with user context
- Step-by-step processing logs

### 🔐 Security

- API keys stored as Railway environment variables
- No secrets in code repository
- Webhook validation enabled
- Database file stored in persistent volume