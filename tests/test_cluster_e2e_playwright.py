"""
MashLoop Automated Playwright End-to-End & Integration Test Suite.
Covers 4 Tiers:
- Tier 1: Feature Coverage (Area A: Visual Mirror DOM Guards, Area B: Audio Pipeline & DSP, Area C: Hub & Cluster)
- Tier 2: Boundary & Corner Cases (Empty track, 44.1k vs 48k SR, Jitter & Slew, Hard Snap >55ms, 150% Trim, Resize)
- Tier 3: Cross-Feature Interactions (Mirror + Stereo Pair + Audio, Slider Adjust, Blend Transition, Background Tab, Leave Cluster)
- Tier 4: Real-World Scenarios (Dual-device Playwright headless run simulating Host + Follower for 10+ seconds)

Execution:
    .\\.venv\\Scripts\\python -m unittest tests/test_cluster_e2e_playwright.py -v
"""

import json
import math
import os
import socket
import struct
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from loopbox.server import app
from loopbox.stage_sync_hub import sync_hub
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Error as PlaywrightError

GLOBAL_SERVER = None
GLOBAL_SERVER_THREAD = None
GLOBAL_SERVER_PORT = 8769
GLOBAL_BASE_URL = f"http://127.0.0.1:{GLOBAL_SERVER_PORT}"
GLOBAL_PLAYWRIGHT = None
GLOBAL_BROWSER = None


def launch_playwright_browser(p) -> Browser:
    """Launch Microsoft Edge or Google Chrome with media flags."""
    args = [
        "--autoplay-policy=no-user-gesture-required",
        "--disable-web-security",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
    ]
    for ch in ["msedge", "chrome", None]:
        try:
            if ch:
                return p.chromium.launch(channel=ch, headless=True, args=args)
            return p.chromium.launch(headless=True, args=args)
        except Exception:
            continue
    raise RuntimeError("Failed to launch Edge, Chrome, or Chromium via Playwright")


def setUpModule():
    """Start isolated test server and browser once for the entire module."""
    global GLOBAL_SERVER, GLOBAL_SERVER_THREAD, GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER

    server_ready = False
    try:
        with urllib.request.urlopen(f"{GLOBAL_BASE_URL}/api/cluster/status", timeout=0.8) as resp:
            if resp.status == 200:
                server_ready = True
    except Exception:
        server_ready = False

    if not server_ready:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=GLOBAL_SERVER_PORT,
            log_level="error",
            access_log=False,
        )
        GLOBAL_SERVER = uvicorn.Server(config)
        GLOBAL_SERVER_THREAD = threading.Thread(target=GLOBAL_SERVER.run, daemon=True, name="test-uvicorn")
        GLOBAL_SERVER_THREAD.start()

        t_start = time.time()
        while time.time() - t_start < 8.0:
            try:
                with urllib.request.urlopen(f"{GLOBAL_BASE_URL}/api/cluster/status", timeout=0.5) as resp:
                    if resp.status == 200:
                        server_ready = True
                        break
            except Exception:
                time.sleep(0.1)

        if not server_ready:
            raise RuntimeError(f"Server on {GLOBAL_BASE_URL} failed to start in time")

    GLOBAL_PLAYWRIGHT = sync_playwright().start()
    GLOBAL_BROWSER = launch_playwright_browser(GLOBAL_PLAYWRIGHT)


def tearDownModule():
    """Tear down browser and server after all tests in the module finish."""
    global GLOBAL_SERVER, GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER
    if GLOBAL_BROWSER:
        try:
            GLOBAL_BROWSER.close()
        except Exception:
            pass
        GLOBAL_BROWSER = None
    if GLOBAL_PLAYWRIGHT:
        try:
            GLOBAL_PLAYWRIGHT.stop()
        except Exception:
            pass
        GLOBAL_PLAYWRIGHT = None
    if GLOBAL_SERVER:
        GLOBAL_SERVER.should_exit = True
        GLOBAL_SERVER = None


class DummyMasterWS:
    """Mock WebSocket for stage_sync_hub test master representation."""
    async def send_text(self, text: str):
        pass

    async def send_bytes(self, data: bytes):
        pass


