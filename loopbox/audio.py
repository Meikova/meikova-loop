import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import SAMPLE_RATE


def _ffmpeg(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def to_flac(src: Path, dst: Path) -> None:
    """Decode any source (webm/opus, m4a, ...) to the one format both the analyser and
    the browser read, so beat times refer to exactly the same samples."""
    r = _ffmpeg("-y", "-i", str(src), "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE),
                "-c:a", "flac", "-sample_fmt", "s16", str(dst))
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")


def load(path: Path) -> np.ndarray:
    """Returns float32 audio shaped (frames, 2)."""
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if sr != SAMPLE_RATE:
        raise RuntimeError(f"unexpected sample rate {sr}")
    if y.shape[1] == 1:
        y = np.repeat(y, 2, axis=1)
    return y


def integrated_loudness(path: Path) -> float:
    # framelog=verbose keeps the per-frame lines below the default log level.
    r = _ffmpeg("-i", str(path), "-af", "ebur128=framelog=verbose", "-f", "null", "-")
    found = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", r.stderr)
    if r.returncode != 0 or not found:
        raise RuntimeError(f"could not measure loudness: {r.stderr[-300:]}")
    return float(found[-1])
