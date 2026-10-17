"""Desktop application launcher for MashLoop using Microsoft Edge WebView2 (pywebview)."""
import argparse
import logging
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import uvicorn
import webview

try:
    from .config import DATA_DIR, PORT as DEFAULT_PORT, WEB_DIR
except (ImportError, ValueError):
    from loopbox.config import DATA_DIR, PORT as DEFAULT_PORT, WEB_DIR

logger = logging.getLogger("mashloop.desktop")

AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".oga", ".opus", ".webm", ".aiff", ".aif", ".wma"}


class DesktopBridge:
    def __init__(self, port: int):
        self.port = port
        self._window = None

    def set_window(self, window):
        self._window = window

    def is_desktop(self) -> bool:
        return True

    def get_sys_info(self) -> dict:
        import platform
        import torch

        has_cuda = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if has_cuda else "CPU"
        return {
            "os": platform.platform(),
            "python": platform.python_version(),
            "cuda": has_cuda,
            "device": gpu_name,
            "port": self.port,
        }

    def select_files(self) -> list[str]:
        if not self._window:
            return []
        file_types = (
            "Audio Files (*.mp3;*.flac;*.wav;*.m4a;*.ogg;*.opus;*.aac;*.wma;*.aiff)",
            "All Files (*.*)",
        )
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=file_types,
        )
        return list(res or [])

    def select_folder(self) -> list[str]:
        if not self._window:
            return []
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return []
        folder_path = res[0] if isinstance(res, (list, tuple)) else res
        folder = Path(folder_path)
        if not folder.is_dir():
            return []
        files = []
        for root, _, filenames in os.walk(folder):
            for name in filenames:
                if not name.startswith("._") and Path(name).suffix.lower() in AUDIO_EXT:
                    files.append(str(Path(root) / name))
        return files

    def minimize(self):
        if self._window:
            self._window.minimize()

    def restore(self):
        if self._window:
            self._window.restore()


def _is_server_alive(port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/tracks", headers={"User-Agent": "MashLoop-Desktop"})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return r.status in (200, 401, 403)
    except Exception:
        return False


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _is_server_alive(port):
            return True
        time.sleep(0.2)
    return False


def _start_background_server(port: int):
    try:
        from .server import app
    except (ImportError, ValueError):
        from loopbox.server import app

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="mashloop-uvicorn", daemon=True)
    thread.start()
    return server, thread


def hide_console():
    """Hide the black terminal window on Windows if launched via python.exe."""
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def apply_dark_titlebar(hwnd):
    """Apply native dark theme to the Windows titlebar to match MashLoop ambient dark style."""
    try:
        import ctypes
        from ctypes import byref, c_int
        dwmapi = ctypes.windll.dwmapi
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark = c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(dark), ctypes.sizeof(dark))
        # DWMWA_CAPTION_COLOR = 35 -> #0b0d10 (BGR: 0x00100D0B)
        caption_color = c_int(0x00100D0B)
        dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(caption_color), ctypes.sizeof(caption_color))
        # DWMWA_TEXT_COLOR = 36 -> #e8e6e3 (BGR: 0x00E3E6E8)
        text_color = c_int(0x00E3E6E8)
        dwmapi.DwmSetWindowAttribute(hwnd, 36, byref(text_color), ctypes.sizeof(text_color))
    except Exception:
        pass


def set_window_icon(hwnd, icon_path: Path):
    """Set titlebar and taskbar icon for the window using Win32 API."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # LR_LOADFROMFILE = 0x0010, IMAGE_ICON = 1, WM_SETICON = 0x0080
        hicon_sm = user32.LoadImageW(0, str(icon_path), 1, 16, 16, 0x00000010)
        hicon_lg = user32.LoadImageW(0, str(icon_path), 1, 32, 32, 0x00000010)
        if hicon_sm:
            user32.SendMessageW(hwnd, 0x0080, 0, hicon_sm)
        if hicon_lg:
            user32.SendMessageW(hwnd, 0x0080, 1, hicon_lg)
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mashloop-desktop", description="MashLoop Desktop Application")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port (default: %(default)s)")
    ap.add_argument("--debug", action="store_true", help="Enable webview DevTools")
    args = ap.parse_args(argv)

    if not args.debug:
        hide_console()

    port = args.port
    server_obj = None

    # Check if server is already running on the port
    if not _is_server_alive(port):
        server_obj, _ = _start_background_server(port)
        if not _wait_for_server(port):
            sys.exit(1)

    bridge = DesktopBridge(port)

    # Window creation
    window = webview.create_window(
        title="MashLoop - Nhạc nhảy nhịp vô tận",
        url=f"http://127.0.0.1:{port}/",
        width=1340,
        height=880,
        min_size=(960, 620),
        background_color="#0a0c10",
        text_select=False,
        js_api=bridge,
    )
    bridge.set_window(window)

    icon_path = WEB_DIR / "img" / "icon.ico"
    icon_str = str(icon_path) if icon_path.is_file() else None

    def on_shown():
        try:
            hwnd = window.native.Handle.ToInt64()
            apply_dark_titlebar(hwnd)
            if icon_path.is_file():
                set_window_icon(hwnd, icon_path)
                try:
                    import clr
                    clr.AddReference("System.Drawing")
                    from System.Drawing import Icon
                    window.native.Icon = Icon(icon_str)
                except Exception:
                    pass
        except Exception:
            pass

    window.events.shown += on_shown

    profile_dir = DATA_DIR / "desktop_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    webview.start(
        debug=args.debug,
        storage_path=str(profile_dir),
        private_mode=False,
        icon=icon_str,
    )

    print("MashLoop Desktop closed.")
    if server_obj:
        server_obj.should_exit = True


if __name__ == "__main__":
    main()
