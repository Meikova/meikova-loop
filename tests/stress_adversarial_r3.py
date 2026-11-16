"""
tests/stress_adversarial_r3.py: Adversarial Empirical Stress Harness for R3 & Playback Lifecycle.

Authored by: challenger_mem_2 (Empirical Challenger)
Probes:
1. Hostile Canvas Context Loss / Restored Storm & Frame Re-entrance
2. Zero/Corrupted Bounding Boxes, NaN inputs, and drawImage IndexSizeError Guards
3. 1x1 Pixel Canvas Texture Disposal Verification on Ring Replacement, Prewarm, Satellite, and Idle
4. Memory Pressure Telemetry: DPR Clamping, Texture Downscaling (1024/512), Bloom/Lights Suppression, and 4s Hysteresis Dwell/Cancel
5. 50-Track Continuous Playback Acceptance Cycle under Memory Oscillations
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from loopbox.server import app

SERVER_PORT = 8776
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"
GLOBAL_SERVER = None
GLOBAL_SERVER_THREAD = None
GLOBAL_PLAYWRIGHT = None
GLOBAL_BROWSER = None


def launch_browser(p) -> Browser:
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
    raise RuntimeError("Failed to launch Edge/Chrome/Chromium via Playwright")


def setUpModule():
    global GLOBAL_SERVER, GLOBAL_SERVER_THREAD, GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER
    config = uvicorn.Config(app, host="127.0.0.1", port=SERVER_PORT, log_level="error", access_log=False)
    GLOBAL_SERVER = uvicorn.Server(config)
    GLOBAL_SERVER_THREAD = threading.Thread(target=GLOBAL_SERVER.run, daemon=True, name="uvicorn-r3-stress")
    GLOBAL_SERVER_THREAD.start()

    t0 = time.time()
    server_ready = False
    while time.time() - t0 < 8.0:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/version", timeout=0.5) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.1)
    if not server_ready:
        raise RuntimeError(f"Server on {BASE_URL} failed to start")

    GLOBAL_PLAYWRIGHT = sync_playwright().start()
    GLOBAL_BROWSER = launch_browser(GLOBAL_PLAYWRIGHT)


def tearDownModule():
    global GLOBAL_SERVER, GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER
    if GLOBAL_BROWSER:
        try:
            GLOBAL_BROWSER.close()
        except Exception:
            pass
    if GLOBAL_PLAYWRIGHT:
        try:
            GLOBAL_PLAYWRIGHT.stop()
        except Exception:
            pass
    if GLOBAL_SERVER:
        GLOBAL_SERVER.should_exit = True


class TestAdversarialR3VisualizerStress(unittest.TestCase):
    def setUp(self):
        self._contexts: list[BrowserContext] = []

    def tearDown(self):
        for ctx in self._contexts:
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts = []

    def new_page(self, width=1280, height=800, dpr=2.0) -> tuple[BrowserContext, Page]:
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
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        page.wait_for_selector("#viz", state="attached", timeout=6000)
        page.wait_for_function(
            "() => Boolean(window.loopbox && window.loopbox.viz && window.loopbox.player && window.loopbox.loader)",
            timeout=8000,
        )
        return ctx, page

    def test_adv_1_context_loss_storm_and_frame_reentrance(self):
        """Stress: 50 interleaved contextlost/contextrestored events while calling _frame()."""
        ctx, page = self.new_page()
        res = page.evaluate("""() => {
            const viz = window.loopbox.viz;
            const canvas = viz.canvas;
            let frameExceptions = [];
            let inFrameStuck = false;

            for (let i = 0; i < 50; i++) {
                // Fire contextlost
                const evLost = new Event("contextlost", { cancelable: true });
                canvas.dispatchEvent(evLost);

                if (!viz._contextLost) {
                    return { error: `_contextLost not set on iteration ${i}` };
                }

                // Render frame during context loss
                try {
                    viz._frame(performance.now());
                } catch (err) {
                    frameExceptions.push(`loss_frame_${i}: ${err}`);
                }

                if (viz._inFrame) {
                    inFrameStuck = true;
                }

                // Fire contextrestored
                const evRestored = new Event("contextrestored");
                canvas.dispatchEvent(evRestored);

                if (viz._contextLost) {
                    return { error: `_contextLost not cleared after restore on iteration ${i}` };
                }

                // Render frame after restore
                try {
                    viz._frame(performance.now());
                } catch (err) {
                    frameExceptions.push(`restored_frame_${i}: ${err}`);
                }

                if (viz._inFrame) {
                    inFrameStuck = true;
                }
            }

            return {
                started: viz.started,
                inFrameStuck,
                frameExceptions,
                contextLostFinal: viz._contextLost,
                hasCtx: viz.ctx !== null,
            };
        }""")

        self.assertTrue(res["started"], "Viz loop must remain started")
        self.assertFalse(res["inFrameStuck"], "Viz _inFrame must never be stuck as true")
        self.assertEqual(res["frameExceptions"], [], f"Frame exceptions during context loss storm: {res.get('frameExceptions')}")
        self.assertFalse(res["contextLostFinal"], "Final contextLost state must be false")
        self.assertTrue(res["hasCtx"], "2D context must be present after restoration")
        self.assertEqual(page._console_errors, [])

    def test_adv_2_hostile_bounding_box_and_drawimage_guards(self):
        """Stress: Zero, negative, sub-threshold bounding boxes, and corrupted 1x1 / 0x0 canvases on _drawRing."""
        ctx, page = self.new_page()
        res = page.evaluate("""() => {
            const viz = window.loopbox.viz;
            const parent = viz.canvas.parentElement;
            const origGetBoundingClientRect = parent.getBoundingClientRect;
            const hostileBoxes = [
                { width: 0, height: 0 },
                { width: -50, height: -50 },
                { width: 1, height: 1 },
                { width: 119, height: 119 },
                { width: 50, height: 400 },
                { width: 800, height: 30 },
            ];

            const boxResults = [];
            for (const b of hostileBoxes) {
                parent.getBoundingClientRect = () => ({ width: b.width, height: b.height, top: 0, left: 0, right: b.width, bottom: b.height });
                viz._resize();
                boxResults.push({
                    input: b,
                    w: viz.w,
                    h: viz.h,
                    safeClamped: viz.w >= 200 && viz.h >= 200,
                });
            }

            // Restore normal bounding box
            parent.getBoundingClientRect = origGetBoundingClientRect;
            viz._resize();

            // Hostile drawRing layers: 0x0 canvas, 1x1 canvas, null canvas, throwing drawImage
            const canvas2d = viz.ctx;
            const hostileLayers = [];

            // 1. 0x0 canvas
            const c0 = document.createElement("canvas");
            c0.width = 0; c0.height = 0;
            const ring0 = {
                role: "primary", alpha: 1, x: 200, y: 200, r: 100, rot: 0, dir: 1, fill: 1,
                track: { id: "tr0", analysis: {}, beats: [0], dur: [0.5] },
                layer: { canvas: c0, S: 100, RL: 100, th: 4 },
                layerKey: "key0"
            };
            try {
                viz._drawRing(canvas2d, ring0);
                hostileLayers.push({ type: "0x0", passed: true });
            } catch (err) {
                hostileLayers.push({ type: "0x0", passed: false, error: String(err) });
            }

            // 2. 1x1 canvas (disposed)
            const c1 = document.createElement("canvas");
            c1.width = 1; c1.height = 1;
            const ring1 = {
                role: "primary", alpha: 1, x: 200, y: 200, r: 100, rot: 0, dir: 1, fill: 1,
                track: { id: "tr1", analysis: {}, beats: [0], dur: [0.5] },
                layer: { canvas: c1, S: 100, RL: 100, th: 4 },
                layerKey: "key1"
            };
            try {
                viz._drawRing(canvas2d, ring1);
                hostileLayers.push({ type: "1x1", passed: true });
            } catch (err) {
                hostileLayers.push({ type: "1x1", passed: false, error: String(err) });
            }

            // 3. layer with null canvas
            const ringNull = {
                role: "primary", alpha: 1, x: 200, y: 200, r: 100, rot: 0, dir: 1, fill: 1,
                track: { id: "trNull", analysis: {}, beats: [0], dur: [0.5] },
                layer: { canvas: null, S: 100, RL: 100, th: 4 },
                layerKey: "keyNull"
            };
            try {
                viz._drawRing(canvas2d, ringNull);
                hostileLayers.push({ type: "null_canvas", passed: true });
            } catch (err) {
                hostileLayers.push({ type: "null_canvas", passed: false, error: String(err) });
            }

            // 4. throwing drawImage simulation
            const origDrawImage = canvas2d.drawImage;
            canvas2d.drawImage = () => { throw new DOMException("Out of GPU Memory (Simulated)", "QuotaExceededError"); };
            const cValid = document.createElement("canvas");
            cValid.width = 100; cValid.height = 100;
            const ringThrow = {
                role: "primary", alpha: 1, x: 200, y: 200, r: 100, rot: 0, dir: 1, fill: 1,
                track: { id: "trThrow", analysis: {}, beats: [0], dur: [0.5] },
                layer: { canvas: cValid, S: 100, RL: 100, th: 4 },
                layerKey: "keyThrow"
            };
            let caughtSafely = false;
            try {
                viz._drawRing(canvas2d, ringThrow);
                caughtSafely = true;
            } catch (err) {
                caughtSafely = false;
            }
            canvas2d.drawImage = origDrawImage;
            hostileLayers.push({ type: "drawImage_throws", passed: caughtSafely });

            return {
                boxResults,
                hostileLayers,
            };
        }""")

        for br in res["boxResults"]:
            self.assertTrue(br["safeClamped"], f"Bounding box {br['input']} failed to clamp to >= 200px: w={br['w']}, h={br['h']}")
        for hl in res["hostileLayers"]:
            self.assertTrue(hl["passed"], f"Hostile layer test {hl['type']} failed: {hl.get('error')}")

    def test_adv_3_texture_1x1_disposal_on_replacement_and_idle(self):
        """Stress: Verify 1x1 canvas dimensions on _disposeRing, layer replacement, prewarm, satellite, and idle layers."""
        ctx, page = self.new_page()
        res = page.evaluate("""() => {
            const viz = window.loopbox.viz;
            const results = {};

            // 1. Direct _disposeRing verification
            const bigCanvas = document.createElement("canvas");
            bigCanvas.width = 1024;
            bigCanvas.height = 1024;
            const ring = {
                layer: { canvas: bigCanvas, S: 500, RL: 200 },
                layerKey: "some_key",
                track: { id: "t1" }
            };
            viz._disposeRing(ring);
            results.directDisposeCanvasW = bigCanvas.width;
            results.directDisposeCanvasH = bigCanvas.height;
            results.directDisposeLayerNull = ring.layer === null;
            results.directDisposeTrackNull = ring.track === null;

            // 2. Layer replacement in _drawRing
            const trA = {
                id: "track_replace_test",
                beats: [0, 0.5, 1.0],
                dur: [0.5, 0.5, 0.5],
                analysis: { beats: [0, 0.5, 1.0], dur: [0.5, 0.5, 0.5], tempo: 120, gain_db: 0, pos: [0, 1, 2] },
                meta: { id: "track_replace_test", title: "Replace Test" }
            };
            const rLive = viz._ring(trA, "primary");
            rLive.target = { x: 200, y: 200, r: 180, rot: 0, alpha: 1 };
            rLive.x = 200;
            rLive.y = 200;
            rLive.r = 180;
            rLive.alpha = 1;
            viz._drawRing(viz.ctx, rLive);
            const initialLayerCanvas = rLive.layer.canvas;
            results.initialCanvasWidth = initialLayerCanvas.width;
            results.initialCanvasIsMultiPixel = initialLayerCanvas.width > 10;

            // Invalidate and force key change
            viz.invalidate();
            rLive.layerKey = "forced_stale_key";
            viz._drawRing(viz.ctx, rLive);
            results.replacedOldCanvasWidth = initialLayerCanvas.width;
            results.replacedOldCanvasHeight = initialLayerCanvas.height;
            results.newLayerAllocated = rLive.layer.canvas !== initialLayerCanvas && rLive.layer.canvas.width > 10;

            // 3. Prewarm layer replacement
            const prewarmInitialCanvas = rLive.layer.canvas;
            rLive.layerKey = "prewarm_stale_key";
            viz._prewarmLayer(trA);
            results.prewarmReplacedOldW = prewarmInitialCanvas.width;
            results.prewarmReplacedOldH = prewarmInitialCanvas.height;

            // 4. Idle layers disposal
            viz._drawIdle(viz.ctx, performance.now(), 1.0);
            const idleLayersCountBefore = Object.keys(viz.idleSt?.layers || {}).length;
            const idleCanvases = Object.values(viz.idleSt?.layers || {}).map(item => item.canvas);
            viz._disposeIdleLayers();
            const idleCanvasesDisposed = idleCanvases.every(c => c.width === 1 && c.height === 1);
            const idleLayersCountAfter = Object.keys(viz.idleSt?.layers || {}).length;

            results.idleLayersCountBefore = idleLayersCountBefore;
            results.idleCanvasesDisposed = idleCanvasesDisposed;
            results.idleLayersCountAfter = idleLayersCountAfter;

            // 5. Satellite stage fading ring disposal
            const satCanvas = document.createElement("canvas");
            satCanvas.width = 512;
            satCanvas.height = 512;
            const satRing = {
                role: "fading",
                alpha: 0.01, // < 0.02 threshold
                x: 100, y: 100, r: 100,
                track: trA,
                layer: { canvas: satCanvas, S: 200, RL: 100 }
            };
            viz.rings.set("sat_fading_test", satRing);
            // Run satellite idle step
            viz._drawSatelliteStage(viz.ctx, performance.now(), { mode: "idle" }, 0.016);
            results.satRingDisposedW = satCanvas.width;
            results.satRingDisposedH = satCanvas.height;
            results.satRingDeleted = !viz.rings.has("sat_fading_test");

            return results;
        }""")

        self.assertEqual(res["directDisposeCanvasW"], 1, "Direct dispose must set canvas width to 1")
        self.assertEqual(res["directDisposeCanvasH"], 1, "Direct dispose must set canvas height to 1")
        self.assertTrue(res["directDisposeLayerNull"])
        self.assertTrue(res["directDisposeTrackNull"])

        self.assertTrue(res["initialCanvasIsMultiPixel"])
        self.assertEqual(res["replacedOldCanvasWidth"], 1, "Replaced layer canvas in _drawRing must be resized to 1x1")
        self.assertEqual(res["replacedOldCanvasHeight"], 1, "Replaced layer canvas in _drawRing must be resized to 1x1")
        self.assertTrue(res["newLayerAllocated"])

        self.assertEqual(res["prewarmReplacedOldW"], 1, "Replaced layer canvas in _prewarmLayer must be resized to 1x1")
        self.assertEqual(res["prewarmReplacedOldH"], 1, "Replaced layer canvas in _prewarmLayer must be resized to 1x1")

        self.assertGreater(res["idleLayersCountBefore"], 0)
        self.assertTrue(res["idleCanvasesDisposed"], "All idle layer canvases must be resized to 1x1 on _disposeIdleLayers()")
        self.assertEqual(res["idleLayersCountAfter"], 0)

        self.assertEqual(res["satRingDisposedW"], 1, "Satellite fading ring must be disposed to 1x1 before deletion")
        self.assertEqual(res["satRingDisposedH"], 1, "Satellite fading ring must be disposed to 1x1 before deletion")
        self.assertTrue(res["satRingDeleted"])

    def test_adv_4_pressure_scaling_bloom_lights_and_hysteresis_cancellation(self):
        """Stress: Verify High/Critical texture scaling, bloom stripping, lights suppression, and rapid hysteresis re-escalation."""
        ctx, page = self.new_page(dpr=2.0)
        res = page.evaluate("""async () => {
            const viz = window.loopbox.viz;
            const tr = {
                id: "adv4_track",
                beats: [0, 0.5, 1.0, 1.5],
                dur: [0.5, 0.5, 0.5, 0.5],
                analysis: { beats: [0, 0.5, 1.0, 1.5], dur: [0.5, 0.5, 0.5, 0.5], tempo: 120, gain_db: 0, pos: [0, 1, 2, 3] },
                meta: { id: "adv4_track", title: "Adv4 Track" }
            };
            const r = viz._ring(tr, "primary");
            r.target = { x: 300, y: 300, r: 240, rot: 0, alpha: 1 };
            r.x = 300;
            r.y = 300;
            r.r = 240;
            r.alpha = 1;
            viz._drawRing(viz.ctx, r);

            // 1. HIGH PRESSURE
            viz.setMemoryPressure("high");
            const highDpr = viz.dpr;
            const highMaxRings = viz.rings.size;
            const highHasBodyClass = document.body.classList.contains("pressure-high");
            const highNoCritClass = !document.body.classList.contains("pressure-critical");
            // Check texture cap on newly built layer under High
            const layerHigh = viz._buildLayer(tr);
            const highTextureDim = Math.max(layerHigh.canvas.width, layerHigh.canvas.height);

            // 2. CRITICAL PRESSURE
            viz.setMemoryPressure("critical");
            const critDpr = viz.dpr;
            const critHasBodyClass = document.body.classList.contains("pressure-critical");
            const critNoHighClass = !document.body.classList.contains("pressure-high");
            // Check texture cap on newly built layer under Critical
            const layerCrit = viz._buildLayer(tr);
            const critTextureDim = Math.max(layerCrit.canvas.width, layerCrit.canvas.height);

            // Verify prewarmLayer does NOT allocate under Critical
            const prewarmTrack = { id: "prewarm_crit", analysis: { beats: [0], dur: [0.5] }, beats: [0], dur: [0.5] };
            const prewarmRing = viz._ring(prewarmTrack, "fading");
            prewarmRing.layer = null;
            viz._prewarmLayer(prewarmTrack);
            const prewarmSkippedUnderCrit = prewarmRing.layer === null;

            // 3. HYSTERESIS DWELL & CANCELLATION
            // Under critical, request transition to normal
            viz.setMemoryPressure("normal");
            const dwellTimerActive = viz._normalDwellTimer !== null;
            const pressureStillCritical = viz.memoryPressure === "critical";

            // Re-escalate to High mid-dwell: timer must be cancelled immediately
            viz.setMemoryPressure("high");
            const timerCancelled = viz._normalDwellTimer === null;
            const pressureElevatedToHigh = viz.memoryPressure === "high";

            // Return to normal immediately via immediate = true
            viz.setMemoryPressure("normal", true);
            const restoredDpr = viz.dpr;
            const restoredPressure = viz.memoryPressure === "normal";
            const noBodyClasses = !document.body.classList.contains("pressure-high") && !document.body.classList.contains("pressure-critical");

            return {
                highDpr,
                highHasBodyClass,
                highNoCritClass,
                highTextureDim,
                critDpr,
                critHasBodyClass,
                critNoHighClass,
                critTextureDim,
                prewarmSkippedUnderCrit,
                dwellTimerActive,
                pressureStillCritical,
                timerCancelled,
                pressureElevatedToHigh,
                restoredDpr,
                restoredPressure,
                noBodyClasses,
            };
        }""")

        self.assertAlmostEqual(res["highDpr"], 1.0, delta=0.01, msg="High pressure must clamp DPR to 1.0")
        self.assertTrue(res["highHasBodyClass"])
        self.assertTrue(res["highNoCritClass"])
        self.assertLessEqual(res["highTextureDim"], 1024, "High pressure texture must be capped at 1024px")

        self.assertAlmostEqual(res["critDpr"], 1.0, delta=0.01, msg="Critical pressure must clamp DPR to 1.0")
        self.assertTrue(res["critHasBodyClass"])
        self.assertTrue(res["critNoHighClass"])
        self.assertLessEqual(res["critTextureDim"], 512, "Critical pressure texture must be capped at 512px")
        self.assertTrue(res["prewarmSkippedUnderCrit"], "Prewarming must be skipped under critical pressure")

        self.assertTrue(res["dwellTimerActive"], "Normal transition must start dwell timer")
        self.assertTrue(res["pressureStillCritical"], "Pressure must remain critical during dwell")
        self.assertTrue(res["timerCancelled"], "Re-escalation must clear dwell timer")
        self.assertTrue(res["pressureElevatedToHigh"])
        self.assertAlmostEqual(res["restoredDpr"], 2.0, delta=0.01, msg="Normal restoration must restore native DPR (2.0)")
        self.assertTrue(res["restoredPressure"])
        self.assertTrue(res["noBodyClasses"])

    def test_adv_5_fifty_track_continuous_cycle_with_pressure_oscillations(self):
        """Stress: 50-track continuous transition stress test with periodic rapid pressure shifts and heap bounds."""
        ctx, page = self.new_page()
        res = page.evaluate("""async () => {
            const viz = window.loopbox.viz;
            const loader = window.loopbox.loader;
            const canvas = viz.canvas;
            const c2d = canvas.getContext("2d");

            function makeTrack(idx) {
                const n = 32;
                const beats = Array.from({ length: n }, (_, i) => i * 0.5);
                const dur = Array.from({ length: n }, () => 0.5);
                const loud = Array.from({ length: n }, () => 0.8);
                const color = Array.from({ length: n }, () => [0.7, 0.15, (idx * 37) % 360]);
                return {
                    id: `stress_trk_${idx}`,
                    n, end: 32, beats, dur,
                    transitions: [{ to: `stress_trk_${idx + 1}`, type: "blend", i: 16, j: 0, len: 8, q: 0.95 }],
                    analysis: { beats, dur, loud, color, tempo: 124, gain_db: 0 },
                    meta: { id: `stress_trk_${idx}`, title: `Track ${idx}` }
                };
            }

            const heapSamples = [];
            let nonTransparentPixels = 0;

            for (let i = 1; i <= 50; i++) {
                const tr = makeTrack(i);

                // Oscillate pressure states to stress dynamic scaling under load
                if (i % 7 === 0) {
                    viz.setMemoryPressure("high");
                    loader.setMemoryPressure("high");
                } else if (i % 13 === 0) {
                    viz.setMemoryPressure("critical");
                    loader.setMemoryPressure("critical");
                } else if (i % 5 === 0) {
                    viz.setMemoryPressure("normal", true);
                    loader.setMemoryPressure("normal");
                }

                const ring = viz._ring(tr, "primary");
                ring.target = { x: viz.w / 2, y: viz.h / 2, r: 210, rot: 0, alpha: 1 };
                ring.x = viz.w / 2;
                ring.y = viz.h / 2;
                ring.r = 210;
                ring.alpha = 1.0;
                ring.fill = 1.0;

                c2d.clearRect(0, 0, canvas.width, canvas.height);
                viz._drawRing(c2d, ring);

                // Clean up previous rings
                for (const [id, r] of viz.rings) {
                    if (id !== `stress_trk_${i}`) {
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

                if (i % 10 === 0) {
                    const heap = window.performance?.memory?.usedJSHeapSize || 0;
                    heapSamples.push({
                        track: i,
                        heapMb: Math.round(heap / (1024 * 1024) * 10) / 10,
                        ringsCount: viz.rings.size
                    });
                }

                if (i === 50) {
                    const img = c2d.getImageData(0, 0, canvas.width, canvas.height).data;
                    for (let p = 3; p < img.length; p += 4) {
                        if (img[p] > 10) nonTransparentPixels++;
                    }
                }
            }

            viz.setMemoryPressure("normal", true);
            loader.setMemoryPressure("normal");

            const maxHeap = Math.max(...heapSamples.map(s => s.heapMb));

            return {
                heapSamples,
                maxHeap,
                finalRingsCount: viz.rings.size,
                nonTransparentPixels,
                vizInFrame: viz._inFrame,
            };
        }""")

        self.assertEqual(page._console_errors, [], f"Console errors in 50-track stress: {page._console_errors}")
        self.assertFalse(res["vizInFrame"], "Viz inFrame must not be stuck")
        self.assertLessEqual(res["finalRingsCount"], 4, "Rings count must not leak")
        self.assertGreater(res["nonTransparentPixels"], 50, "Visualizer stage must actively render pixels")
        if res["maxHeap"] > 0:
            self.assertLess(res["maxHeap"], 400.0, f"Peak JS heap exceeded 400 MB: {res['maxHeap']} MB")

    def test_adv_6_realtime_4s_dwell_and_gradient_call_counts(self):
        """Stress: Real-time 4000ms dwell expiration and gradient invocation counting."""
        from loopbox.memory_monitor import memory_monitor
        memory_monitor.set_simulation(commit_avail_mb=8000.0, commit_pct=50.0, phys_avail_mb=6000.0)
        try:
            ctx, page = self.new_page(dpr=2.0)

            res = page.evaluate("""async () => {
                const viz = window.loopbox.viz;
                const c2d = viz.ctx;

                // 1. Enter critical and transition to normal (start 4s dwell)
                viz.setMemoryPressure("critical");
                const critDpr = viz.dpr;
                viz.setMemoryPressure("normal"); // schedules 4000ms timer
                const hasDwellTimer0 = viz._normalDwellTimer !== null;
                const pressureStillCritical = viz.memoryPressure === "critical";

                // Wait 4800ms for dwell timer to fire
                await new Promise(r => setTimeout(r, 4800));

                const hasDwellTimer1 = viz._normalDwellTimer !== null;
                const pressureRestoredNormal = viz.memoryPressure === "normal";
                const restoredDpr = viz.dpr;

                // 2. Count gradient invocations across pressure states
                const counts = { normal: 0, high: 0, critical: 0 };
                const origRadial = c2d.createRadialGradient;
                const origConic = c2d.createConicGradient;

                let counter = 0;
                c2d.createRadialGradient = function(...args) { counter++; return origRadial.apply(this, args); };
                if (origConic) {
                    c2d.createConicGradient = function(...args) { counter++; return origConic.apply(this, args); };
                }

                // Setup active track and ring
                const tr = {
                    id: "grad_test_trk",
                    beats: [0, 0.5, 1.0, 1.5],
                    dur: [0.5, 0.5, 0.5, 0.5],
                    analysis: { beats: [0, 0.5, 1.0, 1.5], dur: [0.5, 0.5, 0.5, 0.5], tempo: 120, gain_db: 0, pos: [0, 1, 2, 3] },
                    meta: { id: "grad_test_trk", title: "Grad Track" }
                };
                const r = viz._ring(tr, "primary");
                r.x = viz.w / 2; r.y = viz.h / 2; r.r = 200; r.alpha = 1;
                r.col = { l: 0.7, c: 0.15, h: 180 };
                const leadHead = { ring: r, beat: 0, frac: 0.5, angle: 0 };

                // Normal
                viz.setMemoryPressure("normal", true);
                counter = 0;
                viz._drawLights(c2d, r);
                viz._drawHead(c2d, leadHead, 1.0, true);
                counts.normal = counter;

                // High
                viz.setMemoryPressure("high");
                counter = 0;
                viz._drawLights(c2d, r);
                viz._drawHead(c2d, leadHead, 1.0, true);
                counts.high = counter;

                // Critical
                viz.setMemoryPressure("critical");
                counter = 0;
                viz._drawLights(c2d, r);
                viz._drawHead(c2d, leadHead, 1.0, true);
                counts.critical = counter;

                // Restore
                c2d.createRadialGradient = origRadial;
                if (origConic) c2d.createConicGradient = origConic;
                viz.setMemoryPressure("normal", true);

                return {
                    critDpr,
                    hasDwellTimer0,
                    pressureStillCritical,
                    hasDwellTimer1,
                    pressureRestoredNormal,
                    restoredDpr,
                    counts,
                };
            }""")

            self.assertAlmostEqual(res["critDpr"], 1.0, delta=0.01)
            self.assertTrue(res["hasDwellTimer0"], "Dwell timer must be active immediately after setMemoryPressure('normal')")
            self.assertTrue(res["pressureStillCritical"], "Pressure must remain critical during dwell period")
            self.assertFalse(res["hasDwellTimer1"], "Dwell timer must be cleared after 4000ms")
            self.assertTrue(res["pressureRestoredNormal"], "Pressure must be restored to normal after 4000ms")
            self.assertAlmostEqual(res["restoredDpr"], 2.0, delta=0.01, msg="Native DPR 2.0 must be restored upon dwell completion")
            self.assertGreater(res["counts"]["normal"], res["counts"]["high"], "Normal must generate more gradient calls than High")
            self.assertEqual(res["counts"]["critical"], 0, "Critical pressure must generate ZERO gradient calls in lights and head")
        finally:
            memory_monitor.clear_simulation()


if __name__ == "__main__":
    unittest.main()
