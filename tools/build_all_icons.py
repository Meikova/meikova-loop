"""Generate crisp, high-resolution mobile icons for iOS, Android PWA, and Desktop."""
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "web" / "img"

SVG_CONTENT_512 = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <rect width="512" height="512" fill="#16120e"/>
  <path d="M256 256 C 312 168, 432 168, 432 256 C 432 344, 312 344, 256 256 C 200 168, 80 168, 80 256 C 80 344, 200 344, 256 256 Z"
        fill="none" stroke="#f2b45a" stroke-width="44.8" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="371.2" cy="198.4" r="33.6" fill="#fbd79a"/>
</svg>"""

def main():
    temp_svg = IMG_DIR / "temp_icon_512.svg"
    temp_svg.write_text(SVG_CONTENT_512, encoding="utf-8")
    
    icon_512_path = IMG_DIR / "icon_512.png"
    icon_192_path = IMG_DIR / "icon-192.png"
    apple_icon_path = IMG_DIR / "apple-touch-icon.png"
    ico_path = IMG_DIR / "icon.ico"
    
    print("Rendering 512x512 SVG in Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 512, "height": 512}, device_scale_factor=2)
        page.goto(temp_svg.resolve().as_uri())
        svg = page.locator("svg")
        svg.screenshot(path=str(icon_512_path), omit_background=False)
        browser.close()
    
    temp_svg.unlink(missing_ok=True)
    
    # Resize with high-quality Lanczos resampling
    img512 = Image.open(icon_512_path)
    if img512.size != (512, 512):
        img512 = img512.resize((512, 512), Image.Resampling.LANCZOS)
        img512.save(icon_512_path, "PNG", optimize=True)
        
    img192 = img512.resize((192, 192), Image.Resampling.LANCZOS)
    img192.save(icon_192_path, "PNG", optimize=True)
    print(f"Generated {icon_192_path}")

    img180 = img512.resize((180, 180), Image.Resampling.LANCZOS)
    img180.save(apple_icon_path, "PNG", optimize=True)
    print(f"Generated {apple_icon_path}")

    # Generate multi-res Windows ICO
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img512.save(ico_path, format="ICO", sizes=sizes)
    print(f"Generated {ico_path}")

if __name__ == "__main__":
    main()
