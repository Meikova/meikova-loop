# Test Infrastructure & Verification Architecture: Dynamic Memory Pressure Sensing & Adaptive Scaling

## 1. Overview & Verification Strategy

This document details the automated testing infrastructure, 4-tier verification matrix, and regression alignment certifying MashLoop's (Meikova Loop) dynamic memory pressure sensing and adaptive resource scaling architecture.

The testing infrastructure guarantees that MashLoop survives constrained virtual commit memory conditions without WebView2 Out-of-Memory crashes (`STATUS_COMMITMENT_LIMIT / 1455`), maintains continuous 60 FPS visualizer animation without canvas freezing, proactively evicts audio buffers while protecting active stems and mic/recording pipelines, and cleans up all WebAudio filter nodes upon voice disposal.

---

## 2. Test Execution Environment & Prerequisites

- **Python Runtime**: Python 3.12.4 (`.\\.venv\\Scripts\\python.exe`)
- **Test Framework**: Python standard library `unittest`
  *(Note: `pytest` is deliberately omitted from the project virtual environment to eliminate dependency bloat; all tests run via standard library `unittest`)*
- **Browser Automation Engine**: Microsoft Edge / Chromium via Playwright 1.64.0
- **Node.js Environment**: Node.js `v24.14.0`
- **Host OS**: Microsoft Windows (win32) with native `ctypes` Virtual Commit Memory access

---

## 3. 4-Tier Automated Verification Matrix

