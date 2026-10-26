# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install system dependencies (ffmpeg is essential for audio decoding)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install cloudflared for Universal Quick Tunnel support
RUN curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb \
    && dpkg -i /tmp/cloudflared.deb \
    && rm -f /tmp/cloudflared.deb

# Install Deno (official recommended JS engine for yt-dlp signature decryption)
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

# Hugging Face Spaces runs as user with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    MEIKOVA_LOOP_HOST=0.0.0.0 \
    MEIKOVA_LOOP_PORT=7860 \
    MEIKOVA_LOOP_MULTIUSER=1 \
    MEIKOVA_LOOP_DATA=/home/user/app/data

WORKDIR $HOME/app

# Install lightweight CPU versions of torch & torchaudio first
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install Python requirements
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --no-deps demucs beat-this onnxruntime

# Copy project files
COPY --chown=user:user . .

# Ensure data directory exists and is writable
RUN mkdir -p data/library data/pairs data/models

# Hugging Face Spaces exposes port 7860 by default
EXPOSE 7860

CMD ["python", "-m", "loopbox.server"]
