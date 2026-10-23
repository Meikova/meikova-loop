import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient
from loopbox import auth
from loopbox.server import app


class TestLoopStandardization(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_auth_google_config_endpoint(self):
        """Verifies both /api/auth/config and /api/auth/google/config return Google client ID."""
        r1 = self.client.get("/api/auth/config")
        self.assertEqual(r1.status_code, 200)
        self.assertIn("google_client_id", r1.json())

        r2 = self.client.get("/api/auth/google/config")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("google_client_id", r2.json())
        self.assertEqual(r1.json(), r2.json())

    def test_02_sync_status_endpoint(self):
        """Verifies /api/sync/status reports online and authentication status."""
        r = self.client.get("/api/sync/status")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("online"))
        self.assertFalse(data.get("authenticated"))
        self.assertIsNone(data.get("user_id"))

    def test_03_sync_pull_push_endpoints_auth_required(self):
        """Verifies /api/sync/pull and /api/sync/push require valid authentication."""
        # Unauthorized pull
        r_pull = self.client.get("/api/sync/pull")
        self.assertEqual(r_pull.status_code, 401)

        r_legacy_pull = self.client.get("/api/user/sync")
        self.assertEqual(r_legacy_pull.status_code, 401)

        # Unauthorized push
        r_push = self.client.post("/api/sync/push", json={"track_ids": ["test_track_1"]})
        self.assertEqual(r_push.status_code, 401)

        r_legacy_push = self.client.post("/api/user/sync", json={"track_ids": ["test_track_1"]})
        self.assertEqual(r_legacy_push.status_code, 401)

    def test_04_sync_pull_push_authorized(self):
        """Verifies /api/sync/pull and /api/sync/push work with authenticated session."""
        suffix = os.urandom(4).hex()
        username = f"sync_test_{suffix}"
        password = "password123"

        reg = auth.register_user(username, password)
        token = reg.get("token")
        self.assertIsNotNone(token)

        headers = {"Authorization": f"Bearer {token}"}

        # Push library via /api/sync/push
        r_push = self.client.post(
            "/api/sync/push",
            json={"track_ids": ["std_track_1", "std_track_2"], "merge_tracks": True},
            headers=headers
        )
        self.assertEqual(r_push.status_code, 200)
        self.assertEqual(r_push.json().get("status"), "ok")

        # Pull library via /api/sync/pull
        r_pull = self.client.get("/api/sync/pull", headers=headers)
        self.assertEqual(r_pull.status_code, 200)
        lib = r_pull.json().get("library", {})
        self.assertIn("std_track_1", lib.get("track_ids", []))
        self.assertIn("std_track_2", lib.get("track_ids", []))

    def test_05_host_info_discovery(self):
        """Verifies dynamic host discovery endpoints return valid LAN/Tailscale structures."""
        r1 = self.client.get("/api/host-info")
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertIn("lan_ip", d1)
        self.assertIn("active_url", d1)

        r2 = self.client.get("/api/network/host-info")
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertEqual(d1["lan_ip"], d2["lan_ip"])

    def test_06_no_hardcoded_user_paths(self):
        """Verifies no hardcoded developer download/profile paths in codebase."""
        auth_file = ROOT / "loopbox" / "auth.py"
        auth_content = auth_file.read_text(encoding="utf-8")
        self.assertNotIn(r"E:/Downloads", auth_content)
        self.assertNotIn(r"E:\Downloads", auth_content)

        sync_tool = ROOT / "tools" / "sync_cookie_to_space.py"
        sync_content = sync_tool.read_text(encoding="utf-8")
        self.assertNotIn(r"E:\Downloads", sync_content)
        self.assertNotIn(r"E:/Downloads", sync_content)


if __name__ == "__main__":
    unittest.main()
