"""System Tray Icon and Background Runner for Meikova Loop Desktop Application.
Full cross-platform support with ambient-dark themed context menu & icons:
- Windows: Native WinForms NotifyIcon with custom dark ToolStripProfessionalRenderer & icons
- macOS: Native AppKit NSStatusItem with custom menu icons or pystray
- Linux: Native Gtk.StatusIcon with custom menu icons or pystray
"""
import logging
import os
import sys
import webbrowser
from pathlib import Path
from typing import Callable

logger = logging.getLogger("meikova.loop.tray")

# Keep strong references to prevent WinForms / AppKit / GTK objects from being garbage-collected
_GLOBAL_TRAY_REFS: list = []


if sys.platform == "win32":
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Drawing")
        from System.Windows.Forms import (
            ProfessionalColorTable,
            ToolStripProfessionalRenderer,
            TextRenderer,
            TextFormatFlags,
        )
        from System.Drawing import Color, Pen

        class AmbientDarkColorTable(ProfessionalColorTable):
            """Meikova Loop ambient dark color palette for ContextMenuStrip."""

            @property
            def ToolStripDropDownBackground(self):
                return Color.FromArgb(14, 16, 21)  # --ink-0 / #0e1015

            @property
            def ImageMarginGradientBegin(self):
                return Color.FromArgb(14, 16, 21)

            @property
            def ImageMarginGradientMiddle(self):
                return Color.FromArgb(14, 16, 21)

            @property
            def ImageMarginGradientEnd(self):
                return Color.FromArgb(14, 16, 21)

            @property
            def MenuBorder(self):
                return Color.FromArgb(42, 47, 61)  # --line / #2a2f3d

            @property
            def MenuItemBorder(self):
                return Color.FromArgb(65, 52, 28)  # Subtle amber-gold border

            @property
            def MenuItemSelected(self):
                return Color.FromArgb(32, 36, 46)  # --ink-2 / #20242e

            @property
            def MenuItemSelectedGradientBegin(self):
                return Color.FromArgb(32, 36, 46)

            @property
            def MenuItemSelectedGradientEnd(self):
                return Color.FromArgb(32, 36, 46)

            @property
            def MenuItemPressedGradientBegin(self):
                return Color.FromArgb(24, 27, 35)

            @property
            def MenuItemPressedGradientEnd(self):
                return Color.FromArgb(24, 27, 35)

            @property
            def SeparatorDark(self):
                return Color.FromArgb(42, 47, 61)

            @property
            def SeparatorLight(self):
                return Color.FromArgb(14, 16, 21)

        class AmbientDarkRenderer(ToolStripProfessionalRenderer):
            """Custom renderer ensuring anti-aliased dark mode text, gold headers, and clean hairlines."""

            def __init__(self):
                super().__init__(AmbientDarkColorTable())

            def OnRenderItemText(self, e):
                txt = e.Text
                bounds = e.TextRectangle
                item = e.Item
                if not item.Enabled:
                    color = Color.FromArgb(245, 158, 11)  # Amber gold header #f59e0b
                elif item.Name == "item_quit":
                    color = Color.FromArgb(248, 113, 113) if item.Selected else Color.FromArgb(239, 68, 68)
                elif item.Selected:
                    color = Color.FromArgb(255, 255, 255)
                else:
                    color = Color.FromArgb(232, 230, 227)  # Warm ivory #e8e6e3

                flags = TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine
                TextRenderer.DrawText(e.Graphics, txt, e.TextFont, bounds, color, flags)

            def OnRenderSeparator(self, e):
                g = e.Graphics
                y = e.Item.Height // 2
                pen = Pen(Color.FromArgb(42, 47, 61), 1)
                g.DrawLine(pen, 28, y, e.Item.Width - 8, y)
                pen.Dispose()

    except Exception:
        AmbientDarkRenderer = None
else:
    AmbientDarkRenderer = None


