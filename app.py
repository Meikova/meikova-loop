"""Hugging Face Spaces Gradio entrypoint for MashLoop."""
import os
import sys
from pathlib import Path

# Fix Python 3.12 asyncio bug: ValueError: Invalid file descriptor: -1 on BaseEventLoop.__del__
try:
    from asyncio.selector_events import BaseSelectorEventLoop
    _orig_close_self_pipe = BaseSelectorEventLoop._close_self_pipe
    def _safe_close_self_pipe(self):
        try:
            if getattr(self, '_ssock', None) is not None and self._ssock.fileno() != -1:
                _orig_close_self_pipe(self)
            else:
                self._ssock = None
                self._csock = None
        except Exception:
            pass
    BaseSelectorEventLoop._close_self_pipe = _safe_close_self_pipe
except Exception:
    pass

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


_worker_started = False
def _ensure_worker():
    global _worker_started
    if not _worker_started:
        worker.start()
        if MULTIUSER:
            worker.start_retention(AUDIO_TTL_S, sessions.in_use)
        else:
            sessions.local().link()
        _worker_started = True

_ensure_worker()

HEAD = """
<script>
  try {
    if (window.top === window.self && (location.pathname === '/' || location.pathname === '')) {
      location.replace('/web/');
    }
  } catch (e) {}
</script>
"""

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

def _mount_mashloop(target_app):
    if not target_app:
        return
    for r in fastapi_app.router.routes:
        if getattr(r, "name", "") != "web" and r not in target_app.router.routes:
            target_app.router.routes.append(r)
    target_app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="mashloop_web")
    if (WEB_DIR / "css").exists():
        target_app.mount("/css", StaticFiles(directory=WEB_DIR / "css"))
    if (WEB_DIR / "js").exists():
        target_app.mount("/js", StaticFiles(directory=WEB_DIR / "js"))
    if (WEB_DIR / "img").exists():
        target_app.mount("/img", StaticFiles(directory=WEB_DIR / "img"))
    if (WEB_DIR / "audio").exists():
        target_app.mount("/audio", StaticFiles(directory=WEB_DIR / "audio"))

# Pre-mount on demo.app for any direct ASGI usage
_mount_mashloop(demo.app)
app = demo.app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", PORT))
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        head=HEAD,
        css=CSS,
        ssr_mode=False,
        show_error=True,
        prevent_thread_lock=True
    )

    # Post-mount on demo.server_app because launch() recreates server_app
    _mount_mashloop(demo.server_app)

    try:
        demo.block_thread()
    except (KeyboardInterrupt, SystemExit):
        demo.close()

