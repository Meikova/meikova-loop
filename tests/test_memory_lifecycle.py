import unittest
import asyncio
from loopbox.stage_sync_hub import StageSyncHub


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


class TestMemoryLifecycleAndSync(unittest.TestCase):
    def test_cache_limit_constants(self):
        with open("web/js/api.js", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("300 * 1024 * 1024 : 450 * 1024 * 1024", content)
        self.assertIn("entry.track.buffer = null", content)

    def test_voice_node_cleanup(self):
        with open("web/js/engine.js", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("this.lrNodes = []", content)
        self.assertIn("for (const n of this.lrNodes)", content)
        self.assertIn("this.gain?.disconnect()", content)

    def test_viz_ring_dispose(self):
        with open("web/js/viz.js", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("_disposeRing(ring)", content)
        self.assertIn("ring.layer.canvas.width = 0", content)
        self.assertIn("ring.layer.canvas.height = 0", content)
        self.assertIn("Math.max(0.001, ring.fill || 0)", content)

    def test_same_machine_speaker_sync_relay(self):
        async def _run():
            hub = StageSyncHub()
            ws_master = DummyWebSocket("127.0.0.1")
            ws_follower = DummyWebSocket("127.0.0.1")
            ws_remote = DummyWebSocket("192.168.1.100")

            await hub.connect(ws_master, role="host")
            await hub.connect(ws_follower, role="satellite")
            await hub.connect(ws_remote, role="satellite")

            # Follower sends same_machine_speaker_sync
            handled = await hub._handle_common_control_message({
                "type": "same_machine_speaker_sync",
                "clientId": "follower-1",
                "suppressMasterSpeaker": True,
                "isMutedLocal": False,
            }, ws=ws_follower, role="satellite")

            self.assertTrue(handled)
            # Master on 127.0.0.1 should have received the message
            master_received = any("same_machine_speaker_sync" in msg for msg in ws_master.sent_messages)
            self.assertTrue(master_received)

            # Remote follower on 192.168.1.100 should NOT receive same_machine_speaker_sync
            remote_received = any("same_machine_speaker_sync" in msg for msg in ws_remote.sent_messages)
            self.assertFalse(remote_received)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
