FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for building packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libsqlite3-dev \
    pkg-config \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=production

# Copy requirements first for better Docker layer caching
COPY requirements-simple.txt ./

# Install Python dependencies (use simple requirements)
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements-simple.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/raw data/img logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Make the startup script executable
RUN chmod +x /app/railway_start.py

# Run the application using the Python startup script
CMD ["python", "/app/railway_start.py"]