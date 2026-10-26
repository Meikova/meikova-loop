"""Hugging Face Spaces Gradio entrypoint for Meikova Loop."""
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

is_space = bool(os.environ.get("SPACE_ID"))
os.environ.setdefault("MEIKOVA_LOOP_HOST", "0.0.0.0")
os.environ.setdefault("MEIKOVA_LOOP_PORT", os.environ.get("PORT", "7860" if is_space else "8765"))
os.environ.setdefault("MEIKOVA_LOOP_MULTIUSER", "1")
os.environ.setdefault("MEIKOVA_LOOP_DATA", str(ROOT / "data"))

def _sync_private_code():
    is_space = bool(os.environ.get("SPACE_ID"))
    if not is_space and (ROOT / "loopbox" / "server.py").exists() and (ROOT / "web" / "index.html").exists():
        return
    if os.environ.get("_MEIKOVA_LOOP_SYNCED"):
        return
    gh_token = os.environ.get("GH_TOKEN")
    os.environ["_MEIKOVA_LOOP_SYNCED"] = "1"
    import urllib.request, zipfile, io
    print("Syncing codebase from GitHub Meikova/meikova-loop...")
    url = "https://api.github.com/repos/Meikova/meikova-loop/zipball/main"
    req_headers = {"User-Agent": "MeikovaLoop-Space"}
    if gh_token:
        req_headers["Authorization"] = f"token {gh_token}"
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req) as resp:
        z = zipfile.ZipFile(io.BytesIO(resp.read()))
    prefix = z.namelist()[0].split("/")[0] + "/"
    count = 0
    for m in z.namelist():
        if m.endswith("/"):
            continue
        rel = m[len(prefix):]
        if rel.startswith("loopbox/") or rel.startswith("web/"):
            target = ROOT / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as s, open(target, "wb") as d:
                d.write(s.read())
            count += 1
    print(f"Synced {count} files from GitHub private repository.")

def _sync_cookies():
    cookie_content = os.environ.get("YOUTUBE_COOKIES") or os.environ.get("COOKIES_TXT")
    if cookie_content and cookie_content.strip():
        try:
            from loopbox.cookies import save_cookies
            res = save_cookies(cookie_content.strip())
            print(f"Space Secret cookies loaded: {res.get('message', 'OK')}")
        except Exception as e:
            print(f"Failed to load Space Secret cookies: {e}")
def _ensure_deno():
    if sys.platform.startswith("win"):
        return
    import shutil, subprocess, re
    deno_dir = Path.home() / ".local" / "bin"
    deno_bin = deno_dir / "deno"

    needs_install = True
    p = shutil.which("deno") or (str(deno_bin) if deno_bin.exists() else None)
    if p:
        try:
            out = subprocess.check_output([p, "--version"], stderr=subprocess.STDOUT, text=True)
            v_match = re.search(r"deno\s+(\d+)\.(\d+)", out)
            if v_match:
                major, minor = int(v_match.group(1)), int(v_match.group(2))
                if (major, minor) >= (2, 3):
                    needs_install = False
                    if str(deno_dir) not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = f"{deno_dir}:{os.environ.get('PATH', '')}"
                    print(f"Deno runtime verified: {v_match.group(0)} at {p}")
        except Exception:
            pass

    if not needs_install:
        return

    try:
        import urllib.request, zipfile, io
        print("Auto-installing Deno JS engine (v2.9.7 >= 2.3.0 required by yt-dlp)...")
        deno_dir.mkdir(parents=True, exist_ok=True)
        url = "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-unknown-linux-gnu.zip"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            z = zipfile.ZipFile(io.BytesIO(resp.read()))
            z.extract("deno", str(deno_dir))
        deno_bin.chmod(0o755)
        os.environ["PATH"] = f"{deno_dir}:{os.environ.get('PATH', '')}"
        print("Deno v2.9.7 installed successfully at", deno_bin)
    except Exception as e:
        print("Deno auto-install skipped:", e)

