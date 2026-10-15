"""On-disk track library. One folder per track: meta.json, audio.flac,
analysis.json (sent to the browser) and features.npz (kept for linking).

Track ids are YouTube video ids (11 characters); "x" and 16 hex digits for a
song from another site (download.track_id); or, for uploaded files, "u" and
the first 16 hex digits of the file's SHA-1. The same song added twice, by
anyone, is the same track."""
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

from .config import LIBRARY_DIR, PAIRS_DIR, TRANSITIONS_DIR

_lock = threading.RLock()

FINAL_STATES = {"ready", "error"}
_ID = re.compile(r"^(?:[A-Za-z0-9_-]{11}|[ux][0-9a-f]{16})$")


def valid_id(tid: str) -> bool:
    return bool(tid) and bool(_ID.match(tid))


def track_dir(tid: str) -> Path:
    if not valid_id(tid):
        raise ValueError(f"bad track id {tid!r}")
    return LIBRARY_DIR / tid


def pair_path(a: str, b: str) -> Path:
    if not (valid_id(a) and valid_id(b)):
        raise ValueError("bad track id")
    return PAIRS_DIR / a / f"{b}.json"


def touch(tid: str) -> None:
    """Marks a track as just used (what the store keeps longest)."""
    try:
        (track_dir(tid) / "used").touch()
    except OSError:
        pass


def last_used(tid: str) -> float:
    d = track_dir(tid)
    for name in ("used", "meta.json"):
        try:
            return (d / name).stat().st_mtime
        except OSError:
            continue
    return 0.0


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
        if d.is_dir() and valid_id(d.name):
            meta = read_meta(d.name)
            if meta:
                out.append(meta)
    out.sort(key=lambda m: m.get("added_at", 0))
    return out


def ready_ids() -> list[str]:
    return [m["id"] for m in list_tracks() if m.get("status") == "ready"]


def delete(tid: str) -> None:
    """Removes a track and every transition to or from it."""
    with _lock:
        shutil.rmtree(track_dir(tid), ignore_errors=True)
        transitions_path(tid).unlink(missing_ok=True)
        shutil.rmtree(PAIRS_DIR / tid, ignore_errors=True)
        for d in PAIRS_DIR.iterdir():
            (d / f"{tid}.json").unlink(missing_ok=True)


def samples_path() -> Path:
    return LIBRARY_DIR.parent / "samples.json"


def samples() -> dict:
    """The sample library: {"name", "ids"} (set with `cli samples`)."""
    s = read_json(samples_path()) or {}
    return {"name": s.get("name") or "Thư viện mẫu", "ids": [t for t in s.get("ids") or [] if valid_id(t)]}


def _tree_bytes(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def evict(max_bytes: int, keep: set[str]) -> list[str]:
    """Deletes the least recently used finished tracks not in `keep` until the
    library fits in max_bytes (with a tenth of headroom). Returns the ids."""
    sizes = {d.name: _tree_bytes(d) for d in LIBRARY_DIR.iterdir() if d.is_dir() and valid_id(d.name)}
    total = sum(sizes.values())
    if total <= max_bytes:
        return []
    gone = []
    target = 0.9 * max_bytes
    for tid in sorted(sizes, key=last_used):
        if total <= target:
            break
        meta = read_meta(tid) or {}
        if tid in keep or meta.get("status") not in FINAL_STATES:
            continue
        delete(tid)
        total -= sizes[tid]
        gone.append(tid)
    return gone
