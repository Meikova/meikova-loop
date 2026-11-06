"""Native Ambient Dark Splash Screen for Meikova Loop Desktop.

Displays an instant visual loading indicator on startup using pure ctypes Win32 API.
Zero dependencies, zero tkinter, runs on its own background thread.
"""
import ctypes
from ctypes import wintypes, byref, c_int, c_void_p, WINFUNCTYPE
from pathlib import Path
import sys
import threading
import time

_current_splash = None


class NativeSplash:
    def __init__(self, title="Meikova Loop", subtitle="Trạm âm thanh & Nhảy nhịp vô tận", icon_path=None):
        self.title = title
        self.subtitle = subtitle
        self.status = "Đang khởi động..."
        self.icon_path = Path(icon_path) if icon_path else None
        self._hwnd = None
        self._thread = None
        self._stop_event = threading.Event()
        self._hicon = None
        self._progress = 0.0
        self._w = 420
        self._h = 240

    def start(self):
        if sys.platform != "win32":
            return
        self._thread = threading.Thread(target=self._run, name="splash-window", daemon=True)
        self._thread.start()
        t0 = time.time()
        while not self._hwnd and time.time() - t0 < 1.0:
            time.sleep(0.01)

    def set_status(self, text: str):
        self.status = text
        if sys.platform == "win32" and self._hwnd:
            try:
                ctypes.windll.user32.InvalidateRect(self._hwnd, None, True)
            except Exception:
                pass

    def close(self):
        # Dismiss any PyInstaller built-in splash if present
        try:
            import pyi_splash
            if pyi_splash.is_alive():
                pyi_splash.close()
        except Exception:
            pass

        self._stop_event.set()
        if sys.platform == "win32" and self._hwnd:
            try:
                ctypes.windll.user32.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.6)
        self._hwnd = None

    def _run(self):
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        kernel32 = ctypes.windll.kernel32

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = c_void_p

        WNDPROC = WINFUNCTYPE(c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", c_int),
                ("cbWndExtra", c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HANDLE),
            ]

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class PAINTSTRUCT(ctypes.Structure):
            _fields_ = [
                ("hdc", wintypes.HDC),
                ("fErase", wintypes.BOOL),
                ("rcPaint", RECT),
                ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", wintypes.BYTE * 32),
            ]

        hInstance = kernel32.GetModuleHandleW(None)
        className = f"MeikovaLoopSplashClass_{int(time.time() * 1000)}"

        # Load icon if available
        if self.icon_path and self.icon_path.exists():
            try:
                self._hicon = user32.LoadImageW(0, str(self.icon_path), 1, 48, 48, 0x00000010)
            except Exception:
                self._hicon = None

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == 0x000F:  # WM_PAINT
                ps = PAINTSTRUCT()
                hdc = user32.BeginPaint(hwnd, byref(ps))
                self._paint(hwnd, hdc, RECT)
                user32.EndPaint(hwnd, byref(ps))
                return 0
            elif msg == 0x0113:  # WM_TIMER
                self._progress = (self._progress + 0.025) % 1.0
                user32.InvalidateRect(hwnd, None, False)
                return 0
            elif msg == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wndproc_ptr = WNDPROC(wndproc)
        bg_brush = gdi32.CreateSolidBrush(0x00130E0B)  # Ambient dark #0B0E13

        wcex = WNDCLASSEXW()
        wcex.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wcex.style = 0x00020000 | 0x0003  # CS_DROPSHADOW | CS_HREDRAW | CS_VREDRAW
        wcex.lpfnWndProc = wndproc_ptr
        wcex.cbClsExtra = 0
        wcex.cbWndExtra = 0
        wcex.hInstance = hInstance
        wcex.hIcon = self._hicon or 0
        wcex.hCursor = user32.LoadCursorW(0, 32512)  # IDC_ARROW
        wcex.hbrBackground = bg_brush
        wcex.lpszMenuName = None
        wcex.lpszClassName = className
        wcex.hIconSm = self._hicon or 0

        user32.RegisterClassExW(byref(wcex))

        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        x = max(0, (sw - self._w) // 2)
        y = max(0, (sh - self._h) // 2)

        hwnd = user32.CreateWindowExW(
            0x00000008 | 0x00000080,  # WS_EX_TOPMOST | WS_EX_TOOLWINDOW
            className,
            self.title,
            0x80000000 | 0x10000000,  # WS_POPUP | WS_VISIBLE
            x, y, self._w, self._h,
            0, 0, hInstance, None
        )
        self._hwnd = hwnd

        # Round window corners: 18px radius
        rgn = gdi32.CreateRoundRectRgn(0, 0, self._w, self._h, 18, 18)
        user32.SetWindowRgn(hwnd, rgn, True)

        # Smooth 30ms timer for runner animation
        user32.SetTimer(hwnd, 1, 30, None)

        msg = wintypes.MSG()
        while user32.GetMessageW(byref(msg), 0, 0, 0) != 0:
            if self._stop_event.is_set():
                break
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

        if self._hicon:
            try:
                user32.DestroyIcon(self._hicon)
            except Exception:
                pass
        try:
            gdi32.DeleteObject(bg_brush)
        except Exception:
            pass

    def _paint(self, hwnd, hdc, RECT_CLS):
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # 1. Background fill
        rc = RECT_CLS(0, 0, self._w, self._h)
        bg_brush = gdi32.CreateSolidBrush(0x00130E0B)  # #0B0E13
        user32.FillRect(hdc, byref(rc), bg_brush)
        gdi32.DeleteObject(bg_brush)

        # 2. Subtle hairline border
        pen = gdi32.CreatePen(0, 1, 0x00332820)
        old_pen = gdi32.SelectObject(hdc, pen)
        null_brush = gdi32.GetStockObject(5)
        old_brush = gdi32.SelectObject(hdc, null_brush)
        gdi32.RoundRect(hdc, 0, 0, self._w, self._h, 18, 18)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.SelectObject(hdc, old_brush)
        gdi32.DeleteObject(pen)

        gdi32.SetBkMode(hdc, 1)  # TRANSPARENT

        # 3. Draw Icon
        if self._hicon:
            user32.DrawIconEx(hdc, 32, 42, self._hicon, 48, 48, 0, 0, 3)

        tx = 96 if self._hicon else 36

        # 4. App Title
        hFontTitle = gdi32.CreateFontW(22, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 2, 0, "Segoe UI")
        old_font = gdi32.SelectObject(hdc, hFontTitle)
        gdi32.SetTextColor(hdc, 0x00FFFFFF)
        rc_title = RECT_CLS(tx, 42, self._w - 24, 72)
        user32.DrawTextW(hdc, self.title, -1, byref(rc_title), 0x00000000 | 0x00000004)

        # 5. Subtitle
        hFontSub = gdi32.CreateFontW(14, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 2, 0, "Segoe UI")
        gdi32.SelectObject(hdc, hFontSub)
        gdi32.SetTextColor(hdc, 0x00A09B94)
        rc_sub = RECT_CLS(tx, 68, self._w - 24, 94)
        user32.DrawTextW(hdc, self.subtitle, -1, byref(rc_sub), 0x00000000 | 0x00000004)

        # 6. Status text
        hFontStatus = gdi32.CreateFontW(13, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 2, 0, "Segoe UI")
        gdi32.SelectObject(hdc, hFontStatus)
        gdi32.SetTextColor(hdc, 0x0081B910)  # Neon Emerald #10B981
        rc_status = RECT_CLS(32, 145, self._w - 32, 168)
        user32.DrawTextW(hdc, self.status, -1, byref(rc_status), 0x00000000 | 0x00000004)

        # 7. Progress Track
        bar_x = 32
        bar_y = 175
        bar_w = self._w - 64
        bar_h = 4
        rc_track = RECT_CLS(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h)
        track_brush = gdi32.CreateSolidBrush(0x00261F1A)
        user32.FillRect(hdc, byref(rc_track), track_brush)
        gdi32.DeleteObject(track_brush)

        # 8. Animated Runner Bar
        runner_w = int(bar_w * 0.35)
        runner_x = bar_x + int((bar_w - runner_w) * self._progress)
        rc_runner = RECT_CLS(runner_x, bar_y, runner_x + runner_w, bar_y + bar_h)
        runner_brush = gdi32.CreateSolidBrush(0x0081B910)
        user32.FillRect(hdc, byref(rc_runner), runner_brush)
        gdi32.DeleteObject(runner_brush)

        # Clean up GDI fonts
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(hFontTitle)
        gdi32.DeleteObject(hFontSub)
        gdi32.DeleteObject(hFontStatus)


def start_splash(icon_path=None) -> NativeSplash | None:
    """Helper to start the global splash window."""
    global _current_splash
    if sys.platform != "win32":
        return None
    try:
        if icon_path is None:
            # Try to resolve icon from common locations
            root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
            for cand in [root / "web" / "img" / "icon.ico", root / "web" / "img" / "icon-192.png"]:
                if cand.exists():
                    icon_path = cand
                    break
        _current_splash = NativeSplash(icon_path=icon_path)
        _current_splash.start()
        return _current_splash
    except Exception:
        return None


def get_splash() -> NativeSplash | None:
    return _current_splash


def close_splash():
    global _current_splash
    if _current_splash:
        try:
            _current_splash.close()
        except Exception:
            pass
        _current_splash = None
