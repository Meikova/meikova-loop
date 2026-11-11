# TEST INFRASTRUCTURE & 4-TIER VERIFICATION MATRIX
**Project:** MashLoop (Meikova Loop) — Cluster Mirror & High-Fidelity Audio Synchronization  
**Document:** `TEST_INFRA.md`  
**Location:** Project Root (`d:\JOB\DEV\MashLoop\TEST_INFRA.md`)  
**Standard:** Antigravity Master Rules & System Standards (Global Titan Edition)

---

## 1. Test Philosophy

1. **Opaque-Box & Requirement-Driven:**  
   Tests evaluate observable external behavior, network protocol frames, DOM elements, CSS styles, and Web Audio DSP node graphs against specification requirements rather than internal implementation minutiae.
2. **Evidence Before Claims:**  
   No test suite passes without running real code. Exit code 0 with genuine assertion passes must be demonstrated in the terminal before claiming test readiness.
3. **Zero-Dummy & Anti-Cheat Mandate:**  
   Facade tests that always pass (`assert True`), dummy placeholders, or tests designed to mirror broken code are strictly prohibited. Every test asserts tangible properties (e.g., `#rc-kicker` text stability, sample saturation bounds, filter cutoff frequency, NTP jitter recovery).
4. **Environment Isolation & Zero-Port Conflict:**  
   The test suite automatically provisions an isolated server instance on a dedicated test port (e.g., 8769 or ephemeral port) in a background thread, preventing interference with running local development servers on default port 8765.
5. **Multi-Client Browser Orchestration:**  
   Real-world multi-node features (Host Master vs. Follower Node vs. Satellite Display) are orchestrated using isolated Playwright browser contexts, testing true multi-client WebSocket synchronization and audio streaming.

---

## 2. Feature Inventory (Features 1–18 Mapped to Test Suite)

| # | Feature | Target Component | Specification Contract | Test Tier |
|---|---------|------------------|------------------------|-----------|
| 1 | Stage Mirror DOM Guard | `web/js/main.js` | `renderStage`, `renderSetlist` guarded by `isStageMirrorActive` | Tier 1 (Area A) |
| 2 | Transport Control Guard | `web/js/main.js` | `renderTransport` guarded by `isStageMirrorActive` | Tier 1 (Area A) |
| 3 | Ambient Lyrics Guard | `web/js/main.js` | `updateAmbientLyrics` guarded by `isStageMirrorActive` | Tier 1 (Area A) |
| 4 | Heartbeat Deactivation | `web/js/viz.js` | 33ms interval disabled on cluster follower (`!isClusterFollower`) | Tier 1 (Area A) |
| 5 | Canvas Idle Clamping | `web/js/viz.js` | In `_drawSatelliteStage`, `idle = 0` and `_drawIdle` suppressed when active track playing | Tier 1 (Area A) |
| 6 | Full-Stage CSS Isolation | `web/css/app.css` | `body.is-cluster-mirror`: `position: absolute; inset: 0`, centering, `transition: none !important` | Tier 1 (Area A) |
| 7 | Dynamic Mirror Canvas Resize | `web/js/viz.js` | Follower canvas auto-resizes without locking fixed inline pixel styles | Tier 1 (Area A) |
| 8 | 44.1kHz Native PCM Stream | `web/js/stage_sync.js` | Host captures un-decimated PCM at native sample rate (44.1k/48k) with 1024 frames | Tier 1 (Area B) |
| 9 | Soft-Knee Tanh Saturation | `web/js/stage_sync.js` | `Math.tanh()` non-linear saturation prior to Int16 quantization | Tier 1 (Area B) |
| 10 | Native Polyphase Resampling | `web/js/stage_sync.js` | `ctx.createBuffer(channels, frames, srcSr)` delegates rate conversion to browser hardware | Tier 1 (Area B) |
| 11 | 20Hz High-Pass Filter | `web/js/stage_sync.js` | Follower audio chain inserts BiquadFilter 20Hz (Q=0.707) before gain node | Tier 1 (Area B) |
| 12 | Output Brickwall Limiter | `web/js/stage_sync.js` | Follower audio chain inserts DynamicsCompressor (-0.8dB, ratio 20) before destination | Tier 1 (Area B) |
| 13 | Smooth Phase-Lock Slew | `web/js/stage_sync.js` | 10% slew rate phase adjustment for drifts in [8ms, 55ms]; snap only if > 55ms | Tier 1 (Area B) |
| 14 | DelayNode Trashing Guard | `web/js/engine.js` | `setSpeakerSyncDelay` dirty-checks `sec` (< 0.0005) before scheduling AudioParam | Tier 1 (Area B) |
| 15 | 60ms Baseline Host Alignment | `stage_sync_hub.py`, `index.html`, `stage_sync.js` | Default `host_align_ms` initialized to 60ms across hub, UI, and client state | Tier 1 (Area B) |
| 16 | Backend Hub State Relay | `loopbox/stage_sync_hub.py` | Hub manages cluster topology, roles (master/node), and audio streaming | Tier 1 (Area C) |
| 17 | Binary PCM Relay | `loopbox/stage_sync_hub.py` | Hub forwards raw 16-byte header + Int16 PCM frames from master to followers | Tier 1 (Area C) |
| 18 | NTP Clock Sync Protocol | `loopbox/stage_sync_hub.py` | Monotonic clock synchronization (`ping_sync` -> `pong_sync`) for zero-echo phase lock | Tier 1 (Area C) |

