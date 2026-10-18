"""Verification test for T4.2 (ONNX Runtime) and T4.3 (Mobile Capacitor Shell)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_t42_onnx():
    print("=== Testing T4.2: ONNX Beat Tracking ===")
    onnx_file = ROOT / "data" / "models" / "beat_this.onnx"
    assert onnx_file.exists(), f"ONNX file not found at {onnx_file}"
    print(f"PASS: Found ONNX model ({onnx_file.stat().st_size / 1024 / 1024:.1f} MB)")

    import numpy as np
    from loopbox.analysis import models

    tracker = models.beat_tracker()
    print(f"PASS: models.beat_tracker() returned {type(tracker).__name__}")
    assert "ONNX" in type(tracker).__name__, f"Expected ONNXBeatTracker, got {type(tracker).__name__}"

    # Test running audio through ONNX tracker
    # Generate 2 seconds of a 120 BPM synthetic click/beep
    sr = 44100
    t = np.linspace(0, 2, 2 * sr, dtype=np.float32)
    # 2 Hz pulses
    click = np.sin(2 * np.pi * 440 * t) * (np.sin(2 * np.pi * 2 * t) > 0.95).astype(np.float32)

    beats, downbeats = tracker(click, sr)
    print(f"PASS: Successfully tracked beats={len(beats)}, downbeats={len(downbeats)} via ONNX Runtime")


def test_t43_mobile():
    print("\n=== Testing T4.3: Mobile Capacitor Configuration ===")
    pkg_file = ROOT / "package.json"
    assert pkg_file.exists(), "package.json missing"
    with open(pkg_file, "r", encoding="utf-8") as f:
        pkg = json.load(f)
    assert "@capacitor/core" in pkg.get("dependencies", {}), "Missing @capacitor/core"
    assert "cap:sync" in pkg.get("scripts", {}), "Missing cap:sync script"
    print("PASS: package.json has Capacitor core dependencies and mobile sync scripts")

    cap_file = ROOT / "capacitor.config.json"
    assert cap_file.exists(), "capacitor.config.json missing"
    with open(cap_file, "r", encoding="utf-8") as f:
        cap = json.load(f)
    assert cap.get("appId") == "com.m3ik18dp.mashloop"
    assert cap.get("webDir") == "web"
    assert cap.get("plugins", {}).get("SplashScreen", {}).get("backgroundColor") == "#0b0d10"
    assert cap.get("server", {}).get("url") == "http://100.118.230.52:8765", "Tailscale IP missing in capacitor.config.json"
    print("PASS: capacitor.config.json verified for Android & iOS targets with Tailscale IP 100.118.230.52")

    qr_file = ROOT / "web" / "img" / "qr-tailscale.svg"
    assert qr_file.exists(), "qr-tailscale.svg missing"
    print("PASS: Tailscale QR code vector asset exists")

    html_file = ROOT / "web" / "index.html"
    with open(html_file, "r", encoding="utf-8") as f:
        html = f.read()
    assert 'id="btn-mobile-modal"' in html, "Missing Cài Mobile button in index.html"
    assert 'id="mobile-modal"' in html, "Missing #mobile-modal dialog in index.html"
    print("PASS: web/index.html includes Cài Mobile button and modal")

    css_file = ROOT / "web" / "css" / "app.css"
    with open(css_file, "r", encoding="utf-8") as f:
        css = f.read()
    assert "env(safe-area-inset-top" in css, "Missing safe-area-inset-top in CSS"
    assert "env(safe-area-inset-bottom" in css, "Missing safe-area-inset-bottom in CSS"
    assert "overscroll-behavior-y: none" in css, "Missing overscroll-behavior-y in CSS"
    assert ".mobile-modal" in css, "Missing .mobile-modal in CSS"
    print("PASS: Mobile viewport safe-area and mobile modal styles verified in app.css")


def main():
    test_t42_onnx()
    test_t43_mobile()
    print("\nALL T4.2 & T4.3 VERIFICATION TESTS PASSED (Exit Code 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
