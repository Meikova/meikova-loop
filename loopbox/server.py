"""Local web server: python -m loopbox.server  ->  http://127.0.0.1:8765"""
import argparse
import webbrowser

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import download, ingest, library, worker
from .config import HOST, PORT, WEB_DIR

app = FastAPI(title="Mash ∞ Loop")


class AddRequest(BaseModel):
    text: str


class PatchRequest(BaseModel):
    enabled: bool | None = None


def _public(m: dict) -> dict:
    keys = ("id", "title", "channel", "duration", "thumbnail", "url", "status", "stage", "progress",
            "error", "enabled", "bpm", "key", "camelot", "jumps", "beats", "added_at")
    return {k: m.get(k) for k in keys}


def _ready(tid: str) -> dict:
    m = library.read_meta(tid)
    if not m:
        raise HTTPException(404, "unknown track")
    if m.get("status") != "ready":
        raise HTTPException(409, "track not analysed yet")
    return m


@app.get("/api/tracks")
def tracks():
    return {"tracks": [_public(m) for m in library.list_tracks()], "worker": worker.status(),
            "stale_server": worker.stale()}


@app.get("/api/search")
def search(q: str):
    try:
        return {"results": download.search(q, 8)}
    except Exception as e:
        raise HTTPException(502, f"YouTube search failed: {e}")


@app.post("/api/tracks")
def add(req: AddRequest):
    try:
        entries = download.resolve(req.text)
    except Exception as e:
        raise HTTPException(502, f"could not resolve: {e}")
    if not entries:
        raise HTTPException(404, "nothing found")
    added = []
    for e in entries:
        meta = ingest.register(e)
        if meta.get("status") != "ready":
            worker.enqueue("ingest", e["id"])
        added.append(_public(meta))
    return {"added": added}


@app.patch("/api/tracks/{tid}")
def patch(tid: str, req: PatchRequest):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    m = library.update(tid, **fields)
    if not m:
        raise HTTPException(404, "unknown track")
    return _public(m)


@app.delete("/api/tracks/{tid}")
def delete(tid: str):
    library.delete(tid)
    return {"deleted": tid}


@app.post("/api/tracks/{tid}/reanalyze")
def reanalyze(tid: str):
    if not library.read_meta(tid):
        raise HTTPException(404, "unknown track")
    library.update(tid, status="queued", stage="queued", progress=0.0)
    worker.enqueue("ingest", tid)
    return {"queued": tid}


@app.post("/api/relink")
def relink():
    worker.enqueue("relink")
    return {"queued": True}


@app.get("/api/tracks/{tid}/analysis")
def analysis(tid: str):
    _ready(tid)
    return FileResponse(library.analysis_path(tid), media_type="application/json",
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/tracks/{tid}/audio")
def audio(tid: str):
    _ready(tid)
    return FileResponse(library.audio_path(tid), media_type="audio/flac")


@app.get("/api/tracks/{tid}/transitions")
def transitions(tid: str):
    _ready(tid)
    from .analysis import transitions as tr
    ready = {m["id"] for m in library.list_tracks() if m.get("status") == "ready"}
    return {"items": [t for t in tr.read(tid) if t["to"] in ready]}


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="open the browser")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    worker.start()
    if args.open:
        webbrowser.open(f"http://{HOST}:{args.port}")
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
