from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
svg_path = (ROOT / "web" / "img" / "favicon.svg").as_uri()
png_path = ROOT / "web" / "img" / "icon_512.png"
ico_path = ROOT / "web" / "img" / "icon.ico"

def main():
    print("Rendering SVG to 512x512 PNG via Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 512, "height": 512})
        page.goto(svg_path)
        # Target the svg element directly
        svg = page.locator("svg")
        svg.screenshot(path=str(png_path), omit_background=True)
        browser.close()

    img = Image.open(png_path)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)
    print(f"SUCCESS: Generated {ico_path} ({ico_path.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
