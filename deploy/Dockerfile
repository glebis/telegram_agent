FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
#   - ffmpeg: audio processing (Groq Whisper voice transcription)
#   - curl: healthcheck probe
#   - build-essential + libsqlite3-dev: native extensions (sqlite-vss)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsqlite3-dev \
    pkg-config \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=production

# Copy requirements first for better Docker layer caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create runtime directories (volumes will overlay these in production)
RUN mkdir -p data logs

# Create non-root user
RUN groupadd -r verity && useradd -r -g verity -d /app verity \
    && chown -R verity:verity /app

# Switch to non-root user
USER verity

# Expose the default port
EXPOSE 8000

# Healthcheck against the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Start uvicorn directly
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
