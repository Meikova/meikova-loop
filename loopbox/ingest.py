"""Download (or take the uploaded file) -> convert -> analyse, for one track.
Run by the worker processes and by the command line. Linking the track to
other songs is a separate job (worker.py), since which songs it meets depends
on whose library it is in."""
import re
import traceback
from pathlib import Path
from typing import Callable

import soundfile as sf

from . import audio, download, library
from .config import ANALYSIS_VERSION, MAX_DURATION_S


def register(entry: dict) -> dict:
    """Adds a resolved YouTube entry to the library as queued (idempotent)."""
    meta = library.read_meta(entry["id"])
    if meta and meta.get("status") != "error":
        return meta  # ready, or on its way (perhaps for another listener)
    return library.create(
        entry["id"], source=entry.get("source", "youtube"), url=entry["url"], title=entry["title"],
        channel=entry.get("channel", ""), duration=entry.get("duration"),
        thumbnail=entry.get("thumbnail"), status="queued", stage="queued", progress=0.0, error=None,
    )


# Download sites stamp their name on files: "Easy - usesuno.com.mp3".
_WATERMARK = re.compile(r"\s*[-–|]\s*[\w-]+(\.[\w-]+)*\.(com|net|org|io|vn|me|app|to|cc)\s*$", re.I)


def register_upload(tid: str, filename: str, tmp: Path) -> dict:
    """Adds an uploaded file (already hashed into tid) as queued, or returns the
    track that the same file became before."""
    meta = library.read_meta(tid)
    if meta and meta.get("status") != "error":
        tmp.unlink(missing_ok=True)
        return meta
    d = library.track_dir(tid)
    d.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower()[:8] or ".bin"
    for stale in d.glob("source.*"):
        stale.unlink(missing_ok=True)
    tmp.replace(d / f"source{ext}")
    title = _WATERMARK.sub("", Path(filename).stem).replace("_", " ").strip() or "Bài tải lên"
    return library.create(tid, source="upload", url=None, title=title[:200], channel="", duration=None,
                          thumbnail=None, status="queued", stage="queued", progress=0.0, error=None)


def process(tid: str, on_update: Callable[[dict], None] = lambda m: None) -> str:
    """Returns the final status ("ready" or "error")."""
    def stage(name: str, progress: float, **extra):
        m = library.update(tid, stage=name, progress=round(progress, 3), **extra)
        if m:
            on_update(m)

    try:
        meta = library.read_meta(tid)
        if meta is None:
            return "error"
        if (meta.get("analysis_version") or 0) > ANALYSIS_VERSION:
            raise RuntimeError("analysed by a newer Mash ∞ Loop version: restart the server")
        if meta.get("duration") and meta["duration"] > MAX_DURATION_S:
            raise RuntimeError(f"dài hơn {MAX_DURATION_S // 60} phút")
        if not library.audio_path(tid).exists():
            d = library.track_dir(tid)
            if meta.get("source") == "upload":
                src = next(iter(d.glob("source.*")), None)
                if src is None:
                    raise RuntimeError("file tải lên không còn trên server, hãy tải lại")
            else:
                stage("downloading", 0.0, status="downloading")
                src, info = download.download(meta, d, lambda p: stage("downloading", 0.3 * p, status="downloading"))
                if info:
                    library.update(tid, title=info["title"], channel=info["channel"],
                                   duration=info.get("duration"), thumbnail=info.get("thumbnail") or meta.get("thumbnail"))
            stage("converting", 0.3, status="analyzing")
            try:
                audio.to_flac(src, library.audio_path(tid))
            except RuntimeError:
                library.audio_path(tid).unlink(missing_ok=True)
                raise RuntimeError("không đọc được file âm thanh này") from None
            src.unlink(missing_ok=True)
            seconds = sf.info(str(library.audio_path(tid))).duration
            library.update(tid, duration=round(seconds, 1))
            if seconds > MAX_DURATION_S:
                library.audio_path(tid).unlink(missing_ok=True)
                raise RuntimeError(f"dài hơn {MAX_DURATION_S // 60} phút")
            if seconds < 20:
                raise RuntimeError("ngắn quá để lặp")

        from .analysis import pipeline
        stage("analyzing", 0.32, status="analyzing")
        stats = pipeline.analyze(tid, lambda s, p: stage(s, 0.32 + 0.66 * p, status="analyzing"))
        library.update(tid, **stats)
        stage("ready", 1.0, status="ready", error=None)
        return "ready"
    except Exception as e:  # surfaced in the UI, never kills the worker
        traceback.print_exc()
        stage("error", 0.0, status="error", error=f"{type(e).__name__}: {e}" if not isinstance(e, RuntimeError) else str(e))
        return "error"
