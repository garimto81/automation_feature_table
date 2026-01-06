# Poker Hand Auto-Capture System
# For deployment on Synology NAS with Docker/Container Manager
# Supports: x86_64 (Intel/AMD) and ARM64 (DS220j, DS223 등)

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt


# Production image
FROM python:3.11-slim

LABEL maintainer="Poker Hand Capture Team"
LABEL description="PokerGFX JSON file processor for hand capture and classification"
LABEL org.opencontainers.image.source="https://github.com/garimto81/claude"
LABEL org.opencontainers.image.version="0.1.0"

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

# Copy pre-built wheels and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Copy application code
COPY src/ ./src/

# Create necessary directories with proper permissions
RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=Asia/Seoul

# Default to JSON mode for NAS deployment
ENV POKERGFX_MODE=json
ENV POKERGFX_JSON_PATH=/watch
ENV POKERGFX_PROCESSED_DB=/app/data/processed_files.json

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from src.main import PokerHandCaptureSystem; print('OK')" || exit 1

# Run the application
CMD ["python", "-m", "src.main"]
