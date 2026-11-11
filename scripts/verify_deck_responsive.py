"""Verify Deck Responsive HTML, CSS, Cluster Link (PartyBoost), and Zero-Echo Sync."""
from pathlib import Path


def test_deck_and_panel():
    html = Path("web/index.html").read_text(encoding="utf-8")
    css = Path("web/css/app.css").read_text(encoding="utf-8")
    sw = Path("web/sw.js").read_text(encoding="utf-8")
    main_js = Path("web/js/main.js").read_text(encoding="utf-8")
    stage_sync_js = Path("web/js/stage_sync.js").read_text(encoding="utf-8")
    engine_js = Path("web/js/engine.js").read_text(encoding="utf-8")

    # Verify CSS/JS/SW version bump to v176
    assert 'css/app.css?v=176' in html, "CSS version not bumped to v176 in index.html"
    assert 'js/main.js?v=176' in html, "JS version not bumped to v176 in index.html"
    assert 'sw.js?v=176' in html, "SW version not bumped to v176 in index.html"
    assert 'meikova-loop-v176' in sw, "Cache version not bumped to v176 in sw.js"

    # Verify Shelf Head concise title (Less Text, More Signal)
    assert 'Kho bài' in html, "Missing concise title 'Kho bài' in index.html"
    assert 'Các vòng trong thư viện' not in html, "Old verbose title still in index.html"

    # Verify HTML structure
    assert html.count('<div class="deck"') == 1
    assert html.count('<div class="deck__row deck__row--primary">') == 1
    assert html.count('<div class="deck__row deck__row--secondary">') == 1

    deck_start = html.find('<div class="deck"')
    deck_end = html.find('</div>\n      </div>\n\n        <ol', deck_start)
    if deck_end == -1:
        deck_end = html.find('</div>\r\n      </div>\r\n\r\n        <ol', deck_start)
    assert deck_end != -1, "Deck closing tags mismatch"
    deck_html = html[deck_start:deck_end]

    # Verify button IDs inside deck
    for btn_id in [
        "btn-lock", "btn-jump", "btn-play", "btn-next", "btn-kho",
        "btn-record", "btn-vocal-mode", "btn-karaoke-mic", "btn-timer",
        "btn-night", "btn-eq", "btn-mute"
    ]:
        assert f'id="{btn_id}"' in deck_html, f"Missing {btn_id} in deck"

    # Verify Panel Collapse and Expand Buttons in HTML
    assert 'id="btn-panel-collapse"' in html, "Missing #btn-panel-collapse in index.html"
    assert 'id="btn-panel-expand"' in html, "Missing #btn-panel-expand in index.html"
    assert 'id="btn-topbar-panel"' in html, "Missing #btn-topbar-panel in index.html"

    # Verify Cluster Link & Member Banner in HTML
    assert 'id="btn-nav-cluster"' in html, "Missing #btn-nav-cluster in index.html"
    assert 'id="cluster-member-banner"' in html, "Missing #cluster-member-banner in index.html"
    assert 'id="btn-cluster-stage-mirror"' in html, "Missing #btn-cluster-stage-mirror in index.html"
    assert 'id="btn-cluster-leave"' in html, "Missing #btn-cluster-leave in index.html"
    assert 'id="modalClusterLink"' in html, "Missing #modalClusterLink in index.html"
    assert 'id="btn-cluster-mode-party"' in html, "Missing #btn-cluster-mode-party in index.html"
    assert 'id="btn-cluster-mode-stereo"' in html, "Missing #btn-cluster-mode-stereo in index.html"

    # Verify CSS rules
    assert ".deck__row {" in css, "Missing .deck__row default rule"
    assert "overflow-x: hidden" in css, "Missing viewport overflow-x: hidden"
    assert "@media (max-width: 600px)" in css, "Missing @media (max-width: 600px)"
    assert ".deck__row--primary" in css, "Missing .deck__row--primary CSS"
    assert ".deck__row--secondary" in css, "Missing .deck__row--secondary CSS"
    assert "position: fixed !important;" in css, "Missing fixed popovers on mobile"
    assert "orientation: landscape" in css, "Missing orientation: landscape rule"
    assert "clamp(240px, 28vw, 280px) !important;" in css, "Missing direct layout grid column clamp"
    assert "padding: 3px 14px !important;" in css, "Missing 14px deck safe pill padding"
    assert "height: 40px !important;" in css, "Missing 40px deck height in landscape"
    assert "overflow: visible !important;" in css, "Missing overflow: visible on deck in landscape"
    assert "min-height: 46px !important;" in css, "Missing 46px min-height on track card in landscape"
    assert "#btn-lock {" in css, "Missing #btn-lock clearance rule"
    assert ".deck__vol input," in css, "Missing deck__vol input hidden rule"

    # Verify Panel Collapse and Expand CSS
    assert ".btn-panel-collapse" in css, "Missing .btn-panel-collapse in app.css"
    assert ".btn-panel-expand" in css, "Missing .btn-panel-expand in app.css"
    assert ".btn-topbar-panel" in css, "Missing .btn-topbar-panel in app.css"
    assert "body.is-panel-collapsed .layout" in css, "Missing body.is-panel-collapsed .layout in app.css"
    assert "body.is-panel-collapsed #panel" in css, "Missing body.is-panel-collapsed #panel in app.css"
    assert "min-height: 22px !important;" in css, "Missing min-height override for segmented buttons in landscape"
    assert "#add-hint," in css, "Missing #add-hint hide rule in landscape"
    assert ".shelf-head .label {" in css, "Missing .shelf-head .label single-line ellipsis rule"
    assert "@media (max-width: 560px)" in css, "Missing @media (max-width: 560px) topbar responsive rule"
    assert "width: 28px !important;" in css, "Missing 28px !important override for topbar__end buttons on narrow viewports"
    assert "new ResizeObserver(placeIndicators)" in main_js, "Missing ResizeObserver for .seg indicator placement"

    # Verify Cluster Link & Zero-Echo CSS & JS
    assert ".cluster-member-banner" in css, "Missing .cluster-member-banner in app.css"
    assert "body.is-cluster-mirror" in css, "Missing body.is-cluster-mirror in app.css"
    assert ".cluster-node-card" in css, "Missing .cluster-node-card in app.css"
    assert ".cluster-mode-switch" in css, "Missing .cluster-mode-switch in app.css"
    assert "setSpeakerSyncDelay" in engine_js, "Missing setSpeakerSyncDelay in engine.js"
    assert "setOutputChannelMode" in engine_js, "Missing setOutputChannelMode in engine.js"
    assert "_startNtpSyncLoop" in stage_sync_js, "Missing _startNtpSyncLoop in stage_sync.js"
    assert "setClusterMirrorMode" in stage_sync_js, "Missing setClusterMirrorMode in stage_sync.js"

    # Verify JS panel collapse logic
    assert "updatePanelCollapseUI" in main_js, "Missing updatePanelCollapseUI in main.js"
    assert "togglePanelCollapse" in main_js, "Missing togglePanelCollapse function in main.js"
    assert "btn-panel-collapse" in main_js, "Missing btn-panel-collapse event listener in main.js"
    assert "btn-panel-expand" in main_js, "Missing btn-panel-expand event listener in main.js"
    assert "btn-topbar-panel" in main_js, "Missing btn-topbar-panel event listener in main.js"
    assert "is-panel-collapsed" in main_js, "Missing is-panel-collapsed class toggle in main.js"
    assert 'if (e.ctrlKey || e.metaKey) return;' in main_js, "Missing ctrlKey/metaKey guard in global keydown handler"
    assert 'grid-template-columns: repeat(3, minmax(0, 1fr));' in css, "Missing 3-column grid for .platform-tabs"
    assert 'platform-tab__sub' in html and '.platform-tab__sub' in css, "Missing responsive .platform-tab__sub sub-label"
    assert 'sync-tab__sub' in html and '.sync-tab__sub' in css, "Missing responsive .sync-tab__sub sub-label"
    assert 'light-device-sub-row' in stage_sync_js and '.light-device-sub-row' in css, "Missing .light-device-sub-row anti-overlap layout"
    assert 'height: fit-content !important;' in css, "Missing height: fit-content on mobile dialog modals"

    print("ALL TESTS PASSED: Deck responsive layout, Panel Collapse, Cluster Link & Zero-Echo Sync verified!")


if __name__ == "__main__":
    test_deck_and_panel()