def _ensure_ffmpeg():
    import shutil
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            bin_dir = Path.home() / ".local" / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            link = bin_dir / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
            if not link.exists():
                shutil.copy2(exe, link)
                link.chmod(0o755)
            os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
            print("ffmpeg enabled via imageio_ffmpeg at", link)
            return
    except Exception:
        pass
    if not sys.platform.startswith("win"):
        bin_dir = Path.home() / ".local" / "bin"
        ffmpeg_bin = bin_dir / "ffmpeg"
        if ffmpeg_bin.exists():
            os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
            return
        try:
            import urllib.request, tarfile, io
            print("Auto-installing static ffmpeg...")
            url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with tarfile.open(fileobj=io.BytesIO(resp.read())) as tar:
                    for member in tar.getmembers():
                        if member.name.endswith("/ffmpeg"):
                            f = tar.extractfile(member)
                            if f:
                                bin_dir.mkdir(parents=True, exist_ok=True)
                                with open(ffmpeg_bin, "wb") as out:
                                    out.write(f.read())
                                ffmpeg_bin.chmod(0o755)
                                os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
                                print("Static ffmpeg installed at", ffmpeg_bin)
                                return
        except Exception as e:
            print("Static ffmpeg download skipped:", e)

_ensure_deno()
_ensure_ffmpeg()
_sync_private_code()
_sync_cookies()

# (env vars configured at top)

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
        import multiprocessing
        if multiprocessing.current_process().name != "MainProcess":
            return
        worker.start()
        if MULTIUSER:
            worker.start_retention(AUDIO_TTL_S, sessions.in_use)
        else:
            sessions.local().link()
        _worker_started = True



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
#meikova-loop-frame {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    border: none;
    z-index: 999999;
}
"""

with gr.Blocks(title="Meikova Loop") as demo:
    gr.HTML('<iframe id="meikova-loop-frame" src="/web/" allow="autoplay; accelerometer; gyroscope; screen-wake-lock; clipboard-write"></iframe>')

def _mount_meikova_loop(target_app):
    if not target_app:
        return
    _ensure_worker()
    for r in fastapi_app.router.routes:
        if getattr(r, "name", "") != "web" and r not in target_app.router.routes:
            target_app.router.routes.append(r)
    target_app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="meikova_loop_web")
    if (WEB_DIR / "css").exists():
        target_app.mount("/css", StaticFiles(directory=WEB_DIR / "css"))
    if (WEB_DIR / "js").exists():
        target_app.mount("/js", StaticFiles(directory=WEB_DIR / "js"))
    if (WEB_DIR / "img").exists():
        target_app.mount("/img", StaticFiles(directory=WEB_DIR / "img"))
    if (WEB_DIR / "audio").exists():
        target_app.mount("/audio", StaticFiles(directory=WEB_DIR / "audio"))

# Pre-mount on demo.app for any direct ASGI usage
_mount_meikova_loop(demo.app)
app = demo.app

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    target_port = 7860 if bool(os.environ.get("SPACE_ID")) else 8765
    port = int(os.environ.get("PORT") or os.environ.get("MEIKOVA_LOOP_PORT") or target_port)
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
    _mount_meikova_loop(demo.server_app)
    _ensure_worker()

    if "--tunnel" in sys.argv or os.environ.get("AUTO_TUNNEL") in ("1", "true", "True"):
        from loopbox.tunnel_manager import tunnel_manager
        def _space_auto_tunnel():
            import time
            time.sleep(1.0)
            try:
                st = tunnel_manager.start(port)
                print(f"[Tunnel] Active Cloudflare URL: {st.get('url')}")
            except Exception as e:
                print(f"[Tunnel] Auto-start failed: {e}")
        import threading
        threading.Thread(target=_space_auto_tunnel, daemon=True).start()

    try:
        demo.block_thread()
    except (KeyboardInterrupt, SystemExit):
        demo.close()