def is_autostart_enabled(app_name: str = "MeikovaLoop") -> bool:
    """Checks if the app is registered in system autostart across Windows, macOS, and Linux."""
    if sys.platform == "win32":
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
    elif sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.meikova.loop.plist"
        return plist.is_file()
    else:
        desktop = Path.home() / ".config" / "autostart" / "meikova-loop.desktop"
        return desktop.is_file()


def set_autostart(enable: bool, app_name: str = "MeikovaLoop") -> bool:
    """Enables or disables auto-start at logon via system configuration across platforms."""
    if getattr(sys, "frozen", False):
        exe_cmd = f'"{sys.executable}"'
        raw_cmd = sys.executable
    else:
        exe_cmd = f'"{sys.executable}" -m loopbox.desktop'
        raw_cmd = f"{sys.executable} -m loopbox.desktop"

    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as k:
                if enable:
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

    elif sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.meikova.loop.plist"
        try:
            if enable:
                plist.parent.mkdir(parents=True, exist_ok=True)
                content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.meikova.loop</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        {"" if getattr(sys, "frozen", False) else "<string>-m</string><string>loopbox.desktop</string>"}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
                plist.write_text(content, encoding="utf-8")
            else:
                if plist.exists():
                    plist.unlink()
            return True
        except Exception as e:
            logger.warning("Failed to update macOS LaunchAgent: %s", e)
            return False

    else:  # Linux XDG Autostart
        desktop = Path.home() / ".config" / "autostart" / "meikova-loop.desktop"
        try:
            if enable:
                desktop.parent.mkdir(parents=True, exist_ok=True)
                content = f"""[Desktop Entry]
Type=Application
Name=Meikova Loop
Comment=Meikova Loop Desktop Application
Exec={raw_cmd}
Terminal=false
Categories=AudioVideo;Audio;
"""
                desktop.write_text(content, encoding="utf-8")
            else:
                if desktop.exists():
                    desktop.unlink()
            return True
        except Exception as e:
            logger.warning("Failed to update Linux autostart desktop entry: %s", e)
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

    def _get_tray_icon_path(self, name: str) -> Path | None:
        """Finds custom tray icon path in web/img/tray/<name>.png."""
        if not self.icon_path:
            return None
        tray_dir = self.icon_path.parent / "tray"
        f = tray_dir / f"{name}.png"
        return f if f.is_file() else None

    def _get_tray_icon_bitmap(self, name: str):
        """Loads a 32x32 PNG icon as System.Drawing.Bitmap on Windows."""
        f = self._get_tray_icon_path(name)
        if f:
            try:
                from System.Drawing import Bitmap
                return Bitmap(str(f))
            except Exception:
                pass
        return None

    def setup(self):
        """Initializes the tray icon on native platform."""
        if sys.platform == "win32":
            form = getattr(self.window, "native", None)
            if form is not None:
                try:
                    import clr
                    clr.AddReference("System.Windows.Forms")
                    from System.Windows.Forms import MethodInvoker
                    if hasattr(form, "InvokeRequired") and form.InvokeRequired:
                        form.Invoke(MethodInvoker(self._setup_winforms))
                        return
                except Exception as e:
                    logger.debug("form.Invoke setup failed, fallback direct: %s", e)
            self._setup_winforms()
        elif sys.platform == "darwin":
            self._setup_macos()
        else:
            self._setup_linux()

    def show_window(self):
        """Restores and activates the main window across platforms."""
        try:
            form = getattr(self.window, "native", None)
            if sys.platform == "win32" and form is not None:
                import clr
                clr.AddReference("System.Windows.Forms")
                from System.Windows.Forms import FormWindowState, MethodInvoker

                def _do_restore():
                    try:
                        if form.WindowState == FormWindowState.Minimized:
                            form.WindowState = FormWindowState.Normal
                        form.Show()
                        form.Activate()
                        form.BringToFront()
                    except Exception as ex:
                        logger.debug("Restore UI error: %s", ex)

                if hasattr(form, "InvokeRequired") and form.InvokeRequired:
                    form.Invoke(MethodInvoker(_do_restore))
                else:
                    _do_restore()
            elif sys.platform == "darwin":
                try:
                    from AppKit import NSApp
                    NSApp.activateIgnoringOtherApps_(True)
                except Exception:
                    pass
                self.window.show()
                self.window.restore()
            else:
                self.window.show()
                self.window.restore()
        except Exception as e:
            logger.debug("Error restoring window: %s", e)

    def hide_window(self):
        """Hides the window to system tray and shows hint balloon."""
        try:
            form = getattr(self.window, "native", None)
            if sys.platform == "win32" and form is not None:
                import clr
                clr.AddReference("System.Windows.Forms")
                from System.Windows.Forms import MethodInvoker

                def _do_hide():
                    try:
                        form.Hide()
                    except Exception as ex:
                        logger.debug("Hide UI error: %s", ex)

                if hasattr(form, "InvokeRequired") and form.InvokeRequired:
                    form.Invoke(MethodInvoker(_do_hide))
                else:
                    _do_hide()
            else:
                self.window.hide()

            if not self._balloon_shown and self._tray:
                self.show_balloon(
                    "Mash ∞ Loop",
                    "Đang chạy ngầm · Nhấp vào biểu tượng để mở lại.",
                )
                self._balloon_shown = True
        except Exception as e:
            logger.debug("Error hiding window to tray: %s", e)

    def show_balloon(self, title: str, message: str):
        """Displays a clean, iconless system tray balloon notification."""
        if not self._tray or not hasattr(self._tray, "ShowBalloonTip"):
            return
        try:
            from System.Windows.Forms import ToolTipIcon, MethodInvoker
            form = getattr(self.window, "native", None)

            def _do_balloon():
                try:
                    if self._tray:
                        icon_none = getattr(ToolTipIcon, "None", ToolTipIcon.Info)
                        self._tray.ShowBalloonTip(3000, title, message, icon_none)
                except Exception:
                    pass

            if form and hasattr(form, "InvokeRequired") and form.InvokeRequired:
                form.Invoke(MethodInvoker(_do_balloon))
            else:
                _do_balloon()
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
            form = getattr(self.window, "native", None)
            if sys.platform == "win32" and form is not None:
                import clr
                clr.AddReference("System.Windows.Forms")
                from System.Windows.Forms import Application, MethodInvoker

                def _do_cleanup():
                    try:
                        if self._tray and hasattr(self._tray, "Visible"):
                            self._tray.Visible = False
                            self._tray.Dispose()
                        self._tray = None
                        _GLOBAL_TRAY_REFS.clear()
                        Application.Exit()
                    except Exception:
                        pass

                if hasattr(form, "InvokeRequired") and form.InvokeRequired:
                    form.Invoke(MethodInvoker(_do_cleanup))
                else:
                    _do_cleanup()
            elif sys.platform == "darwin":
                if self._tray and hasattr(self._tray, "statusBar"):
                    try:
                        from AppKit import NSStatusBar
                        NSStatusBar.systemStatusBar().removeStatusItem_(self._tray)
                    except Exception:
                        pass
                self._tray = None
                _GLOBAL_TRAY_REFS.clear()
            else:
                if self._tray and hasattr(self._tray, "stop"):
                    try:
                        self._tray.stop()
                    except Exception:
                        pass
                elif self._tray and hasattr(self._tray, "set_visible"):
                    try:
                        self._tray.set_visible(False)
                    except Exception:
                        pass
                self._tray = None
                _GLOBAL_TRAY_REFS.clear()
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
        """Native Windows WinForms NotifyIcon with ambient dark styling and custom icons."""
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
                Padding,
            )
            from System.Drawing import Icon, SystemIcons, Font, FontStyle, Size
            from System import EventHandler

            tray = NotifyIcon()
            icon_loaded = False
            if self.icon_path and self.icon_path.is_file():
                try:
                    tray.Icon = Icon(str(self.icon_path))
                    icon_loaded = True
                except Exception as ex:
                    logger.debug("Failed to load icon from %s: %s", self.icon_path, ex)
            if not icon_loaded:
                tray.Icon = SystemIcons.Application

            tray.Text = "Meikova Loop - Nhạc nhảy nhịp vô tận"[:63]

            menu = ContextMenuStrip()
            if AmbientDarkRenderer:
                menu.Renderer = AmbientDarkRenderer()

            menu.ImageScalingSize = Size(18, 18)
            menu.ShowImageMargin = True
            menu.ShowCheckMargin = False

            font_regular = Font("Segoe UI", 9.5, FontStyle.Regular)
            font_bold = Font("Segoe UI", 9.5, FontStyle.Bold)
            item_pad = Padding(4, 5, 4, 5)

            # 1. Header (disabled title item with logo icon)
            header = ToolStripMenuItem("Meikova Loop // v2.0")
            header.Enabled = False
            header.Font = font_bold
            header.Padding = Padding(4, 6, 4, 6)
            bmp_logo = self._get_tray_icon_bitmap("logo")
            if bmp_logo:
                header.Image = bmp_logo
            menu.Items.Add(header)
            menu.Items.Add(ToolStripSeparator())

            # 2. Show Window
            item_show = ToolStripMenuItem("Mở Meikova Loop")
            item_show.Font = font_regular
            item_show.Padding = item_pad
            bmp_win = self._get_tray_icon_bitmap("window")
            if bmp_win:
                item_show.Image = bmp_win
            item_show.Click += EventHandler(lambda s, e: self.show_window())
            menu.Items.Add(item_show)

            # 3. Open in Browser
            item_web = ToolStripMenuItem("Mở trên trình duyệt Web")
            item_web.Font = font_regular
            item_web.Padding = item_pad
            bmp_web = self._get_tray_icon_bitmap("browser")
            if bmp_web:
                item_web.Image = bmp_web
            item_web.Click += EventHandler(
                lambda s, e: webbrowser.open(f"http://127.0.0.1:{self.port}/")
            )
            menu.Items.Add(item_web)

            # 4. Open Data directory
            if self.data_dir and self.data_dir.exists():
                item_data = ToolStripMenuItem("Mở thư mục lưu trữ (Data)")
                item_data.Font = font_regular
                item_data.Padding = item_pad
                bmp_folder = self._get_tray_icon_bitmap("folder")
                if bmp_folder:
                    item_data.Image = bmp_folder

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
            self._autostart_item.Font = font_regular
            self._autostart_item.Padding = item_pad
            bmp_auto = self._get_tray_icon_bitmap("autostart_on" if auto_on else "autostart")
            if bmp_auto:
                self._autostart_item.Image = bmp_auto

            def _toggle_autostart(s, e):
                current = is_autostart_enabled()
                nxt = not current
                set_autostart(nxt)
                if self._autostart_item:
                    self._autostart_item.Text = (
                        f"Khởi động cùng Windows: {'Bật ✓' if nxt else 'Tắt'}"
                    )
                    new_bmp = self._get_tray_icon_bitmap("autostart_on" if nxt else "autostart")
                    if new_bmp:
                        self._autostart_item.Image = new_bmp

            self._autostart_item.Click += EventHandler(_toggle_autostart)
            menu.Items.Add(self._autostart_item)

            # 6. Reload UI
            item_reload = ToolStripMenuItem("Tải lại giao diện")
            item_reload.Font = font_regular
            item_reload.Padding = item_pad
            bmp_refresh = self._get_tray_icon_bitmap("refresh")
            if bmp_refresh:
                item_reload.Image = bmp_refresh
            item_reload.Click += EventHandler(
                lambda s, e: self.window.evaluate_js("window.location.reload()")
            )
            menu.Items.Add(item_reload)

            menu.Items.Add(ToolStripSeparator())

            # 7. Quit completely
            item_quit = ToolStripMenuItem("Thoát hoàn toàn")
            item_quit.Name = "item_quit"
            item_quit.Font = font_regular
            item_quit.Padding = item_pad
            bmp_quit = self._get_tray_icon_bitmap("quit")
            if bmp_quit:
                item_quit.Image = bmp_quit
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

            # Store strong reference to prevent GC from reclaiming the component
            _GLOBAL_TRAY_REFS.clear()
            _GLOBAL_TRAY_REFS.extend([tray, menu])

            logger.info("Native Windows system tray icon attached with ambient dark theme.")
        except Exception as e:
            logger.warning("Failed to initialize Windows WinForms NotifyIcon: %s", e)
            self._setup_fallback()

    def _setup_macos(self):
        """Native macOS status bar item via AppKit or pystray with custom icons."""
        try:
            import objc
            from AppKit import (
                NSStatusBar,
                NSMenu,
                NSMenuItem,
                NSImage,
                NSVariableStatusItemLength,
            )
            from Foundation import NSObject

            bar = NSStatusBar.systemStatusBar()
            item = bar.statusItemWithLength_(NSVariableStatusItemLength)

            # Set status bar icon
            logo_path = self._get_tray_icon_path("logo") or self.icon_path
            if logo_path and logo_path.is_file():
                ns_img = NSImage.alloc().initWithContentsOfFile_(str(logo_path))
                if ns_img:
                    ns_img.setSize_((18, 18))
                    ns_img.setTemplate_(True)
                    item.button().setImage_(ns_img)
            else:
                item.button().setTitle_("Meikova Loop")

            menu = NSMenu.alloc().init()

            def _ns_icon(name: str):
                p = self._get_tray_icon_path(name)
                if p:
                    img = NSImage.alloc().initWithContentsOfFile_(str(p))
                    if img:
                        img.setSize_((16, 16))
                        return img
                return None

            header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Meikova Loop // v2.0", None, ""
            )
            header.setEnabled_(False)
            h_img = _ns_icon("logo")
            if h_img:
                header.setImage_(h_img)
            menu.addItem_(header)
            menu.addItem_(NSMenuItem.separatorItem())

            class MenuTarget(NSObject):
                def init(self):
                    self = objc.super(MenuTarget, self).init()
                    return self

                def onShow_(self, sender):
                    self.tray.show_window()

                def onWeb_(self, sender):
                    webbrowser.open(f"http://127.0.0.1:{self.tray.port}/")

                def onData_(self, sender):
                    if self.tray.data_dir:
                        webbrowser.open(str(self.tray.data_dir))

                def onQuit_(self, sender):
                    self.tray.quit()

            target = MenuTarget.alloc().init()
            target.tray = self

            m_show = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Mở Meikova Loop", "onShow:", ""
            )
            m_show.setTarget_(target)
            img_win = _ns_icon("window")
            if img_win:
                m_show.setImage_(img_win)
            menu.addItem_(m_show)

            m_web = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Mở trên trình duyệt Web", "onWeb:", ""
            )
            m_web.setTarget_(target)
            img_web = _ns_icon("browser")
            if img_web:
                m_web.setImage_(img_web)
            menu.addItem_(m_web)

            if self.data_dir and self.data_dir.exists():
                m_data = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Mở thư mục lưu trữ (Data)", "onData:", ""
                )
                m_data.setTarget_(target)
                img_folder = _ns_icon("folder")
                if img_folder:
                    m_data.setImage_(img_folder)
                menu.addItem_(m_data)

            menu.addItem_(NSMenuItem.separatorItem())

            m_quit = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Thoát hoàn toàn", "onQuit:", "q"
            )
            m_quit.setTarget_(target)
            img_quit = _ns_icon("quit")
            if img_quit:
                m_quit.setImage_(img_quit)
            menu.addItem_(m_quit)

            item.setMenu_(menu)
            self._tray = item
            _GLOBAL_TRAY_REFS.extend([item, menu, target])
            logger.info("Native macOS status bar item created.")
            return
        except Exception as e:
            logger.debug("Native macOS status item failed, trying fallback: %s", e)

        self._setup_fallback()

    def _setup_linux(self):
        """Native Linux tray icon via Gtk.StatusIcon or pystray with custom icons."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk

            tray = Gtk.StatusIcon()
            logo_path = self._get_tray_icon_path("logo") or self.icon_path
            if logo_path and logo_path.is_file():
                tray.set_from_file(str(logo_path))
            tray.set_tooltip_text("Meikova Loop - Nhạc nhảy nhịp vô tận")

            def on_activate(widget):
                self.show_window()

            def on_popup_menu(status, button, activate_time):
                menu = Gtk.Menu()

                def _gtk_item(label, icon_name, on_click=None):
                    it = Gtk.ImageMenuItem(label=label)
                    p = self._get_tray_icon_path(icon_name)
                    if p:
                        it.set_image(Gtk.Image.new_from_file(str(p)))
                        it.set_always_show_image(True)
                    if on_click:
                        it.connect("activate", on_click)
                    return it

                header = _gtk_item("Meikova Loop // v2.0", "logo")
                header.set_sensitive(False)
                menu.append(header)
                menu.append(Gtk.SeparatorMenuItem())

                item_show = _gtk_item("Mở Meikova Loop", "window", lambda w: self.show_window())
                menu.append(item_show)

                item_web = _gtk_item(
                    "Mở trên trình duyệt Web",
                    "browser",
                    lambda w: webbrowser.open(f"http://127.0.0.1:{self.port}/"),
                )
                menu.append(item_web)

                if self.data_dir and self.data_dir.exists():
                    item_data = _gtk_item(
                        "Mở thư mục lưu trữ (Data)",
                        "folder",
                        lambda w: webbrowser.open(str(self.data_dir)),
                    )
                    menu.append(item_data)

                menu.append(Gtk.SeparatorMenuItem())

                item_quit = _gtk_item("Thoát hoàn toàn", "quit", lambda w: self.quit())
                menu.append(item_quit)

                menu.show_all()
                menu.popup(None, None, Gtk.StatusIcon.position_menu, tray, button, activate_time)

            tray.connect("activate", on_activate)
            tray.connect("popup-menu", on_popup_menu)
            tray.set_visible(True)

            self._tray = tray
            _GLOBAL_TRAY_REFS.append(tray)
            logger.info("Native Linux Gtk.StatusIcon created.")
            return
        except Exception as e:
            logger.debug("Native Linux Gtk.StatusIcon failed, trying fallback: %s", e)

        self._setup_fallback()

    def _setup_fallback(self):
        """Universal cross-platform tray runner via pystray."""
        try:
            import pystray
            from PIL import Image

            icon_file = self.icon_path
            if not icon_file or not icon_file.is_file():
                alt = self.icon_path.parent / "icon-192.png" if self.icon_path else None
                if alt and alt.is_file():
                    icon_file = alt

            if not icon_file or not icon_file.is_file():
                logger.debug("No icon file found for pystray fallback.")
                return

            img = Image.open(str(icon_file))
            menu = pystray.Menu(
                pystray.MenuItem("Meikova Loop // v2.0", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Mở Meikova Loop", lambda: self.show_window(), default=True),
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
                "Meikova Loop", img, "Meikova Loop - Nhạc nhảy nhịp vô tận", menu
            )
            _GLOBAL_TRAY_REFS.append(self._tray)
            import threading
            threading.Thread(target=self._tray.run, daemon=True, name="pystray-runner").start()
            logger.info("Fallback pystray icon started.")
        except Exception as e:
            logger.debug("Fallback pystray tray not active: %s", e)
