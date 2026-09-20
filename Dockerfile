FROM python:3.11-slim AS builder

WORKDIR /app

# Install system deps for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi httpx img2pdf pillow uvicorn[standard] yt-dlp

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install system deps required at runtime
# - ffmpeg: needed by yt-dlp for video/audio merging and MP3 conversion
# - curl: health checks, downloading
# - tzdata: timezone support
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code
COPY app.py instagram.py pdf.py youtube.py ./
COPY static/ ./static/
COPY logs/ ./logs/

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8585

CMD ["uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8585"]