---

## 3. Test Architecture & Runner Setup

### 3.1. Execution Environment
- **Python Runtime:** `.\.venv\Scripts\python.exe`
- **Framework:** `unittest` (Standard Library)
- **Browser Automation:** `playwright.sync_api`
- **Browser Channel:** Microsoft Edge (`channel='msedge'`) with automatic fallback to Google Chrome (`channel='chrome'`)
- **Server Harness:** `uvicorn.Server` running `loopbox.server:app` on an isolated test port (`http://127.0.0.1:8769`) in a background daemon thread.

### 3.2. Directory & Module Structure
```
tests/
├── test_cluster_sync.py              # Backend hub unit & WebSocket integration tests
├── test_stage_sync.py                # Visual telemetry & smart lights tests
├── test_tab_stability.py             # Tab lifecycle & background resilience tests
└── test_cluster_e2e_playwright.py    # Comprehensive 4-Tier Automated Playwright E2E Suite
```

### 3.3. Execution Command
```powershell
.\.venv\Scripts\python -m unittest tests/test_cluster_e2e_playwright.py -v
```

---

## 4. 4-Tier Test Coverage Matrix

```
┌──────────────────────────────────────────────────────────────────────────┐
│                   TIER 1: FEATURE COVERAGE (Unit/E2E)                    │
│ Area A: Visual Isolation & Guards (TEST-A1 to A7)                        │
│ Area B: High-Fidelity Audio Pipeline & DSP (TEST-B1 to B7)               │
│ Area C: Backend Hub & Cluster Protocol (TEST-C1 to C5)                   │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────────────┐
│                 TIER 2: BOUNDARY & CORNER CASES (BC1 to BC7)             │
│ - Empty track state display        - 44.1k vs 48k sample rate mismatch   │
│ - Jitter & slew recovery (8-55ms)  - Hard snap on > 55ms latency spike   │
│ - Buffer underrun restart horizon  - 150% volume trim tanh saturation    │
│ - Extreme window aspect ratios (mobile 360x640 to ultrawide 2560x1080)   │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────────────┐
│             TIER 3: CROSS-FEATURE INTERACTIONS (X1 to X5)                │
│ - Cluster mirror + stereo pair routing + binary audio streaming          │
│ - Live hostAlignMs slider drag during active playback                    │
│ - DJ track blend transition while mirroring (dual rings + lyrics swap)   │
│ - Background tab throttling on follower                                  │
│ - Follower leave cluster and DOM/audio teardown                          │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────────────┐
│                 TIER 4: REAL-WORLD SCENARIOS (RW1 to RW2)                │
│ - Dual-device Playwright headless run: Host + Follower in Cluster Mirror │
│   mode streaming real audio for 10+ seconds.                             │
│   Assertions: Zero text flicker (never "HAI VÒNG ĐANG CHỜ"),             │
│   viz.idle === 0 throughout, zero audio errors, canvas centered.         │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.1. Detailed Test Specifications

#### Tier 1: Feature Coverage
- **TEST-A1 (RenderStage Guard):** Verify that when `stageSync.isStageMirrorActive` is true, follower's local empty player does not overwrite `#rc-kicker` and `#rc-title`.
- **TEST-A2 (RenderTransport Guard):** Verify that `#btn-play` state and deck buttons are not clobbered by follower's local player when mirroring.
- **TEST-A3 (AmbientLyrics Guard):** Verify `#ambient-lyrics` is preserved and not hidden by follower's local player state.
- **TEST-A4 (Heartbeat Deactivation):** Verify the 33ms `_update` heartbeat is not running on cluster followers, preventing idle forcing.
- **TEST-A5 (Canvas Idle Clamping):** Verify `viz._drawSatelliteStage` clamps `idle = 0` and suppresses `_drawIdle` during active track playback.
- **TEST-A6 (Full-Stage CSS Isolation):** Verify `body.is-cluster-mirror` applies fullscreen bounds, hides `#rc-cta`, and disables transitions.
- **TEST-A7 (Dynamic Canvas Resize):** Verify follower canvas auto-resizes and updates its scale on container dimension changes.
- **TEST-B1 (44.1kHz Native PCM Header):** Verify the 16-byte binary header specifies version 2, 2 channels, and native uint32 sample rate (e.g. 44100).
- **TEST-B2 (Soft-Knee Tanh Saturation):** Verify input samples $\ge 1.0$ smoothly saturate through $\tanh(x)$ without hard square-wave clipping, strictly bounded to $[-32768, 32767]$.
- **TEST-B3 (Native Polyphase Resampler):** Verify PCM packet is decoded into `ctx.createBuffer` with source sample rate for hardware polyphase resampling.
- **TEST-B4 (20Hz HighPass & Brickwall Limiter):** Verify follower audio graph includes BiquadFilter (highpass 20Hz) and DynamicsCompressor limiter.
- **TEST-B5 (Phase Slew Smoothing):** Verify phase drift between 8ms and 55ms triggers a 10% slew rate nudge rather than a discontinuity.
- **TEST-B6 (DelayNode Trashing Guard):** Verify `setSpeakerSyncDelay` dirty-checks `sec` against `_speakerSyncDelaySec` (< 0.0005) before scheduling.
- **TEST-B7 (60ms Baseline Host Alignment):** Verify default `host_align_ms` is initialized to 60ms across hub and client state.
- **TEST-C1 (Cluster Status Endpoint):** Verify `GET /api/cluster/status` returns `host_align_ms = 60.0` default and cluster state.
- **TEST-C2 (Cluster Toggle Endpoint):** Verify `POST /api/cluster/toggle` with `mode: "stereo_pair"` and `host_align_ms: 60` activates cluster mode.
- **TEST-C3 (Binary PCM Relay):** Verify backend hub relays raw binary audio frames from master to followers while dropping unauthorized frames.
- **TEST-C4 (NTP Clock Sync Protocol):** Verify `ping_sync` packet returns `pong_sync` with monotonic server timestamps.
- **TEST-C5 (Master DJ Handoff):** Verify follower can claim mastership via `cluster_node_config` with `claim_master: true`.

