FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ffmpeg: MP3 extraction and some YouTube video/audio merges.
# Deno: required for yt-dlp's YouTube JavaScript challenge handling.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

ARG DENO_VERSION=2.9.7
RUN (curl -fsSL --retry 2 \
       "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" \
       -o /tmp/deno.zip \
       && unzip -q /tmp/deno.zip -d /usr/local/bin \
       && chmod +x /usr/local/bin/deno) \
    || echo 'WARNING: Deno unavailable; YouTube Shorts might fail'; \
    rm -f /tmp/deno.zip

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY *.py ./

CMD ["sh", "-c", "uvicorn main:api --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
