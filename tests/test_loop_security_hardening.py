import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from loopbox import library, sessions
from loopbox.server import app


class TestLoopSecurityHardening(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_auth_brute_force_5_strike_lockout(self):
        """Kiểm tra cơ chế 5-Strike Lockout: Thử sai 5 lần liên tiếp sẽ bị khóa ở lần thứ 6 (HTTP 429)."""
        test_ip = "198.51.100.42"
        headers = {"x-forwarded-for": test_ip}

        # 5 lần thử sai mật khẩu đầu tiên -> trả về 401
        for i in range(5):
            res = self.client.post(
                "/api/auth/login",
                json={"username": f"victim_user_{test_ip}", "password": "wrong_password_123"},
                headers=headers,
            )
            self.assertEqual(res.status_code, 401, f"Lần thử thứ {i+1} phải trả về 401")

        # Lần thứ 6 -> Bắt buộc bị Lockout với HTTP 429 Too Many Requests
        lockout_res = self.client.post(
            "/api/auth/login",
            json={"username": f"victim_user_{test_ip}", "password": "wrong_password_123"},
            headers=headers,
        )
        self.assertEqual(lockout_res.status_code, 429, "Lần thử thứ 6 phải bị khóa với HTTP 429")
        data = lockout_res.json()
        self.assertIn("khóa", str(data).lower())

    def test_02_idor_session_spoofing_rejected(self):
        """Kiểm tra ngăn chặn IDOR: Gửi header X-Session: u_<user_id> mà không có JWT token phải bị từ chối."""
        # Giả lập kẻ tấn công cố tình chèn X-Session dạng u_admin1234
        spoofed_sid = "u_victimadmin99"
        res = self.client.get("/api/tracks", headers={"x-session": spoofed_sid})
        # Hệ thống phải từ chối hoặc tạo session mới, tuyệt đối không trả về thư viện của victimadmin99
        if res.status_code == 200:
            # Nếu 200, kiểm tra xem có bị gán session user_id của victim không
            data = res.json()
            session_id = data.get("session_id", "")
            self.assertNotEqual(session_id, spoofed_sid, "Không được phép chấp nhận spoofed session ID dạng u_*")
        else:
            self.assertIn(res.status_code, (401, 403, 410))

    def test_03_lfi_file_schema_blocked(self):
        """Kiểm tra ngăn chặn LFI: Đường dẫn file://... trong hydrate_track phải bị từ chối triệt để."""
        tid = "secrttest01"  # 11 characters
        try:
            # Test direct library call
            with self.assertRaises((ValueError, RuntimeError, PermissionError)):
                library.hydrate_track(tid, remote_url="file:///etc/passwd")

            with self.assertRaises((ValueError, RuntimeError, PermissionError)):
                library.hydrate_track(tid, remote_url="file:///C:/Windows/win.ini")

            # Test qua API endpoint
            res = self.client.post(
                f"/api/library/{tid}/hydrate",
                json={"remote_url": "file:///etc/shadow"}
            )
            self.assertIn(res.status_code, (400, 403, 422), "API phải từ chối file:// schema")
        finally:
            if library.valid_id(tid):
                library.delete(tid)

    def test_04_ssrf_private_and_metadata_ip_blocked(self):
        """Kiểm tra ngăn chặn SSRF: Chặn toàn bộ IP private, loopback và AWS/Cloud metadata (169.254.169.254)."""
        blocked_urls = [
            "http://127.0.0.1:8765/api/admin",
            "http://localhost:8080/secret",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/router",
            "http://192.168.1.1/admin",
            "http://[::1]:8080/test",
        ]
        tid = "ssrfblock01"  # 11 characters
        try:
            for bad_url in blocked_urls:
                res = self.client.post(
                    f"/api/library/{tid}/hydrate",
                    json={"remote_url": bad_url}
                )
                self.assertIn(res.status_code, (400, 403, 422, 502), f"URL {bad_url} phải bị chặn")
        finally:
            if library.valid_id(tid):
                library.delete(tid)

    def test_05_host_boundary_guard_for_sensitive_endpoints(self):
        """Kiểm tra Host Boundary Guard: Các route /api/tunnel/*, /api/cookies, /api/settings từ WAN phải bị chặn 403."""
        wan_ip = "203.0.113.195"
        wan_headers = {"x-forwarded-for": wan_ip}

        # 1. /api/tunnel/stop từ WAN
        res_tunnel = self.client.post("/api/tunnel/stop", headers=wan_headers)
        self.assertEqual(res_tunnel.status_code, 403, "WAN client không được phép gọi /api/tunnel/stop")

        # 2. /api/tunnel/toggle từ WAN
        res_toggle = self.client.post("/api/tunnel/toggle", headers=wan_headers)
        self.assertEqual(res_toggle.status_code, 403, "WAN client không được phép gọi /api/tunnel/toggle")

        # 3. /api/cookies (POST / DELETE) từ WAN
        res_cookies = self.client.post("/api/cookies", json={"content": "test=1"}, headers=wan_headers)
        self.assertEqual(res_cookies.status_code, 403, "WAN client không được phép ghi đè cookie")

        res_del_cookies = self.client.delete("/api/cookies", headers=wan_headers)
        self.assertEqual(res_del_cookies.status_code, 403, "WAN client không được phép xóa cookie")

        # 4. /api/settings (POST) từ WAN
        res_settings = self.client.post("/api/settings", json={"malicious": True}, headers=wan_headers)
        self.assertEqual(res_settings.status_code, 403, "WAN client không được phép ghi đè settings")

    def test_06_security_headers_present(self):
        """Kiểm tra sự hiện diện của các Security Headers chuẩn OWASP trên HTTP response."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        # Kiểm tra X-Content-Type-Options
        self.assertEqual(res.headers.get("x-content-type-options"), "nosniff")
        # Kiểm tra X-Frame-Options
        self.assertIn(res.headers.get("x-frame-options", "").upper(), ("SAMEORIGIN", "DENY"))
        # Kiểm tra Referrer-Policy
        self.assertTrue(bool(res.headers.get("referrer-policy")))

    def test_07_universal_sso_no_predictable_fallback_key(self):
        """Kiểm tra Universal SSO không sử dụng private key hardcoded có thể dự đoán được."""
        from loopbox.universal_sso import UniversalSSO
        # Khi không có private key trong env hay file, sso không được dùng key hardcoded tĩnh
        sso = UniversalSSO()
        # Verify rằng fallback key không phải là chuỗi hardcoded công khai
        hardcoded_sig = "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1DNENBUUF3QlFZREsyVndCQ0lFSVBNVFl3Y2RFUTR5MjhXcTJoOWRpS05TdFhpSGRlU242MDdENGE3S0pXdUkKLS0tLS1FTkQgUFJJVkFURSBLRVktLS0tLQo="
        self.assertNotEqual(getattr(sso, "_ENC", None), hardcoded_sig, "Không được phép giữ fallback private key tĩnh")


if __name__ == "__main__":
    unittest.main()
