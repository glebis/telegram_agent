#!/bin/bash
# Startup script for Railway deployment

# Get PORT from environment or use 8000 as default
PORT="${PORT:-8000}"

echo "Starting server on port: $PORT"

# Start the application with the correct port
exec python -m uvicorn src.main:app --host 0.0.0.0 --port "$PORT"
