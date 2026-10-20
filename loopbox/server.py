"""Web server: python -m loopbox.server [--open] [--host H] [--port P]

Personal by default (http://127.0.0.1:8765, one library on disk). With
MASHLOOP_MULTIUSER=1 every visit gets a library of its own (X-Session header)
over a shared store of songs; see sessions.py."""
import argparse
import hashlib
import os
import tempfile
import threading
import webbrowser
import zipfile
import json
from pathlib import Path
from urllib.parse import unquote

import base64

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, download, ingest, library, ratelimit, sessions, worker
from .audio import BITRATE as SOUND_KBPS
from .audio import encode as encode_sound
from .config import AUDIO_TTL_S, DATA_DIR, HOST, MAX_DURATION_S, MAX_PLAYLIST, MAX_SESSION_TRACKS, MAX_UPLOAD_MB, MULTIUSER, PORT, \
    WEB_DIR

# Songs waiting to be fetched and analysed, all listeners together: past this
# the server says it is busy rather than queueing for hours.
MAX_BACKLOG = 60

app = FastAPI(title="Mash ∞ Loop", docs_url=None if MULTIUSER else "/docs", redoc_url=None,
              openapi_url=None if MULTIUSER else "/openapi.json")


class AddRequest(BaseModel):
    text: str | None = None
    ids: list[str] | None = None  # songs of a library being restored after a server restart


class PatchRequest(BaseModel):
    enabled: bool | None = None


class BatchRequest(BaseModel):
    ids: list[str]
    action: str  # "enable", "disable", "delete"


class LocalIngestRequest(BaseModel):
    paths: list[str]


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class GoogleAuthRequest(BaseModel):
    credential: str


class SyncLibraryRequest(BaseModel):
    track_ids: list[str] | None = None
    off_ids: list[str] | None = None
    playlists: list[dict] | None = None
    favorites: list[str] | None = None
    settings: dict | None = None
    merge_tracks: bool = False


def get_user_from_headers(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
) -> dict | None:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_user_token:
        token = x_user_token.strip()
    if token:
        return auth.validate_token(token)
    return None


def view_of(
    x_session: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
) -> sessions.View:
    user = get_user_from_headers(authorization, x_user_token)
    if user:
        return sessions.get_for_user(user["id"])
    v = sessions.get(x_session)
    if v is None:
        raise HTTPException(410, "session expired")
    return v


@app.get("/api/health")
def health():
    return {"status": "ok", "multiuser": MULTIUSER}


SETTINGS_FILE = DATA_DIR / "settings.json"


