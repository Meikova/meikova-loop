import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from starlette.requests import Request
from starlette.testclient import TestClient

from loopbox.server import app, _ip

def test_ip_extraction():
    # Direct connection without X-Forwarded-For
    scope_direct = {
        "type": "http",
        "headers": [],
        "client": ("192.168.1.10", 12345),
    }
    req_direct = Request(scope_direct)
    assert _ip(req_direct) == "192.168.1.10"

    # Reverse proxy with single X-Forwarded-For
    scope_proxy = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.195")],
        "client": ("10.0.0.1", 12345),
    }
    req_proxy = Request(scope_proxy)
    assert _ip(req_proxy) == "203.0.113.195"

    # Multi-hop proxy chain: client, proxy1, proxy2
    scope_multiproxy = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 10.0.0.2, 10.0.0.3")],
        "client": ("10.0.0.1", 12345),
    }
    req_multiproxy = Request(scope_multiproxy)
    assert _ip(req_multiproxy) == "203.0.113.195"

def test_qr_api():
    client = TestClient(app)
    resp = client.get("/api/qr?url=https://m3ik18dp-mashloop.hf.space")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers.get("content-type", "")
    assert "<svg" in resp.text

def test_samples_api():
    client = TestClient(app)
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert "libraries" in data
    assert isinstance(data["libraries"], list)

