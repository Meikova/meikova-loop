import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from loopbox import db, library
from loopbox.server import app

TURSO_URL = "https://meikova-loop-m3ik18dp.aws-ap-northeast-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTI1ODkxMTksImlkIjoiMDFhMTVlYTMtMmEwMS03NWQ1LWI1NTMtNWNlNDA3OTY0YmRhIiwia2lkIjoibk13eDJZSGtEaHVvYl81SXZkM1FQVzhpVi1ZT0poeHdUbmpIMXo5dl9iMCIsInJpZCI6ImU2YTNlM2Q5LThjZjMtNGNkMS1hNTcyLWNlYTcxZDQ0N2RhMCJ9.Fyj41pvsfrKTUCwRmMfWCbwGOFEUjLIi4b-Jt345VNY8oo3Zk4DthABI1iolkycjPM3GoTVe512ll22TS-WqBQ"


class TestContentHydrationAndTursoAdapter(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.test_tids = []

    def tearDown(self):
        for tid in self.test_tids:
            library.delete(tid)

    def test_01_turso_cloud_connection(self):
        """Kiểm tra kết nối Turso Database meikova-loop thành công qua LoopDbAdapter."""
        adapter = db.get_db(url=TURSO_URL, auth_token=TURSO_TOKEN)
        try:
            self.assertTrue(adapter.is_turso, "Adapter should identify as Turso cloud")
            self.assertEqual(adapter.db_type, "turso")

            # Check existing tables in Turso meikova-loop
            res = adapter.execute("SELECT name FROM sqlite_master WHERE type = ? ORDER BY name", ["table"])
            tables = [r["name"] for r in res]
            self.assertIn("library_items", tables)
            self.assertIn("playlists", tables)
            self.assertIn("user_settings", tables)

            # Query row count
            count_res = adapter.fetchone("SELECT COUNT(*) as cnt FROM library_items")
            self.assertIsNotNone(count_res)
            self.assertGreaterEqual(count_res["cnt"], 0)
        finally:
            adapter.close()

    def test_02_metadata_only_when_audio_missing(self):
        """Phát hiện đúng trạng thái METADATA_ONLY khi file âm thanh vắng mặt nhưng có remote_url."""
        tid = "metaonly001"
        self.test_tids.append(tid)

        # Create metadata with remote_url but no audio.flac
        meta = library.create(
            tid,
            title="Metadata Only Test Track",
            channel="Meikova Music",
            duration=180.0,
            remote_url="https://example.com/audio/sample.mp3",
            status="ready"
        )
        self.assertFalse(library.has_audio(tid), "Track should not have local audio file")

        # Check get_hydration_status
        status = library.get_hydration_status(tid, meta)
        self.assertEqual(status, "METADATA_ONLY")

        # Check in list_tracks()
        tracks = library.list_tracks()
        track_map = {t["id"]: t for t in tracks}
        self.assertIn(tid, track_map)
        self.assertEqual(track_map[tid]["hydration_status"], "METADATA_ONLY")

    def test_03_synced_local_when_audio_exists(self):
        """Chuyển trạng thái sang SYNCED_LOCAL khi file âm thanh tồn tại trên đĩa."""
        tid = "syncedloc01"
        self.test_tids.append(tid)

        # Create metadata
        library.create(
            tid,
            title="Synced Local Test Track",
            duration=120.0,
            remote_url="https://example.com/audio/synced.mp3",
            status="ready"
        )

        # Place audio file
        audio_file = library.audio_path(tid)
        audio_file.parent.mkdir(parents=True, exist_ok=True)
        # Write dummy audio content
        audio_file.write_bytes(b"RIFF" + b"\x00" * 1024)

        self.assertTrue(library.has_audio(tid), "Track must have local audio file")

        # Check get_hydration_status
        status = library.get_hydration_status(tid)
        self.assertEqual(status, "SYNCED_LOCAL")

        # Check in list_tracks()
        tracks = library.list_tracks()
        track_map = {t["id"]: t for t in tracks}
        self.assertIn(tid, track_map)
        self.assertEqual(track_map[tid]["hydration_status"], "SYNCED_LOCAL")

    def test_04_fallback_local_database_when_no_env(self):
        """Fallback local SQLite WAL database tại data/loopbox.db khi không có env vars."""
        old_url = os.environ.pop("TURSO_DATABASE_URL", None)
        old_token = os.environ.pop("TURSO_AUTH_TOKEN", None)

        try:
            adapter = db.get_db()
            try:
                self.assertFalse(adapter.is_turso, "Adapter should fall back to local SQLite")
                self.assertEqual(adapter.db_type, "sqlite")
                self.assertTrue(adapter.db_path.exists(), "Local database file should exist")

                # Verify WAL journal mode
                res = adapter.fetchone("PRAGMA journal_mode")
                self.assertEqual(res[0].lower(), "wal")

                # Verify schema exists in local fallback
                tables_res = adapter.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
                table_names = [r[0] for r in tables_res]
                self.assertIn("library_items", table_names)
                self.assertIn("playlists", table_names)
                self.assertIn("user_settings", table_names)

                # Test local insert & query
                test_id = "loc_test_01"
                adapter.execute(
                    "INSERT OR REPLACE INTO library_items (id, title, hydration_status) VALUES (?, ?, ?)",
                    [test_id, "Local WAL Track", "METADATA_ONLY"]
                )
                row = adapter.fetchone("SELECT title, hydration_status FROM library_items WHERE id = ?", [test_id])
                self.assertIsNotNone(row)
                self.assertEqual(row["title"], "Local WAL Track")
                self.assertEqual(row["hydration_status"], "METADATA_ONLY")
            finally:
                adapter.close()
        finally:
            if old_url:
                os.environ["TURSO_DATABASE_URL"] = old_url
            if old_token:
                os.environ["TURSO_AUTH_TOKEN"] = old_token

    def test_05_hydrate_track_execution(self):
        """Kiểm tra hàm hydrate_track tải file và cập nhật trạng thái SYNCED_LOCAL."""
        tid = "hydratrun01"
        self.test_tids.append(tid)

        # Create temporary dummy source audio file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"MOCK_AUDIO_DATA_" * 128)
            mock_src_path = f.name

        try:
            library.create(
                tid,
                title="Hydrate Run Test",
                remote_url=mock_src_path,
                status="queued"
            )
            self.assertEqual(library.get_hydration_status(tid), "METADATA_ONLY")

            # Execute hydration
            success = library.hydrate_track(tid, remote_url=mock_src_path)
            self.assertTrue(success)
            self.assertTrue(library.has_audio(tid))
            self.assertEqual(library.get_hydration_status(tid), "SYNCED_LOCAL")
        finally:
            if os.path.exists(mock_src_path):
                os.unlink(mock_src_path)

    def test_06_server_hydrate_and_audio_routes(self):
        """Kiểm tra server endpoint /api/library/{tid}/hydrate và streaming fallback."""
        tid = "srvhydrate1"
        self.test_tids.append(tid)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"SAMPLE_MP3_STREAM_CONTENT_" * 64)
            mock_audio_path = f.name

        try:
            # 1. Create track with metadata only
            library.create(
                tid,
                title="Server Hydrate Endpoint Test",
                remote_url=mock_audio_path,
                status="ready"
            )

            # 2. Test /api/tracks returns hydration_status
            tracks_resp = self.client.get("/api/tracks")
            self.assertEqual(tracks_resp.status_code, 200)
            t_data = tracks_resp.json()
            matching = [t for t in t_data.get("tracks", []) if t.get("id") == tid]
            self.assertTrue(len(matching) > 0)
            self.assertEqual(matching[0].get("hydration_status"), "METADATA_ONLY")

            # 3. Test on-demand streaming from remote_url when audio is missing locally
            audio_resp = self.client.get(f"/api/tracks/{tid}/audio")
            self.assertEqual(audio_resp.status_code, 200)
            self.assertGreater(len(audio_resp.content), 0)

            # 4. Test POST /api/library/{tid}/hydrate endpoint
            hyd_resp = self.client.post(f"/api/library/{tid}/hydrate", json={"remote_url": mock_audio_path})
            self.assertEqual(hyd_resp.status_code, 200)
            self.assertIn(hyd_resp.json().get("status"), ("ok", "already_synced"))
        finally:
            if os.path.exists(mock_audio_path):
                os.unlink(mock_audio_path)


if __name__ == "__main__":
    unittest.main()
