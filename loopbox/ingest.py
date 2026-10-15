"""Download -> convert -> analyse -> link, for one track. Used by the background
worker and by the command line."""
import traceback
from typing import Callable

from . import audio, download, library
from .config import ANALYSIS_VERSION, MAX_DURATION_S


def register(entry: dict) -> dict:
    """Adds a resolved YouTube entry to the library as queued (idempotent)."""
    meta = library.read_meta(entry["id"])
    if meta and meta.get("status") == "ready":
        return meta
    return library.create(
        entry["id"], source="youtube", url=entry["url"], title=entry["title"],
        channel=entry.get("channel", ""), duration=entry.get("duration"),
        thumbnail=entry.get("thumbnail"), status="queued", stage="queued", progress=0.0, error=None,
    )


def process(tid: str, on_update: Callable[[dict], None] = lambda m: None) -> None:
    def stage(name: str, progress: float, **extra):
        m = library.update(tid, stage=name, progress=round(progress, 3), **extra)
        if m:
            on_update(m)

    try:
        meta = library.read_meta(tid)
        if meta is None:
            return
        if (meta.get("analysis_version") or 0) > ANALYSIS_VERSION:
            raise RuntimeError("analysed by a newer Mash ∞ Loop version: restart the server")
        if meta.get("duration") and meta["duration"] > MAX_DURATION_S:
            raise RuntimeError(f"longer than {MAX_DURATION_S // 60} minutes")
        if not library.audio_path(tid).exists():
            stage("downloading", 0.0, status="downloading")
            src, info = download.download(tid, library.track_dir(tid),
                                          lambda p: stage("downloading", 0.3 * p, status="downloading"))
            if info:
                library.update(tid, title=info["title"], channel=info["channel"],
                               duration=info.get("duration"), thumbnail=info.get("thumbnail"))
            stage("converting", 0.3, status="analyzing")
            audio.to_flac(src, library.audio_path(tid))
            src.unlink(missing_ok=True)

        from .analysis import pipeline
        stage("analyzing", 0.32, status="analyzing")
        stats = pipeline.analyze(tid, lambda s, p: stage(s, 0.32 + 0.6 * p, status="analyzing"))
        library.update(tid, **stats)

        stage("linking", 0.95, status="linking")
        from .analysis import transitions
        transitions.link_track(tid)
        stage("ready", 1.0, status="ready", error=None)
    except Exception as e:  # surfaced in the UI, never kills the worker
        traceback.print_exc()
        stage("error", 0.0, status="error", error=f"{type(e).__name__}: {e}")
