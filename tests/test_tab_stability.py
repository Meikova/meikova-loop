"""
Test Tab Width Stability and Zero-Jitter Mandate for Meikova Loop.
Ensures switching between 'Thư viện' and 'Tinh chỉnh' tabs never shifts or fluctuates panel width.
"""
from pathlib import Path


def test_tab_and_panel_css_stability():
    css = Path("web/css/app.css").read_text(encoding="utf-8")
    js = Path("web/js/main.js").read_text(encoding="utf-8")
    html = Path("web/index.html").read_text(encoding="utf-8")
    sw = Path("web/sw.js").read_text(encoding="utf-8")

    # 1. Panel CSS must lock width to --panel-w with zero horizontal overflow
    assert "width: var(--panel-w);" in css, "Missing 'width: var(--panel-w);' on .panel"
    assert "min-width: var(--panel-w);" in css, "Missing 'min-width: var(--panel-w);' on .panel"
    assert "max-width: var(--panel-w);" in css, "Missing 'max-width: var(--panel-w);' on .panel"
    assert "overflow-x: hidden;" in css, "Missing 'overflow-x: hidden;' on .panel or .tab"

    # 2. .tab must have scrollbar-gutter: stable and full-width bounds
    assert "scrollbar-gutter: stable;" in css, "Missing 'scrollbar-gutter: stable;' on .tab"
    assert "width: 100%;" in css, "Missing 'width: 100%;' on .tab"
    assert "max-width: 100%;" in css, "Missing 'max-width: 100%;' on .tab"

    # 3. tab-in animation must not use translateY which causes reflow jitter
    assert "@keyframes tab-in { from { opacity: 0; } to { opacity: 1; } }" in css, \
        "tab-in animation must be a clean opacity fade to avoid layout shift"

    # 4. Immediate --panel-w application in main.js
    assert 'document.documentElement.style.setProperty("--panel-w", `${ui.panelWidth}px`);' in js, \
        "main.js must apply --panel-w immediately upon reading localStorage"

    # 5. Asset version match v175
    assert "app.css?v=175" in html, "index.html missing v=175 for app.css"
    assert "main.js?v=175" in html, "index.html missing v=175 for main.js"
    assert "sw.js?v=175" in html, "index.html missing v=175 for sw.js"
    assert "meikova-loop-v175" in sw, "sw.js missing meikova-loop-v175 cache name"

    print("ALL TAB STABILITY UNIT TESTS PASSED (EXIT CODE 0)!")


if __name__ == "__main__":
    test_tab_and_panel_css_stability()