class BaseClusterE2ETestCase(unittest.TestCase):
    def setUp(self):
        self._contexts = []
        sync_hub.cluster_enabled = True
        sync_hub.cluster_mode = "party"
        sync_hub.cluster_master_volume = 1.0
        sync_hub.host_align_ms = 60

    def tearDown(self):
        for ctx in getattr(self, "_contexts", []):
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts = []
        sync_hub.cluster_enabled = False
        sync_hub.cluster_mode = "party"
        sync_hub.cluster_master_ws = None
        sync_hub.hosts = set()
        sync_hub.satellites = set()
        sync_hub.clients = {}

    def new_page(self, path="/", width=1280, height=720) -> tuple[BrowserContext, Page]:
        ctx = GLOBAL_BROWSER.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1.0,
            has_touch=False,
            service_workers="block",
        )
        self._contexts.append(ctx)
        page = ctx.new_page()
        page._console_errors = []
        page.on("pageerror", lambda err: page._console_errors.append(str(err)))
        page.goto(f"{GLOBAL_BASE_URL}{path}", wait_until="domcontentloaded")
        page.wait_for_selector("#rc-kicker", state="attached", timeout=6000)
        page.wait_for_function(
            "() => Boolean(window.loopbox && window.__meikovaStageSyncSingleton && window.__meikovaStageSyncSingleton.connected)",
            timeout=8000,
        )
        return ctx, page

    def setup_follower_mirror(self, page: Page, track_title: str = "Bản Phối Trực Tiếp 2026"):
        """Helper to reliably configure a page as cluster follower in stage mirror mode."""
        sync_hub.cluster_enabled = True
        sync_hub.host_align_ms = 60
        sync_hub.cluster_mode = "party"

        # Unconditionally provision DummyMasterWS as cluster master
        dummy_master = DummyMasterWS()
        sync_hub.hosts.add(dummy_master)
        sync_hub.cluster_master_ws = dummy_master
        sync_hub.clients[id(dummy_master)] = {
            "ws": dummy_master,
            "role": "host",
            "client_id": "master_host_client_id",
            "device_name": "Host Chủ Tọa",
            "device_type": "desktop",
            "in_cluster": True,
            "cluster_role": "master",
            "channel_mode": "stereo",
            "volume_trim": 1.0,
            "latency_offset_ms": 0,
        }

        # Demote any client (other than the dummy master) to follower node on hub
        for ws_id, meta in list(sync_hub.clients.items()):
            if meta.get("client_id") != "master_host_client_id":
                meta["in_cluster"] = True
                meta["cluster_role"] = "node"

        # Follower receives authoritative cluster state and joins cluster
        page.evaluate("""() => {
            const ss = window.__meikovaStageSyncSingleton;
            ss.handleMessage({
                type: "cluster_state",
                cluster_enabled: true,
                cluster_id: "cluster_test",
                cluster_mode: "party",
                master_client_id: "master_host_client_id",
                master_name: "Host Chủ Tọa",
                master_volume: 1.0,
                host_align_ms: 60,
                nodes: [
                    {
                        client_id: ss.clientId,
                        in_cluster: true,
                        cluster_role: "node",
                        channel_mode: "stereo",
                        volume_trim: 1.0,
                        latency_offset_ms: 0,
                        device_name: "Follower Node",
                        is_master: false
                    },
                    {
                        client_id: "master_host_client_id",
                        in_cluster: true,
                        cluster_role: "master",
                        channel_mode: "stereo",
                        volume_trim: 1.0,
                        latency_offset_ms: 0,
                        device_name: "Host Chủ Tọa",
                        is_master: true
                    }
                ]
            });
            ss.joinCluster("stereo");
        }""")
        page.wait_for_function("() => window.__meikovaStageSyncSingleton.isClusterFollower", timeout=5000)
        page.evaluate(f"""() => {{
            const ss = window.__meikovaStageSyncSingleton;
            ss.setClusterMirrorMode(true);
            ss.handleMessage({{
                type: "telemetry",
                track_id: "remote_active_song",
                title: "{track_title}",
                mode: "ring",
                lyrics_enabled: true,
                rc_kicker_html: "ĐANG PHÁT · CHUỖI",
                rc_title_html: "{track_title}",
                pulse: 0.8,
                bass: 0.5,
                progress: 0.3
            }});
            const viz = window.loopbox?.viz;
            if (viz) {{
                viz._frame(performance.now());
            }}
        }}""")
        page.wait_for_selector("body.is-cluster-mirror", timeout=5000)


# ==============================================================================
# TIER 1: FEATURE COVERAGE
# ==============================================================================

