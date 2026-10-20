import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import SAMPLE_RATE

_FFMPEG_BIN: str | None = None


def get_ffmpeg_bin() -> str:
    global _FFMPEG_BIN
    if _FFMPEG_BIN and (shutil.which(_FFMPEG_BIN) or Path(_FFMPEG_BIN).exists()):
        return _FFMPEG_BIN
    # 1. System PATH
    p = shutil.which("ffmpeg")
    if p:
        _FFMPEG_BIN = p
        return p
    # 2. Local user bin (~/.local/bin/ffmpeg)
    local_bin = Path.home() / ".local" / "bin" / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    if local_bin.exists():
        _FFMPEG_BIN = str(local_bin)
        return str(local_bin)
    # 3. imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            _FFMPEG_BIN = str(exe)
            return str(exe)
    except Exception:
        pass
    _FFMPEG_BIN = "ffmpeg"
    return "ffmpeg"


def _ffmpeg(*args: str) -> subprocess.CompletedProcess:
    bin_path = get_ffmpeg_bin()
    return subprocess.run([bin_path, "-hide_banner", "-nostdin", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def to_flac(src: Path, dst: Path) -> None:
    """Decode any source (webm/opus, m4a, ...) to the one format both the analyser and
    the browser read, so beat times refer to exactly the same samples."""
    if not src.exists():
        raise RuntimeError(f"file nguồn không tồn tại: {src}")
    if src.stat().st_size == 0:
        raise RuntimeError(f"file nguồn rỗng (0 bytes): {src}")
    r = _ffmpeg("-y", "-i", str(src), "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE),
                "-c:a", "flac", "-sample_fmt", "s16", str(dst))
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({r.returncode}): {r.stderr[-800:]}")


# What the browser is sent: an MP3 copy of the stored FLAC, ~5x smaller (192
# kbps: about 6 MB for a 4-minute song), which every browser decodes. Every
# sound goes through the same encoder, so whatever delay a browser's decoder
# leaves in is the same for all of them: songs stay on each other's beat, and
# a song and its vocal stem stay aligned for the instrumental (mix minus stem).
TRANSPORT = {"mp3": ["-c:a", "libmp3lame", "-b:a", "{br}k", "-f", "mp3"]}
BITRATE = {"audio": {"mp3": 192}, "vocals": {"mp3": 160}}


def encode(src: Path, dst: Path, fmt: str, kbps: int) -> None:
    """src (any format ffmpeg reads) -> dst in a transport format, written whole."""
    tmp = dst.with_name(dst.name + ".part")
    args = [a.replace("{br}", str(kbps)) for a in TRANSPORT[fmt]]
    r = _ffmpeg("-y", "-i", str(src), "-vn", "-ac", "2", *args, str(tmp))
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed ({r.returncode}): {r.stderr[-500:]}")
    tmp.replace(dst)


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
