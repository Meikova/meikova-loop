import json
import os
from PIL import Image

TARGET_HEX = "#11151B"
TARGET_RGB = (17, 21, 27)

def test_loop_pwa_manifests():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    web_dir = os.path.join(base_dir, "web")

    manifest_files = [
        os.path.join(web_dir, "manifest.json"),
        os.path.join(web_dir, "site.webmanifest")
    ]

    for mf in manifest_files:
        assert os.path.exists(mf), f"Manifest file missing: {mf}"
        with open(mf, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data.get("background_color", "").upper() == TARGET_HEX
        assert data.get("theme_color", "").upper() == TARGET_HEX

        icons = data.get("icons", [])
        assert len(icons) >= 4, "Must have at least 4 icons"

        for icon in icons:
            src = icon["src"]
            assert not src.endswith(".svg"), f"SVG prohibited in manifest icons: {src}"
            assert "logo.png" not in src, f"logo.png prohibited in manifest icons: {src}"
            assert "apple-touch-icon" not in src, f"apple-touch-icon prohibited in manifest icons: {src}"

            img_path = os.path.normpath(os.path.join(web_dir, src.lstrip("/\\")))
            assert os.path.exists(img_path), f"Icon file missing: {img_path}"

            im = Image.open(img_path)
            w, h = im.size
            corners = [
                im.getpixel((0, 0)),
                im.getpixel((w - 1, 0)),
                im.getpixel((0, h - 1)),
                im.getpixel((w - 1, h - 1))
            ]

            if icon.get("purpose") == "any":
                for c in corners:
                    if im.mode == "RGBA":
                        assert c[3] == 255, f"Corner has transparency: {c}"
                        assert c[:3] == TARGET_RGB, f"Corner RGB mismatch: {c[:3]}"
                    else:
                        assert c == TARGET_RGB, f"Corner RGB mismatch: {c}"

if __name__ == "__main__":
    test_loop_pwa_manifests()
    print("test_loop_pwa_manifests: OK")