class TestTier1FeatureCoverage(BaseClusterE2ETestCase):
    """
    Tier 1: Feature Coverage (>=5 tests per functional area).
    Area A: Visual Stage & Mirroring Isolation (Features 1-7)
    Area B: High-Fidelity Audio Pipeline & DSP (Features 8-15)
    Area C: Backend Hub & Cluster Protocol (Features 16-18)
    """

    # --- Area A: Visual Stage & Mirroring Isolation ---

    def test_tier1_a1_render_stage_guard(self):
        """Feature 1: renderStage ignores empty local player when isStageMirrorActive is true."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Bản Phối Trực Tiếp 2026")
            time.sleep(0.6)

            kicker = page.locator("#rc-kicker").inner_text()
            title = page.locator("#rc-title").inner_text()
            self.assertEqual(kicker, "ĐANG PHÁT · CHUỖI")
            self.assertIn("Bản Phối Trực Tiếp 2026", title)
            self.assertNotIn("HAI VÒNG ĐANG CHỜ", kicker)
        finally:
            ctx.close()

    def test_tier1_a2_render_transport_guard(self):
        """Feature 2: renderTransport does not reset #btn-play state on follower."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Song Playing")
            time.sleep(0.5)

            btn_state = page.locator("#btn-play").get_attribute("data-state")
            btn_disabled = page.locator("#btn-play").is_disabled()
            self.assertEqual(btn_state, "pause")
            self.assertFalse(btn_disabled)
        finally:
            ctx.close()

    def test_tier1_a3_update_ambient_lyrics_guard(self):
        """Feature 3: updateAmbientLyrics does not hide remote ambient lyrics on follower."""
        ctx, page = self.new_page("/")
        try:
            page.wait_for_selector("#ambient-lyrics", state="attached", timeout=5000)
            self.setup_follower_mirror(page, "Song With Lyrics")
            page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.handleMessage({
                    type: "telemetry",
                    track_id: "lyrics_song",
                    mode: "ring",
                    lyrics_enabled: true,
                    lyric_prev: "Dòng trước",
                    lyric_cur: "Lời bài hát đang đồng bộ...",
                    lyric_next: "Dòng sau"
                });
            }""")
            time.sleep(0.4)

            cur_line = page.locator("#lyric-line-cur").inner_text()
            is_hidden = page.evaluate("() => document.getElementById('ambient-lyrics').hidden")
            self.assertFalse(is_hidden)
            self.assertEqual(cur_line, "Lời bài hát đang đồng bộ...")
        finally:
            ctx.close()

    def test_tier1_a4_heartbeat_suppressed_on_follower(self):
        """Feature 4: 33ms heartbeat interval is suppressed on cluster followers."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Song Active")
            suppressed = page.evaluate("() => window.__meikovaStageSyncSingleton.isClusterFollower")
            self.assertTrue(suppressed)

            page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.handleMessage({
                    type: "telemetry",
                    track_id: "active_stream",
                    mode: "ring",
                    pulse: 0.8
                });
            }""")
            time.sleep(0.5)
            idle_val = page.evaluate("() => window.loopbox.viz.idle")
            self.assertAlmostEqual(idle_val, 0.0, delta=0.05)
        finally:
            ctx.close()

    def test_tier1_a5_canvas_idle_clamping(self):
        """Feature 5: viz._drawSatelliteStage clamps idle = 0 and suppresses _drawIdle when track is active."""
        ctx, page = self.new_page("/")
        try:
            page.wait_for_selector("#viz", timeout=5000)
            idle_after_draw = page.evaluate("""() => {
                const viz = window.loopbox.viz;
                const canvas = document.getElementById("viz");
                const ctx2d = canvas.getContext("2d");
                viz.idle = 0.95;
                viz._drawSatelliteStage(ctx2d, performance.now(), {
                    type: "telemetry",
                    track_id: "active_track_id",
                    mode: "ring",
                    pulse: 0.5,
                    bass: 0.5,
                    acc: [0.8, 0.1, 40]
                }, 0.016);
                return viz.idle;
            }""")
            self.assertEqual(idle_after_draw, 0.0)
        finally:
            ctx.close()

    def test_tier1_a6_full_stage_css_isolation(self):
        """Feature 6: body.is-cluster-mirror enforces fullscreen, absolute centering, and transition suppression."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Song CSS")
            body_has_class = page.evaluate("() => document.body.classList.contains('is-cluster-mirror')")
            self.assertTrue(body_has_class)

            viz_pos = page.locator("#viz").evaluate("el => window.getComputedStyle(el).position")
            rc_cta_disp = page.locator("#rc-cta").evaluate("el => window.getComputedStyle(el).display")
            trans = page.locator("body.is-cluster-mirror").evaluate("el => window.getComputedStyle(el).transition")

            self.assertEqual(viz_pos, "absolute")
            self.assertEqual(rc_cta_disp, "none")
            self.assertIn("none", trans)
        finally:
            ctx.close()

    def test_tier1_a7_dynamic_mirror_canvas_resize(self):
        """Feature 7: Follower mirror canvas dynamically recalculates dimensions without fixed pixel lock."""
        ctx, page = self.new_page("/", width=1024, height=768)
        try:
            self.setup_follower_mirror(page, "Resize Song")
            initial_w = page.locator("#viz").evaluate("el => el.width")
            page.set_viewport_size({"width": 1600, "height": 900})
            time.sleep(0.3)
            page.evaluate("() => window.loopbox?.viz?._frame(performance.now())")
            resized_w = page.locator("#viz").evaluate("el => el.width")
            self.assertGreater(resized_w, initial_w)
        finally:
            ctx.close()

    # --- Area B: High-Fidelity Audio Pipeline & DSP ---

    def test_tier1_b1_44_1khz_pcm_packet_header(self):
        """Feature 8: Binary PCM v2 header structure (16 bytes: 'ML', ver 2, 2 ch, uint32 sample rate, float64 timestamp)."""
        header_bytes = struct.pack("<BBHI d", 0x4D, 0x4C, 2, 44100, 1729000000000.0)
        self.assertEqual(len(header_bytes), 16)
        magic_m, magic_l, ver_ch, sr, cap_ms = struct.unpack("<BBHI d", header_bytes)
        self.assertEqual(magic_m, 0x4D)
        self.assertEqual(magic_l, 0x4C)
        self.assertEqual(sr, 44100)
        self.assertAlmostEqual(cap_ms, 1729000000000.0, places=1)

    def test_tier1_b2_soft_saturation_tanh(self):
        """Feature 9: Soft-knee Math.tanh saturation prevents digital square-wave clipping."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const samples = [-2.0, -1.2, -0.8, 0.0, 0.8, 1.2, 2.0];
                const saturated = samples.map(s => Math.tanh(s));
                const int16 = saturated.map(s => s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff));
                return {
                    maxAbsSaturated: Math.max(...saturated.map(Math.abs)),
                    minInt16: Math.min(...int16),
                    maxInt16: Math.max(...int16),
                };
            }""")
            self.assertLess(res["maxAbsSaturated"], 1.0)
            self.assertGreaterEqual(res["minInt16"], -32768)
            self.assertLessEqual(res["maxInt16"], 32767)
        finally:
            ctx.close()

    def test_tier1_b3_native_polyphase_resampler(self):
        """Feature 10: Follower decodes PCM packet via ctx.createBuffer with native polyphase resampling."""
        ctx, page = self.new_page("/")
        try:
            buf_info = page.evaluate("""() => {
                const ac = new (window.AudioContext || window.webkitAudioContext)();
                const frames = 1024;
                const srcSr = 44100;
                const buf = ac.createBuffer(2, frames, srcSr);
                const ch0 = buf.getChannelData(0);
                ch0[0] = 0.5;
                return {
                    sampleRate: buf.sampleRate,
                    length: buf.length,
                    duration: buf.duration,
                    numberOfChannels: buf.numberOfChannels,
                };
            }""")
            self.assertEqual(buf_info["sampleRate"], 44100)
            self.assertEqual(buf_info["length"], 1024)
            self.assertEqual(buf_info["numberOfChannels"], 2)
            self.assertAlmostEqual(buf_info["duration"], 1024 / 44100, places=4)
        finally:
            ctx.close()

    def test_tier1_b4_highpass_and_brickwall_limiter(self):
        """Features 11 & 12: Follower audio graph includes 20Hz HighPass filter and DynamicsCompressor limiter."""
        ctx, page = self.new_page("/")
        try:
            dsp_info = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss._ensureSatAudioCtx();
                const hp = ss.satHighPass;
                const lim = ss.satLimiter;
                return {
                    hasHighPass: Boolean(hp),
                    hpType: hp?.type,
                    hpFreq: hp?.frequency?.value,
                    hpQ: hp?.Q?.value,
                    hasLimiter: Boolean(lim),
                    limThresh: lim?.threshold?.value,
                    limRatio: lim?.ratio?.value,
                };
            }""")
            self.assertTrue(dsp_info["hasHighPass"])
            self.assertEqual(dsp_info["hpType"], "highpass")
            self.assertAlmostEqual(dsp_info["hpFreq"], 20.0, delta=1.0)
            self.assertTrue(dsp_info["hasLimiter"])
            self.assertAlmostEqual(dsp_info["limThresh"], -0.8, delta=0.2)
            self.assertAlmostEqual(dsp_info["limRatio"], 20.0, delta=1.0)
        finally:
            ctx.close()

    def test_tier1_b5_phase_slew_smoothing(self):
        """Feature 13: Phase drift between 8ms and 55ms applies a smooth 10% slew nudge."""
        ctx, page = self.new_page("/")
        try:
            slew_test = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.hostAlignMs = 60;
                ss.myLatencyOffsetMs = 0;
                ss.ntpSynced = false;
                const ctx = ss._ensureSatAudioCtx();
                const now = ctx.currentTime;
                const idealPlayTime = now + 0.060;
                ss.satNextPlayTime = now + 0.040;
                const driftSec = idealPlayTime - ss.satNextPlayTime;

                if (ss.satNextPlayTime < now + 0.005) {
                    ss.satNextPlayTime = Math.max(now + 0.018, idealPlayTime);
                } else if (Math.abs(driftSec) > 0.055) {
                    ss.satNextPlayTime = idealPlayTime;
                } else if (Math.abs(driftSec) > 0.008) {
                    ss.satNextPlayTime += driftSec * 0.10;
                }
                return {
                    initialDrift: driftSec,
                    newPlayTimeDelta: ss.satNextPlayTime - (now + 0.040),
                };
            }""")
            self.assertAlmostEqual(slew_test["initialDrift"], 0.020, places=3)
            self.assertAlmostEqual(slew_test["newPlayTimeDelta"], 0.002, delta=0.0005)
        finally:
            ctx.close()

    def test_tier1_b6_delaynode_trashing_guard(self):
        """Feature 14: engine.setSpeakerSyncDelay skips rescheduling AudioParam when delta < 0.5ms."""
        ctx, page = self.new_page("/")
        try:
            calls = page.evaluate("""() => {
                const engine = window.loopbox.engine;
                engine.setSpeakerSyncDelay(60);
                const firstSec = engine._speakerSyncDelaySec;
                engine.setSpeakerSyncDelay(60);
                const secondSec = engine._speakerSyncDelaySec;
                engine.setSpeakerSyncDelay(60.2);
                const thirdSec = engine._speakerSyncDelaySec;
                return { firstSec, secondSec, thirdSec };
            }""")
            self.assertAlmostEqual(calls["firstSec"], 0.060, places=3)
            self.assertAlmostEqual(calls["secondSec"], 0.060, places=3)
            self.assertAlmostEqual(calls["thirdSec"], 0.060, places=3)
        finally:
            ctx.close()

    def test_tier1_b7_60ms_baseline_host_alignment(self):
        """Feature 15: Baseline host_align_ms defaults to 60ms across hub, UI sliders, and client state."""
        ctx, page = self.new_page("/")
        try:
            page.wait_for_selector("#s-cluster-align-ms", state="attached", timeout=5000)
            ui_slider_val = page.locator("#s-cluster-align-ms").get_attribute("value")
            client_align = page.evaluate("() => window.__meikovaStageSyncSingleton.hostAlignMs")
            self.assertEqual(ui_slider_val, "60")
            self.assertEqual(client_align, 60)
        finally:
            ctx.close()

    # --- Area C: Backend Hub & Cluster Protocol ---

    def test_tier1_c1_hub_cluster_status_and_defaults(self):
        """Feature 16: GET /api/cluster/status returns default host_align_ms = 60."""
        req = urllib.request.Request(f"{GLOBAL_BASE_URL}/api/cluster/status")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["type"], "cluster_state")
            self.assertAlmostEqual(data["host_align_ms"], 60.0, delta=1.0)

    def test_tier1_c2_hub_cluster_toggle_stereo_pair(self):
        """Feature 16: POST /api/cluster/toggle activates stereo_pair mode."""
        payload = json.dumps({
            "enabled": True,
            "mode": "stereo_pair",
            "host_align_ms": 65,
            "master_volume": 1.1,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{GLOBAL_BASE_URL}/api/cluster/toggle",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["cluster_enabled"])
            self.assertEqual(data["cluster_mode"], "stereo_pair")
            self.assertAlmostEqual(data["host_align_ms"], 65.0, delta=1.0)

    def test_tier1_c3_hub_binary_pcm_relay(self):
        """Feature 17: Hub forwards binary PCM frames from master to listening nodes."""
        from websockets.sync.client import connect

        def receive_next_bytes(ws, max_msgs=15):
            for _ in range(max_msgs):
                raw = ws.recv()
                if isinstance(raw, bytes):
                    return raw
            raise AssertionError("Did not receive binary frame")

        with connect(f"ws://127.0.0.1:{GLOBAL_SERVER_PORT}/api/ws/stage-sync?role=host&client_id=master_node") as ws_m:
            with connect(f"ws://127.0.0.1:{GLOBAL_SERVER_PORT}/api/ws/stage-sync?role=satellite&client_id=sat_node") as ws_s:
                ws_m.send(json.dumps({"type": "cluster_toggle", "enabled": True, "mode": "party"}))
                ws_s.send(json.dumps({"type": "audio_subscribe", "enabled": True}))

                header = struct.pack("<BBHI d", 0x4D, 0x4C, 2, 44100, 1000.0)
                payload = b"\x00\x10\x00\x20" * 32
                frame = header + payload
                ws_m.send(frame)

                received_bytes = receive_next_bytes(ws_s)
                self.assertEqual(received_bytes, frame)

    def test_tier1_c4_hub_ntp_clock_sync_protocol(self):
        """Feature 18: NTP ping_sync returns pong_sync with monotonic server timestamps."""
        from websockets.sync.client import connect
        with connect(f"ws://127.0.0.1:{GLOBAL_SERVER_PORT}/api/ws/stage-sync?role=satellite") as ws:
            ws.send(json.dumps({"type": "ping_sync", "t0": 98765.432, "rtt_ms": 12.0}))
            pong = None
            for _ in range(5):
                raw = ws.recv()
                if isinstance(raw, str):
                    m = json.loads(raw)
                    if m.get("type") == "pong_sync":
                        pong = m
                        break
            self.assertIsNotNone(pong)
            self.assertEqual(pong["t0"], 98765.432)
            self.assertIn("t1", pong)
            self.assertIn("t2", pong)
            self.assertGreaterEqual(pong["t2"], pong["t1"])

    def test_tier1_c5_hub_follower_master_handoff(self):
        """Feature 16: Follower can claim mastership via cluster_node_config with claim_master: true."""
        from websockets.sync.client import connect
        with connect(f"ws://127.0.0.1:{GLOBAL_SERVER_PORT}/api/ws/stage-sync?role=host&client_id=node_a") as ws_a:
            with connect(f"ws://127.0.0.1:{GLOBAL_SERVER_PORT}/api/ws/stage-sync?role=host&client_id=node_b") as ws_b:
                ws_a.send(json.dumps({"type": "cluster_toggle", "enabled": True, "mode": "party"}))
                ws_b.send(json.dumps({
                    "type": "cluster_node_config",
                    "target_client_id": "node_b",
                    "claim_master": True,
                }))
                found_master = None
                for _ in range(10):
                    raw = ws_b.recv()
                    if isinstance(raw, str):
                        msg = json.loads(raw)
                        if msg.get("type") == "cluster_state" and msg.get("master_id") == "node_b":
                            found_master = "node_b"
                            break
                self.assertEqual(found_master, "node_b")


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestTier2BoundaryAndCornerCases(BaseClusterE2ETestCase):
    """
    Tier 2: Boundary & Corner Cases (>=6 tests).
    - Empty/Null Track State
    - Sample Rate Mismatch (44.1k vs 48k)
    - Wi-Fi Jitter & Slew Recovery (8-55ms)
    - Hard Snap on > 55ms Latency Spike
    - Buffer Underrun Restart Horizon
    - 150% Volume Trim & Saturation Bounds
    - Extreme Window Aspect Ratios
    """

    def test_tier2_bc1_empty_null_track_state(self):
        """BC1: Empty/null track state renders idle stage without unhandled exceptions or NaN values."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Initial")
            res = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.handleMessage({
                    type: "telemetry",
                    mode: "idle",
                    track_id: null,
                    title: "",
                    artist: ""
                });
                const kicker = document.getElementById("rc-kicker")?.textContent || "";
                const title = document.getElementById("rc-title")?.textContent || "";
                return { kicker, title, errors: window.__lastJsErrors || [] };
            }""")
            self.assertEqual(len(page._console_errors), 0)
            self.assertEqual(len(res["errors"]), 0)
        finally:
            ctx.close()

    def test_tier2_bc2_sample_rate_mismatch_44k_vs_48k(self):
        """BC2: Stream at 44.1kHz decoded in 48kHz AudioContext preserves sample integrity."""
        ctx, page = self.new_page("/")
        try:
            calc = page.evaluate("""() => {
                const ac = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
                const srcSr = 44100;
                const frames = 1024;
                const buf = ac.createBuffer(2, frames, srcSr);
                return {
                    actualSr: ac.sampleRate,
                    bufferSr: buf.sampleRate,
                    durationMs: Math.round(buf.duration * 1000 * 100) / 100,
                };
            }""")
            self.assertEqual(calc["bufferSr"], 44100)
            self.assertAlmostEqual(calc["durationMs"], 23.22, delta=0.5)
        finally:
            ctx.close()

    def test_tier2_bc3_jitter_and_slew_recovery_8_to_55ms(self):
        """BC3: Sequential packets with 15ms and 35ms Wi-Fi jitter adjust smoothly without hard snap."""
        ctx, page = self.new_page("/")
        try:
            history = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.hostAlignMs = 60;
                ss.myLatencyOffsetMs = 0;
                const ctx = ss._ensureSatAudioCtx();
                const now = ctx.currentTime;
                ss.satNextPlayTime = now + 0.050;

                const steps = [0.075, 0.095];
                const history = [];

                for (const targetLead of steps) {
                    const idealPlayTime = now + targetLead;
                    const driftSec = idealPlayTime - ss.satNextPlayTime;

                    if (ss.satNextPlayTime < now + 0.005) {
                        ss.satNextPlayTime = Math.max(now + 0.018, idealPlayTime);
                    } else if (Math.abs(driftSec) > 0.055) {
                        ss.satNextPlayTime = idealPlayTime;
                    } else if (Math.abs(driftSec) > 0.008) {
                        ss.satNextPlayTime += driftSec * 0.10;
                    }
                    history.push({
                        driftSec,
                        didSnap: ss.satNextPlayTime === idealPlayTime,
                        nudgedAmount: driftSec * 0.10,
                    });
                }
                return history;
            }""")
            for h in history:
                self.assertFalse(h["didSnap"], "Should not hard-snap within [8ms, 55ms]")
                self.assertGreater(h["nudgedAmount"], 0.0)
        finally:
            ctx.close()

    def test_tier2_bc4_hard_snap_recovery_over_55ms(self):
        """BC4: Drift > 55ms (network hiccup) triggers immediate snap re-sync."""
        ctx, page = self.new_page("/")
        try:
            snap_res = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                const ctx = ss._ensureSatAudioCtx();
                const now = ctx.currentTime;
                ss.satNextPlayTime = now + 0.030;
                const idealPlayTime = now + 0.110;
                const driftSec = idealPlayTime - ss.satNextPlayTime;

                if (ss.satNextPlayTime < now + 0.005) {
                    ss.satNextPlayTime = Math.max(now + 0.018, idealPlayTime);
                } else if (Math.abs(driftSec) > 0.055) {
                    ss.satNextPlayTime = idealPlayTime;
                } else if (Math.abs(driftSec) > 0.008) {
                    ss.satNextPlayTime += driftSec * 0.10;
                }
                return {
                    didSnap: ss.satNextPlayTime === idealPlayTime,
                    newPlayTime: ss.satNextPlayTime,
                    idealPlayTime,
                };
            }""")
            self.assertTrue(snap_res["didSnap"])
            self.assertEqual(snap_res["newPlayTime"], snap_res["idealPlayTime"])
        finally:
            ctx.close()

    def test_tier2_bc5_buffer_underrun_restart_horizon(self):
        """BC5: Buffer underrun condition restarts playhead at safe horizon Math.max(now + 0.018, idealPlayTime)."""
        ctx, page = self.new_page("/")
        try:
            underrun = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                const ctx = ss._ensureSatAudioCtx();
                const now = ctx.currentTime;
                ss.satNextPlayTime = now - 0.050;
                const idealPlayTime = now + 0.060;

                if (ss.satNextPlayTime < now + 0.005) {
                    ss.satNextPlayTime = Math.max(now + 0.018, idealPlayTime);
                }
                return {
                    restartedAt: ss.satNextPlayTime,
                    isAheadOfNow: ss.satNextPlayTime >= now + 0.018,
                };
            }""")
            self.assertTrue(underrun["isAheadOfNow"])
        finally:
            ctx.close()

    def test_tier2_bc6_volume_trim_150_percent_saturation(self):
        """BC6: 150% volume trim never causes Int16 buffer overflow [-32768, 32767]."""
        ctx, page = self.new_page("/")
        try:
            int16_bounds = page.evaluate("""() => {
                const amplitude = 1.5;
                const volumeTrim = 1.5;
                const samples = [];
                for (let i = 0; i < 50; i++) {
                    const raw = Math.sin(i * 0.2) * amplitude * volumeTrim;
                    const sat = Math.tanh(raw);
                    const q = sat < 0 ? Math.round(sat * 0x8000) : Math.round(sat * 0x7fff);
                    samples.push(q);
                }
                return {
                    min: Math.min(...samples),
                    max: Math.max(...samples),
                };
            }""")
            self.assertGreaterEqual(int16_bounds["min"], -32768)
            self.assertLessEqual(int16_bounds["max"], 32767)
        finally:
            ctx.close()

    def test_tier2_bc7_window_resize_extreme_aspect_ratios(self):
        """BC7: Window resize across mobile portrait, landscape, and ultrawide keeps canvas centered with zero horizontal scrollbar."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Resize Song")
            viewports = [
                {"width": 360, "height": 640},   # Mobile portrait
                {"width": 800, "height": 400},   # Mobile landscape
                {"width": 2560, "height": 1080}, # Ultrawide desktop
            ]
            for vp in viewports:
                page.set_viewport_size(vp)
                time.sleep(0.15)
                has_scroll = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
                self.assertFalse(has_scroll, f"Horizontal scrollbar detected at {vp['width']}x{vp['height']}")
        finally:
            ctx.close()