```
┌──────────────────────────────────────────────────────────────────────────┐
│                   TIER 1: FEATURE COVERAGE (Unit & Subsystem)            │
│ R1: Backend Memory Pressure Sensing & Windows Commit Reporting           │
│ R2: AudioBuffer Eviction, Voice Disconnection, Timeline Pruning          │
│ R3: Canvas Texture 1x1 Disposal, Ring Cap Pruning, Context Guards        │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────────────┐
│                 TIER 2: BOUNDARY & CORNER CASES (Stress & Edge)          │
│ - Instant pressure spike to Critical during active DJ crossfade          │
│ - Rapid skip: 10 track skips in quick succession (zero buffer leakage)   │
│ - Silent canvas context loss (simulated contextlost / contextrestored)   │
│ - Null/zero canvas dimensions: requestAnimationFrame never throws        │
│ - 60-minute ultra-long track memory stability                            │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────────────┐
│             TIER 3: CROSS-FEATURE INTERACTIONS (Ecosystem)               │
│ - Cluster Stage Mirroring under Critical memory pressure                 │
│ - Transition cycle: Normal -> High -> Critical -> Normal (SSAA restored)│
│ - Active Karaoke Mic & Mix Recording during memory throttling            │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼─────────────────────────────────────┐
│                 TIER 4: REAL-WORLD E2E ACCEPTANCE SCENARIO               │
│ - 30-track continuous automated playback cycle in headless Edge          │
│ - JS Heap footprint asserts: peak memory <= 400 MB                       │
│ - Zero unhandled page errors, zero canvas freezes, viz.started === true  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Feature Coverage Mapping (Features 1–25)

| Feature # | Feature Description | Target Module | Verified By | Test Tier |
|---|---|---|---|---|
| **1** | Pure ctypes Win32 Memory Sensor | `loopbox/memory_monitor.py` | `test_tier1_r1_backend_win32_ctypes_query` | Tier 1 |
| **2** | Non-Windows Memory Sensor Fallback | `loopbox/memory_monitor.py` | `test_tier1_r1_backend_win32_ctypes_query` | Tier 1 |
| **3** | Memory Pressure Hysteresis Engine | `loopbox/memory_monitor.py` | `test_tier1_r1_threshold_state_classification_and_hysteresis` | Tier 1 |
| **4** | REST Memory Telemetry Endpoint | `loopbox/server.py` | `test_tier1_r1_rest_memory_endpoint_and_websocket_broadcast` | Tier 1 |
| **5** | WebSocket Memory Pressure Broadcast | `loopbox/stage_sync_hub.py` | `test_tier1_r1_rest_memory_endpoint_and_websocket_broadcast` | Tier 1 |
| **6** | 64-Bit Desktop Working Set Trim Bug Fix | `loopbox/desktop.py` | `test_tier1_r1_desktop_bridge_memory_and_trim` | Tier 1 |
| **7** | Desktop Shell IPC & Direct Bridge | `loopbox/desktop.py` | `test_tier1_r1_desktop_bridge_memory_and_trim` | Tier 1 |
| **8** | Adaptive Loader Cache Limits | `web/js/api.js` | `test_tier1_r2_loader_buffer_eviction_and_vocals_accounting` | Tier 1 |
| **9** | Vocal Stem Buffer Byte Accounting | `web/js/api.js` | `test_tier1_r2_loader_buffer_eviction_and_vocals_accounting` | Tier 1 |
| **10** | WebAudio Allocation Strain Signal | `web/js/api.js` | `test_tier1_r2_prefetch_shield_removal_and_webaudio_strain_signal` | Tier 1 |
| **11** | Universal Transition Buffer Eviction | `web/js/player.js` | `test_tier1_r2_timeline_pruning` | Tier 1 |
| **12** | Prefetch Eviction Shield Removal | `web/js/main.js` | `test_tier1_r2_prefetch_shield_removal_and_webaudio_strain_signal` | Tier 1 |
| **13** | WebAudio Voice Teardown Consolidation | `web/js/engine.js` | `test_tier1_r2_voice_audio_node_disconnection` | Tier 1 |
| **14** | Signalsmith & Loop Node Disconnection | `web/js/engine.js` | `test_tier1_r2_voice_audio_node_disconnection` | Tier 1 |
| **15** | Runtime GC Triggering | `web/js/main.js` | `test_tier1_r2_prefetch_shield_removal_and_webaudio_strain_signal` | Tier 1 |
| **16** | 1x1 Pixel Ring Canvas Disposal | `web/js/viz.js` | `test_tier1_r3_dispose_ring_sets_1x1_dimensions` | Tier 1 |
| **17** | Satellite Idle Ring Disposal Fix | `web/js/viz.js` | `test_tier1_r3_satellite_idle_ring_and_lemniscate_disposal` | Tier 1 |
| **18** | Canvas Context Loss & Recovery Guarding | `web/js/viz.js` | `test_tier2_bc3_canvas_context_loss_and_restoration` | Tier 2 |
| **19** | Adaptive Visualizer Canvas Scaling | `web/js/viz.js` | `test_tier1_r3_rings_cap_and_idle_layer_vram_limit` | Tier 1 |
| **20** | Visualizer Hysteresis Reconstruction | `web/js/viz.js` | `test_tier3_x2_full_pressure_lifecycle_hysteresis` | Tier 3 |
| **21** | Lemniscate Idle Layer Disposal | `web/js/viz.js` | `test_tier1_r3_satellite_idle_ring_and_lemniscate_disposal` | Tier 1 |
| **22** | Automated Memory Lifecycle Test Suite | `tests/test_memory_lifecycle.py` | Full 21-test executable suite (Tiers 1–4) | All |
| **23** | Stage Sync Test Assertion Alignment | `tests/test_stage_sync.py:332` | Line 332 aligned to `const maxKeep = 2;` | Regression |
| **24** | Long Track Test Assertion Alignment | `tests/test_long_track_playback.py:210` | Line 210 aligned to `assert.equal(t1.buffer, null)` | Regression |
| **25** | E2E Test Infra & Certification Artifacts | Project Root | `TEST_INFRA.md` & `TEST_READY.md` published | Docs |

---

## 5. Granular Test Case Index

### Tier 1: Feature Coverage (Unit & Subsystem Lifecycle)
1. `test_tier1_r1_backend_win32_ctypes_query`: Win32 ctypes / POSIX memory query returns valid metrics within <10ms.
2. `test_tier1_r1_threshold_state_classification_and_hysteresis`: 3-tier hysteresis state machine classifies Normal, High, and Critical with dwell time.
3. `test_tier1_r1_rest_memory_endpoint_and_websocket_broadcast`: REST GET /api/system/memory and WebSocket broadcast relay telemetry.
4. `test_tier1_r1_desktop_bridge_memory_and_trim`: DesktopBridge memory status query and 64-bit safe EmptyWorkingSet trim.
5. `test_tier1_r2_loader_buffer_eviction_and_vocals_accounting`: Loader dynamic limits, stem accounting, and buffer nulling on eviction.
6. `test_tier1_r2_prefetch_shield_removal_and_webaudio_strain_signal`: WebAudio strain signal, prefetch eviction shield removal, and runtime GC triggering.
7. `test_tier1_r2_timeline_pruning`: player.timeline stays bounded <= 40 events and purges old history past 5s.
8. `test_tier1_r2_voice_audio_node_disconnection`: Voice.dispose() invokes _free() and disconnects all 20+ WebAudio nodes.
9. `test_tier1_r3_dispose_ring_sets_1x1_dimensions`: viz._disposeRing(ring) sets 1x1 dimensions to immediately reclaim GPU textures.
10. `test_tier1_r3_rings_cap_and_idle_layer_vram_limit`: Ring cap enforcement and idle layer width <= 1920px VRAM cap.
11. `test_tier1_r3_satellite_idle_ring_and_lemniscate_disposal`: Satellite idle fading ring disposal and lemniscate idle layer disposal.
12. `test_tier1_same_machine_speaker_sync_relay`: StageSyncHub same-machine speaker sync arbitration.

### Tier 2: Boundary & Corner Cases (Stress & Resilience)
13. `test_tier2_bc1_critical_pressure_spike_mid_transition`: Critical pressure spike mid-transition sheds secondary ring and evicts non-playing buffers.
14. `test_tier2_bc2_rapid_10_track_skip_stress`: 10 rapid track skips in quick succession leave zero orphaned rings or canvas leaks.
15. `test_tier2_bc3_canvas_context_loss_and_restoration`: Canvas context loss pauses rendering safely and restored event reconstructs stage.
16. `test_tier2_bc4_zero_bounding_box_resilience`: Zero parent bounding box clamps to >= 200px and does not crash render loop.
17. `test_tier2_bc5_60_minute_track_memory_stability`: 60-minute track is supported without memory blowup, while >15m stems are omitted.

### Tier 3: Cross-Feature Interactions (Ecosystem)
18. `test_tier3_x1_cluster_stage_mirror_under_critical_pressure`: Cluster follower in stage mirror mode scales down under Critical memory pressure.
19. `test_tier3_x2_full_pressure_lifecycle_hysteresis`: Lifecycle Normal -> High -> Critical -> Normal verifies 4s dwell before SSAA recovery.
20. `test_tier3_x3_active_mic_and_recording_protection`: Active KaraokeMic and MixRecorder nodes remain protected while idle track cache is purged.

### Tier 4: Real-World Acceptance Scenario
21. `test_tier4_30_track_continuous_cycle_acceptance`: 30-track continuous automated playback cycle in headless Microsoft Edge asserting:
    - Stable JS heap footprint (< 400 MB).
    - Zero unhandled browser page errors.
    - Zero canvas freezes (`viz._inFrame === false`).
    - Active visualizer stage rendering (non-transparent pixel validation).

---

## 6. Regression Alignment Specifications

1. **`tests/test_stage_sync.py:332`**:
   - Reconciled static test assertion to match `web/js/api.js`:
     ```python
     assert "const maxKeep = 2;" in api_js
     ```
   - Confirms that cache retention on desktop and mobile web is unified to 2 tracks to eliminate commit memory spikes.

2. **`tests/test_long_track_playback.py:210`**:
   - Reconciled buffer nulling assertion to match R2 float PCM memory reclamation:
     ```javascript
     assert.equal(t1.buffer, null, "Evicted unprotected track t1.buffer must be nulled out to reclaim float PCM memory!");
     ```
   - Confirms that while live/pinned tracks retain their buffer, evicted unprotected tracks have their buffer property nulled out to release RAM.

---

## 7. Execution Guide

Run all tests via PowerShell from project root (`d:\JOB\DEV\MashLoop`):

```powershell
# 1. Memory Lifecycle 4-Tier Test Suite
.\.venv\Scripts\python.exe -m unittest tests/test_memory_lifecycle.py -v

# 2. Stage Sync & Light Telemetry Regression Suite
.\.venv\Scripts\python.exe tests/test_stage_sync.py

# 3. Long Track Playback & Range Streaming Regression Suite
.\.venv\Scripts\python.exe -m unittest tests/test_long_track_playback.py -v

# 4. Tab Stability Regression Suite
.\.venv\Scripts\python.exe tests/test_tab_stability.py

# 5. Responsive Deck Layout & Touch Bridge Verification
.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py

# 6. Cluster Synchronization Regression Suite
.\.venv\Scripts\python.exe -m unittest tests/test_cluster_sync.py -v

# 7. Visualizer Render & OOM E2E Suite
.\.venv\Scripts\python.exe tests/test_viz_render_and_oom_e2e.py
```
