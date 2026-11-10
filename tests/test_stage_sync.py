import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unittest.mock import patch
from fastapi.testclient import TestClient
from loopbox.server import app
from loopbox.smart_lights import oklch_to_led_rgb, oklch_to_srgb, smart_lights


def test_oklch_to_srgb_conversion():
    # Pure white / black / primary colors
    r, g, b = oklch_to_srgb(0.0, 0.0, 0)
    assert r == 0 and g == 0 and b == 0

    r, g, b = oklch_to_srgb(1.0, 0.0, 0)
    assert r >= 250 and g >= 250 and b >= 250

    # Test warm amber
    r, g, b = oklch_to_srgb(0.8, 0.12, 40)
    assert 0 <= r <= 255
    assert 0 <= g <= 255
    assert 0 <= b <= 255
    assert r > b  # Warm hue has high red compared to blue


def test_sync_room_info_endpoint():
    client = TestClient(app)
    resp = client.get("/api/sync/room-info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "room_id" in data
    assert "satellite_url" in data
    assert "satellites_count" in data


def test_smart_lights_endpoints():
    client = TestClient(app)
    with patch.object(smart_lights.tuf_driver, "set_rgb", return_value=True), \
         patch.object(smart_lights, "_save_persisted_devices"):
        # 1. Status
        st = client.get("/api/lights/status").json()
        assert "enabled" in st
        assert "wled_ip" in st

        # 2. Config
        cfg_resp = client.post("/api/lights/config", json={
            "enabled": True,
            "wled_ip": "192.168.1.99",
            "brightness": 1.2,
            "keyboard_sync": True
        })
        assert cfg_resp.status_code == 200
        assert cfg_resp.json()["wled_ip"] == "192.168.1.99"
        assert cfg_resp.json()["brightness"] == 1.2

        # 3. Test color
        test_resp = client.post("/api/lights/test", json={"r": 255, "g": 100, "b": 50})
        assert test_resp.status_code == 200
        assert test_resp.json()["rgb"] == [255, 100, 50]
        smart_lights.wled_ip = ""
        smart_lights.devices.pop("manual:wled_ddp:192.168.1.99:4048", None)


def test_dual_color_transition_sync():
    with patch.object(smart_lights.tuf_driver, "set_rgb", return_value=True), \
         patch.object(smart_lights, "_save_persisted_devices"):
        # Test dual-color processing in smart lights
        smart_lights.configure({
            "enabled": True,
            "keyboard_sync": True,
            "wled_ip": "127.0.0.1",
            "wled_led_count": 30
        })

        # Telemetry during transition: Song A (Red hue 30) -> Song B (Cyan hue 200)
        telemetry = {
            "type": "telemetry",
            "track_id": "song_a",
            "title": "Song A",
            "mode": "ring",
            "acc": [0.8, 0.15, 115],  # 50% blend hue
            "acc2": [0.75, 0.14, 200], # Song B
            "color_a": [0.85, 0.16, 30], # Song A (warm/red)
            "color_b": [0.75, 0.14, 200], # Song B (cool/cyan)
            "is_transitioning": True,
            "progress": 0.5,
            "pulse": 0.8,
            "bass": 0.5
        }

        smart_lights.process_telemetry(telemetry)
        # Verify that color was processed and last_rgb was updated
        r, g, b = smart_lights.last_rgb
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255
        smart_lights.wled_ip = ""
        smart_lights.devices.pop("manual:wled_ddp:127.0.0.1:4048", None)


def test_websocket_stage_sync():
    client = TestClient(app)
    with patch.object(smart_lights.tuf_driver, "set_rgb", return_value=True):
        # Test host and satellite connection
        with client.websocket_connect("/api/ws/stage-sync?role=host") as host_ws:
            with client.websocket_connect("/api/ws/stage-sync?role=satellite") as sat_ws:
                first_msg = sat_ws.receive_json()
                assert "type" in first_msg

                # Host emits telemetry with dual-song metadata
                telemetry_data = {
                    "type": "telemetry",
                    "track_id": "test_track",
                    "title": "Ngược Lối Yêu",
                    "artist": "Vicky Nhung",
                    "mode": "ring",
                    "acc": [0.82, 0.14, 45],
                    "acc2": [0.75, 0.12, 180],
                    "color_a": [0.82, 0.14, 45],
                    "color_b": [0.75, 0.12, 180],
                    "is_transitioning": True,
                    "progress": 0.35,
                    "ground": [40, 0.012],
                    "fill_a": 0.3,
                    "pulse": 0.95,
                    "bass": 0.6,
                    "peak": 0.8,
                    "angle": 3.14,
                    "bpm": 128
                }
                host_ws.send_json(telemetry_data)

                # Satellite receives telemetry
                received = None
                for _ in range(5):
                    m = sat_ws.receive_json()
                    if m.get("type") == "telemetry" and m.get("track_id") == "test_track":
                        received = m
                        break
                assert received is not None
                assert received["type"] == "telemetry"
                assert received["track_id"] == "test_track"
                assert received["title"] == "Ngược Lối Yêu"
                assert received["is_transitioning"] is True
                assert received["color_b"] == [0.75, 0.12, 180]

                # Satellite sends command back to host
                sat_ws.send_json({"type": "command", "action": "pause"})
                cmd_received = None
                for _ in range(15):
                    m = host_ws.receive_json()
                    if m.get("type") == "command":
                        cmd_received = m
                        break
                assert cmd_received is not None
                assert cmd_received["action"] == "pause"


def test_satellite_viz_loop_resilience():
    viz_js = Path("web/js/viz.js").read_text(encoding="utf-8")
    stage_sync_js = Path("web/js/stage_sync.js").read_text(encoding="utf-8")
    app_css = Path("web/css/app.css").read_text(encoding="utf-8")

    # 1. Must never have unsafe `ring?.track.id` that throws TypeError when ring has no track
    assert "ring?.track.id" not in viz_js, "Unsafe ring?.track.id found in viz.js"
    assert "ring?.track?.id" in viz_js, "Missing safe ring?.track?.id in _placeCenter"

    # 2. RAF loop must be guarded by try/finally so requestAnimationFrame(loop) never dies
    assert "try {\n        this._frame(now);\n      } catch (err) {" in viz_js
    assert "} finally {\n        requestAnimationFrame(loop);\n      }" in viz_js

    # 3. Satellite telemetry must stamp _recvAt and interpolate angle smoothly at 60/120 FPS
    assert "data._recvAt =" in stage_sync_js
    assert "t._recvAt" in viz_js

    # 4. No per-beat concentric target ripples (_lastSatBeat) or protruding rectangular beat peg
    assert "_lastSatBeat" not in viz_js, "Per-beat concentric ripple bullseye (_lastSatBeat) must not exist"
    assert "th + (full ? 5 : 2)" not in viz_js, "Protruding rectangular beat peg in _drawHead must not exist"
    assert "_satSmoothAng" in viz_js, "Missing PLL smoothed playhead angle on Satellite"

    # 5. Unified .deck & Host configuration sync (viz_scale, ui_scale, glow, keep, neon field)
    assert "viz_scale:" in viz_js, "Host telemetry must broadcast viz_scale"
    assert "ui_scale:" in viz_js, "Host telemetry must broadcast ui_scale"
    assert "const isPaused = !this.player?.playing;" in viz_js, "Host telemetry must use !this.player?.playing for pause state"
    assert "this.player?.paused" not in viz_js, "Non-existent this.player?.paused must not be used in viz.js"
    assert "this._drawIdle(ctx, now, this.idle);" in viz_js, "Satellite idle stage must draw the infinity lemniscate"
    assert "this.viz.setScale(data.viz_scale)" in stage_sync_js, "Satellite must apply viz_scale"
    assert "theme.applyPage(primary, second" in stage_sync_js, "Satellite must call theme.applyPage for neon glow sync"
    assert "satellite-deck" not in stage_sync_js, "Legacy .satellite-deck must be replaced by unified .deck"
    assert "body.is-satellite-mode .deck {\n  display: inline-flex !important;" in app_css, "Unified .deck must be visible on Satellite"
    assert 'body.is-satellite-mode .ring-center[data-mode="idle"]' in app_css, "Idle caption positioning under infinity loop must be styled on Satellite"
    assert "background: transparent !important;" in app_css, "Satellite body must be transparent to show .field neon lights"
    assert "const coreGlowR = (full ? 6.5 : 4.2)" in viz_js, "_drawHead must use ring.r-independent corona radius"
    assert "this.bands[i] = t.bands[i];" in viz_js, "Satellite must copy Host spectrum bands 1:1 without damping"
    assert "rc_kicker_html:" in viz_js, "Host telemetry must broadcast rc_kicker_html"
    assert "rc_title_html:" in viz_js, "Host telemetry must broadcast rc_title_html"
    assert "rc_meta_html:" in viz_js, "Host telemetry must broadcast rc_meta_html"
    assert "rcKicker.innerHTML = data.rc_kicker_html" in stage_sync_js, "Satellite must sync rc_kicker_html 1:1 from Host"
    assert "rcTitle.innerHTML = data.rc_title_html" in stage_sync_js, "Satellite must sync rc_title_html 1:1 from Host"
    assert "rcMeta.innerHTML = data.rc_meta_html" in stage_sync_js, "Satellite must sync rc_meta_html 1:1 from Host"
    assert "ĐỒNG BỘ VỆ TINH" not in stage_sync_js, "Satellite must not override #rc-kicker with custom text"
    assert "Array.from(this.player.plan.jumps)" in viz_js, "Host must serialize Map plan.jumps via Array.from()"
    assert "placeholder: this.placeholder ? { id: this.placeholder.id } : null" in viz_js, "Host must broadcast placeholder state"
    assert "this._drawPlaceholder(ctx, { id: t.placeholder?.id || t.second.id, ...L.b }, now)" in viz_js, "Satellite must draw dashed placeholder when Host is loading next track"
    assert "lead_head:" in viz_js and "ghost_head:" in viz_js, "Host must broadcast lead_head and ghost_head for dual-playhead blend parity"
    sat_body = viz_js.split("_drawSatelliteStage(ctx, now, t")[1].split("_drawSatelliteHead")[0]
    assert "⇄" not in sat_body, "Satellite must not draw mismatched Camelot badge over crossing"
    assert "satellitePrimaryRing" not in sat_body, "Satellite must use unified this.rings state machine instead of static satellitePrimaryRing"
    assert 'if (before) before.role = "leaving";' in sat_body, "Satellite must mark previous ring as leaving during song transitions"
    assert 'ring.role === "leaving" || ring.role === "fading"' in sat_body, "Satellite must animate leaving and fading rings"
    assert "_prefetchCandidateTransitions" in stage_sync_js, "Satellite must pre-fetch candidate transition tracks"
    assert "setBeatPulse(enabled)" in viz_js, "Viz must provide setBeatPulse(enabled) method"
    assert "beat_pulse: this.beatPulse !== false" in viz_js, "Host telemetry must broadcast beat_pulse state"
    assert "this.viz.setBeatPulse(data.beat_pulse)" in stage_sync_js, "Satellite must sync beat_pulse from Host"
    assert "ring._layoutR * (1 + pulseAmt)" in viz_js, "Both Host and Satellite must pulse ring.r around ring._layoutR"
    index_html = Path("web/index.html").read_text(encoding="utf-8")
    main_js = Path("web/js/main.js").read_text(encoding="utf-8")
    assert 'id="s-beat-pulse"' in index_html, "Settings panel must contain #s-beat-pulse toggle"
    assert "#s-beat-pulse" in main_js and "viz.setBeatPulse" in main_js, "main.js must wire #s-beat-pulse to viz.setBeatPulse"


def test_satellite_audio_binary_relay():
    client = TestClient(app)
    with client.websocket_connect("/api/ws/stage-sync?role=host") as host_ws:
        with client.websocket_connect("/api/ws/stage-sync?role=satellite") as sat_ws:
            _ = sat_ws.receive_json()  # initial telemetry or sync_status
            # Satellite subscribes to multi-room audio stream
            sat_ws.send_json({"type": "audio_subscribe", "enabled": True})
            info = client.get("/api/sync/room-info").json()
            assert info["audio_satellites_count"] >= 1

            # Host streams binary Int16 PCM packet ("ML" header + payload)
            pcm_packet = b"ML\x01\x02\x22\x56\x00\x00" + (b"\x10\x00\xf0\xff" * 64)
            host_ws.send_bytes(pcm_packet)
            got_bytes = None
            for _ in range(8):
                msg = sat_ws.receive()
                if msg.get("bytes"):
                    got_bytes = msg["bytes"]
                    break
            assert got_bytes == pcm_packet

            # Host sends remote control to disable satellite audio
            host_ws.send_json({"type": "satellite_audio_control", "enabled": False, "latency_ms": 95})
            ctrl_msg = None
            for _ in range(8):
                msg = sat_ws.receive()
                if msg.get("text"):
                    parsed = __import__("json").loads(msg["text"])
                    if parsed.get("type") == "satellite_audio_control":
                        ctrl_msg = parsed
                        break
            assert ctrl_msg is not None
            assert ctrl_msg["enabled"] is False
            assert ctrl_msg["latency_ms"] == 95


def test_lyrics_endpoints_and_lrc_parser():
    import tempfile
    from loopbox import library
    from loopbox.server import _clean_song_query, _parse_lrc_lines

    parsed = _parse_lrc_lines("[00:12.50] Dong thu hai\n[00:05.100][01:00.0] Diep khuc\nInvalid line")
    assert [round(x["t"], 2) for x in parsed] == [5.1, 12.5, 60.0]
    assert parsed[0]["text"] == "Diep khuc"

    queries = _clean_song_query("Nua Trai Tim (DJ Remix) x Khong Danh [Ver 2]", "Official Channel")
    assert queries and "Remix" not in queries[0]

    tid = "testLyric01"
    orig_read = library.read_meta
    orig_dir = library.track_dir
    with tempfile.TemporaryDirectory() as tmp:
        tpath = Path(tmp) / tid
        tpath.mkdir(parents=True, exist_ok=True)
        library.read_meta = lambda k: {"id": tid, "title": "Bai Hat Test", "artist": "Ca Si", "duration": 180} if k == tid else orig_read(k)
        library.track_dir = lambda k: tpath if k == tid else orig_dir(k)
        try:
            client = TestClient(app)
            bad_resp = client.get("/api/tracks/invalid!id/lyrics")
            assert bad_resp.status_code == 404

            save_resp = client.post(f"/api/tracks/{tid}/lyrics", json={"lrc": "[00:04.00] Hello loop\n[00:08.50] Second line"})
            assert save_resp.status_code == 200
            saved = save_resp.json()
            assert saved["found"] is True
            assert saved["source"] == "custom"
            assert len(saved["synced"]) == 2

            get_resp = client.get(f"/api/tracks/{tid}/lyrics")
            assert get_resp.status_code == 200
            cached = get_resp.json()
            assert cached["found"] is True
            assert cached["synced"][1]["t"] == 8.5

            clr_resp = client.post(f"/api/tracks/{tid}/lyrics", json={"lrc": "   "})
            assert clr_resp.status_code == 200
            assert clr_resp.json()["found"] is False
            assert clr_resp.json()["source"] == "cleared"
        finally:
            library.read_meta = orig_read
            library.track_dir = orig_dir


def test_v164_features_and_security_gates():
    import re
    index_html = Path("web/index.html").read_text(encoding="utf-8")
    main_js = Path("web/js/main.js").read_text(encoding="utf-8")
    player_js = Path("web/js/player.js").read_text(encoding="utf-8")
    api_js = Path("web/js/api.js").read_text(encoding="utf-8")
    viz_js = Path("web/js/viz.js").read_text(encoding="utf-8")
    stage_sync_js = Path("web/js/stage_sync.js").read_text(encoding="utf-8")

    # Multi-room satellite audio controls wired
    for eid in ['id="btn-sat-audio"', 'id="btn-toggle-sat-audio"', 'id="s-sat-latency"', 'id="s-sat-local-vol"']:
        assert eid in index_html, f"Missing {eid}"
    assert "initStageSyncControls({ player, engine })" in main_js
    assert "attachHostEngine(" in stage_sync_js and "handleAudioPacket(" in stage_sync_js

    # F6 Synced Ambient Lyrics
    for eid in ['id="ambient-lyrics"', 'id="s-lyrics"', 'id="zen-btn-lyrics"', 'id="modal-lyrics-editor"']:
        assert eid in index_html, f"Missing {eid}"
    assert "lyrics_enabled:" in viz_js and "lyric_cur:" in viz_js
    assert "getAudibleSongTime()" in player_js

    # F7 Session Setlist & M3U8 Exporter
    for eid in ['id="btn-export-setlist"', 'id="zen-btn-setlist"', 'id="modal-setlist-export"', 'id="btn-dl-setlist-m3u"']:
        assert eid in index_html, f"Missing {eid}"
    assert "sessionSetlist" in player_js
    assert "#EXTM3U" in main_js and "#EXTINF:" in main_js

    # F8 Smart Pre-buffer (Desktop upgrade while keeping Mobile RAM caps)
    assert "const maxKeep = isMobile ? 2 : 3;" in api_js
    assert "const maxPrefetch = IS_MOBILE ? 1 : 2;" in player_js
    assert "const PREFETCH_LEAD = IS_MOBILE ? 20 : 28;" in player_js

    # Security / UX gates: zero native dialog calls in app code
    for js_txt in (main_js, player_js, api_js, viz_js, stage_sync_js):
        assert not re.search(r"(?<!\.)\bconfirm\s*\(", js_txt)
        assert not re.search(r"(?<!\.)\bprompt\s*\(", js_txt)

    # Anti-flicker invariants (v165):
    # 1. Satellite _frame() measures parentElement box, NOT window.innerHeight (prevents 60Hz canvas buffer wipe)
    frame_body = viz_js.split("_frame(now) {")[1].split("const view = this.player.audible()")[0]
    assert "this.canvas.parentElement" in frame_body, "Satellite _frame() must measure canvas.parentElement box"
    assert "window.innerHeight" not in frame_body, "Satellite _frame() must NOT compare box height against window.innerHeight"
    # 2. _resize() short-circuits when dimensions & DPR match
    resize_body = viz_js.split("_resize() {")[1].split("// Where the loops sit:")[0]
    assert "this.canvas.width === pxW" in resize_body and "return;" in resize_body, "_resize() must guard against redundant buffer clears"
    # 3. _broadcastHostTelemetry checks _switchingTrack and player.js resumes AudioContext before reset()
    assert "_switchingTrack" in player_js and "_switchingTrack" in viz_js, "player.js & viz.js must guard mid-switch track telemetry"
    start_body = player_js.split("async start(trackId)")[1].split("async pause()")[0]
    assert start_body.index("this.engine.ctx.resume()") < start_body.index("this.reset()"), "AudioContext.resume() must precede this.reset()"
    # 4. StageSync holds transient idle blips briefly & uses forward-only app_ver check
    assert "_idleConfirmTimer" in stage_sync_js, "stage_sync.js must debounce transient idle blips"
    assert "remoteVerNum > LOCAL_APP_VER" in stage_sync_js, "stage_sync.js must only auto-reload on strictly newer server versions"
    # 5. main.js prevents applySettings() from overwriting Satellite state
    apply_body = main_js.split("function applySettings() {")[1].split("const s = player.settings;")[0]
    assert "if (stageSync.isSatellite) return;" in apply_body, "applySettings() must bail out in Satellite mode"


def test_multi_host_arbitration():
    import time
    from loopbox.stage_sync_hub import sync_hub

    sync_hub.hosts.clear()
    sync_hub.satellites.clear()
    sync_hub.audio_satellites.clear()
    sync_hub.active_host = None
    sync_hub.host_last_playing.clear()
    sync_hub.host_last_seen.clear()

    client = TestClient(app)
    with client.websocket_connect("/api/ws/stage-sync?role=host") as host1_ws:
        with client.websocket_connect("/api/ws/stage-sync?role=satellite") as sat_ws:
            sat_ws.send_json({"type": "audio_subscribe", "enabled": True})
            with client.websocket_connect("/api/ws/stage-sync?role=host") as host2_ws:
                info = client.get("/api/sync/room-info").json()
                assert info["hosts_count"] >= 2

                # 1. Host 1 starts actively playing -> claims active_host
                host1_ws.send_json({
                    "type": "telemetry",
                    "track_id": "song_primary",
                    "title": "Primary Track",
                    "mode": "ring",
                    "progress": 0.1,
                    "bpm": 128,
                })

                # Drain initial messages until song_primary arrives
                got_start = False
                for _ in range(10):
                    m = sat_ws.receive_json()
                    if m.get("type") == "telemetry" and m.get("track_id") == "song_primary":
                        got_start = True
                        break
                assert got_start

                # 2. Secondary idle/paused host2 attempts to spam idle & paused frames -> MUST be dropped
                host2_ws.send_json({
                    "type": "telemetry",
                    "track_id": None,
                    "title": "",
                    "mode": "idle",
                })
                host2_ws.send_json({
                    "type": "telemetry",
                    "track_id": "song_stale",
                    "title": "Stale Paused",
                    "mode": "paused",
                })

                # Marker packet from Host 1 right after -> FIFO order proves zero idle/stale packets leaked
                host1_ws.send_json({
                    "type": "telemetry",
                    "track_id": "song_primary",
                    "title": "Primary Track",
                    "mode": "ring",
                    "progress": 0.42,
                    "bpm": 128,
                })
                seen_idle_or_stale = []
                got_marker = False
                for _ in range(10):
                    m = sat_ws.receive_json()
                    if m.get("type") == "telemetry":
                        if m.get("mode") == "idle" or m.get("track_id") == "song_stale":
                            seen_idle_or_stale.append(m)
                        if m.get("track_id") == "song_primary" and m.get("progress") == 0.42:
                            got_marker = True
                            break
                assert got_marker
                assert not seen_idle_or_stale, f"Competing host leaked telemetry: {seen_idle_or_stale}"

                # 3. Binary audio packets from non-active host2 must also be dropped
                # Ensure sat_ws audio_subscribe has been processed before streaming PCM frames
                for _ in range(10):
                    if client.get("/api/sync/room-info").json().get("audio_satellites_count", 0) >= 1:
                        break
                    time.sleep(0.01)
                bad_pcm = b"ML\x01\x02\x22\x56\x00\x00" + b"\x00\x00" * 16
                good_pcm = b"ML\x01\x02\x22\x56\x00\x00" + b"\x11\x22" * 16
                host2_ws.send_bytes(bad_pcm)
                host1_ws.send_bytes(good_pcm)
                got_pcm = None
                for _ in range(8):
                    msg = sat_ws.receive()
                    if msg.get("bytes") is not None:
                        got_pcm = msg["bytes"]
                        break
                assert got_pcm == good_pcm, "Binary audio must only forward from active_host"

                # 3b. Satellite playback commands route ONLY to active_host (never waking idle secondary host2)
                sat_ws.send_json({"type": "command", "action": "toggle_pause"})
                got_cmd_h1 = False
                for _ in range(20):
                    m = host1_ws.receive_json()
                    if m.get("type") == "command" and m.get("action") == "toggle_pause":
                        got_cmd_h1 = True
                        break
                assert got_cmd_h1, "Active host must receive satellite command"
                sat_ws.send_json({"type": "audio_subscribe", "enabled": True})
                h2_cmds = []
                for _ in range(8):
                    m = host2_ws.receive_json()
                    if m.get("type") == "command":
                        h2_cmds.append(m)
                    if m.get("type") == "sync_status":
                        break
                assert not h2_cmds, f"Idle secondary host must not receive satellite commands: {h2_cmds}"

                # 4. If host1 pauses, secondary host2 playing after >0.45s promotes smoothly
                host1_ws.send_json({
                    "type": "telemetry",
                    "track_id": "song_primary",
                    "title": "Primary Track",
                    "mode": "paused",
                })
                time.sleep(0.5)
                host2_ws.send_json({
                    "type": "telemetry",
                    "track_id": "song_two",
                    "title": "Second Host Track",
                    "mode": "ring",
                    "progress": 0.2,
                })
                got_takeover = False
                for _ in range(10):
                    m = sat_ws.receive_json()
                    if m.get("type") == "telemetry" and m.get("track_id") == "song_two":
                        got_takeover = True
                        break
                assert got_takeover, "Second active host should take over after active host stops/pauses >0.45s"

            # When active host2 exits cleanly, remaining host1 is idle -> satellite receives idle reset
            got_idle_reset = False
            for _ in range(10):
                m = sat_ws.receive_json()
                if m.get("type") == "telemetry" and m.get("mode") == "idle":
                    got_idle_reset = True
                    break
            assert got_idle_reset, "Closing authoritative active host must reset satellite to idle"


def test_v166_calm_docking_and_pulse_continuity():
    """Verify v166 fixes for circle size pumping & beat pulse interruption during next-song search."""
    from pathlib import Path
    viz_js = Path("web/js/viz.js").read_text(encoding="utf-8")
    player_js = Path("web/js/player.js").read_text(encoding="utf-8")
    app_css = Path("web/css/app.css").read_text(encoding="utf-8")

    # 1. Viz only docks the 2-ring infinity layout once next track is confirmed ready (or picked by user)
    assert "const DOCK_LEAD_S =" in viz_js, "Missing DOCK_LEAD_S threshold for calm docking"
    assert "p.plan.target && p.plan.ready && (p.urgent || etaLeft <= DOCK_LEAD_S)" in viz_js, (
        "Automatic plan must not shrink primary ring until target audio/stems/stretch are ready within DOCK_LEAD_S"
    )
    assert "this._prewarmLayer(p.plan.target)" in viz_js, "Must silently prewarm next track layer before docking"
    assert "this._twoHoldUntil" in viz_js, "Must apply layout hysteresis guard to prevent two<->one pumping"
    assert "const kLayout =" in viz_js, "Must separate gentle kLayout easing from beat pulse"

    # 2. _buildLayer must cap canvas dimensions <= 2048 and batch draw calls to prevent rAF stalls
    assert "2048 / S" in viz_js, "_buildLayer must cap offscreen texture dimension <= 2048px"
    assert "CHORD_BUCKETS" in viz_js and "faintChords" in viz_js, "_buildLayer must batch chord strokes"
    assert "loPts" in viz_js and "hiPts" in viz_js, "_buildLayer must batch dust particle fills"

    # 3. Player must track destination-level failures/slow loads and sum full lead-time budget
    assert "_failedTrackUntil" in player_js and "_slowTrackUntil" in player_js, (
        "Player must track track-level failed/slow cooldowns so broken tracks are not re-picked on next beat"
    )
    assert "if (arrival < loadLead + prepLead + bendLead) continue;" in player_js, (
        "Planner must sum download + stem/stretch prep + tempo ramp lead times"
    )
    assert "tr._cooldownUntil" in player_js, "Unready triggers must get a cooldown before retry"

    # 4. .next readout box must lock 2-line height so long track names cannot resize .canvas-wrap
    assert "max-height: 3.1em;" in app_css and "-webkit-line-clamp: 2;" in app_css, (
        ".next status bar must clamp height to 2 lines so stage canvas never resizes/invalidates"
    )


def test_v168_mobile_satellite_audio_and_popover_css():
    """Verify v168 mobile satellite audio iOS unlock + resampling + popover CSS layout & slider --v sync."""
    from pathlib import Path
    stage_sync_js = Path("web/js/stage_sync.js").read_text(encoding="utf-8")
    app_css = Path("web/css/app.css").read_text(encoding="utf-8")

    # 1. iOS Safari hardware silent-switch & gesture unlock
    assert "_initSatSilenceAnchor(" in stage_sync_js and "/audio/silence.mp3" in stage_sync_js, (
        "Satellite audio must play /audio/silence.mp3 anchor to bypass iOS hardware Silent Switch"
    )
    assert "_unlockSatAudio(" in stage_sync_js and "navigator.audioSession" in stage_sync_js, (
        "Satellite audio must set navigator.audioSession.type='playback' and unlock WebAudio synchronously"
    )
    assert "_schedulePcmPacket(" in stage_sync_js and "_pendingAudioPackets" in stage_sync_js, (
        "Satellite audio must queue/resample PCM packets cleanly across hardware sample rates"
    )

    # 2. Slider --v custom property updates in _updateSatelliteAudioUI
    assert 'volSlider.style.setProperty("--v"' in stage_sync_js, "Volume slider must update --v fill percentage"
    assert 'latSlider.style.setProperty("--v"' in stage_sync_js, "Latency slider must update --v fill percentage"

    # 3. Mobile centered popover & single-line header/badge CSS
    assert ".sat-audio-popover .mic-popover__title" in app_css and "white-space: nowrap;" in app_css
    assert ".sat-audio-popover .mic-popover__badge.is-on" in app_css
    assert ".sat-audio-wrap.is-active" in app_css


def test_v169_dynamic_light_discovery_and_manual_connect():
    """Verify v169 zero-hardcoded light devices in HTML + dynamic hardware/LAN discovery + manual connect CRUD."""
    from pathlib import Path
    from unittest.mock import patch

    index_html = Path("web/index.html").read_text(encoding="utf-8")
    pane_lights = index_html.split('id="pane-lights"')[1].split("</dialog>")[0]
    assert "ASUS TUF" not in pane_lights and "TUF Gaming" not in pane_lights, (
        "pane-lights HTML must NOT hardcode ASUS TUF Gaming"
    )
    assert 'id="lights-devices-list"' in pane_lights
    assert 'id="btn-scan-lights"' in pane_lights
    assert 'id="btn-add-light-device"' in pane_lights

    # Simulate a machine WITHOUT ASUS ATKACPI driver -> hw:asus_acpi must NOT appear
    with patch.object(smart_lights.tuf_driver, "reprobe", return_value=False):
        smart_lights.tuf_driver.available = False
        devs = smart_lights.discover_devices(include_lan=False)
        assert not any(d["id"] == "hw:asus_acpi" for d in devs), (
            "Non-ASUS machine must not list hw:asus_acpi keyboard device"
        )

    # Restore real hardware probe
    smart_lights.discover_devices(include_lan=False)

    # Test manual device add -> toggle -> test flash -> remove via REST API
    client = TestClient(app)
    with patch.object(smart_lights.tuf_driver, "set_rgb", return_value=True) as mock_kbd, \
         patch.object(smart_lights, "_save_persisted_devices"):
        add_res = client.post("/api/lights/devices/add", json={
            "protocol": "wiz_udp",
            "address": "192.168.1.188",
            "port": 38899,
            "name": "Đèn bàn làm việc WiZ",
            "enabled": True,
        })
        assert add_res.status_code == 200
        st = add_res.json()
        dev_id = "manual:wiz_udp:192.168.1.188:38899"
        added = next((d for d in st["devices"] if d["id"] == dev_id), None)
        assert added is not None
        assert added["name"] == "Đèn bàn làm việc WiZ"
        assert added["enabled"] is True

        # Toggle off
        tog_res = client.post("/api/lights/devices/toggle", json={"device_id": dev_id, "enabled": False})
        assert tog_res.status_code == 200
        toggled = next((d for d in tog_res.json()["devices"] if d["id"] == dev_id), None)
        assert toggled["enabled"] is False

        # Test single-device flash -> must NOT leak onto ASUS keyboard driver
        test_res = client.post("/api/lights/test", json={"r": 50, "g": 220, "b": 100, "device_id": dev_id})
        assert test_res.status_code == 200
        assert dev_id in test_res.json()["tested_devices"]
        assert mock_kbd.call_count == 0, "Single-device test for WiZ must not overwrite ASUS keyboard RGB"

        # Remove manual device
        rem_res = client.post("/api/lights/devices/remove", json={"device_id": dev_id})
        assert rem_res.status_code == 200
        assert not any(d["id"] == dev_id for d in rem_res.json()["devices"])


def test_v170_led_color_calibration_and_satellite_sync():
    """Verify v170 linear-PWM LED color calibration (no green washout on orange songs) & Satellite ring color sync."""
    # 1. Orange / Amber songs (h = 40..72, L = 0.79..0.83) must produce pure vivid orange on physical LEDs
    for h in (40, 50.8, 60, 68.2, 72):
        r, g, b = oklch_to_led_rgb(0.80, 0.13, h, boost=1.0)
        assert r == 255, f"Expected full red for orange hue {h}, got {(r, g, b)}"
        assert 10 <= g <= 70, f"Expected calibrated orange green channel (10..70) for hue {h}, got {(r, g, b)}"
        assert b == 0, f"Expected zero blue bleed for orange hue {h}, got {(r, g, b)}"
        assert r >= g * 3.5, f"Orange hue {h} must never have green approaching red {(r, g, b)}"

    # 2. Emerald green song (h = 145) must produce vivid green
    rg, gg, bg = oklch_to_led_rgb(0.79, 0.15, 145, boost=1.0)
    assert gg == 255 and gg > rg * 4 and gg > bg * 4

    # 3. Satellite ring layer rebuilds when Host color_a / color_b changes
    viz_js = Path("web/js/viz.js").read_text(encoding="utf-8")
    assert "_buildLayer(track, forcedCol = null)" in viz_js
    assert "this._buildLayer(ring.track, satForcedCol)" in viz_js
    assert "satHueKey" in viz_js
    assert "const a = activeTrack ? theme.accentOf(activeTrack.id, activeMood) : theme.idleAccent();" in viz_js
    assert "focused:" in viz_js


if __name__ == '__main__':
    test_oklch_to_srgb_conversion()
    print('PASS: test_oklch_to_srgb_conversion')
    test_sync_room_info_endpoint()
    print('PASS: test_sync_room_info_endpoint')
    test_smart_lights_endpoints()
    print('PASS: test_smart_lights_endpoints')
    test_dual_color_transition_sync()
    print('PASS: test_dual_color_transition_sync')
    test_websocket_stage_sync()
    print('PASS: test_websocket_stage_sync')
    test_multi_host_arbitration()
    print('PASS: test_multi_host_arbitration')
    test_satellite_viz_loop_resilience()
    print('PASS: test_satellite_viz_loop_resilience')
    test_satellite_audio_binary_relay()
    print('PASS: test_satellite_audio_binary_relay')
    test_lyrics_endpoints_and_lrc_parser()
    print('PASS: test_lyrics_endpoints_and_lrc_parser')
    test_v164_features_and_security_gates()
    print('PASS: test_v164_features_and_security_gates')
    test_v166_calm_docking_and_pulse_continuity()
    print('PASS: test_v166_calm_docking_and_pulse_continuity')
    test_v168_mobile_satellite_audio_and_popover_css()
    print('PASS: test_v168_mobile_satellite_audio_and_popover_css')
    test_v169_dynamic_light_discovery_and_manual_connect()
    print('PASS: test_v169_dynamic_light_discovery_and_manual_connect')
    test_v170_led_color_calibration_and_satellite_sync()
    print('PASS: test_v170_led_color_calibration_and_satellite_sync')
    print('\nALL STAGE SYNC & LIGHT TESTS PASSED (EXIT CODE 0)!')
