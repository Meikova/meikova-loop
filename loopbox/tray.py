"""System Tray Icon and Background Runner for MashLoop Desktop Application.
Supports native Windows WinForms NotifyIcon and cross-platform fallback.
"""
import logging
import os
import sys
import webbrowser
from pathlib import Path
from typing import Callable

logger = logging.getLogger("mashloop.tray")


def is_autostart_enabled(app_name: str = "MashLoop") -> bool:
    """Checks if the app is registered in Windows startup registry."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as k:
            val, _ = winreg.QueryValueEx(k, app_name)
            return bool(val)
    except OSError:
        return False


def set_autostart(enable: bool, app_name: str = "MashLoop") -> bool:
    """Enables or disables auto-start at Windows logon via registry."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as k:
            if enable:
                if getattr(sys, "frozen", False):
                    exe_cmd = f'"{sys.executable}"'
                else:
                    exe_cmd = f'"{sys.executable}" -m loopbox.desktop'
                winreg.SetValueEx(k, app_name, 0, winreg.REG_SZ, exe_cmd)
            else:
                try:
                    winreg.DeleteValue(k, app_name)
                except OSError:
                    pass
        return True
    except Exception as e:
        logger.warning("Failed to update Windows autostart registry: %s", e)
        return False


class DesktopTray:
    """Manages the desktop System Tray icon, menu actions, and minimize-to-tray lifecycle."""

    def __init__(
        self,
        window,
        port: int,
        icon_path: Path | None = None,
        data_dir: Path | None = None,
        on_quit: Callable[[], None] | None = None,
    ):
        self.window = window
        self.port = port
        self.icon_path = icon_path
        self.data_dir = data_dir
        self.on_quit = on_quit
        self.is_quitting = False
        self._balloon_shown = False
        self._tray = None
        self._autostart_item = None

    def setup(self):
        """Initializes the tray icon."""
        if sys.platform == "win32":
            self._setup_winforms()
        else:
            self._setup_fallback()

    def show_window(self):
        """Restores and activates the main window."""
        try:
            if sys.platform == "win32" and getattr(self.window, "native", None):
                import clr
                clr.AddReference("System.Windows.Forms")
                from System.Windows.Forms import FormWindowState, MethodInvoker
                form = self.window.native

                def _do_restore():
                    if form.WindowState == FormWindowState.Minimized:
                        form.WindowState = FormWindowState.Normal
                    form.Show()
                    form.Activate()
                    form.BringToFront()

                if hasattr(form, "InvokeRequired") and form.InvokeRequired:
                    form.Invoke(MethodInvoker(_do_restore))
                else:
                    _do_restore()
            else:
                self.window.show()
                self.window.restore()
        except Exception as e:
            logger.debug("Error restoring window: %s", e)

    def hide_window(self):
        """Hides the window to system tray and shows hint balloon."""
        try:
            self.window.hide()
            if not self._balloon_shown and self._tray:
                self.show_balloon(
                    "MashLoop",
                    "MashLoop vẫn đang chạy ngầm trong khay hệ thống. Nhấp vào biểu tượng để mở lại.",
                )
                self._balloon_shown = True
        except Exception as e:
            logger.debug("Error hiding window to tray: %s", e)

    def show_balloon(self, title: str, message: str):
        """Displays a system tray balloon notification."""
        if self._tray and hasattr(self._tray, "ShowBalloonTip"):
            try:
                from System.Windows.Forms import ToolTipIcon
                self._tray.ShowBalloonTip(3000, title, message, ToolTipIcon.Info)
            except Exception:
                pass

    def handle_closing(self) -> bool:
        """Handler for pywebview window.events.closing.
        Returns False to cancel close and hide to tray; returns True when quitting.
        """
        if self.is_quitting:
            return True
        self.hide_window()
        return False

    def quit(self):
        """Cleanly destroys the tray icon and exits the desktop application."""
        self.is_quitting = True
        try:
            if self._tray:
                self._tray.Visible = False
                self._tray.Dispose()
                self._tray = None
        except Exception:
            pass

        if self.on_quit:
            try:
                self.on_quit()
            except Exception:
                pass

        try:
            self.window.destroy()
        except Exception:
            pass

    def _setup_winforms(self):
        try:
            import clr
            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System.Drawing")
            from System.Windows.Forms import (
                NotifyIcon,
                ContextMenuStrip,
                ToolStripMenuItem,
                ToolStripSeparator,
                MouseButtons,
                MouseEventHandler,
            )
            from System.Drawing import Icon
            from System import EventHandler

            tray = NotifyIcon()
            if self.icon_path and self.icon_path.is_file():
                tray.Icon = Icon(str(self.icon_path))
            tray.Text = "MashLoop - Nhạc nhảy nhịp vô tận"[:63]

            menu = ContextMenuStrip()

            # 1. Header (disabled title item)
            header = ToolStripMenuItem("MashLoop // v2.0")
            header.Enabled = False
            menu.Items.Add(header)
            menu.Items.Add(ToolStripSeparator())

            # 2. Show Window
            item_show = ToolStripMenuItem("Mở MashLoop")
            item_show.Click += EventHandler(lambda s, e: self.show_window())
            menu.Items.Add(item_show)

            # 3. Open in Browser
            item_web = ToolStripMenuItem("Mở trên trình duyệt Web")
            item_web.Click += EventHandler(
                lambda s, e: webbrowser.open(f"http://127.0.0.1:{self.port}/")
            )
            menu.Items.Add(item_web)

            # 4. Open Data directory
            if self.data_dir and self.data_dir.exists():
                item_data = ToolStripMenuItem("Mở thư mục lưu trữ (Data)")

                def _open_data(s, e):
                    if hasattr(os, "startfile"):
                        os.startfile(str(self.data_dir))
                    else:
                        webbrowser.open(str(self.data_dir))

                item_data.Click += EventHandler(_open_data)
                menu.Items.Add(item_data)

            menu.Items.Add(ToolStripSeparator())

            # 5. Autostart toggle
            auto_on = is_autostart_enabled()
            self._autostart_item = ToolStripMenuItem(
                f"Khởi động cùng Windows: {'Bật ✓' if auto_on else 'Tắt'}"
            )

            def _toggle_autostart(s, e):
                current = is_autostart_enabled()
                nxt = not current
                set_autostart(nxt)
                if self._autostart_item:
                    self._autostart_item.Text = (
                        f"Khởi động cùng Windows: {'Bật ✓' if nxt else 'Tắt'}"
                    )

            self._autostart_item.Click += EventHandler(_toggle_autostart)
            menu.Items.Add(self._autostart_item)

            # 6. Reload UI
            item_reload = ToolStripMenuItem("Tải lại giao diện")
            item_reload.Click += EventHandler(
                lambda s, e: self.window.evaluate_js("window.location.reload()")
            )
            menu.Items.Add(item_reload)

            menu.Items.Add(ToolStripSeparator())

            # 7. Quit completely
            item_quit = ToolStripMenuItem("Thoát hoàn toàn")
            item_quit.Click += EventHandler(lambda s, e: self.quit())
            menu.Items.Add(item_quit)

            tray.ContextMenuStrip = menu

            # Mouse click & Double-click to restore window
            def _on_mouse_click(s, args):
                if args.Button == MouseButtons.Left:
                    self.show_window()

            tray.MouseClick += MouseEventHandler(_on_mouse_click)
            tray.DoubleClick += EventHandler(lambda s, e: self.show_window())

            tray.Visible = True
            self._tray = tray
            logger.info("Native Windows system tray icon attached successfully.")
        except Exception as e:
            logger.warning("Failed to initialize Windows WinForms NotifyIcon: %s", e)

    def _setup_fallback(self):
        try:
            import pystray
            from PIL import Image

            if not self.icon_path or not self.icon_path.is_file():
                return
            img = Image.open(str(self.icon_path))
            menu = pystray.Menu(
                pystray.MenuItem("MashLoop // v2.0", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Mở MashLoop", lambda: self.show_window(), default=True),
                pystray.MenuItem(
                    "Mở trên trình duyệt Web",
                    lambda: webbrowser.open(f"http://127.0.0.1:{self.port}/"),
                ),
                pystray.MenuItem(
                    "Mở thư mục lưu trữ (Data)",
                    lambda: webbrowser.open(str(self.data_dir)),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Thoát hoàn toàn", lambda: self.quit()),
            )
            self._tray = pystray.Icon(
                "MashLoop", img, "MashLoop - Nhạc nhảy nhịp vô tận", menu
            )
            import threading
            threading.Thread(target=self._tray.run, daemon=True, name="pystray-runner").start()
            logger.info("Fallback pystray icon started.")
        except Exception as e:
            logger.debug("Fallback pystray tray not active: %s", e)
