import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from loopbox.cluster_discovery import ClusterBeaconManager
from loopbox.server import app
from loopbox.smart_lights import smart_lights
from loopbox.stage_sync_hub import stage_sync_hub


class TestClusterSync(unittest.TestCase):
    def setUp(self):
        stage_sync_hub.cluster_enabled = False
        stage_sync_hub.cluster_mode = "party"
        stage_sync_hub.cluster_master_id = ""
        stage_sync_hub.cluster_master_volume = 1.0
        stage_sync_hub.host_align_ms = 60.0

    def tearDown(self):
        stage_sync_hub.cluster_enabled = False
        stage_sync_hub.cluster_mode = "party"
        stage_sync_hub.cluster_master_id = ""
        stage_sync_hub.cluster_master_volume = 1.0
        stage_sync_hub.host_align_ms = 60.0

    def test_cluster_beacon_manual_peer_lifecycle(self):
        beacon = ClusterBeaconManager(port=8765)
        peer = beacon.add_manual_peer("192.168.1.88:8765", name="Loa Phòng Khách")
        self.assertIsNotNone(peer)
        self.assertEqual(peer["ip"], "192.168.1.88")
        self.assertEqual(peer["port"], 8765)
        self.assertEqual(peer["url"], "http://192.168.1.88:8765")
        self.assertEqual(peer["ws_url"], "ws://192.168.1.88:8765/api/ws/stage-sync")

        active = beacon.get_active_peers()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["name"], "Loa Phòng Khách")

        removed = beacon.remove_peer("192.168.1.88:8765")
        self.assertTrue(removed)
        self.assertEqual(len(beacon.get_active_peers()), 0)

    def test_cluster_rest_endpoints(self):
        client = TestClient(app)
        st = client.get("/api/cluster/status")
        self.assertEqual(st.status_code, 200)
        data = st.json()
        self.assertEqual(data["type"], "cluster_state")
        self.assertFalse(data["cluster_enabled"])
        self.assertEqual(data["cluster_mode"], "party")
        self.assertEqual(data["host_align_ms"], 60)

        # Toggle cluster on in stereo_pair mode
        tog = client.post(
            "/api/cluster/toggle",
            json={
                "enabled": True,
                "mode": "stereo_pair",
                "master_volume": 1.15,
                "host_align_ms": 50,
            },
        )
        self.assertEqual(tog.status_code, 200)
        tdata = tog.json()
        self.assertTrue(tdata["cluster_enabled"])
        self.assertEqual(tdata["cluster_mode"], "stereo_pair")
        self.assertAlmostEqual(tdata["master_volume"], 1.15, places=2)
        self.assertAlmostEqual(tdata["host_align_ms"], 50.0, places=1)

        # Manual LAN peer add & remove
        add_r = client.post("/api/cluster/peers/add", json={"address": "10.0.0.42:8765"})
        self.assertEqual(add_r.status_code, 200)
        self.assertEqual(add_r.json()["peer"]["ip"], "10.0.0.42")

        rem_r = client.post("/api/cluster/peers/remove", json={"address": "10.0.0.42:8765"})
        self.assertEqual(rem_r.status_code, 200)
        self.assertTrue(rem_r.json()["removed"])

    def test_websocket_ntp_sync_and_cluster_pcm_v2_forwarding(self):
        client = TestClient(app)

        def drain_until_type(ws, expected_type, max_msgs=10):
            for _ in range(max_msgs):
                msg = ws.receive_json()
                if msg.get("type") == expected_type:
                    return msg
            raise AssertionError(f"Did not receive {expected_type}")

        def receive_next_bytes(ws, max_msgs=10):
            for _ in range(max_msgs):
                raw_msg = ws.receive()
                if "bytes" in raw_msg and raw_msg["bytes"] is not None:
                    return raw_msg["bytes"]
            raise AssertionError("Did not receive binary frame")

        with patch.object(smart_lights.tuf_driver, "set_rgb", return_value=True):
            with client.websocket_connect(
                "/api/ws/stage-sync?role=host&client_id=node_master&device_name=MasterDJ&device_type=desktop"
            ) as ws_master:
                init_m = drain_until_type(ws_master, "cluster_state")
                self.assertEqual(init_m["type"], "cluster_state")

                with client.websocket_connect(
                    "/api/ws/stage-sync?role=host&client_id=node_follower&device_name=LoaPhu&device_type=mobile"
                ) as ws_follower:
                    drain_until_type(ws_follower, "cluster_state")
                    drain_until_type(ws_master, "cluster_state")

                    # 1. Verify Zero-Echo NTP ping_sync -> pong_sync
                    ws_follower.send_json({"type": "ping_sync", "t0": 12345.678, "rtt_ms": 8.4})
                    pong = drain_until_type(ws_follower, "pong_sync")
                    self.assertEqual(pong["t0"], 12345.678)
                    self.assertIn("t1", pong)
                    self.assertIn("t2", pong)
                    self.assertGreaterEqual(pong["t2"], pong["t1"])

                    # 2. Enable Cluster in Stereo Pair mode from Master
                    ws_master.send_json(
                        {
                            "type": "cluster_toggle",
                            "enabled": True,
                            "mode": "stereo_pair",
                            "master_volume": 1.1,
                            "host_align_ms": 45,
                        }
                    )
                    st_master = drain_until_type(ws_master, "cluster_state")
                    st_follower = drain_until_type(ws_follower, "cluster_state")
                    self.assertTrue(st_master["cluster_enabled"])
                    self.assertEqual(st_master["cluster_mode"], "stereo_pair")
                    self.assertEqual(st_master["master_id"], "node_master")
                    self.assertTrue(st_follower["audio_stream_required"])

                    # Verify automatic L/R assignment across the 2 nodes
                    nodes_by_id = {n["client_id"]: n for n in st_master["nodes"]}
                    self.assertEqual(nodes_by_id["node_master"]["channel_mode"], "left")
                    self.assertEqual(nodes_by_id["node_follower"]["channel_mode"], "right")

                    # 3. Master sends 16-byte v2 PCM audio frame -> Follower receives binary frame
                    header_v2 = struct.pack(
                        "<BBHI d",
                        0xA5,
                        2,
                        1024,
                        48000,
                        stage_sync_hub.clock_ms(),
                    )
                    pcm_payload = b"\x10\x00\x20\x00" * 64
                    packet = header_v2 + pcm_payload
                    ws_master.send_bytes(packet)

                    received_bytes = receive_next_bytes(ws_follower)
                    self.assertEqual(received_bytes, packet)
                    magic, ch, frames, sr, cap_ms = struct.unpack("<BBHI d", received_bytes[:16])
                    self.assertEqual(magic, 0xA5)
                    self.assertEqual(ch, 2)
                    self.assertEqual(frames, 1024)
                    self.assertEqual(sr, 48000)
                    self.assertGreater(cap_ms, 0.0)

                    # 4. Follower claims Master DJ handoff
                    ws_follower.send_json(
                        {
                            "type": "cluster_node_config",
                            "target_client_id": "node_follower",
                            "claim_master": True,
                        }
                    )
                    st_after_claim = drain_until_type(ws_follower, "cluster_state")
                    self.assertEqual(st_after_claim["master_id"], "node_follower")

    def test_cluster_pcm_v2_44100hz_full_fidelity_relay(self):
        """Verify full fidelity 44.1kHz stereo PCM v2 packet (1024 frames = 4096 payload bytes) relay."""
        client = TestClient(app)
        with patch.object(smart_lights.tuf_driver, "set_rgb", return_value=True):
            with client.websocket_connect(
                "/api/ws/stage-sync?role=host&client_id=master_44k&device_name=StudioMaster&device_type=desktop"
            ) as ws_m:
                with client.websocket_connect(
                    "/api/ws/stage-sync?role=host&client_id=node_44k&device_name=StudioMonitor&device_type=desktop"
                ) as ws_n:
                    # Drain cluster_state
                    for _ in range(5):
                        m = ws_m.receive_json()
                        if m.get("type") == "cluster_state":
                            break
                    for _ in range(5):
                        m = ws_n.receive_json()
                        if m.get("type") == "cluster_state":
                            break

                    # Enable cluster link
                    ws_m.send_json({
                        "type": "cluster_toggle",
                        "enabled": True,
                        "mode": "party",
                        "host_align_ms": 60,
                    })
                    for _ in range(5):
                        m = ws_m.receive_json()
                        if m.get("type") == "cluster_state" and m.get("cluster_enabled"):
                            break

                    # Create 44.1kHz 1024 stereo frames packet (16 bytes header + 4096 bytes PCM = 4112 bytes)
                    now_ms = stage_sync_hub.clock_ms()
                    header = struct.pack("<BBHI d", 0x4D, 2, 1024, 44100, now_ms)
                    payload = (b"\x12\x34\x56\x78" * 1024)
                    full_packet = header + payload
                    self.assertEqual(len(full_packet), 16 + 1024 * 4)

                    ws_m.send_bytes(full_packet)

                    received_bytes = None
                    for _ in range(10):
                        msg = ws_n.receive()
                        if msg.get("bytes"):
                            received_bytes = msg["bytes"]
                            break

                    self.assertIsNotNone(received_bytes)
                    self.assertEqual(received_bytes, full_packet)
                    magic, ch, frames, sr, cap_ms = struct.unpack("<BBHI d", received_bytes[:16])
                    self.assertEqual(magic, 0x4D)
                    self.assertEqual(ch, 2)
                    self.assertEqual(frames, 1024)
                    self.assertEqual(sr, 44100)
                    self.assertAlmostEqual(cap_ms, now_ms, places=1)

    def test_audio_pipeline_and_stage_sync_m2_spec_invariants(self):
        """Verify M2 acoustic cleansing specifications and structural requirements."""
        stage_sync_js = Path("web/js/stage_sync.js").read_text(encoding="utf-8")
        engine_js = Path("web/js/engine.js").read_text(encoding="utf-8")
        hub_py = Path("loopbox/stage_sync_hub.py").read_text(encoding="utf-8")
        index_html = Path("web/index.html").read_text(encoding="utf-8")

        # 1. Host Capture: Native 44.1k/48k sample rate + Math.tanh soft saturation + Int16 rounding
        self.assertIn("Math.round(ctx.sampleRate || 44100)", stage_sync_js)
        self.assertIn("Math.tanh(inL[i] || 0)", stage_sync_js)
        self.assertIn("Math.tanh(inR[i] || 0)", stage_sync_js)
        self.assertIn("Math.round(sL * 0x8000)", stage_sync_js)
        self.assertIn("Math.round(sR * 0x8000)", stage_sync_js)
        self.assertNotIn("const outFrames = bufSize >> 1", stage_sync_js)

        # 2. Follower DSP Chain: 20Hz High-Pass + DynamicsCompressor Brickwall Limiter
        self.assertIn("this.satHighPass = this.satAudioCtx.createBiquadFilter();", stage_sync_js)
        self.assertIn('this.satHighPass.type = "highpass";', stage_sync_js)
        self.assertIn("this.satHighPass.frequency.value = 20;", stage_sync_js)
        self.assertIn("this.satHighPass.Q.value = 0.707;", stage_sync_js)
        self.assertIn("this.satLimiter = this.satAudioCtx.createDynamicsCompressor();", stage_sync_js)
        self.assertIn("this.satLimiter.threshold.value = -0.8;", stage_sync_js)
        self.assertIn("this.satLimiter.ratio.value = 20.0;", stage_sync_js)
        self.assertIn("this.satChannelMerger.connect(this.satHighPass);", stage_sync_js)
        self.assertIn("this.satHighPass.connect(this.satGainNode);", stage_sync_js)
        self.assertIn("this.satGainNode.connect(this.satLimiter);", stage_sync_js)
        self.assertIn("this.satLimiter.connect(this.satAudioCtx.destination);", stage_sync_js)

        # 3. Resampler & Slew Phase-Lock: Native Web Audio buffer + continuous varispeed rate nudge
        self.assertIn("const audioBuf = ctx.createBuffer(channels, frames, srcSr);", stage_sync_js)
        self.assertIn("src.playbackRate.value = rateNudge;", stage_sync_js)
        self.assertIn("this.satNextPlayTime += (audioBuf.duration / rateNudge);", stage_sync_js)

        # 4. Engine AudioParam Guard: Anti-trashing check and 0.02s slew time
        self.assertIn("Math.abs(sec - (this._speakerSyncDelaySec || 0)) < 0.0005", engine_js)
        self.assertIn("this.speakerDelay.delayTime.setTargetAtTime(sec, now, 0.02);", engine_js)

        # 5. Baseline 60ms Alignment across Ecosystem
        self.assertIn("self.host_align_ms: int = 60", hub_py)
        self.assertIn("this.hostAlignMs = 60;", stage_sync_js)
        self.assertIn('id="v-sat-latency" style="font-size: 12px; color: var(--accent);">60ms</span>', index_html)
        self.assertIn('id="s-sat-latency" min="15" max="150" step="5" value="60"', index_html)
        self.assertIn('id="v-cluster-align-ms" style="font-size: 12px; color: var(--accent);">60ms</span>', index_html)
        self.assertIn('id="s-cluster-align-ms" min="15" max="150" step="5" value="60"', index_html)


if __name__ == "__main__":
    unittest.main()
