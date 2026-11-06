"""Desktop application launcher for Meikova Loop using Microsoft Edge WebView2 (pywebview)."""
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
    from .config import ANCHOR_DIR, DATA_DIR, PORT as DEFAULT_PORT, HOST as DEFAULT_HOST, WEB_DIR
except (ImportError, ValueError):
    from loopbox.config import ANCHOR_DIR, DATA_DIR, PORT as DEFAULT_PORT, HOST as DEFAULT_HOST, WEB_DIR

logger = logging.getLogger("meikova.loop.desktop")

# Enable file logging in data directory for desktop diagnostics
try:
    _log_file = DATA_DIR / "desktop.log"
    _file_handler = logging.FileHandler(str(_log_file), encoding="utf-8", mode="a")
    _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(_file_handler)
    logging.getLogger().setLevel(logging.INFO)
except Exception:
    pass

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes, c_float, c_void_p, byref, HRESULT, WINFUNCTYPE, Structure
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


    class _GUID(Structure):
        _fields_ = [
            ('Data1', wintypes.DWORD),
            ('Data2', wintypes.WORD),
            ('Data3', wintypes.WORD),
            ('Data4', wintypes.BYTE * 8)
        ]

    def _guid(s: str) -> _GUID:
        g = _GUID()
        try:
            ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), byref(g))
        except Exception:
            pass
        return g

    class WindowsVolume:
        """Zero-dependency Windows Core Audio Master Volume controller using ctypes."""
        def __init__(self):
            self._vol_endpoint = None
            self._get_scalar = None
            self._set_scalar = None
            self._init_endpoint()

        def _init_endpoint(self):
            try:
                ole32 = ctypes.oledll.ole32
                ole32.CoInitialize(None)
                clsid_enum = _guid('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
                iid_enum = _guid('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
                iid_vol = _guid('{5CDF2C82-841E-4546-9722-0CF74078229A}')

                p_enum = c_void_p()
                if ole32.CoCreateInstance(byref(clsid_enum), None, 1, byref(iid_enum), byref(p_enum)) != 0:
                    return

                vtable_enum = ctypes.cast(p_enum, ctypes.POINTER(ctypes.POINTER(c_void_p)))[0]
                fn_get_def = WINFUNCTYPE(HRESULT, c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(c_void_p))(vtable_enum[4])
                p_device = c_void_p()
                if fn_get_def(p_enum, 0, 1, byref(p_device)) != 0:
                    return

                vtable_dev = ctypes.cast(p_device, ctypes.POINTER(ctypes.POINTER(c_void_p)))[0]
                fn_act = WINFUNCTYPE(HRESULT, c_void_p, ctypes.POINTER(_GUID), wintypes.DWORD, c_void_p, ctypes.POINTER(c_void_p))(vtable_dev[3])
                p_vol = c_void_p()
                if fn_act(p_device, byref(iid_vol), 1, None, byref(p_vol)) != 0:
                    return

                vtable_vol = ctypes.cast(p_vol, ctypes.POINTER(ctypes.POINTER(c_void_p)))[0]
                self._set_scalar = WINFUNCTYPE(HRESULT, c_void_p, c_float, c_void_p)(vtable_vol[7])
                self._get_scalar = WINFUNCTYPE(HRESULT, c_void_p, ctypes.POINTER(c_float))(vtable_vol[9])
                self._set_mute = WINFUNCTYPE(HRESULT, c_void_p, wintypes.BOOL, c_void_p)(vtable_vol[14])
                self._get_mute = WINFUNCTYPE(HRESULT, c_void_p, ctypes.POINTER(wintypes.BOOL))(vtable_vol[15])
                self._vol_endpoint = p_vol
            except Exception as e:
                logger.debug("Windows volume init error: %s", e)

        def get_volume(self) -> float:
            if not self._vol_endpoint or not self._get_scalar:
                return 1.0
            try:
                m = wintypes.BOOL()
                if self._get_mute and self._get_mute(self._vol_endpoint, byref(m)) == 0 and m.value:
                    return 0.0
                val = c_float()
                if self._get_scalar(self._vol_endpoint, byref(val)) == 0:
                    return float(val.value)
            except Exception:
                self._init_endpoint()
            return 1.0

        def set_volume(self, val: float):
            if not self._vol_endpoint or not self._set_scalar:
                return
            try:
                clamped = max(0.0, min(1.0, float(val)))
                self._set_scalar(self._vol_endpoint, c_float(clamped), None)
                if self._set_mute:
                    if clamped <= 0.001:
                        self._set_mute(self._vol_endpoint, 1, None)
                    else:
                        self._set_mute(self._vol_endpoint, 0, None)
            except Exception:
                self._init_endpoint()
else:
    class WindowsVolume:
        """Fallback volume controller for non-Windows platforms (macOS / Linux)."""
        def __init__(self):
            pass

        def get_volume(self) -> float:
            return 1.0

        def set_volume(self, val: float):
            pass


AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".oga", ".opus", ".webm", ".aiff", ".aif", ".wma"}


class DesktopBridge:
    def __init__(self, port: int):
        self.port = port
        self._window = None
        self._tray = None
        self._win_vol = WindowsVolume()

    def set_window(self, window):
        self._window = window

    def set_tray(self, tray):
        self._tray = tray

    def hide_to_tray(self):
        if self._tray:
            self._tray.hide_window()
        elif self._window:
            self._window.hide()

    def is_desktop(self) -> bool:
        return True

    def get_system_volume(self) -> float:
        return self._win_vol.get_volume()

    def set_system_volume(self, val: float):
        self._win_vol.set_volume(val)

    def get_sys_info(self) -> dict:
        import platform
        has_cuda = False
        gpu_name = "CPU"
        try:
            import torch
            has_cuda = torch.cuda.is_available()
            gpu_name = torch.cuda.get_device_name(0) if has_cuda else "CPU"
        except Exception:
            pass
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

    def open_google_login(self) -> dict:
        import webbrowser
        try:
            from . import auth
        except Exception:
            from loopbox import auth
        redirect_uri = f"http://127.0.0.1:{self.port}/api/auth/google/callback"
        state = auth.create_desktop_auth_request()
        auth_url = auth.get_google_auth_url(redirect_uri, state=state)
        webbrowser.open(auth_url)
        res = auth.wait_for_desktop_auth(state, timeout=120.0)
        if res:
            return res
        return {"error": "Timeout hoặc hủy xác thực Google trên trình duyệt."}

    def choose_storage_folder(self) -> str | None:
        if not self._window:
            return None
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return None
        folder_path = res[0] if isinstance(res, (list, tuple)) else res
        return str(Path(folder_path).resolve())

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

    def toggle_maximize(self) -> bool:
        if not self._window:
            return False
        # ponytail: safe toggle maximize/restore via pywebview UI-thread invokers to prevent WinForms deadlocks
        if getattr(self, "_is_maximized", False):
            self._window.restore()
            self._is_maximized = False
            return False
        else:
            self._window.maximize()
            self._is_maximized = True
            return True

    def close(self):
        if self._tray:
            self._tray.handle_closing()
        elif self._window:
            self._window.destroy()

    def minimize_window(self):
        if self._tray:
            self._tray.handle_closing()
        elif self._window:
            self._window.minimize()

    def toggle_mini_player(self) -> bool:
        """Toggle between full desktop window and compact Always-On-Top Mini Player."""
        if not self._window:
            return False
        self._is_mini = getattr(self, "_is_mini", False)
        self._is_mini = not self._is_mini
        try:
            if self._is_mini:
                try:
                    self._normal_bounds = (self._window.x, self._window.y, self._window.width, self._window.height)
                except Exception:
                    self._normal_bounds = (100, 100, 1340, 880)

                target_w, target_h = 360, 130
                if sys.platform == "win32":
                    try:
                        import System.Drawing
                        if hasattr(self._window.native, "MinimumSize"):
                            scale = getattr(self._window.native, "_scale", 1.0)
                            self._window.native.MinimumSize = System.Drawing.Size(int(300 * scale), int(80 * scale))
                    except Exception:
                        pass
                    try:
                        hwnd = self._window.native.Handle.ToInt64()
                        scale = getattr(self._window.native, "_scale", 1.0)
                        phys_w = int(target_w * scale)
                        phys_h = int(target_h * scale)
                        HWND_TOPMOST = -1
                        SWP_NOMOVE = 0x0002
                        SWP_SHOWWINDOW = 0x0040
                        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, phys_w, phys_h, SWP_NOMOVE | SWP_SHOWWINDOW)
                    except Exception:
                        pass

                self._window.resize(target_w, target_h)
                self._window.evaluate_js("document.body.classList.add('is-desktop-shell', 'is-desktop-app', 'is-mini-player'); window.__onMiniPlayerChange && window.__onMiniPlayerChange(true);")
            else:
                target_w, target_h = 1340, 880
                orig_x, orig_y = 100, 100
                if getattr(self, "_normal_bounds", None):
                    orig_x, orig_y, w, h = self._normal_bounds
                    target_w = max(960, w)
                    target_h = max(620, h)

                if sys.platform == "win32":
                    try:
                        import System.Drawing
                        if hasattr(self._window.native, "MinimumSize"):
                            scale = getattr(self._window.native, "_scale", 1.0)
                            self._window.native.MinimumSize = System.Drawing.Size(int(350 * scale), int(120 * scale))
                    except Exception:
                        pass
                    try:
                        hwnd = self._window.native.Handle.ToInt64()
                        scale = getattr(self._window.native, "_scale", 1.0)
                        phys_w = int(target_w * scale)
                        phys_h = int(target_h * scale)
                        phys_x = int(orig_x * scale)
                        phys_y = int(orig_y * scale)
                        HWND_NOTOPMOST = -2
                        SWP_SHOWWINDOW = 0x0040
                        ctypes.windll.user32.SetWindowPos(hwnd, HWND_NOTOPMOST, phys_x, phys_y, phys_w, phys_h, SWP_SHOWWINDOW)
                    except Exception:
                        pass

                self._window.resize(target_w, target_h)
                try:
                    self._window.move(orig_x, orig_y)
                except Exception:
                    pass
                self._window.evaluate_js("document.body.classList.remove('is-mini-player'); window.__onMiniPlayerChange && window.__onMiniPlayerChange(false);")
        except Exception as ex:
            logger.debug("toggle_mini_player notice: %s", ex)
        return self._is_mini

    def is_mini_player(self) -> bool:
        return getattr(self, "_is_mini", False)


