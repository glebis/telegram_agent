# Development Scripts

This directory contains enhanced development scripts for the Telegram Agent project.

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