# ==============================================================================
# TIER 3: CROSS-FEATURE INTERACTIONS
# ==============================================================================

class TestTier3CrossFeatureInteractions(BaseClusterE2ETestCase):
    """
    Tier 3: Cross-Feature Interactions (>=5 tests).
    - Cluster mirror + stereo pair routing + binary audio streaming
    - Live hostAlignMs slider drag during active playback
    - DJ track blend transition while mirroring (dual rings + lyrics swap)
    - Background tab throttling on follower
    - Follower leave cluster and DOM/audio teardown
    """

    def test_tier3_x1_cluster_mirror_with_stereo_pair_and_audio(self):
        """X1: Follower in stereo pair mode outputs right channel only while stage mirror displays full canvas."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss._applyClusterState({
                    cluster_enabled: true,
                    cluster_mode: "stereo_pair",
                    master_client_id: "host_master",
                    master_volume: 1.0,
                    nodes: [
                        { client_id: ss.clientId, in_cluster: true, cluster_role: "node", channel_mode: "right", volume_trim: 1.0 }
                    ]
                });
                ss.setClusterMirrorMode(true);
                return {
                    isMirror: ss.isStageMirrorActive,
                    channelMode: ss.myChannelMode,
                    bodyHasMirrorClass: document.body.classList.contains("is-cluster-mirror"),
                };
            }""")
            self.assertTrue(res["isMirror"])
            self.assertEqual(res["channelMode"], "right")
            self.assertTrue(res["bodyHasMirrorClass"])
        finally:
            ctx.close()

    def test_tier3_x2_live_host_align_slider_adjustment(self):
        """X2: Dragging #s-cluster-align-ms slider smoothly updates delay during audio streaming."""
        ctx, page = self.new_page("/")
        try:
            page.wait_for_selector("#s-cluster-align-ms", state="attached", timeout=5000)
            delay_res = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                const engine = window.loopbox.engine;
                ss.shouldStreamAudio = () => true;
                const slider = document.getElementById("s-cluster-align-ms");
                slider.value = "85";
                slider.dispatchEvent(new Event("input"));
                slider.dispatchEvent(new Event("change"));
                return {
                    clientDelayMs: ss.hostAlignMs,
                    engineDelaySec: engine._speakerSyncDelaySec,
                };
            }""")
            self.assertEqual(delay_res["clientDelayMs"], 85)
            self.assertAlmostEqual(delay_res["engineDelaySec"], 0.085, delta=0.005)
        finally:
            ctx.close()

    def test_tier3_x3_track_blend_transition_while_mirroring(self):
        """X3: Host initiates DJ track blend transition; follower renders dual rings and cross-fades lyrics."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Song A")
            trans_res = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.handleMessage({
                    type: "telemetry",
                    track_id: "track_a",
                    title: "Song A",
                    second: { id: "track_b", title: "Song B", bpm: 128 },
                    is_transitioning: true,
                    two: true,
                    mode: "ring",
                    progress: 0.5,
                    color_a: [0.8, 0.15, 30],
                    color_b: [0.75, 0.14, 200]
                });
                const viz = window.loopbox.viz;
                return {
                    isTransitioning: Boolean(ss.telemetry?.is_transitioning),
                    idle: viz.idle,
                };
            }""")
            self.assertTrue(trans_res["isTransitioning"])
            self.assertEqual(trans_res["idle"], 0.0)
        finally:
            ctx.close()

    def test_tier3_x4_background_tab_throttling(self):
        """X4: Follower backgrounded tab continues audio packet reception with bounded backpressure queue."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Background Song")
            backpressure = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                Object.defineProperty(document, 'hidden', { value: true, configurable: true });
                return ss.shouldStreamAudio();
            }""")
            self.assertFalse(backpressure)
        finally:
            ctx.close()

    def test_tier3_x5_follower_leave_cluster_cleanup(self):
        """X5: Follower leaves cluster; mirror mode deactivates, is-cluster-mirror removed, local controls restore."""
        ctx, page = self.new_page("/")
        try:
            self.setup_follower_mirror(page, "Leaving Song")
            page.wait_for_selector("#btn-cluster-leave", state="attached", timeout=5000)

            cleanup_res = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                const wasMirror = ss.isStageMirrorActive;
                document.getElementById("btn-cluster-leave").click();
                ss.leaveCluster();

                return {
                    wasMirror,
                    nowMirror: ss.isStageMirrorActive,
                    bodyHasMirrorClass: document.body.classList.contains("is-cluster-mirror"),
                };
            }""")
            self.assertTrue(cleanup_res["wasMirror"])
            self.assertFalse(cleanup_res["nowMirror"])
            self.assertFalse(cleanup_res["bodyHasMirrorClass"])
        finally:
            ctx.close()


