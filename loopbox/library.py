"""On-disk track library. One folder per track: meta.json, audio.flac,
analysis.json (sent to the browser) and features.npz (kept for linking)."""
import json
import os
import shutil
import threading
import time
from pathlib import Path

from .config import LIBRARY_DIR, TRANSITIONS_DIR

_lock = threading.RLock()

FINAL_STATES = {"ready", "error"}


def track_dir(tid: str) -> Path:
    return LIBRARY_DIR / tid


def audio_path(tid: str) -> Path:
    return track_dir(tid) / "audio.flac"


def analysis_path(tid: str) -> Path:
    return track_dir(tid) / "analysis.json"


def features_path(tid: str) -> Path:
    return track_dir(tid) / "features.npz"


def transitions_path(tid: str) -> Path:
    return TRANSITIONS_DIR / f"{tid}.json"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # allow_nan=False: NaN/Infinity are not JSON and would break the browser's parser.
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    os.replace(tmp, path)


def read_json(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def read_meta(tid: str) -> dict | None:
    return read_json(track_dir(tid) / "meta.json")


def create(tid: str, **fields) -> dict:
    with _lock:
        meta = read_meta(tid)
        if meta is None:
            meta = {"id": tid, "added_at": time.time(), "enabled": True}
        meta.update(fields)
        write_json(track_dir(tid) / "meta.json", meta)
        return meta


def update(tid: str, **fields) -> dict | None:
    with _lock:
        meta = read_meta(tid)
        if meta is None:
            return None
        meta.update(fields)
        write_json(track_dir(tid) / "meta.json", meta)
        return meta


def list_tracks() -> list[dict]:
    out = []
    for d in LIBRARY_DIR.iterdir():
        if d.is_dir():
            meta = read_meta(d.name)
            if meta:
                out.append(meta)
    out.sort(key=lambda m: m.get("added_at", 0))
    return out


def ready_ids() -> list[str]:
    return [m["id"] for m in list_tracks() if m.get("status") == "ready"]


def delete(tid: str) -> None:
    with _lock:
        shutil.rmtree(track_dir(tid), ignore_errors=True)
        transitions_path(tid).unlink(missing_ok=True)
