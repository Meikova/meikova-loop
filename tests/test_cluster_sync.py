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
        stage_sync_hub.host_align_ms = 45.0

    def tearDown(self):
        stage_sync_hub.cluster_enabled = False
        stage_sync_hub.cluster_mode = "party"
        stage_sync_hub.cluster_master_id = ""
        stage_sync_hub.cluster_master_volume = 1.0
        stage_sync_hub.host_align_ms = 45.0

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


if __name__ == "__main__":
    unittest.main()