@app.get("/api/settings")
def get_settings():
    res = {}
    if SETTINGS_FILE.exists():
        try:
            res = json.loads(SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            pass
    res["max_duration_s"] = MAX_DURATION_S
    return res


@app.post("/api/settings")
async def save_settings(request: Request):
    try:
        data = await request.json()
        SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(400, str(e))


def _public(m: dict) -> dict:
    keys = ("id", "title", "channel", "duration", "thumbnail", "url", "status", "stage", "progress",
            "error", "enabled", "bpm", "key", "camelot", "jumps", "beats", "added_at", "mood", "source", "credit")
    out = {k: m.get(k) for k in keys}
    # A vocal stem lets the player hand over one layer at a time.
    out["stems"] = library.valid_id(m.get("id") or "") and library.has_vocals(m["id"])
    return out


def _meta(tid: str) -> dict:
    m = library.read_meta(tid) if library.valid_id(tid) else None
    if not m:
        raise HTTPException(404, "unknown track")
    return m


def _ready(tid: str) -> dict:
    m = _meta(tid)
    if m.get("status") != "ready":
        raise HTTPException(409, "track not analysed yet")
    return m


def _ip(request: Request) -> str:
    # Prefer the leftmost client address from X-Forwarded-For when behind reverse proxies
    xff = request.headers.get("x-forwarded-for")
    if xff:
        client = xff.split(",")[0].strip()
        if client:
            return client
    return request.client.host if request.client else "?"



def _is_new(tid: str) -> bool:
    """True when adding tid means fetching it, and analysing it unless it was
    analysed before (it is not in the store, its sound was deleted after going
    unused, or it is not on its way for someone else)."""
    m = library.read_meta(tid)
    return not m or m.get("status") == "error" or _dropped(m)


def _dropped(m: dict) -> bool:
    return m.get("status") == "ready" and not library.has_audio(m["id"])


def _lost(tid: str) -> bool:
    """An uploaded song whose sound was deleted: only uploading the file again brings it back."""
    m = library.read_meta(tid) or {}
    return bool(m) and _dropped(m) and m.get("source") == "upload"


def _restore(tid: str) -> bool:
    """Queues the sound of a song whose audio was deleted after going unused to
    be fetched again from its link (the analysis is kept, so it is not redone).
    False for an uploaded song: only uploading the file again brings it back."""
    m = library.read_meta(tid) or {}
    if not m or not _dropped(m):
        return True
    if m.get("source") == "upload":
        return False
    library.update(tid, status="queued", stage="queued", progress=0.0, error=None)
    return True


def _admit(ip: str, v: sessions.View, ids: list[str]) -> tuple[list[str], str | None]:
    """Of the songs asked for, the ones this library has room for and this
    client may still bring in new. Returns them and a note on what was left out."""
    have = set(v.track_ids())
    samples = set(library.samples()["ids"])
    fresh = [t for t in dict.fromkeys(ids) if t not in have]
    room = v.room()
    keep, note = [], None
    for t in fresh:
        if t not in samples:
            if room <= 0:
                note = f"Thư viện tối đa {MAX_SESSION_TRACKS} bài: phần còn lại không được thêm"
                break
            room -= 1
        keep.append(t)
    new = [t for t in keep if _is_new(t)]
    if new:
        allowed = min(ratelimit.room(ip, "new_track"), max(0, MAX_BACKLOG - worker.backlog()))
        if allowed <= 0:
            if worker.backlog() >= MAX_BACKLOG:
                raise HTTPException(503, "Server đang bận phân tích nhiều bài, thử lại sau ít phút")
            ratelimit.check(ip, "new_track", len(new))  # raises 429 with the wait
        if len(new) > allowed:
            drop = set(new[allowed:])
            keep = [t for t in keep if t not in drop]
            new = new[:allowed]
            note = "Một số bài chưa được thêm: bạn đã thêm nhiều bài mới, thử lại sau"
        ratelimit.check(ip, "new_track", len(new))
    return keep, note


def _add(v: sessions.View, tid: str, added: list) -> None:
    try:
        v.add(tid)
    except sessions.LimitError as e:
        raise HTTPException(409, str(e))
    _restore(tid)
    m = library.read_meta(tid) or {}
    if m.get("status") == "ready":
        v.link(tid)
    else:
        worker.enqueue_ingest(tid)
    added.append(_public({**m, "enabled": True}))


@app.post("/api/session")
def new_session(
    request: Request,
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    ratelimit.check(_ip(request), "session")
    user = get_user_from_headers(authorization, x_user_token)
    if user:
        v = sessions.get_for_user(user["id"])
        return {
            "sid": v.id,
            "multiuser": MULTIUSER,
            "k": base64.b64encode(v.key).decode() if v.key else None,
            "user": user,
            "limits": {
                "tracks": MAX_SESSION_TRACKS if MULTIUSER else None,
                "playlist": MAX_PLAYLIST,
                "upload_mb": MAX_UPLOAD_MB,
                "audio_ttl_h": AUDIO_TTL_S // 3600 if MULTIUSER else None,
                "max_duration_s": MAX_DURATION_S,
            },
        }
    v = sessions.create()
    return {
        "sid": v.id,
        "multiuser": MULTIUSER,
        "k": base64.b64encode(v.key).decode() if v.key else None,
        "limits": {
            "tracks": MAX_SESSION_TRACKS if MULTIUSER else None,
            "playlist": MAX_PLAYLIST,
            "upload_mb": MAX_UPLOAD_MB,
            "audio_ttl_h": AUDIO_TTL_S // 3600 if MULTIUSER else None,
            "max_duration_s": MAX_DURATION_S,
        },
    }


@app.get("/api/auth/config")
def auth_config():
    return {"google_client_id": auth.get_google_client_id()}


@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    try:
        res = auth.register_user(req.username, req.password, req.display_name or "")
        user = res["user"]
        token = res["token"]
        library_data = auth.get_user_library(user["id"])
        return {"status": "ok", "user": user, "token": token, "library": library_data}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Registration failed: {e}")


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    try:
        res = auth.authenticate_user(req.username, req.password)
        if not res:
            raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không chính xác")
        user = res["user"]
        token = res["token"]
        library_data = auth.get_user_library(user["id"])
        return {"status": "ok", "user": user, "token": token, "library": library_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Login failed: {e}")


@app.post("/api/auth/google")
def auth_google(req: GoogleAuthRequest):
    try:
        res = auth.google_auth(req.credential)
        user = res["user"]
        token = res["token"]
        library_data = auth.get_user_library(user["id"])
        return {"status": "ok", "user": user, "token": token, "library": library_data}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Google authentication failed: {e}")


@app.get("/api/auth/google/start")
def auth_google_start(request: Request):
    host_header = request.headers.get("host", f"127.0.0.1:{PORT}")
    proto = "https" if "hf.space" in host_header else "http"
    redirect_uri = f"{proto}://{host_header}/api/auth/google/callback"
    auth_url = auth.get_google_auth_url(redirect_uri)
    return {"auth_url": auth_url, "redirect_uri": redirect_uri}


@app.get("/api/auth/google/callback")
def auth_google_callback(request: Request, code: str | None = None, error: str | None = None):
    if error:
        return HTMLResponse(f"<h3 style='color:#ef4444;background:#181b22;padding:20px;font-family:sans-serif;'>Lỗi đăng nhập Google: {error}</h3>", status_code=400)
    if not code:
        return HTMLResponse("<h3 style='color:#ef4444;background:#181b22;padding:20px;font-family:sans-serif;'>Thiếu mã xác thực từ Google</h3>", status_code=400)
    host_header = request.headers.get("host", f"127.0.0.1:{PORT}")
    proto = "https" if "hf.space" in host_header else "http"
    redirect_uri = f"{proto}://{host_header}/api/auth/google/callback"
    try:
        res = auth.exchange_google_code(code, redirect_uri)
        token = res["token"]
        user = res["user"]
        user_name = user.get("display_name") or user.get("username")
        html = f"""<!doctype html>
        <html>
        <head>
          <meta charset="utf-8"/>
          <title>MashLoop // Đăng nhập thành công</title>
          <style>
            body {{ background: #0e1015; color: #f0eee9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .card {{ background: #181b22; border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 16px; padding: 36px 32px; text-align: center; max-width: 380px; box-shadow: 0 20px 50px rgba(0,0,0,0.6); }}
            h2 {{ color: #f59e0b; margin: 0 0 10px; font-size: 22px; }}
            p {{ color: #a1a1aa; font-size: 14px; line-height: 1.5; margin: 0 0 24px; }}
            .btn {{ display: inline-block; background: #f59e0b; color: #0e1015; font-weight: 600; padding: 10px 24px; border-radius: 999px; text-decoration: none; cursor: pointer; border: none; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h2>Đăng nhập thành công!</h2>
            <p>Chào mừng <b>{user_name}</b>.<br>Bạn có thể đóng tab này và quay lại ứng dụng MashLoop.</p>
            <button class="btn" onclick="window.close()">Đóng cửa sổ</button>
          </div>
          <script>
            try {{
              localStorage.setItem('mashloop:token', '{token}');
              localStorage.setItem('mashloop:login_event', JSON.stringify({{ token: '{token}', user: {json.dumps(user)}, time: Date.now() }}));
              if (window.opener) {{
                window.opener.postMessage({{ type: 'MASHLOOP_AUTH_SUCCESS', token: '{token}', user: {json.dumps(user)} }}, '*');
              }}
            }} catch(e) {{}}
            setTimeout(() => window.close(), 2500);
          </script>
        </body>
        </html>"""
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h3 style='color:#ef4444;background:#181b22;padding:20px;font-family:sans-serif;'>Xác thực Google thất bại: {e}</h3>", status_code=500)



@app.get("/api/auth/me")
def auth_me(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user = get_user_from_headers(authorization, x_user_token)
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")
    library_data = auth.get_user_library(user["id"])
    return {"user": user, "library": library_data}


@app.post("/api/auth/logout")
def auth_logout(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_user_token:
        token = x_user_token.strip()
    if token:
        auth.delete_session(token)
    return {"status": "ok"}


@app.get("/api/user/sync")
def user_sync_get(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user = get_user_from_headers(authorization, x_user_token)
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")
    return {"library": auth.get_user_library(user["id"])}


@app.post("/api/user/sync")
def user_sync_post(
    req: SyncLibraryRequest,
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user = get_user_from_headers(authorization, x_user_token)
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")
    updated = auth.save_user_library(
        user["id"],
        track_ids=req.track_ids,
        off_ids=req.off_ids,
        playlists=req.playlists,
        favorites=req.favorites,
        settings=req.settings,
        merge_tracks=req.merge_tracks,
    )
    v = sessions.get_for_user(user["id"])
    if hasattr(v, "reload_from_db"):
        v.reload_from_db()
    return {"status": "ok", "library": updated}



@app.get("/api/tracks")
def tracks(v: sessions.View = Depends(view_of)):
    metas = v.metas()
    return {"tracks": [_public(m) for m in metas], "worker": worker.status([m["id"] for m in metas]),
            "links": v.link_ver, "room": v.room() if MULTIUSER else None, "stale_server": worker.stale(metas),
            "max_duration_s": MAX_DURATION_S}


@app.get("/api/search")
def search(q: str, request: Request, v: sessions.View = Depends(view_of)):
    ratelimit.check(_ip(request), "search")
    try:
        return {"results": download.search(q[:200], 8)}
    except Exception as e:
        raise HTTPException(502, f"YouTube search failed: {e}")


@app.post("/api/tracks")
def add(req: AddRequest, request: Request, v: sessions.View = Depends(view_of)):
    ip = _ip(request)
    added: list = []
    if req.ids:  # songs already on the server (a restored library, the samples)
        ids = [t for t in req.ids[:MAX_SESSION_TRACKS * 3] if library.valid_id(t) and library.read_meta(t)]
        gone = [t for t in ids if _lost(t)]
        keep, note = _admit(ip, v, [t for t in ids if t not in gone])
        for tid in keep:
            _add(v, tid, added)
        if gone:
            note = "; ".join(filter(None, [note, f"{len(gone)} bài tải lên đã được xoá khỏi server sau "
                                                f"{AUDIO_TTL_S // 3600} giờ không ai nghe: hãy tải lại file"]))
        return {"added": added, "note": note}
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "nothing to add")
    if v.room() <= 0:
        raise HTTPException(409, f"Thư viện đã đủ {MAX_SESSION_TRACKS} bài: bỏ bớt một bài để thêm bài khác")
    if not text.startswith(("http://", "https://")):
        ratelimit.check(ip, "search")
    try:
        entries = download.resolve(text)
    except ValueError as e:
        raise HTTPException(400, download.clean_error(e))
    except Exception as e:
        raise HTTPException(502, download.clean_error(e))
    if not entries:
        raise HTTPException(404, "nothing found")
    by_id = {e["id"]: e for e in entries}
    keep, note = _admit(ip, v, list(by_id))
    for tid in keep:
        ingest.register(by_id[tid])
        _add(v, tid, added)
    return {"added": added, "note": note}


AUDIO_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".oga", ".opus", ".webm", ".aiff", ".aif", ".wma"}


def _tmp_dir() -> Path:
    d = DATA_DIR / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _unzip(path: Path, v: sessions.View, added: list, ip: str) -> str | None:
    """Every audio file in a zip becomes a track (a playlist exported from
    somewhere, a folder of songs), as many as the library has room for;
    anything else in it is ignored. Returns a note on what was left out."""
    limit = MAX_UPLOAD_MB * 1024 * 1024
    note = None
    with zipfile.ZipFile(path) as z:
        members = [i for i in z.infolist()
                   if not i.is_dir() and Path(i.filename).suffix.lower() in AUDIO_EXT
                   and not Path(i.filename).name.startswith("._")]
        if not members:
            raise HTTPException(400, "trong file zip không có bài nhạc nào")
        room = min(v.room(), ratelimit.room(ip, "upload"))
        if len(members) > room:
            note = f"Chỉ thêm {room} bài đầu: thư viện tối đa {MAX_SESSION_TRACKS} bài" if room else None
            members = members[:room]
            if not members:
                raise HTTPException(409, f"Thư viện đã đủ {MAX_SESSION_TRACKS} bài: bỏ bớt một bài để thêm bài khác")
        if sum(i.file_size for i in members) > 4 * limit:
            raise HTTPException(413, "file zip giải nén ra quá lớn")
        ratelimit.check(ip, "upload", len(members))
        for info in members:
            fd, name = tempfile.mkstemp(dir=_tmp_dir())
            tmp, h, size = Path(name), hashlib.sha1(), 0
            try:
                with z.open(info) as src, os.fdopen(fd, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        size += len(chunk)
                        if size > limit:
                            raise HTTPException(413, f"{Path(info.filename).name} lớn hơn {MAX_UPLOAD_MB} MB")
                        h.update(chunk)
                        dst.write(chunk)
                tid = "u" + h.hexdigest()[:16]
                if _is_new(tid) and worker.backlog() >= MAX_BACKLOG:
                    raise HTTPException(503, "Server đang bận phân tích nhiều bài, thử lại sau ít phút")
                ingest.register_upload(tid, Path(info.filename).name, tmp)
            finally:
                tmp.unlink(missing_ok=True)
            _add(v, tid, added)
    return note


@app.post("/api/upload")
async def upload(request: Request, v: sessions.View = Depends(view_of), x_filename: str = Header(default="upload")):
    """The file itself is the request body; its name comes URL-encoded in X-Filename.
    Identical files, from anyone, become the same track. A zip adds every song in it."""
    ip = _ip(request)
    if v.room() <= 0:
        raise HTTPException(409, f"Thư viện đã đủ {MAX_SESSION_TRACKS} bài: bỏ bớt một bài để thêm bài khác")
    if ratelimit.room(ip, "upload") <= 0:
        ratelimit.check(ip, "upload")
    limit = MAX_UPLOAD_MB * 1024 * 1024
    fd, name = tempfile.mkstemp(dir=_tmp_dir())
    tmp = Path(name)
    h, size = hashlib.sha1(), 0
    added: list = []
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"file lớn hơn {MAX_UPLOAD_MB} MB")
                h.update(chunk)
                f.write(chunk)
        if size < 4096:
            raise HTTPException(400, "file trống hoặc quá nhỏ")
        if zipfile.is_zipfile(tmp):
            note = _unzip(tmp, v, added, ip)
            return {"added": added, "note": note}
        tid = "u" + h.hexdigest()[:16]
        if _is_new(tid) and worker.backlog() >= MAX_BACKLOG:
            raise HTTPException(503, "Server đang bận phân tích nhiều bài, thử lại sau ít phút")
        ratelimit.check(ip, "upload")
        ingest.register_upload(tid, unquote(x_filename)[:200], tmp)
    finally:
        tmp.unlink(missing_ok=True)
    _add(v, tid, added)
    return {"added": added}


@app.post("/api/desktop/ingest_local")
def ingest_local(req: LocalIngestRequest, request: Request, v: sessions.View = Depends(view_of)):
    """Ingest local audio files from the user's computer directly into the library.
    Restricted to localhost/desktop client."""
    ip = _ip(request)
    if ip not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(403, "Local ingestion only available on desktop/local host")
    if v.room() <= 0:
        raise HTTPException(409, f"Thư viện đã đủ {MAX_SESSION_TRACKS} bài: bỏ bớt một bài để thêm bài khác")

    room = v.room()
    valid_paths = []
    for p_str in req.paths:
        p = Path(p_str)
        if p.is_file() and p.suffix.lower() in AUDIO_EXT and not p.name.startswith("._"):
            valid_paths.append(p)
            if len(valid_paths) >= room:
                break

    if not valid_paths:
        raise HTTPException(400, "Không tìm thấy file nhạc hợp lệ")

    added = []
    limit = MAX_UPLOAD_MB * 4 * 1024 * 1024
    for p in valid_paths:
        try:
            if p.stat().st_size > limit or p.stat().st_size < 4096:
                continue
            h = hashlib.sha1()
            fd, tmp_name = tempfile.mkstemp(dir=_tmp_dir())
            tmp = Path(tmp_name)
            try:
                with p.open("rb") as src, os.fdopen(fd, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        h.update(chunk)
                        dst.write(chunk)
                tid = "u" + h.hexdigest()[:16]
                if _is_new(tid) and worker.backlog() >= MAX_BACKLOG:
                    continue
                ingest.register_upload(tid, p.name[:200], tmp)
                _add(v, tid, added)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception:
            continue

    note = f"Đã thêm {len(added)} bài từ máy tính" if added else "Không thể đọc các file đã chọn"
    return {"added": added, "note": note}


@app.get("/api/samples")
def samples():
    """The sample libraries, by theme: songs kept analysed on the server that any
    library can take in whole."""
    out = []
    for lib in library.samples()["libraries"]:
        ready = [tid for tid in lib["ids"] if (library.read_meta(tid) or {}).get("status") == "ready"]
        if ready:
            out.append({"key": lib["key"], "name": lib["name"], "blurb": lib["blurb"], "ids": ready})
    return {"libraries": out}


@app.patch("/api/tracks/{tid}")
def patch(tid: str, req: PatchRequest, v: sessions.View = Depends(view_of)):
    m = _meta(tid)
    if req.enabled is not None:
        v.set_enabled(tid, req.enabled)
    return _public({**m, "enabled": v.is_enabled(tid, library.read_meta(tid) or m)})


@app.delete("/api/tracks/{tid}")
def delete(tid: str, v: sessions.View = Depends(view_of)):
    """Hosted, the song only leaves this library (the store keeps it for others)."""
    _meta(tid)
    v.remove(tid)
    m = library.read_meta(tid) or {}
    if not MULTIUSER or not sessions.in_use(tid) or m.get("status") != "ready":
        worker.cancel(tid)
        library.delete(tid)
    return {"deleted": tid}


@app.post("/api/tracks/batch")
def batch(req: BatchRequest, v: sessions.View = Depends(view_of)):
    ids = [t for t in req.ids if library.valid_id(t)]
    if req.action == "delete":
        v.remove_many(ids)
        for tid in ids:
            m = library.read_meta(tid) or {}
            if not MULTIUSER or not sessions.in_use(tid) or m.get("status") != "ready":
                worker.cancel(tid)
                library.delete(tid)
        return {"deleted": ids}
    elif req.action == "enable":
        v.set_enabled_many(ids, True)
        return {"updated": ids, "enabled": True}
    elif req.action == "disable":
        v.set_enabled_many(ids, False)
        return {"updated": ids, "enabled": False}
    elif req.action == "reanalyze":
        for tid in ids:
            m = library.read_meta(tid)
            if m and (not MULTIUSER or m.get("status") == "error"):
                library.update(tid, status="queued", stage="queued", progress=0.0, error=None)
                worker.enqueue_ingest(tid)
        return {"queued": ids}
    raise HTTPException(400, "unknown action")


@app.post("/api/tracks/{tid}/reanalyze")
def reanalyze(tid: str, v: sessions.View = Depends(view_of)):
    m = _meta(tid)
    if MULTIUSER and m.get("status") != "error":
        raise HTTPException(409, "only failed songs can be retried")
    library.update(tid, status="queued", stage="queued", progress=0.0, error=None)
    worker.enqueue_ingest(tid)
    return {"queued": tid}


@app.post("/api/relink")
def relink(v: sessions.View = Depends(view_of)):
    if MULTIUSER:
        v.link()  # only what is missing: pairs are shared, never recomputed for one listener
    else:
        worker.relink_all()
    return {"queued": True}


def _held(v: sessions.View, tid: str) -> None:
    """Hosted, a song's data only goes to a library that holds it."""
    if MULTIUSER and tid not in v.track_ids():
        raise HTTPException(404, "unknown track")


def keystream(key: bytes, tid: str) -> bytes:
    """4 KiB of SHA-256 output from the session key and the track id, repeated
    over the audio (web/js/api.js derives the same block to undo it)."""
    t = tid.encode()
    return b"".join(hashlib.sha256(key + t + i.to_bytes(4, "big")).digest() for i in range(128))


@app.get("/api/tracks/{tid}/analysis")
def analysis(tid: str, v: sessions.View = Depends(view_of)):
    _ready(tid)
    _held(v, tid)
    return FileResponse(library.analysis_path(tid), media_type="application/json",
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/tracks/{tid}/audio")
def audio(tid: str, request: Request, v: sessions.View = Depends(view_of)):
    """Hosted, the audio is not a file anyone can save: it only goes to the
    session that holds the song, scrambled with that session's key, and the
    page unscrambles it in memory right before decoding. (A browser has to
    receive playable sound, so this stops download tools and casual saving,
    not a determined listener.)"""
    _ready(tid)
    _held(v, tid)
    library.touch(tid)
    if not library.has_audio(tid):  # deleted after going unused, just before this listener asked
        if _restore(tid):
            worker.enqueue_ingest(tid)
            raise HTTPException(409, "bài đang được tải lại")
        raise HTTPException(409, "bài tải lên đã được xoá khỏi server: hãy tải lại file")
    return _send_sound(_transport(tid, "audio"), tid, request, v)


@app.get("/api/tracks/{tid}/vocals")
def vocals(tid: str, request: Request, v: sessions.View = Depends(view_of)):
    """The vocal stem of a sung song, sent the way its audio is (scrambled
    with its own key, "<id>:v"), to the session that holds the song."""
    _ready(tid)
    _held(v, tid)
    if not library.has_vocals(tid):
        raise HTTPException(404, "no vocal stem")
    return _send_sound(_transport(tid, "vocals"), f"{tid}:v", request, v)


_encoding: dict[str, threading.Lock] = {}
_encoding_guard = threading.Lock()


def _transport(tid: str, kind: str) -> Path:
    """The MP3 a browser is sent (library.transport_path), encoded from the
    stored lossless file the first time it is asked for when the worker has
    not made it yet; a vocal stem kept as FLAC before MP3 is converted then."""
    out = library.transport_path(tid, kind)
    if out.exists():
        return out
    with _encoding_guard:
        lock = _encoding.setdefault(f"{tid}:{kind}", threading.Lock())
    with lock:
        if not out.exists():
            src = library.audio_path(tid) if kind == "audio" else library.track_dir(tid) / "vocals.flac"
            if not src.exists():
                raise HTTPException(404, "no such sound")
            encode_sound(src, out, "mp3", SOUND_KBPS[kind]["mp3"])
            if kind == "vocals":
                src.unlink(missing_ok=True)
    return out


def _send_sound(path: Path, kid: str, request: Request, v: sessions.View) -> Response:
    if not MULTIUSER:
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})
    ratelimit.check(_ip(request), "audio")
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    start = 0
    end = file_size - 1
    status_code = 200
    headers = {
        "Cache-Control": "no-store",
        "X-Mash": "1",
        "Accept-Ranges": "bytes",
    }
    if range_header:
        try:
            unit, ranges = range_header.strip().split("=", 1)
            if unit.strip().lower() == "bytes":
                start = max(0, int(r_start)) if r_start.strip() else 0
                end = int(r_end) if r_end.strip() else file_size - 1
                if start > end or start >= file_size:
                    raise HTTPException(416, "Requested Range Not Satisfiable")
                end = min(end, file_size - 1)
                status_code = 206
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        except (ValueError, IndexError):
            pass

    content_length = end - start + 1
    headers["Content-Length"] = str(content_length)
    ks = np.frombuffer(keystream(v.key, kid), dtype=np.uint8)

    def chunk_generator(chunk_size: int = 65536):
        with open(path, "rb") as f:
            f.seek(start)
            remaining = content_length
            curr_offset = start
            ks_len = len(ks)
            while remaining > 0:
                to_read = min(chunk_size, remaining)
                raw = f.read(to_read)
                if not raw:
                    break
                data = np.frombuffer(raw, dtype=np.uint8)
                ks_offset = curr_offset % ks_len
                repeats = (len(data) + ks_offset + ks_len - 1) // ks_len
                sub_ks = np.tile(ks, repeats)[ks_offset : ks_offset + len(data)]
                yield (data ^ sub_ks).tobytes()
                curr_offset += len(data)
                remaining -= len(data)

    return StreamingResponse(chunk_generator(), status_code=status_code, media_type="application/octet-stream", headers=headers)


@app.get("/api/tracks/{tid}/transitions")
def transitions(tid: str, v: sessions.View = Depends(view_of)):
    _ready(tid)
    _held(v, tid)
    return {"items": v.transitions(tid), "onward": v.onward(tid)}


@app.get("/api/qr")
def get_qr(data: str | None = None, request: Request = None):
    import io
    import qrcode
    import qrcode.image.svg
    text = (data or str(request.base_url)).strip()
    if len(text) > 2048:
        raise HTTPException(400, "data too long")
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(text, image_factory=factory)
    buf = io.BytesIO()
    img.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"}
    )


@app.get("/api/cookies")
def get_cookie_status():
    from . import cookies as cookie_mgr
    return cookie_mgr.cookie_status()


@app.post("/api/cookies")
async def upload_cookies(request: Request):
    from . import cookies as cookie_mgr
    content = ""
    ct = request.headers.get("content-type", "")
    if "multipart/form-data" in ct:
        form = await request.form()
        file = form.get("file")
        if file and hasattr(file, "read"):
            data = await file.read()
            content = data.decode("utf-8", errors="ignore")
    elif "application/json" in ct:
        body = await request.json()
        content = body.get("content", "")
    else:
        raw = await request.body()
        content = raw.decode("utf-8", errors="ignore")

    if not content.strip():
        raise HTTPException(400, "Nội dung cookie trống")

    res = cookie_mgr.save_cookies(content)
    if not res.get("success"):
        raise HTTPException(400, res.get("message", "Cookie không hợp lệ"))
    return res


@app.delete("/api/cookies")
def delete_cookies():
    from . import cookies as cookie_mgr
    return cookie_mgr.delete_cookies()


@app.api_route("/api/download/{target}", methods=["GET", "HEAD"])
def download_app(target: str, request: Request):
    """Phục vụ file tải ứng dụng: desktop (.exe/.zip), android (.apk), ios (.ipa).
    Nếu server local có sẵn file thì trả về FileResponse trực tiếp (hoặc headers nếu HEAD).
    Nếu chạy trên Space/cloud, tự động redirect sang GitHub Releases mới nhất."""
    target_lower = target.lower().strip()
    root = Path(__file__).resolve().parent.parent
    dl_dir = root / "web" / "downloads"
    release_base = "https://github.com/m3iK18dp/mashloop/releases/latest/download"

    def _serve(path: Path, media_type: str, filename: str):
        if request.method == "HEAD":
            return Response(status_code=200, media_type=media_type, headers={
                "Content-Length": str(path.stat().st_size),
                "Content-Disposition": f'attachment; filename="{filename}"',
            })
        return FileResponse(path, media_type=media_type, filename=filename)

    if target_lower in ("desktop", "windows", "exe", "win"):
        zip_file = dl_dir / "MashLoop-Windows.zip"
        if zip_file.exists() and zip_file.stat().st_size > 0:
            return _serve(zip_file, "application/zip", "MashLoop-Windows.zip")
        exe_file = root / "dist" / "MashLoop" / "MashLoop.exe"
        if exe_file.exists() and exe_file.stat().st_size > 0:
            return _serve(exe_file, "application/octet-stream", "MashLoop.exe")
        return RedirectResponse(f"{release_base}/MashLoop-Windows.zip", status_code=307)

    elif target_lower in ("macos", "mac", "darwin", "osx"):
        zip_file = dl_dir / "MashLoop-macOS.zip"
        if zip_file.exists() and zip_file.stat().st_size > 0:
            return _serve(zip_file, "application/zip", "MashLoop-macOS.zip")
        dist_zip = root / "dist" / "MashLoop-macOS.zip"
        if dist_zip.exists() and dist_zip.stat().st_size > 0:
            return _serve(dist_zip, "application/zip", "MashLoop-macOS.zip")
        return RedirectResponse(f"{release_base}/MashLoop-macOS.zip", status_code=307)

    elif target_lower in ("linux", "tar.gz"):
        tar_file = dl_dir / "MashLoop-Linux.tar.gz"
        if tar_file.exists() and tar_file.stat().st_size > 0:
            return _serve(tar_file, "application/gzip", "MashLoop-Linux.tar.gz")
        dist_tar = root / "dist" / "MashLoop-Linux.tar.gz"
        if dist_tar.exists() and dist_tar.stat().st_size > 0:
            return _serve(dist_tar, "application/gzip", "MashLoop-Linux.tar.gz")
        return RedirectResponse(f"{release_base}/MashLoop-Linux.tar.gz", status_code=307)

    elif target_lower in ("apk", "android"):
        apk_file = dl_dir / "MashLoop.apk"
        if apk_file.exists() and apk_file.stat().st_size > 0:
            return _serve(apk_file, "application/vnd.android.package-archive", "MashLoop.apk")
        debug_apk = root / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if debug_apk.exists() and debug_apk.stat().st_size > 0:
            return _serve(debug_apk, "application/vnd.android.package-archive", "MashLoop.apk")
        return RedirectResponse(f"{release_base}/MashLoop.apk", status_code=307)

    elif target_lower in ("ipa", "ios", "iphone"):
        ipa_file = dl_dir / "MashLoop.ipa"
        if ipa_file.exists() and ipa_file.stat().st_size > 0:
            return _serve(ipa_file, "application/octet-stream", "MashLoop.ipa")
        return RedirectResponse(f"{release_base}/MashLoop.ipa", status_code=307)

    raise HTTPException(404, f"Không hỗ trợ tải mục tiêu: {target}")


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="open the browser")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    worker.start()
    if MULTIUSER:
        worker.start_retention(AUDIO_TTL_S, sessions.in_use)
    else:
        sessions.local().link()  # pairs missing after an update are computed in the background
    if args.open:
        open_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
        webbrowser.open(f"http://{open_host}:{args.port}")
    # No access log: the client addresses are not kept anywhere.
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", access_log=False, proxy_headers=True,
                forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
