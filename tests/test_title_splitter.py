import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class TestTitleSplitter(unittest.TestCase):
    """Test smart title detection and splitting in viz.js."""

    def _split(self, title: str, channel: str = "") -> dict:
        code = f"""
        import {{ splitTitle }} from './web/js/viz.js';
        const res = splitTitle({json.dumps(title)}, {json.dumps(channel)});
        console.log(JSON.stringify(res));
        """
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        self.assertEqual(proc.returncode, 0, f"Node error: {proc.stderr}")
        return json.loads(proc.stdout.strip())

    def test_user_reported_vietnamese_tracks(self):
        """Verify the 6 specific tracks from user screenshot have correct song title and singer."""
        # Track 1
        t1 = "Dâu Hào Môn Remix (Bản Hot TikTok) - Tú Tú | Hào Môn Có Sướng Vui Chưa Hay Giông Tố Đem Mưa Remix"
        r1 = self._split(t1, "VuNhann Music")
        self.assertIn("Dâu Hào Môn", r1["title"])
        self.assertIn("Tú Tú", r1["artist"])

        # Track 2
        t2 = "Cause I Love You (ctri Remix) - Noo Phước Thịnh 🎼 Bản mel chuẩn TikTok"
        r2 = self._split(t2, "ctri")
        self.assertIn("Cause I Love You", r2["title"])
        self.assertIn("Noo Phước Thịnh", r2["artist"])

        # Track 3
        t3 = "SƠN THUỶ TRÙNG MÂY x THUỶ CHUNG x YẾN VÔ HIẾT (VIETZ x WI. REMIX) - JENA, ANH RỒNG,THƯƠNG VÕ,MÂY BAE"
        r3 = self._split(t3, "VietZ")
        self.assertIn("SƠN THUỶ TRÙNG MÂY", r3["title"])
        self.assertIn("JENA", r3["artist"])

        # Track 4
        t4 = "NGƯỢC LỐI YÊU (STYLE DK REMIX) - VICKY NHUNG 🎶 NGƯỢC LỐI ĐỂ THƯƠNG EM QUÁ NHIỀU"
        r4 = self._split(t4, "CMT BEAT MUSIC")
        self.assertIn("NGƯỢC LỐI YÊU", r4["title"])
        self.assertIn("VICKY NHUNG", r4["artist"])

        # Track 5
        t5 = "Anh Đau Từ Lúc Em Đi - Trần Mạnh Cường (Duzme Remix) / Audio Lyrics"
        r5 = self._split(t5, "Duzme Music")
        self.assertIn("Anh Đau Từ Lúc Em Đi", r5["title"])
        self.assertIn("Trần Mạnh Cường", r5["artist"])

        # Track 6
        t6 = "Mở Lòng Vì Ai (Thazh x Đông Remix) - Inso Cover ♫ Em Một Lòng Vì Anh Nhưng Anh Mở Lòng Vì Ai Remix"
        r6 = self._split(t6, "Air Remix")
        self.assertIn("Mở Lòng Vì Ai", r6["title"])
        self.assertIn("Inso Cover", r6["artist"])

    def test_western_and_channel_matching_tracks(self):
        """Verify Western format 'Artist - Title' and channel matching."""
        # Western tracks
        r_cp = self._split("Coldplay - Yellow", "Coldplay")
        self.assertEqual(r_cp["title"], "Yellow")
        self.assertEqual(r_cp["artist"], "Coldplay")

        r_qn = self._split("Queen - Bohemian Rhapsody (Official Video)", "Queen Official")
        self.assertEqual(r_qn["title"], "Bohemian Rhapsody")
        self.assertEqual(r_qn["artist"], "Queen")

        r_av = self._split("Avicii - Wake Me Up (Official Video)", "AviciiVEVO")
        self.assertEqual(r_av["title"], "Wake Me Up")
        self.assertEqual(r_av["artist"], "Avicii")

        # Vietnamese Artist - Title when channel matches artist
        r_sb = self._split("Soobin Hoàng Sơn - Anh Đã Quen Với Cô Đơn | Official MV", "SOOBIN Official")
        self.assertIn("Anh Đã Quen Với Cô Đơn", r_sb["title"])
        self.assertEqual(r_sb["artist"], "Soobin Hoàng Sơn")

        r_st = self._split("Sơn Tùng M-TP - NƠI NÀY CÓ ANH | OFFICIAL MUSIC VIDEO", "Sơn Tùng M-TP Official")
        self.assertEqual(r_st["title"], "NƠI NÀY CÓ ANH")
        self.assertEqual(r_st["artist"], "Sơn Tùng M-TP")


if __name__ == "__main__":
    unittest.main()
