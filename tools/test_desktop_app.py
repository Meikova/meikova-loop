"""Automated test for Desktop backend and API integration."""
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fastapi.testclient
from loopbox import desktop, sessions
from loopbox.server import app

client = fastapi.testclient.TestClient(app)


def test_desktop_bridge():
    bridge = desktop.DesktopBridge(8765)
    assert bridge.is_desktop() is True
    sys_info = bridge.get_sys_info()
    assert "os" in sys_info
    assert "device" in sys_info
    print(f"PASS: DesktopBridge sys_info = {sys_info}")


def test_ingest_local_security():
    # Attempting to call ingest_local with a remote host should fail with 403
    r = client.post(
        "/api/desktop/ingest_local",
        json={"paths": ["C:/fake/path.mp3"]},
        headers={"X-Forwarded-For": "203.0.113.195"},
    )
    # The endpoint validates client IP
    assert r.status_code in (403, 400), f"Expected 403 or 400, got {r.status_code}"
    print(f"PASS: Ingest local security check: status {r.status_code}")


def test_ingest_local_execution():
    # Create a small valid WAV file in a temporary folder
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Write minimal 44-byte WAV header + silence
        import wave
        with wave.open(f, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(b"\x00" * 88200)  # 1 second of silence
        temp_wav = f.name

    try:
        # Create session
        s_resp = client.post("/api/session")
        sid = s_resp.json()["sid"]

        # Call ingest_local
        r = client.post(
            "/api/desktop/ingest_local",
            json={"paths": [temp_wav]},
            headers={"X-Session": sid},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "added" in data
        assert len(data["added"]) == 1
        tid = data["added"][0]["id"]
        print(f"PASS: Successfully ingested local file into track {tid}")

        # Verify track is listed in session
        tr_resp = client.get("/api/tracks", headers={"X-Session": sid})
        tracks = tr_resp.json()["tracks"]
        assert any(t["id"] == tid for t in tracks), f"Track {tid} not in tracks list"
        print(f"PASS: Track {tid} confirmed in session tracks list")

    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass


def main():
    test_desktop_bridge()
    test_ingest_local_security()
    test_ingest_local_execution()
    print("\nALL DESKTOP INTEGRATION TESTS PASSED (Exit Code 0)")
    return 0


if __name__ == "__main__":
    os._exit(main())