def _is_server_alive(port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health", headers={"User-Agent": "MeikovaLoop-Desktop"})
        with urllib.request.urlopen(req, timeout=1.0) as r:
            return r.status in (200, 401, 403)
    except Exception:
        return False



VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


def _media_keys_loop(bridge):
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        for vk in (VK_MEDIA_PLAY_PAUSE, VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK, VK_MEDIA_STOP):
            user32.GetAsyncKeyState(vk)
        while True:
            time.sleep(0.04)  # 25Hz polling, <0.01% CPU
            try:
                if user32.GetAsyncKeyState(VK_MEDIA_PLAY_PAUSE) & 1:
                    if bridge._window:
                        bridge._window.evaluate_js("window.__onMediaKey && window.__onMediaKey('play_pause');")
                if user32.GetAsyncKeyState(VK_MEDIA_NEXT_TRACK) & 1:
                    if bridge._window:
                        bridge._window.evaluate_js("window.__onMediaKey && window.__onMediaKey('next');")
                if user32.GetAsyncKeyState(VK_MEDIA_PREV_TRACK) & 1:
                    if bridge._window:
                        bridge._window.evaluate_js("window.__onMediaKey && window.__onMediaKey('previous');")
                if user32.GetAsyncKeyState(VK_MEDIA_STOP) & 1:
                    if bridge._window:
                        bridge._window.evaluate_js("window.__onMediaKey && window.__onMediaKey('stop');")
            except Exception:
                pass
    except Exception as e:
        logger.debug("Media keys loop notice: %s", e)

def _wait_for_server(port: int, timeout: float = 15.0, splash=None) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _is_server_alive(port):
            return True
        time.sleep(0.05)
    return False


def _start_background_server(port: int, host: str = DEFAULT_HOST):
    try:
        from .server import app
    except (ImportError, ValueError):
        from loopbox.server import app

    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="meikova-loop-uvicorn", daemon=True)
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
    """Apply native dark theme to the Windows titlebar to match Meikova Loop ambient dark style."""
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


