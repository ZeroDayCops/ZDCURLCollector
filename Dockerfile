# ──────────────────────────────────────────────────────────────────
# Social Media Scraper API - Dockerfile
# Python 3.12 + Playwright Chromium + yt-dlp
# ──────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System deps for Playwright Chromium ──────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium runtime deps
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libfontconfig1 \
    libxshmfence1 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    # Fonts
    fonts-liberation \
    fonts-noto-color-emoji \
    # General tools
    curl \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── App setup ────────────────────────────────────────────────────
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only to keep image lean)
RUN playwright install chromium

# ── Copy application source ────────────────────────────────────
COPY app/ ./app/
COPY static/ ./static/
COPY run.py .
COPY .env* ./

# ── Session & output dirs ─────────────────────────────────────
RUN mkdir -p /app/sessions /app/debug_screenshots

# ── Environment variables (override at runtime) ───────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV SESSIONS_DIR=/app/sessions
ENV DEBUG_SCREENSHOTS=false

# Expose API port
EXPOSE 8000

# ── Healthcheck ───────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Run the API ───────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
