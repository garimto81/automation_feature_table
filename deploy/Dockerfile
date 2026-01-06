# Poker Hand Auto-Capture System
# For deployment on Synology NAS with Docker/Container Manager

FROM python:3.11-slim

LABEL maintainer="Poker Hand Capture Team"
LABEL description="PokerGFX JSON file processor for hand capture and classification"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default to JSON mode for NAS deployment
ENV POKERGFX_MODE=json
ENV POKERGFX_JSON_PATH=/watch
ENV POKERGFX_PROCESSED_DB=/app/data/processed_files.json

# Health check - verify Python can import main module
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.main import PokerHandCaptureSystem; print('OK')" || exit 1

# Run the application
CMD ["python", "-m", "src.main"]