#### Tier 2: Boundary & Corner Cases
- **TEST-BC1 (Empty Track State):** Follower receiving `mode: "idle"` gracefully renders idle stage without NaN errors or unhandled exceptions.
- **TEST-BC2 (Sample Rate Mismatch):** Host at 44.1kHz and Follower at 48kHz decodes cleanly without buffer underrun or pitch warp.
- **TEST-BC3 (Jitter & Slew Recovery 8–55ms):** Injected 25ms jitter recovers smoothly through 10% slew rate nudges.
- **TEST-BC4 (Hard Snap Recovery > 55ms):** Injected 80ms latency hiccup triggers immediate snap re-sync within 1 packet cycle.
- **TEST-BC5 (Buffer Underrun Restart Horizon):** Underrun condition (`satNextPlayTime < now + 0.005s`) restarts playhead at safe horizon `now + 0.018s`.
- **TEST-BC6 (Volume Trim 150% Saturation):** High-amplitude input at 150% volume trim never overflows Int16 range and engages output limiter.
- **TEST-BC7 (Window Resize Extreme Ratios):** Resizing between 360x640 and 2560x1080 keeps canvas centered with zero horizontal scrollbar.

#### Tier 3: Cross-Feature Interactions
- **TEST-X1 (Cluster Mirror + Stereo Pair + Audio Streaming):** Follower in stereo pair mode outputs right channel while stage mirror displays full canvas.
- **TEST-X2 (Live hostAlignMs Slider Adjustment):** Dragging `#s-cluster-align-ms` during active playback smoothly updates delay without audio dropouts.
- **TEST-X3 (Track Blend Transition While Mirroring):** Host cross-fades tracks; follower renders dual rings and cross-fades lyrics seamlessly.
- **TEST-X4 (Background Tab Throttling):** Backgrounded follower tab continues audio playback with WebSocket backpressure under 48KB.
- **TEST-X5 (Follower Cluster Leave & Teardown):** Clicking `#btn-cluster-leave` deactivates mirror mode, removes CSS classes, and restores local player.

#### Tier 4: Real-World Scenarios
- **TEST-RW1 (Dual-Device Playwright Real-World 10+ Seconds Playback):**
  - Host and Follower run concurrently in separate Playwright browser contexts.
  - Follower enters Cluster Mirror mode with audio enabled.
  - Over 10+ seconds of live playback, continuously monitor:
    1. `#rc-kicker` never displays `"HAI VÒNG ĐANG CHỜ"`.
    2. `#rc-title` consistently displays the active Master track title.
    3. `viz.idle === 0` throughout (zero lemniscate ghost overlap).
    4. Zero browser console errors and zero audio context underrun crashes.
    5. Canvas dimensions remain centered in viewport.
