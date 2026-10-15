"""Per-client limits for the hosted app, so it cannot be used as a free
download service or have its YouTube access burnt: how many visits, searches,
new songs (the ones the server must fetch and analyse), uploads and audio
files one address may ask for in a window. In memory: a restart forgives."""
import threading
import time
from collections import deque

from fastapi import HTTPException

from .config import MULTIUSER

# kind -> (requests allowed, per seconds, message)
LIMITS = {
    "session": (60, 3600, "mở trang quá nhiều lần"),
    "search": (60, 600, "tìm quá nhiều lần"),
    "new_track": (20, 3600, "thêm quá nhiều bài mới"),
    "upload": (30, 3600, "tải lên quá nhiều file"),
    "audio": (200, 3600, "tải nhạc quá nhiều lần"),
}

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = {}


def check(ip: str, kind: str, n: int = 1) -> None:
    """Counts n requests of a kind from ip, or refuses them (HTTP 429)."""
    if not MULTIUSER:
        return
    allowed, window, what = LIMITS[kind]
    now = time.time()
    with _lock:
        q = _hits.setdefault((ip, kind), deque())
        while q and now - q[0] > window:
            q.popleft()
        if len(q) + n > allowed:
            wait = int(window - (now - q[0])) + 1 if q else window
            raise HTTPException(429, f"Bạn {what}, thử lại sau {max(1, wait // 60)} phút")
        q.extend([now] * n)
        if len(_hits) > 50_000:  # forget idle addresses
            for key in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
                _hits.pop(key, None)


def room(ip: str, kind: str) -> int:
    """How many more requests of a kind ip may make right now."""
    if not MULTIUSER:
        return 1 << 30
    allowed, window, _ = LIMITS[kind]
    now = time.time()
    with _lock:
        q = _hits.get((ip, kind)) or deque()
        return max(0, allowed - sum(1 for t in q if now - t <= window))
