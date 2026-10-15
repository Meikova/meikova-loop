"""YouTube access through yt-dlp. Node is used as the JS runtime that recent
YouTube player versions require."""
import re
from pathlib import Path
from typing import Callable

import yt_dlp

BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "js_runtimes": {"node": {}},
}

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _entry(e: dict) -> dict | None:
    vid = e.get("id")
    if not vid or not _VIDEO_ID.match(vid):
        return None
    thumbs = e.get("thumbnails") or []
    return {
        "id": vid,
        "title": e.get("title") or vid,
        "channel": e.get("channel") or e.get("uploader") or "",
        "duration": e.get("duration"),
        "thumbnail": thumbs[-1]["url"] if thumbs else f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def search(query: str, n: int = 8) -> list[dict]:
    opts = {**BASE_OPTS, "extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return [x for x in (_entry(e) for e in info.get("entries") or []) if x]


def resolve(text: str) -> list[dict]:
    """A video URL gives one entry, a playlist URL gives all of its videos,
    and anything else is treated as a search for the best match."""
    text = text.strip()
    if not re.match(r"^https?://", text):
        return search(text, 1)
    opts = {**BASE_OPTS, "extract_flat": "in_playlist", "skip_download": True}
    # A watch URL that also carries &list= is treated as the single video.
    if "watch?" in text or "youtu.be/" in text:
        opts["noplaylist"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(text, download=False)
    if info.get("_type") == "playlist" or "entries" in info:
        return [x for x in (_entry(e) for e in info.get("entries") or []) if x]
    e = _entry(info)
    return [e] if e else []


def download(video_id: str, dest_dir: Path, on_progress: Callable[[float], None] | None = None) -> tuple[Path, dict]:
    def hook(d):
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(1.0, d.get("downloaded_bytes", 0) / total))

    dest_dir.mkdir(parents=True, exist_ok=True)
    last_error = None
    # YouTube intermittently answers 403 for one player client's stream URLs;
    # another client usually gets through.
    for client in (None, "tv", "web_safari", "mweb"):
        for stale in dest_dir.glob("source.*"):
            stale.unlink(missing_ok=True)
        opts = {
            **BASE_OPTS,
            "format": "bestaudio/best",
            "noplaylist": True,
            "outtmpl": str(dest_dir / "source.%(ext)s"),
            "progress_hooks": [hook],
            "retries": 3,
        }
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": [client]}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            path = Path(info["requested_downloads"][0]["filepath"])
            return path, _entry(info) or {}
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            if "403" not in str(e) and "Forbidden" not in str(e):
                raise
    raise last_error
