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

if __name__ == "__main__":
    test_ip_extraction()
    test_qr_api()
    test_samples_api()
    test_multi_source_detection()
    test_playlist_and_album_detection()
    test_ssrf_protection()
    test_track_id_generation()
    test_batch_tracks_api()
    print("ALL TESTS PASSED WITH EXIT CODE 0")
