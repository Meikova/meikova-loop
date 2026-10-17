"""Hugging Face Spaces Gradio entrypoint for MashLoop."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MASHLOOP_HOST", "0.0.0.0")
os.environ.setdefault("MASHLOOP_PORT", os.environ.get("PORT", "7860"))
os.environ.setdefault("MASHLOOP_MULTIUSER", "1")
os.environ.setdefault("MASHLOOP_DATA", str(ROOT / "data"))

import gradio as gr
from fastapi.staticfiles import StaticFiles
from loopbox.config import PORT, HOST, AUDIO_TTL_S, MULTIUSER, WEB_DIR
from loopbox.server import app as fastapi_app, worker, sessions

# Satisfies Hugging Face ZeroGPU startup scanner
try:
    import spaces
    @spaces.GPU
    def _gpu_entry():
        pass
except (ImportError, Exception):
    def _gpu_entry():
        pass


CSS = """
body, html, .gradio-container, .main, gradio-app {
    margin: 0 !important;
    padding: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    max-width: 100% !important;
    overflow: hidden !important;
    background: #0b0d10 !important;
}
footer { display: none !important; }
.contain { padding: 0 !important; }
#mashloop-frame {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    border: none;
    z-index: 999999;
}
"""

with gr.Blocks(title="Mash ∞ Loop") as demo:
    gr.HTML('<iframe id="mashloop-frame" src="/web/" allow="autoplay; accelerometer; gyroscope; screen-wake-lock; clipboard-write"></iframe>')

# Forward all MashLoop FastAPI API routes to Gradio's internal FastAPI app
for r in fastapi_app.router.routes:
    if getattr(r, "name", "") != "web":
        demo.app.router.routes.append(r)

# Mount static web assets
demo.app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="mashloop_web")
if (WEB_DIR / "css").exists():
    demo.app.mount("/css", StaticFiles(directory=WEB_DIR / "css"))
if (WEB_DIR / "js").exists():
    demo.app.mount("/js", StaticFiles(directory=WEB_DIR / "js"))
if (WEB_DIR / "img").exists():
    demo.app.mount("/img", StaticFiles(directory=WEB_DIR / "img"))
if (WEB_DIR / "audio").exists():
    demo.app.mount("/audio", StaticFiles(directory=WEB_DIR / "audio"))

app = demo.app

if __name__ == "__main__":
    worker.start()
    if MULTIUSER:
        worker.start_retention(AUDIO_TTL_S, sessions.in_use)
    else:
        sessions.local().link()

    port = int(os.environ.get("PORT", PORT))
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        css=CSS,
        show_error=True
    )
