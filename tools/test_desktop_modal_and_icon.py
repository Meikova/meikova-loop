"""Verification test for custom desktop icon and universal modal dialogs."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_desktop_icon():
    print("=== Testing Desktop Icon Integration ===")
    ico_file = ROOT / "web" / "img" / "icon.ico"
    assert ico_file.is_file(), f"Missing icon at {ico_file}"
    assert ico_file.stat().st_size > 1000, f"Icon file too small: {ico_file.stat().st_size} bytes"
    print(f"PASS: Icon file exists ({ico_file.stat().st_size} bytes)")

    desktop_py = ROOT / "loopbox" / "desktop.py"
    content = desktop_py.read_text(encoding="utf-8")
    assert "WEB_DIR" in content, "Missing WEB_DIR in desktop.py"
    assert "set_window_icon" in content, "Missing set_window_icon in desktop.py"
    assert "icon=icon_str" in content, "Missing icon argument in webview.start"
    print("PASS: desktop.py correctly configures window and taskbar icon")


def test_modal_dialogs():
    print("\n=== Testing Universal Ambient Modal Dialogs ===")
    html_file = ROOT / "web" / "index.html"
    html = html_file.read_text(encoding="utf-8")
    assert 'id="app-modal"' in html, "Missing #app-modal dialog in index.html"
    assert 'id="modal-title"' in html, "Missing #modal-title in index.html"
    assert 'id="modal-body"' in html, "Missing #modal-body in index.html"
    assert 'id="modal-cancel"' in html, "Missing #modal-cancel in index.html"
    assert 'id="modal-ok"' in html, "Missing #modal-ok in index.html"
    print("PASS: web/index.html includes #app-modal dialog structure")

    css_file = ROOT / "web" / "css" / "app.css"
    css = css_file.read_text(encoding="utf-8")
    assert ".consent__yes--danger" in css, "Missing .consent__yes--danger in app.css"
    assert ".modal-dialog" in css, "Missing .modal-dialog in app.css"
    print("PASS: web/css/app.css includes danger button and modal styling")

    js_file = ROOT / "web" / "js" / "main.js"
    js = js_file.read_text(encoding="utf-8")
    assert "function showModal(" in js, "Missing showModal implementation in main.js"
    assert "window.alert =" in js, "Missing window.alert override in main.js"

    # Verify no raw alert/confirm calls outside showModal definition
    alert_matches = [m.start() for m in re.finditer(r"\balert\(", js)]
    confirm_matches = [m.start() for m in re.finditer(r"\bconfirm\(", js)]
    print(f"PASS: main.js defines showModal and overrides window.alert (alert call count: {len(alert_matches)}, confirm call count: {len(confirm_matches)})")
    assert len(alert_matches) <= 1, f"Found unexpected alert() calls: {len(alert_matches)}"
    assert len(confirm_matches) <= 1, f"Found unexpected confirm() calls: {len(confirm_matches)}"


def main():
    test_desktop_icon()
    test_modal_dialogs()
    print("\nALL DESKTOP ICON & MODAL VERIFICATION TESTS PASSED (Exit Code 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
