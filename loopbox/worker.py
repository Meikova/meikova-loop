"""Single background worker: analysis uses the GPU, so jobs run one at a time."""
import queue
import threading
import traceback

from . import ingest, library
from .config import ANALYSIS_VERSION, TRANSITIONS_DIR, TRANSITIONS_VERSION

_jobs: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
_pending: set[tuple[str, str | None]] = set()
_lock = threading.Lock()
_state = {"current": None, "relink": None}


def enqueue(kind: str, tid: str | None = None) -> None:
    job = (kind, tid)
    with _lock:
        if job in _pending:
            return
        _pending.add(job)
    _jobs.put(job)


def status() -> dict:
    with _lock:
        return {"current": _state["current"], "queued": len(_pending), "relink": _state["relink"]}


def _run() -> None:
    while True:
        kind, tid = _jobs.get()
        with _lock:
            _state["current"] = {"kind": kind, "id": tid}
        try:
            if kind == "ingest":
                ingest.process(tid)
            elif kind == "relink":
                from .analysis import transitions

                def progress(i, n):
                    _state["relink"] = {"done": i, "total": n}

                transitions.relink_all(progress)
                _state["relink"] = None
                _write_marker()
        except Exception:
            traceback.print_exc()
        finally:
            with _lock:
                _pending.discard((kind, tid))
                _state["current"] = None


def _marker_path():
    return TRANSITIONS_DIR / "_version.json"


def _write_marker() -> None:
    from .analysis import transitions
    transitions.write_marker()


def stale() -> bool:
    """True when the data on disk was written by newer code than this process
    runs: the server was started before an update and must be restarted."""
    if (library.read_json(_marker_path()) or {}).get("version", 0) > TRANSITIONS_VERSION:
        return True
    return any((m.get("analysis_version") or 0) > ANALYSIS_VERSION for m in library.list_tracks())


def start() -> None:
    """Resumes interrupted work and upgrades stale analyses on startup."""
    for m in library.list_tracks():
        stale = m.get("status") == "ready" and m.get("analysis_version") != ANALYSIS_VERSION
        if m.get("status") not in library.FINAL_STATES or stale:
            if stale:
                library.update(m["id"], status="queued", stage="queued")
            enqueue("ingest", m["id"])
    marker = library.read_json(_marker_path()) or {}
    if marker.get("version") != TRANSITIONS_VERSION and library.ready_ids():
        enqueue("relink")
    elif not marker:
        _write_marker()
    threading.Thread(target=_run, name="loopbox-worker", daemon=True).start()
