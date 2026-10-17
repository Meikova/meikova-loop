"""Hugging Face Spaces entrypoint for MashLoop."""
import os
import sys
from pathlib import Path

# Ensure root directory is in sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Default environment configuration for Hugging Face Spaces
os.environ.setdefault("MASHLOOP_HOST", "0.0.0.0")
os.environ.setdefault("MASHLOOP_PORT", os.environ.get("PORT", "7860"))
os.environ.setdefault("MASHLOOP_MULTIUSER", "1")
os.environ.setdefault("MASHLOOP_DATA", str(ROOT / "data"))

import uvicorn
from loopbox.config import PORT, HOST, AUDIO_TTL_S, MULTIUSER
from loopbox.server import app, worker, sessions

# Start background workers
worker.start()
if MULTIUSER:
    worker.start_retention(AUDIO_TTL_S, sessions.in_use)
else:
    sessions.local().link()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", PORT))
    host = os.environ.get("MASHLOOP_HOST", "0.0.0.0")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
