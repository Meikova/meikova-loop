"""Unit tests for cross-platform DesktopTray and Autostart functions."""
import sys
import unittest
from pathlib import Path
from loopbox.config import DATA_DIR, WEB_DIR
from loopbox.tray import DesktopTray, is_autostart_enabled, set_autostart


class DummyWindow:
    def __init__(self):
        self.shown = False
        self.hidden = False
        self.destroyed = False

    def show(self):
        self.shown = True
        self.hidden = False

    def hide(self):
        self.hidden = True
        self.shown = False

    def restore(self):
        self.shown = True

    def destroy(self):
        self.destroyed = True

    def evaluate_js(self, script):
        pass


class TestDesktopTray(unittest.TestCase):
    def test_autostart_query(self):
        # Querying autostart status should return a bool without raising
        status = is_autostart_enabled("MashLoopTest")
        self.assertIsInstance(status, bool)

    def test_tray_initialization(self):
        win = DummyWindow()
        icon = WEB_DIR / "img" / ("icon.ico" if sys.platform == "win32" else "icon-192.png")
        quit_called = []
        tray = DesktopTray(
            window=win,
            port=8765,
            icon_path=icon,
            data_dir=DATA_DIR,
            on_quit=lambda: quit_called.append(True),
        )
        self.assertFalse(tray.is_quitting)
        self.assertFalse(tray._balloon_shown)

        # Test handle_closing returns False (cancels close and hides to tray)
        res = tray.handle_closing()
        self.assertFalse(res)
        self.assertTrue(win.hidden)

        # Test show_window restores window
        tray.show_window()
        self.assertTrue(win.shown)

        # Test quit
        tray.quit()
        self.assertTrue(tray.is_quitting)
        self.assertTrue(win.destroyed)
        self.assertEqual(quit_called, [True])

        # After quitting, handle_closing should return True (allow close)
        res_after_quit = tray.handle_closing()
        self.assertTrue(res_after_quit)


if __name__ == "__main__":
    unittest.main()
