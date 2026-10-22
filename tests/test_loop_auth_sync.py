import os
import sys
import time
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from loopbox import auth
from loopbox.server import app

shared_priv = Path(__file__).resolve().parent.parent.parent / "shared" / "keys" / "ed25519_private.pem"
shared_pub = Path(__file__).resolve().parent.parent.parent / "shared" / "keys" / "ed25519_public.pem"

try:
    from loopbox.universal_sso import UniversalSSO
except ImportError:
    _shared_dir = str(Path(__file__).resolve().parent.parent.parent / 'shared')
    if _shared_dir not in sys.path:
        sys.path.insert(0, _shared_dir)
    from universal_sso import UniversalSSO

sso_signer = UniversalSSO()


class TestLoopAuthSync(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_find_user_by_identifier(self):
        suffix = os.urandom(4).hex()
        username = f"smart_{suffix}"
        email = f"smart_{suffix}@meikova.io"
        password = "password123"

        reg = auth.register_user(username, password, display_name="Smart User")
        user_id = reg["user"]["id"]

        # 1. By ID
        u1 = auth.find_user_by_identifier(user_id)
        self.assertIsNotNone(u1)
        self.assertEqual(u1["username"], username)

        # 2. By Username
        u2 = auth.find_user_by_identifier(username)
        self.assertIsNotNone(u2)
        self.assertEqual(u2["id"], user_id)

        # 3. By Email (if clean_username contains @ or prefix)
        email_user = f"user_{suffix}@example.com"
        reg_email = auth.register_user(email_user, password)
        u3 = auth.find_user_by_identifier(email_user)
        self.assertIsNotNone(u3)
        self.assertEqual(u3["email"], email_user)

        # 4. By prefix before @
        prefix = f"user_{suffix}"
        u4 = auth.find_user_by_identifier(prefix)
        self.assertIsNotNone(u4)
        self.assertEqual(u4["email"], email_user)

    def test_02_jit_provisioning_sso(self):
        suffix = os.urandom(4).hex()
        sub = f"gw_{suffix}"
        username = f"sso_user_{suffix}"
        email = f"sso_{suffix}@meikova.io"

        token = sso_signer.issue_token(
            user_id=sub,
            username=username,
            email=email,
            display_name=f"SSO {suffix}",
            expires_in_sec=86400
        )

        resp = self.client.post("/api/auth/sso/callback", json={"token": token})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["user"]["id"], sub)

        # Verify mirrored in local database
        u = auth.find_user_by_identifier(sub)
        self.assertIsNotNone(u)
        self.assertEqual(u["gateway_user_id"], sub)
        self.assertEqual(u["email"], email)

        # Verify library persists cleanly
        lib = auth.save_user_library(sub, track_ids=["track_1", "track_2"])
        self.assertIn("track_1", lib["track_ids"])
        read_lib = auth.get_user_library(sub)
        self.assertIn("track_2", read_lib["track_ids"])

    def test_03_auth_sync_queue_and_push(self):
        suffix = os.urandom(4).hex()
        username = f"offline_{suffix}"
        password = "password123"

        reg = auth.register_user(username, password)
        user_id = reg["user"]["id"]

        # Check sync status API
        resp = self.client.get("/api/auth/sync/status")
        self.assertEqual(resp.status_code, 200)
        status_data = resp.json()
        self.assertTrue(status_data["success"])
        self.assertGreaterEqual(status_data["queue_count"], 1)

        # Push queue
        push_resp = self.client.post("/api/auth/sync/push")
        self.assertEqual(push_resp.status_code, 200)
        push_data = push_resp.json()
        self.assertTrue(push_data["success"])
        self.assertGreaterEqual(push_data["synced_count"], 1)

    def test_04_conflict_resolution_same_email(self):
        suffix = os.urandom(4).hex()
        email = f"alice_{suffix}@test.io"
        password = "password123"

        # Local user registered with email as username
        reg = auth.register_user(email, password, display_name="Alice Local")
        local_id = reg["user"]["id"]
        auth.save_user_library(local_id, favorites=["fav_track_1"])

        gw_sub = f"gw_alice_{suffix}"
        gw_sync_resp = self.client.post("/api/auth/sync/gateway", json={
            "account": {
                "id": gw_sub,
                "email": email,
                "username": f"alice_{suffix}",
                "display_name": "Alice Gateway"
            }
        })
        self.assertEqual(gw_sync_resp.status_code, 200)
        res_data = gw_sync_resp.json()
        self.assertTrue(res_data["success"])
        results = res_data["results"]
        self.assertEqual(results[0]["action"], "LINKED")
        self.assertEqual(results[0]["local_id"], local_id)

        # Verify existing library data preserved
        lib = auth.get_user_library(gw_sub)
        self.assertIn("fav_track_1", lib["favorites"])

    def test_05_conflict_resolution_same_username(self):
        suffix = os.urandom(4).hex()
        username = f"bob_{suffix}"
        password = "password123"

        reg = auth.register_user(username, password, display_name="Bob Local")
        local_id = reg["user"]["id"]

        gw_sub = f"gw_bob_{suffix}"
        gw_email = f"bob_gw_{suffix}@gateway.io"
        gw_sync_resp = self.client.post("/api/auth/sync/gateway", json={
            "account": {
                "id": gw_sub,
                "email": gw_email,
                "username": username,
                "display_name": "Bob Gateway"
            }
        })
        self.assertEqual(gw_sync_resp.status_code, 200)
        res_data = gw_sync_resp.json()
        self.assertTrue(res_data["success"])
        results = res_data["results"]
        self.assertEqual(results[0]["action"], "RESOLVED_NAMESPACE")
        self.assertIn(f"{username}_local_", results[0]["local_renamed_to"])

        # Local user renamed
        old_local = auth.find_user_by_identifier(local_id)
        self.assertEqual(old_local["username"], results[0]["local_renamed_to"])

        # Gateway user now has the canonical username
        gw_user = auth.find_user_by_identifier(gw_sub)
        self.assertEqual(gw_user["username"], username)


if __name__ == "__main__":
    unittest.main()
