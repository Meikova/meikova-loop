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

if __name__ == "__main__":
    test_ip_extraction()
    test_qr_api()
    test_samples_api()
    print("ALL TESTS PASSED WITH EXIT CODE 0")