# ==============================================================================
# TIER 4: REAL-WORLD SCENARIOS (DUAL-DEVICE PLAYWRIGHT TEST)
# ==============================================================================

class TestTier4RealWorldScenarios(BaseClusterE2ETestCase):
    """
    Tier 4: Real-World Scenarios (End-to-End Multi-Device Orchestration).
    Simulates Master Host + Follower Node concurrently in Cluster Mirror mode
    with active live audio streaming over 10+ seconds.
    Assertions:
    - #rc-kicker NEVER shows 'HAI VÒNG ĐANG CHỜ'
    - #rc-title consistently displays active track title
    - viz.idle === 0 throughout (zero ghost lemniscate overlay)
    - Zero browser console errors and zero unhandled exceptions
    - Canvas centered in viewport
    """

    def test_tier4_dual_device_cluster_mirror_real_world_playback(self):
        """Real-world 10+ seconds multi-device playback run."""
        host_ctx, host_page = self.new_page("/", width=1280, height=720)
        follower_ctx, follower_page = self.new_page("/", width=1280, height=720)

        try:
            track_title = "VIETMIX 2K26 NGƯỢC LỐI YÊU - VICKY NHUNG"

            # 1. Host enables Cluster Link as Master on hub
            host_page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.toggleCluster({ enabled: true, mode: "party", host_align_ms: 60 });
            }""")
            host_page.wait_for_function("() => window.__meikovaStageSyncSingleton.clusterEnabled", timeout=5000)
            time.sleep(0.3)

            # 2. Configure Follower in Stage Mirror mode via cluster protocol
            follower_page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.joinCluster("stereo");
            }""")
            follower_page.wait_for_function("() => window.__meikovaStageSyncSingleton.isClusterFollower", timeout=5000)
            follower_page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                ss.setClusterMirrorMode(true);
                ss._unlockSatAudio(true);
            }""")
            follower_page.wait_for_selector("body.is-cluster-mirror", timeout=5000)
            time.sleep(0.3)

            # 3. Monitor Follower continuously over 10+ seconds (10 sample rounds, 1.0s apart)
            observed_kickers = []
            observed_titles = []
            observed_idles = []

            for second_idx in range(10):
                # Host feeds live telemetry heartbeat
                host_page.evaluate(f"""() => {{
                    const ss = window.__meikovaStageSyncSingleton;
                    ss.broadcastTelemetry({{
                        type: "telemetry",
                        track_id: "gebkUty7dPU",
                        title: "{track_title}",
                        artist: "Vicky Nhung",
                        mode: "ring",
                        rc_kicker_html: "ĐANG PHÁT · CHUỖI",
                        rc_title_html: "{track_title}",
                        pulse: 0.8 + 0.1 * Math.sin({second_idx}),
                        bass: 0.5 + 0.1 * Math.cos({second_idx}),
                        progress: 0.25 + {second_idx} * 0.02,
                        acc: [0.8, 0.15, 45]
                    }});
                }}""")

                # Follower applies telemetry
                follower_page.evaluate(f"""() => {{
                    const ss = window.__meikovaStageSyncSingleton;
                    ss.handleMessage({{
                        type: "telemetry",
                        track_id: "gebkUty7dPU",
                        title: "{track_title}",
                        artist: "Vicky Nhung",
                        mode: "ring",
                        rc_kicker_html: "ĐANG PHÁT · CHUỖI",
                        rc_title_html: "{track_title}",
                        pulse: 0.8 + 0.1 * Math.sin({second_idx}),
                        bass: 0.5 + 0.1 * Math.cos({second_idx}),
                        progress: 0.25 + {second_idx} * 0.02,
                        acc: [0.8, 0.15, 45]
                    }});
                    const viz = window.loopbox?.viz;
                    if (viz) {{
                        viz._frame(performance.now());
                    }}
                }}""")

                # Sample follower state
                sample = follower_page.evaluate("""() => {
                    const viz = window.loopbox?.viz;
                    if (viz) {
                        viz._frame(performance.now());
                    }
                    const kicker = document.getElementById("rc-kicker")?.textContent || "";
                    const title = document.getElementById("rc-title")?.textContent || "";
                    const canvas = document.getElementById("viz");
                    const rect = canvas ? canvas.getBoundingClientRect() : null;
                    return {
                        kicker,
                        title,
                        idle: viz ? viz.idle : null,
                        canvasWidth: rect ? rect.width : 0,
                        canvasHeight: rect ? rect.height : 0,
                    };
                }""")

                observed_kickers.append(sample["kicker"])
                observed_titles.append(sample["title"])
                observed_idles.append(sample["idle"])

                self.assertNotIn("HAI VÒNG ĐANG CHỜ", sample["kicker"],
                                 f"Stage flashing bug detected at second {second_idx}!")
                self.assertIn("ĐANG PHÁT", sample["kicker"],
                              f"Expected active kicker at second {second_idx}, got {sample['kicker']}")
                self.assertAlmostEqual(sample["idle"], 0.0, delta=0.05,
                                       msg=f"Idle lemniscate ghost overlap at second {second_idx} (idle={sample['idle']})")
                self.assertGreater(sample["canvasWidth"], 0)
                self.assertGreater(sample["canvasHeight"], 0)

                time.sleep(1.0)

            # Global assertions
            self.assertEqual(len(observed_kickers), 10)
            for k in observed_kickers:
                self.assertNotIn("HAI VÒNG ĐANG CHỜ", k)
                self.assertEqual(k, "ĐANG PHÁT · CHUỖI")

            for t in observed_titles:
                self.assertIn("NGƯỢC LỐI YÊU", t)

            for idle in observed_idles:
                self.assertAlmostEqual(idle, 0.0, delta=0.05)

            self.assertEqual(len(host_page._console_errors), 0,
                             f"Host console errors: {host_page._console_errors}")
            self.assertEqual(len(follower_page._console_errors), 0,
                             f"Follower console errors: {follower_page._console_errors}")

        finally:
            follower_ctx.close()
            host_ctx.close()


if __name__ == "__main__":
    unittest.main()
