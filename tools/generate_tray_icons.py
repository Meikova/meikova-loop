"""Generates high-DPI tray icons for Meikova Loop matching ambient-dark gold theme."""
import math
from pathlib import Path
from PIL import Image, ImageDraw

SIZE = 128
TARGET_SIZE = 32

GOLD = (245, 158, 11, 255)        # Brand accent #f59e0b
GOLD_LIGHT = (251, 191, 36, 255)  # #fbbf24
IVORY = (240, 238, 233, 255)      # Soft warm white
GREEN = (52, 211, 153, 255)       # Emerald #34d399
RED = (248, 113, 113, 255)        # Soft red #f87171
MUTED = (156, 163, 175, 255)      # Neutral grey


def save_icon(img: Image.Image, out_dir: Path, name: str):
    res = img.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)
    path = out_dir / f"{name}.png"
    res.save(path, "PNG")
    print(f"Generated {path}")


def make_logo(out_dir: Path):
    """Infinity curve with orbital glow dot."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    scale = 44
    cx, cy = SIZE // 2, SIZE // 2
    points = []
    for step in range(360):
        t = math.radians(step)
        denom = 1 + (math.sin(t) ** 2)
        x = cx + (scale * math.cos(t)) / denom
        y = cy + (scale * math.sin(t) * math.cos(t) * 1.5) / denom
        points.append((x, y))

    for i in range(len(points)):
        p1 = points[i]
        p2 = points[(i + 1) % len(points)]
        d.line([p1, p2], fill=GOLD, width=13)

    # Orbital accent dot on top-right loop
    d.ellipse([78, 30, 96, 48], fill=GOLD_LIGHT)
    save_icon(img, out_dir, "logo")


def make_window(out_dir: Path):
    """Desktop player window with audio waveform."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([18, 22, 110, 106], radius=14, outline=GOLD, width=10)
    d.line([18, 50, 110, 50], fill=GOLD, width=8)
    d.ellipse([30, 33, 38, 41], fill=GOLD)
    d.ellipse([46, 33, 54, 41], fill=GOLD)
    # Audio waveform bars in window body
    d.line([36, 88, 36, 72], fill=IVORY, width=7)
    d.line([50, 94, 50, 62], fill=GOLD_LIGHT, width=7)
    d.line([64, 98, 64, 58], fill=GOLD_LIGHT, width=7)
    d.line([78, 92, 78, 66], fill=GOLD_LIGHT, width=7)
    d.line([92, 86, 92, 74], fill=IVORY, width=7)
    save_icon(img, out_dir, "window")


def make_browser(out_dir: Path):
    """Globe / Web interface icon."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([18, 18, 110, 110], outline=GOLD, width=10)
    d.line([18, 64, 110, 64], fill=GOLD, width=8)
    d.ellipse([40, 18, 88, 110], outline=GOLD, width=8)
    save_icon(img, out_dir, "browser")


def make_folder(out_dir: Path):
    """Audio data folder with musical note."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([18, 40, 110, 102], radius=10, outline=GOLD, width=10)
    d.line([(18, 40), (18, 30), (52, 30), (64, 40), (110, 40)], fill=GOLD, width=10)
    # Musical note inside folder
    d.ellipse([44, 76, 58, 88], fill=IVORY)
    d.line([56, 56, 56, 82], fill=IVORY, width=7)
    d.line([56, 56, 76, 50], fill=IVORY, width=7)
    d.ellipse([68, 70, 82, 82], fill=IVORY)
    d.line([80, 50, 80, 76], fill=IVORY, width=7)
    save_icon(img, out_dir, "folder")


def make_autostart(out_dir: Path, is_on: bool):
    """Rocket / Power startup icon."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = GREEN if is_on else MUTED
    # Power circle
    d.arc([24, 24, 104, 104], start=120, end=420, fill=color, width=10)
    # Vertical line
    d.line([64, 18, 64, 60], fill=color, width=10)
    if is_on:
        # Checkmark badge in bottom-right
        d.ellipse([70, 70, 116, 116], fill=(14, 16, 21, 255))
        d.ellipse([72, 72, 114, 114], outline=GREEN, width=6)
        d.line([82, 92, 90, 102], fill=GREEN, width=7)
        d.line([90, 102, 104, 84], fill=GREEN, width=7)
    save_icon(img, out_dir, "autostart_on" if is_on else "autostart")


def make_refresh(out_dir: Path):
    """Reload loop icon."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.arc([24, 24, 104, 104], start=45, end=325, fill=GOLD, width=10)
    d.polygon([(92, 20), (114, 40), (86, 52)], fill=GOLD)
    save_icon(img, out_dir, "refresh")


def make_quit(out_dir: Path):
    """Standby / quit icon in coral red."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.arc([24, 24, 104, 104], start=130, end=410, fill=RED, width=10)
    d.line([64, 18, 64, 60], fill=RED, width=10)
    save_icon(img, out_dir, "quit")


def generate_all(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    make_logo(out_dir)
    make_window(out_dir)
    make_browser(out_dir)
    make_folder(out_dir)
    make_autostart(out_dir, is_on=False)
    make_autostart(out_dir, is_on=True)
    make_refresh(out_dir)
    make_quit(out_dir)
    print("All tray icons generated successfully!")


if __name__ == "__main__":
    from loopbox.config import WEB_DIR
    generate_all(WEB_DIR / "img" / "tray")