def main(argv=None, splash=None):
    ap = argparse.ArgumentParser(prog="meikova-loop-desktop", description="Meikova Loop Desktop Application")
    ap.add_argument("--host", default=DEFAULT_HOST, help="Server host (default: %(default)s)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port (default: %(default)s)")
    ap.add_argument("--debug", action="store_true", help="Enable webview DevTools")
    args = ap.parse_args(argv)

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Meikova Loop")
        except Exception:
            pass
    if not args.debug:
        hide_console()

    # Ensure splash screen is active if not in debug mode
    if splash is None and not args.debug:
        try:
            from .splash import get_splash, start_splash
            splash = get_splash() or start_splash()
        except Exception:
            try:
                from loopbox.splash import get_splash, start_splash
                splash = get_splash() or start_splash()
            except Exception:
                splash = None

    host = args.host
    port = args.port
    server_obj = None

    # Single-instance protection across platforms
    _h_mutex = None
    _lock_file = None
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            mutex_name = f"Local\\MeikovaLoop_Desktop_Mutex_{port}"
            _h_mutex = kernel32.CreateMutexW(None, False, mutex_name)
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                if splash:
                    splash.close()
                logger.info("Another Meikova Loop Desktop instance is already running. Restoring window.")
                hwnd = ctypes.windll.user32.FindWindowW(None, "Meikova Loop - Nhạc nhảy nhịp vô tận")
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                else:
                    import webbrowser
                    webbrowser.open(f"http://127.0.0.1:{port}/")
                sys.exit(0)
        except Exception as e:
            logger.debug("Mutex check failed: %s", e)
    else:
        try:
            import fcntl
            lock_path = DATA_DIR / f"desktop_{port}.lock"
            _lock_file = open(lock_path, "w")
            fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            if _is_server_alive(port):
                logger.info("Another Meikova Loop instance is already running on port %s. Opening browser.", port)
                import webbrowser
                webbrowser.open(f"http://127.0.0.1:{port}/")
                sys.exit(0)
        except Exception:
            pass

    # Check if server is already running on the port
    if not _is_server_alive(port):
        if splash:
            splash.set_status("Đang khởi tạo máy chủ âm thanh...")
        server_obj, _ = _start_background_server(port, host=host)
        if not _wait_for_server(port, splash=splash):
            if splash:
                splash.close()
            sys.exit(1)

    bridge = DesktopBridge(port)
    if splash:
        splash.set_status("Đang mở không gian làm việc...")

    # Window creation (Frameless with custom titlebar controls inspired by Meikova Harvest)
    window = webview.create_window(
        title="Meikova Loop - Nhạc nhảy nhịp vô tận",
        url=f"http://127.0.0.1:{port}/",
        width=1340,
        height=880,
        min_size=(320, 100),
        background_color="#080a0e",
        text_select=False,
        js_api=bridge,
        frameless=True,
        easy_drag=False,
        shadow=True,
    )
    bridge.set_window(window)

    def _on_window_maximized():
        bridge._is_maximized = True
        try:
            window.evaluate_js("window.__onWindowState && window.__onWindowState(true);")
        except Exception:
            pass

    def _on_window_restored():
        bridge._is_maximized = False
        try:
            window.evaluate_js("window.__onWindowState && window.__onWindowState(false);")
        except Exception:
            pass

    window.events.maximized += _on_window_maximized
    window.events.restored += _on_window_restored

    icon_ico = WEB_DIR / "img" / "icon.ico"
    icon_png = WEB_DIR / "img" / "icon-192.png"
    if sys.platform == "win32":
        icon_path = icon_ico if icon_ico.is_file() else icon_png
    else:
        icon_path = icon_png if icon_png.is_file() else icon_ico
    icon_str = str(icon_path) if icon_path and icon_path.is_file() else None

    # ponytail: native system tray runner inspired by Meikova Harvest; minimize to tray on window close
    desktop_tray = None
    try:
        from .tray import DesktopTray
    except (ImportError, ValueError):
        from loopbox.tray import DesktopTray

    def _on_tray_quit():
        if server_obj:
            server_obj.should_exit = True

    desktop_tray = DesktopTray(
        window=window,
        port=port,
        icon_path=icon_path,
        data_dir=DATA_DIR,
        on_quit=_on_tray_quit,
    )
    bridge.set_tray(desktop_tray)

    def on_closing():
        if desktop_tray:
            return desktop_tray.handle_closing()
        return True

    window.events.closing += on_closing

    def _volume_sync_loop():
        try:
            ctypes.oledll.ole32.CoInitialize(None)
        except Exception:
            pass
        thread_win_vol = WindowsVolume()
        last_v = -1.0  # Force immediate sync on first tick
        while True:
            time.sleep(0.04)  # 25Hz fast polling for instant smooth response
            try:
                cur_v = thread_win_vol.get_volume()
                if abs(cur_v - last_v) >= 0.005:
                    last_v = cur_v
                    if bridge._window:
                        bridge._window.evaluate_js(f"window.__onSystemVolume && window.__onSystemVolume({cur_v:.3f});")
            except Exception:
                pass

    def on_shown():
        try:
            if splash:
                splash.close()
            hwnd = window.native.Handle.ToInt64()
            if sys.platform == "win32":
                # ponytail: constrain frameless maximized bounds to working area so taskbar remains visible
                try:
                    from System.Windows.Forms import Screen
                    window.native.MaximizedBounds = Screen.FromHandle(window.native.Handle).WorkingArea
                except Exception:
                    pass
            if icon_path.is_file():
                set_window_icon(hwnd, icon_path)
                try:
                    import clr
                    clr.AddReference("System.Drawing")
                    from System.Drawing import Icon
                    window.native.Icon = Icon(icon_str)
                except Exception:
                    pass
            if desktop_tray:
                desktop_tray.setup()
            threading.Thread(target=_volume_sync_loop, name="volume-sync", daemon=True).start()
            threading.Thread(target=_media_keys_loop, args=(bridge,), name="media-keys", daemon=True).start()
            init_v = bridge.get_system_volume()
            window.evaluate_js(f"window.__onSystemVolume && window.__onSystemVolume({init_v:.3f});")
        except Exception:
            pass

    window.events.shown += on_shown

    profile_dir = ANCHOR_DIR / "desktop_profile"
    # Seamless migration: if profile exists in old location (e.g. ANCHOR_DIR/data/desktop_profile or DATA_DIR/desktop_profile)
    # copy it to ANCHOR_DIR/desktop_profile so user credentials, localStorage, and playlists are permanently preserved.
    if not profile_dir.exists():
        import shutil
        old_profiles = [
            ANCHOR_DIR / "data" / "desktop_profile",
            DATA_DIR / "desktop_profile",
        ]
        for op in old_profiles:
            if op.exists() and op != profile_dir:
                try:
                    shutil.copytree(op, profile_dir, dirs_exist_ok=True)
                    logger.info("Migrated desktop_profile from %s to %s", op, profile_dir)
                    break
                except Exception as ex:
                    logger.debug("Profile migration notice: %s", ex)
    profile_dir.mkdir(parents=True, exist_ok=True)

    webview.start(
        debug=args.debug,
        storage_path=str(profile_dir),
        private_mode=False,
        icon=icon_str,
    )

    print("Meikova Loop Desktop closed.")
    if desktop_tray:
        desktop_tray.quit(fast_exit=False)
    if server_obj:
        server_obj.should_exit = True
    import os
    os._exit(0)


if __name__ == "__main__":
    main()