def test_multi_source_detection():
    from loopbox import download
    assert download.site_of("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
    assert download.site_of("https://youtu.be/dQw4w9WgXcQ") == "youtube"
    assert download.site_of("https://soundcloud.com/artist/track") == "soundcloud"
    assert download.site_of("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") == "spotify"
    assert download.site_of("https://zingmp3.vn/bai-hat/test/ZWZB986W.html") == "zingmp3"
    assert download.site_of("https://artist.bandcamp.com/track/song") == "bandcamp"
    assert download.site_of("https://www.tiktok.com/@user/video/123456789") == "tiktok"
    assert download.site_of("https://www.facebook.com/reel/123456789") == "facebook"
    assert download.site_of("https://www.instagram.com/reel/C8abcde123/") == "instagram"
    assert download.site_of("https://x.com/user/status/123456789") == "twitter"
    assert download.site_of("https://www.bilibili.com/video/BV1xx411c7mD") == "bilibili"
    assert download.site_of("https://vimeo.com/123456789") == "vimeo"
    assert download.site_of("https://www.dailymotion.com/video/x8abcde") == "dailymotion"
    assert download.site_of("https://audius.co/artist/track-name") == "audius"
    assert download.site_of("https://archive.org/download/test/song.mp3") == "generic"

def test_playlist_and_album_detection():
    from loopbox import download
    assert download.is_playlist_url("https://www.youtube.com/playlist?list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI") is True
    assert download.is_playlist_url("https://www.youtube.com/watch?v=abc&list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI") is True
    assert download.is_playlist_url("https://www.youtube.com/watch?v=abc&list=OLAK5uy_k12345") is True
    assert download.is_playlist_url("https://www.youtube.com/watch?v=abc&list=RD12345") is True  # radio mix is now supported as playlist
    assert download.is_playlist_url("https://open.spotify.com/album/4m2880jivSbbyEGAKfITCa") is True
    assert download.is_playlist_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is True
    assert download.is_playlist_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") is False
    assert download.is_playlist_url("https://soundcloud.com/artist/sets/my-album") is True
    assert download.is_playlist_url("https://zingmp3.vn/album/test/ZWZB986W.html") is True

def test_ssrf_protection():
    from loopbox import download
    assert download.site_of("http://localhost:8765/test.mp3") is None
    assert download.site_of("http://127.0.0.1:8765/test.mp3") is None
    assert download.site_of("http://0.0.0.0:8765/test.mp3") is None
    assert download.site_of("http://169.254.169.254/latest/meta-data") is None
    assert download.site_of("http://192.168.1.1/admin") is None
    assert download.site_of("http://10.0.0.5/api") is None
    assert download.site_of("http://172.16.0.1/test") is None

def test_track_id_generation():
    from loopbox import download
    # YouTube keeps 11 char ID
    assert download.track_id("youtube", "dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Other sites get x + 16 hex digits
    tid = download.track_id("soundcloud", "12345678")
    assert tid.startswith("x") and len(tid) == 17

def test_batch_tracks_api():
    client = TestClient(app)
    # Test batch enable/disable
    resp = client.post("/api/tracks/batch", json={"ids": ["dQw4w9WgXcQ"], "action": "enable"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("enabled") is True

    resp_off = client.post("/api/tracks/batch", json={"ids": ["dQw4w9WgXcQ"], "action": "disable"})
    assert resp_off.status_code == 200
    data_off = resp_off.json()
    assert data_off.get("enabled") is False

def test_frontend_playlist_management():
    # Verify index.html contains the new batch and playlist modal elements
    index_html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    assert "batch-btn-pl-remove" in index_html
    assert "pl-modal-mode" in index_html
    assert "pl-mode-copy" in index_html
    assert "pl-mode-move" in index_html

    # Verify app.css contains the new classes
    app_css = (Path(__file__).resolve().parent.parent / "web" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".batch-btn--warn" in app_css
    assert ".pl-modal__mode" in app_css
    assert ".pl-btn-apply" in app_css
    assert 'button[data-act="pl-remove"]' in app_css
    assert 'button[data-act="move-up"]' in app_css

    # Verify main.js contains required actions and icons
    main_js = (Path(__file__).resolve().parent.parent / "web" / "js" / "main.js").read_text(encoding="utf-8")
    assert "plRemove:" in main_js
    assert "apply-copy" in main_js
    assert 'case "pl-remove":' in main_js

def test_search_sort_queue_inspect():
    # Verify index.html contains tools and inspect modal
    index_html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    assert "lib-tools" in index_html
    assert "lib-search-input" in index_html
    assert "lib-sort-select" in index_html
    assert "inspect-modal" in index_html

    # Verify app.css contains styles
    app_css = (Path(__file__).resolve().parent.parent / "web" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".lib-tools" in app_css
    assert ".lib-search" in app_css
    assert ".lib-sort" in app_css
    assert ".inspect-modal" in app_css
    assert ".badge-queued" in app_css

    # Verify player.js contains targetNextId and setTargetNext
    player_js = (Path(__file__).resolve().parent.parent / "web" / "js" / "player.js").read_text(encoding="utf-8")
    assert "targetNextId" in player_js
    assert "setTargetNext" in player_js

    # Verify main.js contains required actions, icons, and listeners
    main_js = (Path(__file__).resolve().parent.parent / "web" / "js" / "main.js").read_text(encoding="utf-8")
    assert "queueNext:" in main_js
    assert "download:" in main_js
    assert "inspect:" in main_js
    assert 'data-act="queue-next"' in main_js
    assert 'data-act="download"' in main_js
    assert 'data-act="inspect"' in main_js
    assert "downloadTrack(" in main_js
    assert "openInspectModal(" in main_js
    assert "libSearchQuery" in main_js
    assert "libSortMode" in main_js
    assert "target-next" in main_js
    assert "lib-sort-popover" in index_html
    assert "lib-sort-btn" in index_html
    assert "lib-sort-popover" in app_css
    assert "batch-bar__head" in index_html
    assert "batch-bar__head" in app_css
    assert ".inspect-acts" in app_css
    assert ".track .acts button:focus-visible" in app_css

def test_zen_hud_and_neon_engine():
    root = Path(__file__).resolve().parent.parent
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    app_css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")
    theme_js = (root / "web" / "js" / "theme.js").read_text(encoding="utf-8")
    main_js = (root / "web" / "js" / "main.js").read_text(encoding="utf-8")

    # Zen fullscreen & HUD elements
    assert "btn-zen" in index_html
    assert "btn-zen-exit" in index_html
    assert "zen-hud-top" in index_html
    assert "zen-fx-tape" in index_html
    assert "zen-fx-sweep" in index_html
    assert "zen-glow-toggle" in index_html
    assert ".btn-topbar-zen" in app_css
    assert ".zen-hud-top" in app_css
    assert "toggleZen" in main_js
    assert "is-zen" in main_js
    assert "updateZenUI" in main_js

    # Neon glow engine
    assert 'id="s-glow"' in index_html
    assert "setGlow" in theme_js
    assert "reapply" in theme_js
    assert "--glow-mult" in app_css
    assert "--glow-mult" in theme_js

def test_responsive_mobile_declutter():
    root = Path(__file__).resolve().parent.parent
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    app_css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")
    sw_js = (root / "web" / "sw.js").read_text(encoding="utf-8")

    # Cache bump
    assert "mashloop-v68" in sw_js
    assert "app.css?v=68" in index_html
    assert "main.js?v=68" in index_html
    assert "sw.js?v=68" in index_html

    # Segmented tabs SVG icons
    assert '<button type="button" data-tab="library"' in index_html or 'data-tab="library"' in index_html
    assert '<button type="button" data-tab="settings"' in index_html or 'data-tab="settings"' in index_html
    assert 'data-tab="library"' in index_html and 'data-tab="settings"' in index_html

    # Mobile topbar buttons & SVG actions
    assert "max-width: 520px" in app_css
    assert "pl-action-btn--play" in index_html
    assert "btn-relink" in index_html
    assert "inspect-modal" in index_html

def test_volume_svg_bounds_and_night_button():
    root = Path(__file__).resolve().parent.parent
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    app_css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")
    main_js = (root / "web" / "js" / "main.js").read_text(encoding="utf-8")
    engine_js = (root / "web" / "js" / "engine.js").read_text(encoding="utf-8")

    # Volume icon must not have outer arc clipping at x > 24
    assert 'M21.5 4.5a10.5 10.5 0 0 1 0 15' not in index_html, "Old clipping arc path must be replaced"
    assert 'M19 4.5a14 14 0 0 1 0 15' in index_html, "New perfectly bounded arc path must be present"
    assert "M2 9.5h3.5L10 6v12l-4.5-3.5H2z" in index_html, "Speaker cone must start at x=2 for balanced margin"
    assert ".deck__vol svg" in app_css
    assert "overflow: visible" in app_css, "Volume SVG must have overflow visible to avoid clipping"

    # Night mode button on deck & Vietnam UTC+7 schedule
    assert "btn-night" in index_html
    assert ".deck__night" in app_css
    assert "body.is-night" in app_css
    assert "btn-night" in main_js
    assert "getVietnamHour" in main_js
    assert "Asia/Ho_Chi_Minh" in main_js
    assert "checkNightButtonVisibility" in main_js
    assert "setNightMode" in engine_js

    # Typographic orphan word fix in footer
    assert "text-wrap: pretty" in app_css
    assert "cá&nbsp;nhân" in index_html

def test_download_error_handling_and_ui_cleanup():
    root = Path(__file__).resolve().parent.parent
    from loopbox import download
    import loopbox.ingest as ingest

    # Test bot verification message cleaning
    bot_raw = "DownloadError: ERROR: [youtube] B-ygvoi4-Mg: Sign in to confirm you're not a bot. This helps protect our community. Learn more: https://support.google.com/youtube/answer/123. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp for how to pass cookies to yt-dlp"
    bot_clean = download.clean_error(bot_raw)
    assert "YouTube yêu cầu xác minh bot" in bot_clean
    assert "http" not in bot_clean
    assert "cookies" not in bot_clean
    assert len(bot_clean) <= 120

    # Test unavailable message cleaning
    unavail_raw = "DownloadError: ERROR: [youtube] abc12345678: This video is unavailable"
    unavail_clean = download.clean_error(unavail_raw)
    assert "không khả dụng" in unavail_clean

    # Verify js_runtimes in BASE_OPTS and dynamic client selection
    assert "js_runtimes" in download.BASE_OPTS
    opts = download._opts("youtube")
    assert "allowed_extractors" in opts

    # Verify Deno in Dockerfile
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "denoland/deno:bin" in dockerfile

    # Verify ingest error handling
    ingest_py = (root / "loopbox" / "ingest.py").read_text(encoding="utf-8")
    assert "download.clean_error(e)" in ingest_py

    # Verify frontend 2-line clamping & clean error rendering
    app_css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")
    main_js = (root / "web" / "js" / "main.js").read_text(encoding="utf-8")
    assert "-webkit-line-clamp: 2" in app_css
    assert "cleanUiError" in main_js

def test_cookies_api_and_playlist_scroll_navigation():
    root = Path(__file__).resolve().parent.parent
    client = TestClient(app)

    # Clean existing test cookies
    client.delete("/api/cookies")

    # Initial cookie status
    res = client.get("/api/cookies")
    assert res.status_code == 200
    assert res.json()["has_cookies"] is False

    # Upload test Netscape cookies
    test_cookie = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tLOGIN_INFO\ttest_token_value\n"
    res_upload = client.post("/api/cookies", json={"content": test_cookie})
    assert res_upload.status_code == 200
    data = res_upload.json()
    assert data["success"] is True
    assert "YouTube" in data["domains"]

    # Verify cookie status is now active
    res_status = client.get("/api/cookies")
    assert res_status.status_code == 200
    assert res_status.json()["has_cookies"] is True
    assert "YouTube" in res_status.json()["domains"]

    # Delete cookies
    res_del = client.delete("/api/cookies")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # Verify cookie status is false again
    res_after = client.get("/api/cookies")
    assert res_after.json()["has_cookies"] is False

    # Test env var cookie loading (for Hugging Face Space secrets)
    import os
    from loopbox import cookies as cookie_mgr
    os.environ["YOUTUBE_COOKIES"] = test_cookie
    try:
        p = cookie_mgr.get_cookie_file_path()
        assert p is not None
        assert p.exists()
    finally:
        os.environ.pop("YOUTUBE_COOKIES", None)
        client.delete("/api/cookies")

    # Verify playlist scroll navigation & hidden relink section
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    app_css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")
    main_js = (root / "web" / "js" / "main.js").read_text(encoding="utf-8")

    assert "pl-scroll-left" in index_html
    assert "pl-scroll-right" in index_html
    assert ".pl-nav__arrow" in app_css
    assert "group-relink" in index_html
    assert "group-relink" in main_js
    assert "cookie-modal" in index_html
    assert "initCookieManagement" in main_js

def test_track_cancellation_on_delete():
    from loopbox import library, worker, sessions, server
    client = TestClient(app)
    test_id = "testcanc001"
    library.create(test_id, source="test", url="http://example.com", title="Test Cancel", status="queued", stage="queued")
    assert library.is_cancelled(test_id) is False
    worker.enqueue_ingest(test_id)
    assert test_id in worker._ingesting

    # Test sessions.in_use signatures
    assert isinstance(sessions.in_use(), set)
    assert isinstance(sessions.in_use(test_id), bool)

    # Test delete under MULTIUSER = True (Space environment)
    orig_multi = server.MULTIUSER
    try:
        server.MULTIUSER = True
        res = client.delete(f"/api/tracks/{test_id}")
        assert res.status_code == 200
        assert library.is_cancelled(test_id) is True
        assert test_id not in worker._ingesting

        # Test batch delete under MULTIUSER = True
        test_id2 = "testcanc002"
        library.create(test_id2, source="test", url="http://example.com", title="Test Cancel 2", status="queued", stage="queued")
        worker.enqueue_ingest(test_id2)
        res_batch = client.post("/api/tracks/batch", json={"action": "delete", "ids": [test_id2]})
        assert res_batch.status_code == 200
        assert library.is_cancelled(test_id2) is True
        assert test_id2 not in worker._ingesting
        library.clear_cancelled(test_id2)
    finally:
        server.MULTIUSER = orig_multi
        library.clear_cancelled(test_id)

def test_max_duration_guard_and_frontend_limits():
    """Verify backend max duration is 15 minutes and frontend guards protect against Web Audio OOM."""
    from loopbox import config
    assert config.TARGET_LUFS == -14.0
    assert config.MAX_DURATION_S == 15 * 60, f"Expected 900s, got {config.MAX_DURATION_S}"

    api_js = (Path(__file__).parent.parent / "web" / "js" / "api.js").read_text(encoding="utf-8")
    assert "MAX_SAFE_DURATION_S" in api_js
    assert "isOversized" in api_js

    player_js = (Path(__file__).parent.parent / "web" / "js" / "player.js").read_text(encoding="utf-8")
    assert "isOversized" in player_js
    assert "plan-failed" in player_js

if __name__ == "__main__":
    test_ip_extraction()
    test_qr_api()
    test_samples_api()
    test_multi_source_detection()
    test_playlist_and_album_detection()
    test_ssrf_protection()
    test_track_id_generation()
    test_batch_tracks_api()
    test_frontend_playlist_management()
    test_search_sort_queue_inspect()
    test_zen_hud_and_neon_engine()
    test_responsive_mobile_declutter()
    test_volume_svg_bounds_and_night_button()
    test_download_error_handling_and_ui_cleanup()
    test_cookies_api_and_playlist_scroll_navigation()
    test_track_cancellation_on_delete()
    test_max_duration_guard_and_frontend_limits()
    print("ALL TESTS PASSED WITH EXIT CODE 0")


