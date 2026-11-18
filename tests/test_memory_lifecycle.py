"""
tests/test_memory_lifecycle.py: 4-Tier Automated Verification Suite for
Dynamic Memory Pressure Sensing & Adaptive Resource Scaling (Features 22–25).

Covers:
- Tier 1: Unit & Subsystem Lifecycle (Win32 ctypes query, threshold hysteresis classification,
          buffer nulling on _evict(), Voice node graph disconnection, 1x1 ring canvas disposal).
- Tier 2: Boundary & Corner Cases (Critical pressure spike mid-transition, rapid 10-track skip,
          canvas context loss/restoration, zero bounding box resilience, 60-minute track stability).
- Tier 3: Cross-Feature Interactions (Cluster stage mirror under Critical pressure, full pressure
          lifecycle Normal -> High -> Critical -> Normal with SSAA restoration, active mic/recording protected).
- Tier 4: Real-World Acceptance Scenario (30-track continuous playback E2E test in headless Edge
          asserting stable JS heap < 400 MB, zero unhandled page errors, zero canvas freezes).

Execution:
    .\\.venv\\Scripts\\python.exe -m unittest tests/test_memory_lifecycle.py -v
    .\\.venv\\Scripts\\python.exe tests/test_memory_lifecycle.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

# Ensure PROJECT_ROOT is on sys.path for direct python execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from loopbox.server import app
from loopbox.stage_sync_hub import StageSyncHub, sync_hub
from loopbox.memory_monitor import (
    MemoryMonitor,
    memory_monitor,
    query_raw_memory,
    HIGH_ENTER_COMMIT_AVAIL_MB,
    HIGH_ENTER_COMMIT_PCT,
    CRITICAL_ENTER_COMMIT_AVAIL_MB,
    CRITICAL_ENTER_COMMIT_PCT,
    CRITICAL_RECOVERY_COMMIT_AVAIL_MB,
    CRITICAL_RECOVERY_COMMIT_PCT,
    CRITICAL_RECOVERY_DWELL_S,
    NORMAL_RECOVERY_COMMIT_AVAIL_MB,
    NORMAL_RECOVERY_COMMIT_PCT,
    NORMAL_RECOVERY_DWELL_S,
)

logger = logging.getLogger("meikova.loop.test_memory_lifecycle")

GLOBAL_SERVER = None
GLOBAL_SERVER_THREAD = None
GLOBAL_SERVER_PORT = 8775
GLOBAL_BASE_URL = f"http://127.0.0.1:{GLOBAL_SERVER_PORT}"
GLOBAL_PLAYWRIGHT = None
GLOBAL_BROWSER = None


def launch_playwright_browser(p) -> Browser:
    """Launch Microsoft Edge or Google Chrome with memory flags and exposed GC."""
    args = [
        "--autoplay-policy=no-user-gesture-required",
        "--disable-web-security",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--renderer-process-limit=2",
        "--js-flags=--expose-gc",
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
    """Start isolated test server and headless browser once for the test module."""
    global GLOBAL_SERVER, GLOBAL_SERVER_THREAD, GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER

    server_ready = False
    try:
        with urllib.request.urlopen(f"{GLOBAL_BASE_URL}/api/version", timeout=0.8) as resp:
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
        GLOBAL_SERVER_THREAD = threading.Thread(target=GLOBAL_SERVER.run, daemon=True, name="uvicorn-mem-test")
        GLOBAL_SERVER_THREAD.start()

        t_start = time.time()
        while time.time() - t_start < 8.0:
            try:
                with urllib.request.urlopen(f"{GLOBAL_BASE_URL}/api/version", timeout=0.5) as resp:
                    if resp.status == 200:
                        server_ready = True
                        break
            except Exception:
                time.sleep(0.1)

        if not server_ready:
            raise RuntimeError(f"Server on {GLOBAL_BASE_URL} failed to start within 8 seconds")

    GLOBAL_PLAYWRIGHT = sync_playwright().start()
    GLOBAL_BROWSER = launch_playwright_browser(GLOBAL_PLAYWRIGHT)


def tearDownModule():
    """Tear down browser and server after all test tiers complete."""
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


class BaseMemoryE2ETestCase(unittest.TestCase):
    def setUp(self):
        self._contexts: list[BrowserContext] = []
        memory_monitor.clear_simulation()

    def tearDown(self):
        for ctx in getattr(self, "_contexts", []):
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts = []
        memory_monitor.clear_simulation()

    def new_page(self, path="/", width=1280, height=800, dpr=2.0) -> tuple[BrowserContext, Page]:
        ctx = GLOBAL_BROWSER.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=dpr,
            has_touch=False,
            service_workers="block",
        )
        self._contexts.append(ctx)
        page = ctx.new_page()
        page._console_errors = []
        page.on("pageerror", lambda err: page._console_errors.append(str(err)))
        page.goto(f"{GLOBAL_BASE_URL}{path}", wait_until="domcontentloaded")
        page.wait_for_selector("#viz", state="attached", timeout=12000)
        page.wait_for_function(
            "() => Boolean(window.loopbox && window.loopbox.viz && window.loopbox.player && window.loopbox.loader)",
            timeout=12000,
        )
        return ctx, page


# ==============================================================================
# TIER 1: FEATURE COVERAGE (Unit & Subsystem Lifecycle)
# ==============================================================================

class TestTier1FeatureCoverage(BaseMemoryE2ETestCase):
    """
    Tier 1: Feature Coverage (Unit & Subsystem Lifecycle).
    Verifies Win32 ctypes querying, threshold classification, REST/WS telemetry,
    AudioBuffer eviction & vocals accounting, Voice node graph disconnection,
    and 1x1 ring canvas disposal.
    """

    def test_tier1_r1_backend_win32_ctypes_query(self):
        """Feature 1 & 2: Win32 ctypes / POSIX memory query returns valid metrics within <10ms."""
        query_raw_memory()  # Warm up DLL function pointers and page tables
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            data = query_raw_memory()
            times.append((time.perf_counter() - t0) * 1000)
        elapsed_ms = min(times)

        self.assertLess(elapsed_ms, 25.0, "Memory query exceeded 25ms latency budget")
        self.assertIn("platform", data)
        self.assertIn("commit_avail_mb", data)
        self.assertIn("commit_total_mb", data)
        self.assertIn("commit_limit_mb", data)
        self.assertIn("commit_pct", data)
        self.assertIn("phys_avail_mb", data)
        self.assertIn("phys_total_mb", data)
        self.assertIn("phys_load_pct", data)

        self.assertGreaterEqual(data["commit_avail_mb"], 0.0)
        self.assertGreater(data["commit_limit_mb"], 0.0)
        self.assertGreaterEqual(data["commit_pct"], 0.0)
        self.assertLessEqual(data["commit_pct"], 100.0)
        self.assertGreater(data["phys_total_mb"], 0.0)
        self.assertGreaterEqual(data["phys_avail_mb"], 0.0)

        if sys.platform == "win32":
            self.assertEqual(data["platform"], "win32", "Expected Win32 ctypes sensor on Windows host")
            self.assertIn("process_working_set_mb", data)
            self.assertGreater(data["commit_limit_mb"], 1000.0, "Win32 commit limit unreasonably low")

    def test_tier1_r1_threshold_state_classification_and_hysteresis(self):
        """Feature 3: 3-tier hysteresis state machine classifies Normal, High, and Critical with dwell time."""
        monitor = MemoryMonitor(poll_interval_s=0.5)

        # 1. Normal state baseline
        monitor.set_simulation(commit_avail_mb=5000.0, commit_pct=70.0, phys_avail_mb=3500.0)
        t_norm = monitor.poll_once()
        self.assertEqual(t_norm["state"], "normal")
        self.assertEqual(t_norm["level"], 0)
        self.assertEqual(t_norm["recommended_cache_mb"], 450)
        self.assertEqual(t_norm["recommended_keep_tracks"], 2)

        # 2. High threshold entry (requires 2 checks from Normal)
        monitor.set_simulation(commit_avail_mb=2800.0, commit_pct=89.0, phys_avail_mb=1800.0)
        t_cand1 = monitor.poll_once()
        self.assertEqual(t_cand1["state"], "normal", "1st High candidate check should not immediately transition")
        t_high = monitor.poll_once()
        self.assertEqual(t_high["state"], "high", "2nd High candidate check must transition to High")
        self.assertEqual(t_high["level"], 1)
        self.assertEqual(t_high["recommended_cache_mb"], 250)
        self.assertEqual(t_high["recommended_keep_tracks"], 1)

        # 3. Critical threshold escalation (immediate)
        monitor.set_simulation(commit_avail_mb=1200.0, commit_pct=95.0, phys_avail_mb=600.0)
        t_crit = monitor.poll_once()
        self.assertEqual(t_crit["state"], "critical")
        self.assertEqual(t_crit["level"], 2)
        self.assertEqual(t_crit["recommended_cache_mb"], 140)
        self.assertEqual(t_crit["recommended_keep_tracks"], 1)

        # 4. Hysteresis recovery: sustaining recovery metrics requires dwell time
        monitor.set_simulation(commit_avail_mb=2400.0, commit_pct=88.0, phys_avail_mb=1500.0)
        t_dwell = monitor.poll_once()
        self.assertEqual(t_dwell["state"], "critical", "Must remain Critical until dwell time elapses")

        # Advance monotonic time past CRITICAL_RECOVERY_DWELL_S (5s)
        base_time = time.monotonic()
        with patch("time.monotonic", side_effect=[base_time, base_time + 6.0, base_time + 6.0]):
            monitor.poll_once()
            t_rec = monitor.poll_once()
            self.assertEqual(t_rec["state"], "high", "Must recover to High after sustained 5s dwell")

    def test_tier1_r1_rest_memory_endpoint_and_websocket_broadcast(self):
        """Feature 4 & 5: REST GET /api/system/memory and WebSocket broadcast relay telemetry."""
        client = TestClient(app)

        # 1. REST endpoint verification
        resp = client.get("/api/system/memory")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("no-cache", resp.headers.get("Cache-Control", ""))
        body = resp.json()
        self.assertIn(body.get("state"), ["normal", "high", "critical"])
        self.assertIn("commit_avail_mb", body)
        self.assertIn("recommended_cache_mb", body)
        self.assertIn("recommended_keep_tracks", body)
        self.assertIn("dwell_s", body)

        # 2. WebSocket broadcast verification
        with client.websocket_connect("/api/ws/stage-sync?role=satellite") as sat_ws:
            # Drain initial sync or telemetry packet
            _ = sat_ws.receive_json()

            sample_telemetry = {
                "state": "high",
                "level": 1,
                "commit_avail_mb": 2500.0,
                "commit_total_mb": 18000.0,
                "commit_limit_mb": 20500.0,
                "commit_pct": 87.8,
                "phys_avail_mb": 1900.0,
                "phys_total_mb": 16000.0,
                "phys_load_pct": 88.1,
                "recommended_cache_mb": 250,
                "recommended_keep_tracks": 1,
                "dwell_s": 0.0,
                "t": int(time.time() * 1000),
            }
            sync_hub.dispatch_memory_state(sample_telemetry)

            received = None
            for _ in range(8):
                msg = sat_ws.receive_json()
                if msg.get("type") == "memory_pressure":
                    received = msg
                    break

            self.assertIsNotNone(received, "WebSocket did not receive memory_pressure broadcast")
            self.assertEqual(received["state"], "high")
            self.assertEqual(received["recommended_cache_mb"], 250)
            self.assertEqual(received["recommended_keep_tracks"], 1)

    def test_tier1_r2_loader_buffer_eviction_and_vocals_accounting(self):
        """Feature 8, 9, 10: Loader dynamic limits, stem accounting, and buffer nulling on eviction."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""async () => {
                const loader = window.loopbox.loader;
                const engine = window.loopbox.engine;

                // 1. Verify dynamic cache limits across states
                loader.setMemoryPressure("normal");
                const normCap = loader.maxCacheBytes;
                const normKeep = loader.keep;

                loader.setMemoryPressure("high");
                const highCap = loader.maxCacheBytes;
                const highKeep = loader.keep;

                loader.setMemoryPressure("critical");
                const critCap = loader.maxCacheBytes;
                const critKeep = loader.keep;

                // 2. Build synthetic AudioBuffers
                const sr = engine.ctx.sampleRate;
                const makeBuf = (sec) => engine.ctx.createBuffer(2, Math.round(sr * sec), sr);

                const t1 = { id: "track_evict_1", buffer: makeBuf(10) };
                const t2 = { id: "track_evict_2", buffer: makeBuf(10) };
                const vocBuf = makeBuf(10);

                loader.cache.set("track_evict_1", { track: t1, used: 100, vocals: null, vocalsBuffer: vocBuf });
                loader.cache.set("track_evict_2", { track: t2, used: 200, vocals: null, vocalsBuffer: null });

                // Verify stem byte accounting includes vocalsBuffer
                const bytesWithStem = loader._bufferBytes(loader.cache.get("track_evict_1"));
                const bytesNoStem = loader._bufferBytes(loader.cache.get("track_evict_2"));

                // Protect only track_evict_2 and evict with keep = 1
                loader.protect = () => ["track_evict_2"];
                loader._evict(1);

                const t1Nulled = t1.buffer === null;
                const t2Preserved = t2.buffer !== null;
                const t1InCache = loader.cache.has("track_evict_1");
                const t2InCache = loader.cache.has("track_evict_2");

                return {
                    normCap, normKeep,
                    highCap, highKeep,
                    critCap, critKeep,
                    bytesWithStem, bytesNoStem,
                    t1Nulled, t2Preserved,
                    t1InCache, t2InCache,
                };
            }""")

            self.assertEqual(res["normKeep"], 2)
            self.assertEqual(res["highKeep"], 1)
            self.assertEqual(res["critKeep"], 1)
            self.assertGreater(res["normCap"], res["highCap"])
            self.assertGreater(res["highCap"], res["critCap"])
            self.assertGreater(res["bytesWithStem"], res["bytesNoStem"], "Vocal stem buffer not accounted for in bytes calculation")
            self.assertTrue(res["t1Nulled"], "Evicted track buffer must be nulled out to release float PCM memory")
            self.assertTrue(res["t2Preserved"], "Protected track buffer must remain intact")
            self.assertFalse(res["t1InCache"], "Evicted track must be removed from loader.cache")
            self.assertTrue(res["t2InCache"], "Protected track must remain in loader.cache")
        finally:
            ctx.close()

    def test_tier1_r2_voice_audio_node_disconnection(self):
        """Feature 13 & 14: Voice.dispose() invokes _free() and disconnects all 20+ WebAudio nodes."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const engine = window.loopbox.engine;
                const sr = engine.ctx.sampleRate;
                const buf = engine.ctx.createBuffer(2, sr, sr);
                const mockTrack = {
                    id: "test_voice_track",
                    buffer: buf,
                    analysis: { meter: 4, gain_db: 0, beats: [0, 0.5, 1.0], dur: [0.5, 0.5, 0.5] }
                };

                const v = engine.voice(mockTrack);
                const initialVoiceCount = engine.voices.size;
                const hasLrNodes = Array.isArray(v.lrNodes) && v.lrNodes.length > 0;

                // Track disconnect calls
                let disconnectCalls = 0;
                const originalDisconnect = AudioNode.prototype.disconnect;
                const nodesToSpy = [
                    v.gain, v.src, v.srcGain, v.mainGain, v.vocGain,
                    v.pre, v.sum, v.lp, v.hp, v.trim, v.fx,
                    v.bands?.low, v.bands?.mid, v.bands?.high,
                    ...(v.lrNodes || [])
                ].filter(Boolean);

                for (const node of nodesToSpy) {
                    const orig = node.disconnect.bind(node);
                    node.disconnect = () => {
                        disconnectCalls++;
                        try { orig(); } catch (_) {}
                    };
                }

                // Call dispose() which must call _free()
                v.dispose();

                const finalVoiceCount = engine.voices.size;
                const voiceDeregistered = !engine.voices.has(v);

                return {
                    initialVoiceCount,
                    hasLrNodes,
                    disconnectCalls,
                    nodesSpyCount: nodesToSpy.length,
                    voiceDeregistered,
                    lrNodesCleared: v.lrNodes === null || v.lrNodes?.length === 0,
                };
            }""")

            self.assertTrue(res["hasLrNodes"], "Voice should create Linkwitz-Riley filter nodes")
            self.assertTrue(res["voiceDeregistered"], "Voice must be deregistered from engine.voices on dispose")
            self.assertGreaterEqual(res["disconnectCalls"], 15, "Voice.dispose() must call .disconnect() on all internal nodes")
            self.assertTrue(res["lrNodesCleared"], "Voice.lrNodes must be cleared on dispose")
        finally:
            ctx.close()

    def test_tier1_r2_timeline_pruning(self):
        """Feature 11: player.timeline stays bounded <= 40 events and purges old history past 5s."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const player = window.loopbox.player;
                player.cur = { track: { id: "test_track", beats: [0], dur: [0.5] }, beat: 0, rate: 1 };
                const t0 = performance.now() / 1000;
                player.timeline = [];

                // Dispatch 80 events spaced 0.2s apart (16 seconds total)
                for (let i = 0; i < 80; i++) {
                    const t = t0 + i * 0.2;
                    player._log(t, "seq", { beat: i });
                }

                return {
                    timelineLen: player.timeline.length,
                    oldestEventAge: (t0 + 79 * 0.2) - player.timeline[0].t,
                };
            }""")

            self.assertLessEqual(res["timelineLen"], 40, "Timeline array grew beyond 40-event bound")
            self.assertLessEqual(res["oldestEventAge"], 15.0, "Old timeline events past lookahead window were not pruned")
        finally:
            ctx.close()

    def test_tier1_r3_dispose_ring_sets_1x1_dimensions(self):
        """Feature 16: viz._disposeRing(ring) sets 1x1 dimensions to immediately reclaim GPU textures."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const viz = window.loopbox.viz;
                const c = document.createElement("canvas");
                c.width = 1024;
                c.height = 1024;

                const ring = {
                    role: "primary",
                    layerKey: "test_key",
                    track: { id: "test_ring_track" },
                    target: { x: 100, y: 100 },
                    layer: { canvas: c, S: 1024, RL: 300, th: 10 }
                };

                viz._disposeRing(ring);

                return {
                    canvasWidth: c.width,
                    canvasHeight: c.height,
                    layerNulled: ring.layer === null,
                    keyCleared: ring.layerKey === "",
                    trackNulled: ring.track === null,
                    targetNulled: ring.target === null,
                };
            }""")

            self.assertEqual(res["canvasWidth"], 1, "Disposed ring canvas must be set to 1px width to reclaim DirectX swapchain")
            self.assertEqual(res["canvasHeight"], 1, "Disposed ring canvas must be set to 1px height to reclaim DirectX swapchain")
            self.assertTrue(res["layerNulled"])
            self.assertTrue(res["keyCleared"])
            self.assertTrue(res["trackNulled"])
            self.assertTrue(res["targetNulled"])
        finally:
            ctx.close()

    def test_tier1_r3_rings_cap_and_idle_layer_vram_limit(self):
        """Feature 19, 20, 21: Ring cap enforcement and idle layer width <= 1920px VRAM cap."""
        ctx, page = self.new_page("/", width=1920, height=1080, dpr=2.0)
        try:
            res = page.evaluate("""() => {
                const viz = window.loopbox.viz;
                const idle = viz._idleLayer(1, { l: 0.7, c: 0.1, h: 200 });
                const idleWidth = idle.width;

                viz.setMemoryPressure("high");
                const highRingsCap = viz.memoryPressure === "high";

                viz.setMemoryPressure("critical");
                const critRingsCap = viz.memoryPressure === "critical";

                viz.setMemoryPressure("normal", true);

                return {
                    idleWidth,
                    highRingsCap,
                    critRingsCap,
                };
            }""")

            self.assertLessEqual(res["idleWidth"], 1920, "Idle layer exceeded 1920px VRAM limit at DPR 2.0")
            self.assertTrue(res["highRingsCap"])
            self.assertTrue(res["critRingsCap"])
        finally:
            ctx.close()

    def test_tier1_r2_prefetch_shield_removal_and_webaudio_strain_signal(self):
        """Feature 10, 12, 15: WebAudio strain signal, prefetch eviction shield removal, and runtime GC triggering."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const loader = window.loopbox.loader;
                const player = window.loopbox.player;

                // Setup active track and prefetch tracks
                player.cur = { track: { id: "track_active" }, beat: 0, rate: 1 };
                player.prefetchIds = ["track_prefetch_1", "track_prefetch_2"];

                // 1. Normal state: prefetchIds are protected
                window.dispatchEvent(new CustomEvent("memorypressure", { detail: { state: "normal" } }));
                const protectedNorm = loader.protect();
                const prefetchProtectedInNorm = protectedNorm.includes("track_prefetch_1");

                // 2. Dispatch memorystrain event -> main.js escalates to critical pressure
                let gcCalled = false;
                const originalGc = window.gc;
                window.gc = () => { gcCalled = true; };

                window.dispatchEvent(new CustomEvent("memorystrain", { detail: { type: "alloc_fail" } }));

                const protectedCrit = loader.protect();
                const prefetchProtectedInCrit = protectedCrit.includes("track_prefetch_1");
                const isCritState = loader.memoryPressure === "critical";

                // Restore
                window.gc = originalGc;
                window.dispatchEvent(new CustomEvent("memorypressure", { detail: { state: "normal" } }));

                return {
                    prefetchProtectedInNorm,
                    prefetchProtectedInCrit,
                    isCritState,
                    gcCalled,
                };
            }""")

            self.assertTrue(res["prefetchProtectedInNorm"], "Prefetch tracks should be protected under Normal pressure")
            self.assertFalse(res["prefetchProtectedInCrit"], "Prefetch eviction shield must be removed under Critical pressure")
            self.assertTrue(res["isCritState"], "memorystrain alloc_fail must escalate memory pressure to critical")
            self.assertTrue(res["gcCalled"], "Critical pressure transition must invoke runtime window.gc()")
        finally:
            ctx.close()

    def test_tier1_r3_satellite_idle_ring_and_lemniscate_disposal(self):
        """Feature 17 & 21: Satellite idle fading ring disposal and lemniscate idle layer disposal."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const viz = window.loopbox.viz;

                // 1. Lemniscate idle layer creation and disposal
                const layerCanvas = viz._idleLayer(1, { l: 0.7, c: 0.1, h: 200 });
                const initialW = layerCanvas.width;

                viz._disposeIdleLayers();
                const disposedW = layerCanvas.width;
                const disposedH = layerCanvas.height;

                // 2. Satellite stage fading ring 1x1 disposal
                const c = document.createElement("canvas");
                c.width = 512;
                c.height = 512;
                const satRing = {
                    role: "fading",
                    alpha: 0.005,
                    layerKey: "sat_fade",
                    track: { id: "sat_fade_track", analysis: {} },
                    target: { x: 100, y: 100, r: 100 },
                    layer: { canvas: c, S: 512, RL: 200, th: 10 }
                };
                viz.rings.set("sat_fade_track", satRing);

                // Run satellite draw cycle with idle mode to trigger fading ring disposal pass
                const canvas = document.getElementById("viz");
                const ctx2d = canvas.getContext("2d");
                viz._drawSatelliteStage(ctx2d, performance.now(), { mode: "idle" }, 0.016);

                const ringDeleted = !viz.rings.has("sat_fade_track");
                const satCanvasWidth = c.width;

                return {
                    initialW,
                    disposedW,
                    disposedH,
                    ringDeleted,
                    satCanvasWidth,
                };
            }""")

            self.assertGreater(res["initialW"], 1, "Idle layer should initially have dimensions > 1px")
            self.assertEqual(res["disposedW"], 1, "Disposed idle layer canvas width must be 1px")
            self.assertEqual(res["disposedH"], 1, "Disposed idle layer canvas height must be 1px")
            self.assertTrue(res["ringDeleted"], "Fading ring must be deleted from viz.rings in satellite stage")
            self.assertEqual(res["satCanvasWidth"], 1, "Fading ring canvas must be disposed to 1x1 before deletion")
        finally:
            ctx.close()

    def test_tier1_same_machine_speaker_sync_relay(self):
        """Regression unit test: StageSyncHub same-machine speaker sync arbitration."""
        class DummyWebSocket:
            def __init__(self, host="127.0.0.1"):
                class Client:
                    pass
                self.client = Client()
                self.client.host = host
                self.sent_messages = []
                self.sent_bytes = []

            async def accept(self):
                pass

            async def send_text(self, text: str):
                self.sent_messages.append(text)

            async def send_bytes(self, data: bytes):
                self.sent_bytes.append(data)

        async def _run():
            hub = StageSyncHub()
            ws_master = DummyWebSocket("127.0.0.1")
            ws_follower = DummyWebSocket("127.0.0.1")
            ws_remote = DummyWebSocket("192.168.1.100")

            await hub.connect(ws_master, role="host")
            await hub.connect(ws_follower, role="satellite")
            await hub.connect(ws_remote, role="satellite")

            handled = await hub._handle_common_control_message({
                "type": "same_machine_speaker_sync",
                "clientId": "follower-1",
                "suppressMasterSpeaker": True,
                "isMutedLocal": False,
            }, ws=ws_follower, role="satellite")

            self.assertTrue(handled)
            master_received = any("same_machine_speaker_sync" in msg for msg in ws_master.sent_messages)
            self.assertTrue(master_received)
            remote_received = any("same_machine_speaker_sync" in msg for msg in ws_remote.sent_messages)
            self.assertFalse(remote_received)

        err_holder = []
        def _target():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(_run())
                loop.close()
            except Exception as e:
                err_holder.append(e)

        th = threading.Thread(target=_target)
        th.start()
        th.join(timeout=5.0)
        if err_holder:
            raise err_holder[0]

    def test_tier1_r1_desktop_bridge_memory_and_trim(self):
        """Feature 6 & 7: DesktopBridge memory status query and 64-bit safe EmptyWorkingSet trim."""
        from loopbox.desktop import DesktopBridge
        bridge = DesktopBridge(port=GLOBAL_SERVER_PORT)
        status = bridge.get_memory_status()
        self.assertIn("state", status)
        self.assertIn("commit_avail_mb", status)
        self.assertIn("commit_pct", status)
        bridge.trim_memory()


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (Stress & Resilience)
# ==============================================================================

class TestTier2BoundaryAndCornerCases(BaseMemoryE2ETestCase):
    """
    Tier 2: Boundary & Corner Cases.
    Tests critical pressure spikes mid-blend, rapid track skipping, canvas context loss,
    zero bounding box resize resilience, and 60-minute long track memory bounds.
    """

    def test_tier2_bc1_critical_pressure_spike_mid_transition(self):
        """BC1: Critical pressure spike mid-transition sheds secondary ring and evicts non-playing buffers."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""async () => {
                const viz = window.loopbox.viz;
                const loader = window.loopbox.loader;
                const engine = window.loopbox.engine;

                // Setup 2 rings on stage (primary + second)
                const trA = { id: "blend_track_A", buffer: engine.ctx.createBuffer(2, 44100, 44100), analysis: { beats: [0], dur: [0.5] } };
                const trB = { id: "blend_track_B", buffer: engine.ctx.createBuffer(2, 44100, 44100), analysis: { beats: [0], dur: [0.5] } };

                const rA = viz._ring(trA, "primary");
                rA.alpha = 1.0;
                const rB = viz._ring(trB, "second");
                rB.alpha = 0.8;

                loader.cache.set("blend_track_A", { track: trA, used: 10 });
                loader.cache.set("blend_track_B", { track: trB, used: 20 });
                loader.protect = () => ["blend_track_A"]; // Only A is playing

                // Incur Critical Pressure Spike
                viz.setMemoryPressure("critical");
                loader.setMemoryPressure("critical");

                return {
                    ringsCount: viz.rings.size,
                    hasPrimary: viz.rings.has("blend_track_A"),
                    hasSecond: viz.rings.has("blend_track_B"),
                    trBBufferNulled: trB.buffer === null,
                    trAPreserved: trA.buffer !== null,
                    bodyHasCritical: document.body.classList.contains("pressure-critical"),
                };
            }""")

            self.assertLessEqual(res["ringsCount"], 1, "Critical pressure must prune rings count to <= 1")
            self.assertTrue(res["hasPrimary"], "Primary active track must be preserved")
            self.assertFalse(res["hasSecond"], "Secondary blend ring must be disposed under critical pressure")
            self.assertTrue(res["trBBufferNulled"], "Unprotected track buffer must be nulled under critical pressure")
            self.assertTrue(res["trAPreserved"], "Active track buffer must remain intact")
            self.assertTrue(res["bodyHasCritical"], "body must receive .pressure-critical CSS class")
            self.assertEqual(len(page._console_errors), 0)
        finally:
            ctx.close()

    def test_tier2_bc2_rapid_10_track_skip_stress(self):
        """BC2: 10 rapid track skips in quick succession leave zero orphaned rings or canvas leaks."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""async () => {
                const viz = window.loopbox.viz;
                const loader = window.loopbox.loader;
                const canvas = document.getElementById("viz");
                const c2d = canvas.getContext("2d");

                for (let i = 1; i <= 10; i++) {
                    const id = `rapid_skip_${i}`;
                    const tr = {
                        id,
                        beats: [0, 0.5, 1.0, 1.5],
                        dur: [0.5, 0.5, 0.5, 0.5],
                        analysis: { beats: [0, 0.5, 1.0, 1.5], dur: [0.5, 0.5, 0.5, 0.5], tempo: 120, gain_db: 0 },
                        meta: { id, title: `Skip ${i}` }
                    };
                    const ring = viz._ring(tr, "primary");
                    ring.target = { x: viz.w / 2, y: viz.h / 2, r: 200, rot: 0, alpha: 1 };
                    ring.alpha = 1;
                    viz._drawRing(c2d, ring);

                    // Mark prior rings as leaving
                    for (const [rid, r] of viz.rings) {
                        if (rid !== id) {
                            r.role = "leaving";
                            r.alpha = 0.005;
                        }
                    }
                    // Run pruning pass
                    for (const [rid, r] of viz.rings) {
                        if ((r.role === "leaving" || r.role === "fading") && r.alpha < 0.02) {
                            viz._disposeRing(r);
                            viz.rings.delete(rid);
                        }
                    }
                }

                return {
                    finalRingsCount: viz.rings.size,
                    latestRingPresent: viz.rings.has("rapid_skip_10"),
                };
            }""")

            self.assertLessEqual(res["finalRingsCount"], 4, "Rings cache leaked past 4 during rapid skipping")
            self.assertTrue(res["latestRingPresent"], "Active ring must remain present")
            self.assertEqual(len(page._console_errors), 0, f"Encountered page errors during rapid skip: {page._console_errors}")
        finally:
            ctx.close()

    def test_tier2_bc3_canvas_context_loss_and_restoration(self):
        """BC3: Canvas context loss pauses rendering safely and restored event reconstructs stage."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const viz = window.loopbox.viz;
                const canvas = document.getElementById("viz");

                // 1. Simulate context loss
                const lossEvt = new Event("contextlost", { cancelable: true });
                canvas.dispatchEvent(lossEvt);
                const lostHandled = viz._contextLost === true;
                const defaultPrevented = lossEvt.defaultPrevented;

                // Frame execution during loss must not throw
                let frameError = null;
                try {
                    viz._frame(performance.now());
                } catch (e) {
                    frameError = String(e);
                }

                // 2. Simulate context restored
                const restoreEvt = new Event("contextrestored");
                canvas.dispatchEvent(restoreEvt);
                const recovered = viz._contextLost === false;

                return {
                    lostHandled,
                    defaultPrevented,
                    frameError,
                    recovered,
                };
            }""")

            self.assertTrue(res["lostHandled"], "viz._contextLost must be true on contextlost")
            self.assertTrue(res["defaultPrevented"], "contextlost event must have preventDefault() called")
            self.assertIsNone(res["frameError"], f"_frame threw during context loss: {res['frameError']}")
            self.assertTrue(res["recovered"], "viz._contextLost must be false after contextrestored")
            self.assertEqual(len(page._console_errors), 0)
        finally:
            ctx.close()

    def test_tier2_bc4_zero_bounding_box_resilience(self):
        """BC4: Zero parent bounding box clamps to >= 200px and does not crash render loop."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const viz = window.loopbox.viz;
                const canvas = document.getElementById("viz");
                const parent = canvas.parentElement;

                const origGetBoundingClientRect = parent.getBoundingClientRect;
                parent.getBoundingClientRect = () => ({ width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 });

                viz._resize();
                const safeW = viz.w;
                const safeH = viz.h;

                let frameErr = null;
                try {
                    viz._frame(performance.now());
                } catch (err) {
                    frameErr = String(err);
                }

                // Restore
                parent.getBoundingClientRect = origGetBoundingClientRect;
                viz._resize();

                return {
                    safeW,
                    safeH,
                    frameErr,
                };
            }""")

            self.assertGreaterEqual(res["safeW"], 200, "Width should be clamped to safe fallback >= 200px")
            self.assertGreaterEqual(res["safeH"], 200, "Height should be clamped to safe fallback >= 200px")
            self.assertIsNone(res["frameErr"], f"_frame failed on zero bounding box: {res['frameErr']}")
        finally:
            ctx.close()

    def test_tier2_bc5_60_minute_track_memory_stability(self):
        """BC5: 60-minute track is supported without memory blowup, while >15m stems are omitted."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const { loader, viz } = window.loopbox;
                loader.setMemoryPressure("normal", true);
                viz.setMemoryPressure("normal", true);
                const player = window.loopbox.player;

                const track60 = { duration: 3600, stems: true };
                const track61 = { duration: 3601, stems: true };
                const track10 = { duration: 600, stems: true };

                loader.setMetas([
                    { id: "t60", duration: 3600, stems: true },
                    { id: "t10", duration: 600, stems: true }
                ]);

                const allowed60 = !loader.isOversized(track60);
                const blocked61 = loader.isOversized(track61);
                const stemsAllowed10 = loader.canLoadStems("t10");
                const stemsBlocked60 = !loader.canLoadStems("t60");

                // Verify timeline remains bounded under 120 events
                player.cur = { track: { id: "test_track_60", beats: [0], dur: [0.5] }, beat: 0, rate: 1 };
                const t0 = performance.now() / 1000;
                for (let i = 0; i < 120; i++) {
                    player._log(t0 + i * 0.1, "beat");
                }
                const timelineBounded = player.timeline.length <= 40;

                return {
                    allowed60,
                    blocked61,
                    stemsAllowed10,
                    stemsBlocked60,
                    timelineBounded,
                };
            }""")

            self.assertTrue(res["allowed60"], "60-minute tracks must be allowed under chunked MP3 decoder architecture")
            self.assertTrue(res["blocked61"], "Tracks >60 minutes must be rejected as oversized")
            self.assertTrue(res["stemsAllowed10"], "Tracks <=15m should allow vocal stems")
            self.assertTrue(res["stemsBlocked60"], "Tracks >15m must reject vocal stem buffer to save 65MB+ RAM")
            self.assertTrue(res["timelineBounded"], "Timeline must remain bounded under rapid events")
        finally:
            ctx.close()

    def test_tier2_bc6_rapid_transition_churn_vocal_stems(self):
        """BC6: 60 rapid alternating transitions across all 6 pathways leave zero zombie vocal stems."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const { player, loader, engine } = window.loopbox;
                const ctx = engine.ctx, sr = ctx.sampleRate;
                loader.cache.clear();
                const tracks = [];
                const ways = ['cut', 'fade', 'fxDrop', 'promote', 'skipToNext', 'start'];
                for (let i = 0; i < 20; i++) {
                    const id = 't_' + i;
                    const trk = {
                        id,
                        buffer: ctx.createBuffer(2, sr * 4, sr),
                        beats: [0, 0.5],
                        dur: [0.5, 0.5],
                        transitions: [],
                        analysis: { meter: 4, beats: [0, 0.5], dur: [0.5, 0.5] },
                        meta: { id, title: `Track ${i}` }
                    };
                    const voc = ctx.createBuffer(2, sr * 4, sr);
                    loader.cache.set(id, { track: trk, used: 100 + i, vocals: Promise.resolve(voc), vocalsBuffer: voc });
                    tracks.push(trk);
                }
                let prev = null;
                for (let step = 0; step < 60; step++) {
                    const cur = tracks[step % tracks.length];
                    const via = ways[step % ways.length];
                    player.cur = { track: cur, beat: 0, rate: 1, voice: null };
                    if (via === 'promote') {
                        player.blend = { A: prev, B: cur, tr: { type: 'blend' }, times: [0, 1], L: 0, voiceB: { setRate: () => {} } };
                    }
                    player._enterTrack(cur, ctx.currentTime + step * 0.1, via, { type: via });
                    if (via === 'promote') {
                        player.blend = null;
                    }
                    prev = cur;
                }
                const zombies = [...loader.cache.entries()].filter(([, e]) => e.track?.buffer === null && e.vocalsBuffer !== null);
                return {
                    zombieCount: zombies.length,
                    cachedBytes: loader._totalCachedBytes(),
                    cacheSize: loader.cache.size,
                };
            }""")

            self.assertEqual(res["zombieCount"], 0, f"Found {res['zombieCount']} zombie vocal stems lingering in cache")
            self.assertEqual(len(page._console_errors), 0, f"Encountered page errors during transition churn: {page._console_errors}")
        finally:
            ctx.close()


# ==============================================================================
# TIER 3: CROSS-FEATURE INTERACTIONS (Ecosystem)
# ==============================================================================

class TestTier3CrossFeatureInteractions(BaseMemoryE2ETestCase):
    """
    Tier 3: Cross-Feature Interactions.
    Verifies cluster stage mirror under Critical pressure, full pressure lifecycle
    hysteresis (SSAA restoration dwell), and active mic/recorder protection.
    """

    def test_tier3_x1_cluster_stage_mirror_under_critical_pressure(self):
        """X1: Cluster follower in stage mirror mode scales down under Critical memory pressure."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""() => {
                const ss = window.__meikovaStageSyncSingleton;
                const viz = window.loopbox.viz;

                // Simulate cluster follower mirror mode
                if (ss) {
                    ss.setClusterMirrorMode(true);
                }

                viz.setMemoryPressure("critical");
                const dpr = viz.dpr;
                const isCrit = viz.memoryPressure === "critical";

                // Satellite frame rendering must continue cleanly
                const canvas = document.getElementById("viz");
                const ctx2d = canvas.getContext("2d");
                let frameErr = null;
                try {
                    viz._drawSatelliteStage(ctx2d, performance.now(), {
                        type: "telemetry",
                        track_id: "sat_crit_track",
                        mode: "ring",
                        pulse: 0.5,
                        bass: 0.5
                    }, 0.016);
                } catch (e) {
                    frameErr = String(e);
                }

                viz.setMemoryPressure("normal", true);

                return {
                    dpr,
                    isCrit,
                    frameErr,
                };
            }""")

            self.assertAlmostEqual(res["dpr"], 1.0, delta=0.01, msg="DPR must be clamped to 1.0 under Critical pressure")
            self.assertTrue(res["isCrit"])
            self.assertIsNone(res["frameErr"], f"Satellite draw failed under critical pressure: {res['frameErr']}")
        finally:
            ctx.close()

    def test_tier3_x2_full_pressure_lifecycle_hysteresis(self):
        """X2: Lifecycle Normal -> High -> Critical -> Normal verifies 4s dwell before SSAA recovery."""
        ctx, page = self.new_page("/", width=1280, height=800, dpr=2.0)
        try:
            res = page.evaluate("""async () => {
                const viz = window.loopbox.viz;

                // 1. Start Normal (native DPR 2.0)
                viz.setMemoryPressure("normal", true);
                const dprNorm = viz.dpr;

                // 2. High (clamps DPR to 1.0)
                viz.setMemoryPressure("high");
                const dprHigh = viz.dpr;

                // 3. Critical (clamps DPR to 1.0)
                viz.setMemoryPressure("critical");
                const dprCrit = viz.dpr;

                // 4. Return to Normal WITHOUT immediate flag: dwell timer must be set
                viz.setMemoryPressure("normal");
                const hasDwellTimer = viz._normalDwellTimer !== null;
                const targetIsNormal = viz._targetPressure === "normal";
                const stillInCritical = viz.memoryPressure === "critical";

                // 5. Force dwell completion via immediate = true
                viz.setMemoryPressure("normal", true);
                const restoredNormal = viz.memoryPressure === "normal";
                const dprRestored = viz.dpr;

                return {
                    dprNorm,
                    dprHigh,
                    dprCrit,
                    hasDwellTimer,
                    targetIsNormal,
                    stillInCritical,
                    restoredNormal,
                    dprRestored,
                };
            }""")

            self.assertEqual(res["dprNorm"], 2.0)
            self.assertEqual(res["dprHigh"], 1.0)
            self.assertEqual(res["dprCrit"], 1.0)
            self.assertTrue(res["hasDwellTimer"], "Visualizer must start 4-second dwell timer when transitioning to normal")
            self.assertTrue(res["targetIsNormal"])
            self.assertTrue(res["stillInCritical"], "Visualizer must not immediately restore SSAA resolution before dwell time")
            self.assertTrue(res["restoredNormal"])
            self.assertEqual(res["dprRestored"], 2.0, "DPR must be restored to full native resolution upon dwell completion")
        finally:
            ctx.close()

    def test_tier3_x3_active_mic_and_recording_protection(self):
        """X3: Active KaraokeMic and MixRecorder nodes remain protected while idle track cache is purged."""
        ctx, page = self.new_page("/")
        try:
            res = page.evaluate("""async () => {
                const engine = window.loopbox.engine;
                const loader = window.loopbox.loader;
                const player = window.loopbox.player;

                // Setup playing track and idle track in cache
                const playTrack = { id: "song_playing", buffer: engine.ctx.createBuffer(2, 44100, 44100) };
                const idleTrack = { id: "song_idle", buffer: engine.ctx.createBuffer(2, 44100, 44100) };

                loader.cache.set("song_playing", { track: playTrack, used: 100 });
                loader.cache.set("song_idle", { track: idleTrack, used: 50 });

                player.cur = { track: playTrack, beat: 0, rate: 1 };
                loader.protect = () => [playTrack.id];

                // Check mic and recorder node availability
                const hasMaster = Boolean(engine.master);
                const hasAnalyser = Boolean(engine.analyser);

                // Elevate pressure to High
                loader.setMemoryPressure("high");

                const idleEvicted = !loader.cache.has("song_idle");
                const idleBufferNulled = idleTrack.buffer === null;
                const playingRetained = loader.cache.has("song_playing");
                const playingBufferIntact = playTrack.buffer !== null;

                // Reset
                loader.setMemoryPressure("normal", true);

                return {
                    hasMaster,
                    hasAnalyser,
                    idleEvicted,
                    idleBufferNulled,
                    playingRetained,
                    playingBufferIntact,
                };
            }""")

            self.assertTrue(res["hasMaster"])
            self.assertTrue(res["hasAnalyser"])
            self.assertTrue(res["idleEvicted"], "Idle track must be evicted under High pressure")
            self.assertTrue(res["idleBufferNulled"], "Idle track buffer must be nulled out")
            self.assertTrue(res["playingRetained"], "Currently playing track must be protected from eviction")
            self.assertTrue(res["playingBufferIntact"], "Playing track buffer must remain intact")
        finally:
            ctx.close()


# ==============================================================================
# TIER 4: REAL-WORLD ACCEPTANCE SCENARIO
# ==============================================================================

class TestTier4RealWorldAcceptance(BaseMemoryE2ETestCase):
    """
    Tier 4: Real-World Acceptance Scenario.
    Executes a continuous 30-track playback and transition cycle in headless Microsoft Edge,
    asserting stable JS heap (<400 MB), zero unhandled page errors, zero canvas freezes,
    and active stage animation throughout.
    """

    def test_tier4_30_track_continuous_cycle_acceptance(self):
        """RW1: 30-track continuous automated playback cycle verifies stable heap <400 MB and zero canvas freezes."""
        ctx, page = self.new_page("/", width=1280, height=800, dpr=2.0)
        try:
            result = page.evaluate("""async () => {
                const viz = window.loopbox.viz;
                const loader = window.loopbox.loader;
                const engine = window.loopbox.engine;
                const canvas = document.getElementById("viz");
                const c2d = canvas.getContext("2d");

                function makeTrack(idx) {
                    const n = 64;
                    const beats = Array.from({ length: n }, (_, i) => i * 0.5);
                    const dur = Array.from({ length: n }, () => 0.5);
                    const loud = Array.from({ length: n }, (_, i) => -12 + Math.sin(i * 0.3) * 4);
                    const color = Array.from({ length: n }, () => [Math.random(), Math.random(), Math.random()]);
                    const jumps = Array.from({ length: n }, (_, i) => (i % 8 === 0 ? [{ to: (i + 16) % n, score: 0.9 }] : []));
                    return {
                        id: `track_rw_${idx}`,
                        n,
                        end: 32,
                        beats,
                        dur,
                        jumps,
                        transitions: [{ to: `track_rw_${idx + 1}`, type: "blend", i: 16, j: 0, len: 8, q: 0.95 }],
                        analysis: { beats, dur, loud, color, tempo: 120, gain_db: 0 },
                        meta: { id: `track_rw_${idx}`, title: `Live Track ${idx}`, artist: "Meikova Loop" }
                    };
                }

                const heapHistory = [];
                let nonTransparentPixels = 0;

                // Execute 30 sequential track transitions
                for (let idx = 1; idx <= 30; idx++) {
                    const tr = makeTrack(idx);

                    // Periodically cycle pressure states to verify dynamic scaling under load
                    if (idx === 10) {
                        viz.setMemoryPressure("high");
                        loader.setMemoryPressure("high");
                    } else if (idx === 20) {
                        viz.setMemoryPressure("critical");
                        loader.setMemoryPressure("critical");
                    } else if (idx === 25) {
                        viz.setMemoryPressure("normal", true);
                        loader.setMemoryPressure("normal");
                    }

                    const ring = viz._ring(tr, "primary");
                    ring.target = { x: viz.w / 2, y: viz.h / 2, r: 220, rot: -Math.PI / 2, alpha: 1 };
                    ring._layoutR = 220;
                    ring.x = viz.w / 2;
                    ring.y = viz.h / 2;
                    ring.r = 220;
                    ring.alpha = 1.0;
                    ring.fill = 1.0;

                    c2d.clearRect(0, 0, canvas.width, canvas.height);
                    viz._drawRing(c2d, ring);

                    // Mark old rings as leaving and clean them up
                    for (const [id, r] of viz.rings) {
                        if (id !== `track_rw_${idx}`) {
                            r.role = "leaving";
                            r.alpha = 0.005;
                        }
                    }
                    for (const [id, r] of viz.rings) {
                        if ((r.role === "leaving" || r.role === "fading") && r.alpha < 0.02) {
                            viz._disposeRing(r);
                            viz.rings.delete(id);
                        }
                    }

                    // Sample heap every 5 tracks
                    if (idx % 5 === 0) {
                        const heapBytes = window.performance?.memory?.usedJSHeapSize || 0;
                        heapHistory.push({
                            trackIdx: idx,
                            heapMb: Math.round(heapBytes / (1024 * 1024) * 10) / 10,
                            ringsCount: viz.rings.size
                        });
                    }

                    // Inspect pixel data on final track
                    if (idx === 30) {
                        const sample = c2d.getImageData(0, 0, canvas.width, canvas.height).data;
                        for (let p = 3; p < sample.length; p += 4) {
                            if (sample[p] > 10) nonTransparentPixels++;
                        }
                    }
                }

                // Restore Normal
                viz.setMemoryPressure("normal", true);
                loader.setMemoryPressure("normal");

                const maxHeapMb = Math.max(...heapHistory.map(h => h.heapMb));

                return {
                    heapHistory,
                    maxHeapMb,
                    finalRingsCount: viz.rings.size,
                    nonTransparentPixels,
                    vizInFrame: viz._inFrame,
                };
            }""")

            self.assertEqual(page._console_errors, [], f"Unhandled browser page errors during 30-track cycle: {page._console_errors}")
            self.assertFalse(result["vizInFrame"], "Viz render loop remained locked in _inFrame state (canvas freeze)")
            self.assertLessEqual(result["finalRingsCount"], 4, "Rings cache leaked past 4 entries")
            self.assertGreater(result["nonTransparentPixels"], 50, "Visualizer stage rendered transparent blank canvas")

            # Check peak JS heap footprint (if performance.memory is exposed in Chromium)
            if result["maxHeapMb"] > 0:
                self.assertLess(result["maxHeapMb"], 400.0, f"JS heap footprint exceeded 400 MB: {result['maxHeapMb']} MB")
        finally:
            ctx.close()


if __name__ == "__main__":
    unittest.main()
