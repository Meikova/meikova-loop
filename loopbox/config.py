from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LIBRARY_DIR = DATA_DIR / "library"
TRANSITIONS_DIR = DATA_DIR / "transitions"
WEB_DIR = ROOT / "web"

HOST = "127.0.0.1"
PORT = 8765

# Audio stored for playback and analysis: identical samples on both sides.
SAMPLE_RATE = 44100
ANALYSIS_SR = 22050
TARGET_LUFS = -14.0
MAX_DURATION_S = 15 * 60

DEVICE = "cuda"  # falls back to cpu at runtime when CUDA is unavailable

# Bump when the analysis output changes in a way that requires re-analysis.
ANALYSIS_VERSION = 5
# Bump when only the cross-track transition search changes.
TRANSITIONS_VERSION = 5

for d in (LIBRARY_DIR, TRANSITIONS_DIR):
    d.mkdir(parents=True, exist_ok=True)
