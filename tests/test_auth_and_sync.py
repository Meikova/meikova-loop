import base64
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from loopbox import auth, sessions
from loopbox.server import app


class TestAuthAndMultiDeviceSync(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_auth_config(self):
        resp = self.client.get("/api/auth/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("google_client_id", data)
        self.assertIn("515668723869", data["google_client_id"])

    def test_02_register_and_login_flow(self):
        suffix = os.urandom(4).hex()
        username = f"testuser_{suffix}"
        password = "secretpassword123"

        # Register
        reg_resp = self.client.post("/api/auth/register", json={
            "username": username,
            "password": password,
            "display_name": "Test Audiophile"
        })
        self.assertEqual(reg_resp.status_code, 200)
        reg_data = reg_resp.json()
        self.assertEqual(reg_data["status"], "ok")
        self.assertIn("token", reg_data)
        token = reg_data["token"]
        user = reg_data["user"]
        self.assertEqual(user["username"], username)
        self.assertEqual(user["display_name"], "Test Audiophile")

        # Duplicate username rejection
        dup_resp = self.client.post("/api/auth/register", json={
            "username": username,
            "password": password,
        })
        self.assertEqual(dup_resp.status_code, 400)

        # Me check
        me_resp = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.json()
        self.assertEqual(me_data["user"]["id"], user["id"])

        # Login with correct password
        login_resp = self.client.post("/api/auth/login", json={
            "username": username,
            "password": password,
        })
        self.assertEqual(login_resp.status_code, 200)
        login_data = login_resp.json()
        self.assertIn("token", login_data)

        # Login with wrong password
        fail_resp = self.client.post("/api/auth/login", json={
            "username": username,
            "password": "wrongpassword",
        })
        self.assertEqual(fail_resp.status_code, 401)

    def test_03_multi_device_sync_simulation(self):
        suffix = os.urandom(4).hex()
        username = f"multidevice_{suffix}"
        password = "strongpassword99"

        reg_resp = self.client.post("/api/auth/register", json={
            "username": username,
            "password": password,
            "display_name": "Multi Device Tester"
        })
        token = reg_resp.json()["token"]

        # 1. Device 1 (Laptop) syncs playlist and favorite tracks
        laptop_tracks = ["sample_funk_1", "sample_disco_2"]
        laptop_playlists = [{"id": "pl_chill", "name": "Chill Beats", "track_ids": ["sample_funk_1"]}]
        laptop_favorites = ["sample_funk_1"]

        sync_resp = self.client.post(
            "/api/user/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "track_ids": laptop_tracks,
                "off_ids": [],
                "playlists": laptop_playlists,
                "favorites": laptop_favorites,
                "settings": {"auto_mash": True, "bpm_target": 128},
            }
        )
        self.assertEqual(sync_resp.status_code, 200)
        lib = sync_resp.json()["library"]
        self.assertEqual(lib["track_ids"], laptop_tracks)
        self.assertEqual(lib["favorites"], laptop_favorites)

        # 2. Device 2 (PC) opens web, logs in with same account
        login_pc = self.client.post("/api/auth/login", json={
            "username": username,
            "password": password,
        })
        pc_token = login_pc.json()["token"]

        # PC queries /api/user/sync or /api/session
        pc_sess = self.client.post("/api/session", headers={"Authorization": f"Bearer {pc_token}"})
        self.assertEqual(pc_sess.status_code, 200)
        sess_data = pc_sess.json()
        self.assertIn("user", sess_data)
        self.assertEqual(sess_data["user"]["username"], username)

        # PC queries user sync library
        pc_sync = self.client.get("/api/user/sync", headers={"Authorization": f"Bearer {pc_token}"})
        self.assertEqual(pc_sync.status_code, 200)
        pc_lib = pc_sync.json()["library"]
        self.assertEqual(pc_lib["track_ids"], laptop_tracks)
        self.assertEqual(pc_lib["playlists"], laptop_playlists)
        self.assertEqual(pc_lib["favorites"], laptop_favorites)

        # 3. PC adds another track
        merge_resp = self.client.post(
            "/api/user/sync",
            headers={"Authorization": f"Bearer {pc_token}"},
            json={
                "track_ids": ["sample_rock_3"],
                "merge_tracks": True,
            }
        )
        self.assertEqual(merge_resp.status_code, 200)
        merged_lib = merge_resp.json()["library"]
        self.assertIn("sample_funk_1", merged_lib["track_ids"])
        self.assertIn("sample_rock_3", merged_lib["track_ids"])

        # 4. Laptop fetches sync and sees new track added from PC
        laptop_fetch = self.client.get("/api/user/sync", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(laptop_fetch.status_code, 200)
        self.assertIn("sample_rock_3", laptop_fetch.json()["library"]["track_ids"])

    def test_04_logout(self):
        suffix = os.urandom(4).hex()
        username = f"logout_{suffix}"
        password = "password1234"
        reg = self.client.post("/api/auth/register", json={"username": username, "password": password})
        token = reg.json()["token"]

        # Logout
        logout_resp = self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(logout_resp.status_code, 200)

        # Check me fails
        me_resp = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 401)

    def test_05_google_token_decode_mock(self):
        # Create a mock JWT-like credential with payload
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(json.dumps({
            "email": "tester@example.com",
            "name": "Google Tester",
            "sub": "google-sub-123456"
        }).encode()).rstrip(b"=").decode()
        mock_credential = f"{header}.{payload}.signature"

        resp = self.client.post("/api/auth/google", json={"credential": mock_credential})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["user"]["username"], "tester@example.com")
        self.assertIn("token", data)

    def test_06_desktop_and_mobile_auth_isolation(self):
        from unittest.mock import patch

        mock_token = "mock_isolated_token_123"
        mock_user = {"id": 999, "username": "isolated@gmail.com", "display_name": "Isolated User"}

        with patch("loopbox.auth.exchange_google_code", return_value={"token": mock_token, "user": mock_user}):
            # 1. Desktop Flow
            desk_state = auth.create_auth_request("desktop")
            desk_resp = self.client.get(f"/api/auth/google/callback?code=fake_code&state={desk_state}")
            self.assertEqual(desk_resp.status_code, 200)
            desk_html = desk_resp.text
            self.assertIn("Đã xác thực cho Desktop App!", desk_html)
            self.assertNotIn("localStorage.setItem('meikova:loop:token'", desk_html)
            self.assertNotIn("window.location.href = '/'", desk_html)

            # Check that desktop thread received the result
            desk_result = auth.wait_for_auth_request(desk_state, timeout=1.0)
            self.assertIsNotNone(desk_result)
            self.assertEqual(desk_result["token"], mock_token)
            self.assertEqual(desk_result["user"]["username"], "isolated@gmail.com")

            # 2. Mobile Native Flow
            mob_state = auth.create_auth_request("mobile")
            mob_resp = self.client.get(f"/api/auth/google/callback?code=fake_code&state={mob_state}")
            self.assertEqual(mob_resp.status_code, 200)
            mob_html = mob_resp.text
            self.assertIn("Đã xác thực cho Mobile App!", mob_html)
            self.assertIn("com.meikova.loop://", mob_html)
            self.assertNotIn("localStorage.setItem('meikova:loop:token'", mob_html)
            self.assertNotIn("window.location.href = '/'", mob_html)

            # Check that mobile polling endpoint retrieves the result
            poll_resp = self.client.get(f"/api/auth/google/poll?state={mob_state}")
            self.assertEqual(poll_resp.status_code, 200)
            poll_data = poll_resp.json()
            self.assertEqual(poll_data["status"], "ok")
            self.assertEqual(poll_data["token"], mock_token)
            self.assertEqual(poll_data["user"]["display_name"], "Isolated User")

            # Subsequent poll should show pending/cleared
            poll2_resp = self.client.get(f"/api/auth/google/poll?state={mob_state}")
            self.assertEqual(poll2_resp.json()["status"], "pending")

            # 3. Standard Web Flow (no desktop/mobile state)
            web_resp = self.client.get("/api/auth/google/callback?code=fake_code")
            self.assertEqual(web_resp.status_code, 200)
            web_html = web_resp.text
            self.assertIn("localStorage.setItem('meikova:loop:token'", web_html)
            self.assertIn("window.location.href = '/'", web_html)



    def test_07_multi_device_session_key_and_audio_protection(self):
        from unittest.mock import patch
        from loopbox import config, server

        with patch.object(config, "MULTIUSER", True), \
             patch.object(sessions, "MULTIUSER", True), \
             patch.object(server, "MULTIUSER", True):
            suffix = os.urandom(4).hex()
            username = f"audio_sync_{suffix}"
            password = "testpass999!"

            # Register user
            reg_resp = self.client.post("/api/auth/register", json={
                "username": username,
                "password": password,
                "display_name": "Audio Device Sync"
            })
            self.assertEqual(reg_resp.status_code, 200)
            reg_data = reg_resp.json()
            self.assertIn("session", reg_data)
            self.assertIsNotNone(reg_data["session"]["k"])
            key_reg = reg_data["session"]["k"]

            # Machine A: Login
            login_a = self.client.post("/api/auth/login", json={"username": username, "password": password})
            self.assertEqual(login_a.status_code, 200)
            data_a = login_a.json()
            token_a = data_a["token"]
            self.assertIn("session", data_a)
            key_a = data_a["session"]["k"]
            self.assertEqual(key_a, key_reg)

            # Machine B: Login independently
            login_b = self.client.post("/api/auth/login", json={"username": username, "password": password})
            self.assertEqual(login_b.status_code, 200)
            data_b = login_b.json()
            token_b = data_b["token"]
            self.assertIn("session", data_b)
            key_b = data_b["session"]["k"]
            # Keys MUST match across devices!
            self.assertEqual(key_a, key_b)

            # Machine B: POST /api/session with token
            sess_b = self.client.post("/api/session", headers={"Authorization": f"Bearer {token_b}"})
            self.assertEqual(sess_b.status_code, 200)
            self.assertEqual(sess_b.json()["k"], key_b)

            # /api/auth/me returns same session key
            me_resp = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
            self.assertEqual(me_resp.status_code, 200)
            self.assertEqual(me_resp.json()["session"]["k"], key_a)

            # Test simulation of cache sweep / memory reload
            sessions._user_sessions.clear()
            sessions._sessions.clear()
            v_reloaded = sessions.get_for_user(data_a["user"]["id"])
            key_reloaded_b64 = base64.b64encode(v_reloaded.key).decode()
            self.assertEqual(key_reloaded_b64, key_a)


if __name__ == "__main__":
    unittest.main()
