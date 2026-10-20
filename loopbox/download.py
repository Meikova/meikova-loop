"""Music from the web through yt-dlp: YouTube (and YouTube Music), SoundCloud,
Spotify, Zing MP3, Bandcamp, TikTok, Facebook, Instagram, Twitter/X, Bilibili,
Mixcloud, Jamendo, Vimeo, Dailymotion, Audius and generic web media.
Single songs, albums and playlists. A JS runtime (node or deno, MASHLOOP_JS_RUNTIME)
solves YouTube's player challenges.

Ids: a YouTube video keeps its own 11-character id; a song from any other
site is "x" and 16 hex digits of a hash of the site and its id there, so the
same song is the same track whoever adds it and however it was linked."""
import copy
import hashlib
import json
import logging
import re
import sys
import urllib.request
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import yt_dlp

try:
    from yt_dlp.networking.impersonate import ImpersonateTarget
except ImportError:
    ImpersonateTarget = None

from .config import JS_RUNTIME, MAX_PLAYLIST, MAX_DURATION_S

logger = logging.getLogger(__name__)


def _get_impersonate():
    if not ImpersonateTarget:
        return None
    try:
        return ImpersonateTarget.from_str("chrome")
    except Exception:
        return None


def _find_js_runtimes():
    runtimes = {}
    deno_dir = Path.home() / ".local" / "bin"
    deno_bin = deno_dir / ("deno.exe" if sys.platform.startswith("win") else "deno")
    if deno_bin.exists():
        runtimes["deno"] = {"path": str(deno_bin)}
    for rt in ("deno", "node", "bun", "quickjs"):
        if rt in runtimes:
            continue
        p = shutil.which(rt)
        if p:
            runtimes[rt] = {"path": p}
    if JS_RUNTIME and JS_RUNTIME not in runtimes:
        p = shutil.which(JS_RUNTIME)
        if p:
            runtimes[JS_RUNTIME] = {"path": p}
    return runtimes


BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "nocheckcertificate": True,
    "js_runtimes": _find_js_runtimes(),
    "remote_components": ["ejs:github"],
    "socket_timeout": 30,
}

# site -> (hosts, yt-dlp extractors allowed for it)
SOURCES = {
    "youtube": ({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}, [r"youtube.*"]),
    "soundcloud": ({"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"}, [r"soundcloud.*"]),
    "spotify": ({"open.spotify.com", "spotify.com"}, []),
    "zingmp3": ({"zingmp3.vn", "www.zingmp3.vn", "m.zingmp3.vn", "mp3.zing.vn"}, [r"zingmp3.*"]),
    "bandcamp": ({"bandcamp.com"}, [r"Bandcamp.*"]),
    "mixcloud": ({"mixcloud.com", "www.mixcloud.com", "m.mixcloud.com"}, [r"mixcloud.*"]),
    "jamendo": ({"jamendo.com", "www.jamendo.com"}, [r"Jamendo.*"]),
    "tiktok": ({"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vt.tiktok.com", "douyin.com", "v.douyin.com"}, [r"tiktok.*", r"douyin.*"]),
    "facebook": ({"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com", "fb.watch", "fb.com"}, [r"facebook.*"]),
    "instagram": ({"instagram.com", "www.instagram.com", "instagr.am"}, [r"instagram.*"]),
    "twitter": ({"twitter.com", "www.twitter.com", "x.com", "www.x.com"}, [r"twitter.*"]),
    "bilibili": ({"bilibili.com", "www.bilibili.com", "bilibili.tv"}, [r"bilibili.*"]),
    "vimeo": ({"vimeo.com", "www.vimeo.com", "player.vimeo.com"}, [r"vimeo.*"]),
    "dailymotion": ({"dailymotion.com", "www.dailymotion.com", "dai.ly"}, [r"dailymotion.*"]),
    "audius": ({"audius.co", "www.audius.co"}, [r"audius.*"]),
    "generic": (set(), [r"generic.*"]),
}

SITE_NAMES = {
    "youtube": "YouTube",
    "soundcloud": "SoundCloud",
    "spotify": "Spotify",
    "zingmp3": "Zing MP3",
    "bandcamp": "Bandcamp",
    "mixcloud": "Mixcloud",
    "jamendo": "Jamendo",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "twitter": "X (Twitter)",
    "bilibili": "Bilibili",
    "vimeo": "Vimeo",
    "dailymotion": "Dailymotion",
    "audius": "Audius",
    "generic": "Web Audio",
}


def cc_name(license_url_or_code: str | None) -> str | None:
    """"http://creativecommons.org/licenses/by-nc-sa/3.0/" (or "by-nc-sa") -> "CC BY-NC-SA 3.0"."""
    s = str(license_url_or_code or "").strip()
    m = re.search(r"/licenses/([a-z-]+)(?:/(\d(?:\.\d)?))?", s, re.I) or re.fullmatch(r"([a-z-]+)()", s, re.I)
    if not m or not re.fullmatch(r"by(-(nc|sa|nd))*", m.group(1).lower()):
        return None
    return " ".join(filter(None, ["CC", m.group(1).upper(), m.group(2)]))


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _is_private_host(host: str) -> bool:
    h = host.lower().strip("[]")
    if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if h.startswith("10.") or h.startswith("192.168.") or h.startswith("169.254."):
        return True
    if re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", h):
        return True
    return False


def site_of(url: str) -> str | None:
    try:
        u = urlparse(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = (u.hostname or "").lower()
    if not host or _is_private_host(host):
        return None
    for site, (hosts, _) in SOURCES.items():
        if host in hosts or (site == "bandcamp" and host.endswith(".bandcamp.com")):
            return site
    path = u.path.lower()
    if any(path.endswith(ext) for ext in (".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".webm")):
        return "generic"
    if "." in host and not host.endswith(".local") and not host.endswith(".internal"):
        return "generic"
    return None


def is_youtube(url: str) -> bool:
    return site_of(url) == "youtube"


def clean_youtube_url(url: str) -> str:
    """Cleans tracking query params while preserving video and playlist IDs."""
    if not url:
        return url
    try:
        parsed = urlparse(url)
        if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            v = qs.get("v", [None])[0]
            l = qs.get("list", [None])[0]
            # Handle youtu.be/<vid> path
            if not v and "youtu.be" in parsed.netloc and parsed.path.strip("/"):
                path_vid = parsed.path.strip("/")
                if _VIDEO_ID.match(path_vid):
                    v = path_vid

            # If it's a YouTube Mix / Radio (list starts with RD, RDMM, RDAMVM),
            # YouTube rejects /playlist?list=RD... with "This playlist type is unviewable".
            # The seed video ID is embedded directly in the list ID after the prefix!
            if not v and l:
                m_mix = re.match(r"^(?:RDMM|RDAMVM|RD)([A-Za-z0-9_-]{11})$", l)
                if m_mix:
                    v = m_mix.group(1)

            if v and l:
                return f"https://www.youtube.com/watch?v={v}&list={l}"
            elif l:
                return f"https://www.youtube.com/playlist?list={l}"
            elif v:
                return f"https://www.youtube.com/watch?v={v}"
    except Exception:
        pass
    return url


def is_playlist_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        if "/playlist" in u or "list=" in u:
            return True
    if "soundcloud.com" in u and ("/sets/" in u or "/albums/" in u):
        return True
    if "spotify.com" in u and ("/album/" in u or "/playlist/" in u):
        return True
    if "zingmp3.vn" in u and ("/album/" in u or "/playlist/" in u):
        return True
    if "bandcamp.com" in u and "/album/" in u:
        return True
    if "dailymotion.com" in u and "/playlist/" in u:
        return True
    if "bilibili.com" in u and ("/medialist/" in u or "/series/" in u):
        return True
    return False


YOUTUBE_CLIENT_CONFIGS = (
    ["visionos"],
    ["android_vr"],
    ["android_music"],
    ["android_embedded"],
    ["tv_embedded"],
    ["ios_music"],
    ["android"],
    ["visionos", "android_vr"],
    ["mweb"],
    ["web_music", "web"],
    ["web"],
    None,
)


def _opts(site: str, use_cookies: bool = True, **extra) -> dict:
    extractors = SOURCES.get(site, (set(), []))[1]
    opts = {**BASE_OPTS, **extra}
    opts["js_runtimes"] = _find_js_runtimes()
    if extractors:
        opts["allowed_extractors"] = extractors
    if site == "youtube":
        imp = _get_impersonate()
        if imp:
            opts["impersonate"] = imp
        ext_args = opts.setdefault("extractor_args", {})
        yt_args = ext_args.setdefault("youtube", {})
        yt_args.setdefault("formats", ["missing_pot"])
    if use_cookies:
        from . import cookies as cookie_mgr
        cookie_file = cookie_mgr.get_cookie_file_path()
        if cookie_file:
            opts["cookiefile"] = str(cookie_file)
    else:
        opts.pop("cookiefile", None)
    return opts


def track_id(site: str, native_id: str) -> str:
    if site == "youtube" and _VIDEO_ID.match(native_id):
        return native_id
    return "x" + hashlib.sha1(f"{site}:{native_id}".encode()).hexdigest()[:16]


def _entry(e: dict, site: str = "youtube") -> dict | None:
    native = str(e.get("id") or "")
    if not native:
        native = hashlib.sha1((e.get("webpage_url") or e.get("url") or "").encode()).hexdigest()[:11]
    if site == "youtube" and not _VIDEO_ID.match(native):
        return None
    thumbs = e.get("thumbnails") or []
    thumb = e.get("thumbnail") or (thumbs[-1]["url"] if thumbs else None)
    if site == "youtube":
        url = f"https://www.youtube.com/watch?v={native}"
        thumb = thumb or f"https://i.ytimg.com/vi/{native}/mqdefault.jpg"
    else:
        url = e.get("webpage_url") or e.get("url")
        if not url:
            return None
    title = e.get("title") or e.get("track")
    if not title:
        title = Path(urlparse(url).path).name.replace("-", " ").replace(".html", "").strip() or native
    out = {
        "id": track_id(site, native),
        "source": site,
        "title": title,
        "channel": e.get("artist") or e.get("channel") or e.get("uploader") or "",
        "duration": e.get("duration"),
        "thumbnail": thumb,
        "url": url,
    }
    if site == "jamendo" and cc_name(e.get("license")):
        out["credit"] = {"artist": out["channel"], "license": cc_name(e.get("license")), "license_url": None,
                         "page": url, "via": "Jamendo"}
    return out


def search(query: str, n: int = 8) -> list[dict]:
    opts = _opts("youtube", extract_flat="in_playlist", skip_download=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return [x for x in (_entry(e) for e in info.get("entries") or []) if x]


def resolve_spotify(url: str, max_tracks: int = 50) -> list[dict]:
    """Resolves Spotify track/album/playlist URLs into YouTube playable entries."""
    m = re.search(r"spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)", url)
    if not m:
        return []
    kind, sid = m.group(1), m.group(2)
    req = urllib.request.Request(
        f"https://open.spotify.com/embed/{kind}/{sid}",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"Spotify embed fetch failed: {e}")
        # Fallback to oEmbed for track
        if kind == "track":
            try:
                oe_req = urllib.request.Request(f"https://open.spotify.com/oembed?url={url}")
                with urllib.request.urlopen(oe_req, timeout=5) as oe_resp:
                    oe_data = json.loads(oe_resp.read().decode("utf-8"))
                    title = oe_data.get("title")
                    if title:
                        return search(title, 1)
            except Exception:
                pass
        return []

    match = re.search(r'id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
    except Exception:
        return []

    if kind == "track":
        title = entity.get("name") or entity.get("title")
        artists = [a.get("name") for a in entity.get("artists", []) if isinstance(a, dict) and a.get("name")]
        artist_str = ", ".join(artists) if artists else (entity.get("subtitle") or "")
        query = f"{title} {artist_str}".strip()
        return search(query, 1)
    else:
        track_items = entity.get("trackList", [])[:max_tracks]
        if not track_items:
            return []
        queries = []
        for t in track_items:
            title = t.get("title")
            artist = t.get("subtitle") or ""
            if title:
                queries.append(f"{title} {artist}".strip())

        def _fetch(q: str):
            res = search(q, 1)
            return res[0] if res else None

        results = []
        with ThreadPoolExecutor(max_workers=min(5, len(queries))) as pool:
            for item in pool.map(_fetch, queries):
                if item:
                    results.append(item)
        return results


def resolve_youtube_oembed(video_id: str) -> dict | None:
    """Extracts public YouTube video metadata via Google's official oEmbed API.
    Bypasses datacenter bot verification / CAPTCHA completely."""
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            title = data.get("title") or video_id
            author = data.get("author_name") or ""
            thumb = data.get("thumbnail_url") or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
            return {
                "id": video_id,
                "source": "youtube",
                "title": title,
                "channel": author,
                "duration": None,
                "thumbnail": thumb,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
    except Exception as e:
        logger.debug(f"oEmbed resolution failed for {video_id}: {e}")
        return None


def resolve(text: str) -> list[dict]:
    """A song link gives one entry, a playlist (set, album) link gives its songs,
    and anything else is a YouTube search for the best match."""
    text = text.strip()
    if not re.match(r"^https?://", text):
        return search(text[:200], 1)

    if "youtube.com" in text or "youtu.be" in text:
        text = clean_youtube_url(text)

    site = site_of(text)
    if site is None:
        raise ValueError("link không hợp lệ hoặc không thuộc nguồn internet được hỗ trợ")

    if site == "spotify":
        return resolve_spotify(text, MAX_PLAYLIST)

    is_playlist = is_playlist_url(text)
    from . import cookies as cookie_mgr
    has_cookies = bool(cookie_mgr.get_cookie_file_path()) if site == "youtube" else False
    cookie_passes = [True, False] if has_cookies else [False]

    clients = YOUTUBE_CLIENT_CONFIGS if site == "youtube" else (None,)
    info = None
    last_e = None

    for use_cookies in cookie_passes:
        opts = _opts(site, use_cookies=use_cookies, extract_flat="in_playlist", skip_download=True, playlistend=MAX_PLAYLIST)
        if is_playlist:
            opts["noplaylist"] = False
        elif site == "youtube":
            opts["noplaylist"] = True

        for client in clients:
            cur_opts = copy.deepcopy(opts)
            if client:
                cur_opts.setdefault("extractor_args", {}).setdefault("youtube", {})["player_client"] = client
            else:
                if "extractor_args" in cur_opts and "youtube" in cur_opts["extractor_args"]:
                    cur_opts["extractor_args"]["youtube"].pop("player_client", None)
            try:
                with yt_dlp.YoutubeDL(cur_opts) as ydl:
                    info = ydl.extract_info(text, download=False)
                break
            except Exception as e:
                last_e = e
                if site != "youtube":
                    break
        if info is not None:
            break

    if info is None:
        # Check if text contains a Mix list ID (RD...) to resolve via seed watch URL
        m_mix = re.search(r"list=((?:RDMM|RDAMVM|RD)([A-Za-z0-9_-]{11}))", text)
        if m_mix:
            full_list, seed_vid = m_mix.group(1), m_mix.group(2)
            watch_url = f"https://www.youtube.com/watch?v={seed_vid}&list={full_list}"
            for client in clients:
                mix_opts = copy.deepcopy(opts)
                mix_opts["noplaylist"] = False
                if client:
                    mix_opts.setdefault("extractor_args", {}).setdefault("youtube", {})["player_client"] = client
                else:
                    if "extractor_args" in mix_opts and "youtube" in mix_opts["extractor_args"]:
                        mix_opts["extractor_args"]["youtube"].pop("player_client", None)
                try:
                    with yt_dlp.YoutubeDL(mix_opts) as ydl:
                        info = ydl.extract_info(watch_url, download=False)
                    break
                except Exception as e:
                    last_e = e
                    if site != "youtube":
                        break

        if info is None and ("watch?v=" in text or "youtu.be/" in text):
            m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", text)
            if m:
                single_url = f"https://www.youtube.com/watch?v={m.group(1)}"
                for client in clients:
                    single_opts = copy.deepcopy(opts)
                    single_opts["noplaylist"] = True
                    if client:
                        single_opts.setdefault("extractor_args", {}).setdefault("youtube", {})["player_client"] = client
                    else:
                        if "extractor_args" in single_opts and "youtube" in single_opts["extractor_args"]:
                            single_opts["extractor_args"]["youtube"].pop("player_client", None)
                    try:
                        with yt_dlp.YoutubeDL(single_opts) as ydl:
                            info = ydl.extract_info(single_url, download=False)
                        break
                    except Exception as e:
                        last_e = e
                        if site != "youtube":
                            break
        if info is None:
            if site == "youtube":
                m_vid = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", text)
                if m_vid:
                    oembed_res = resolve_youtube_oembed(m_vid.group(1))
                    if oembed_res:
                        return [oembed_res]
            if last_e:
                raise last_e

    if info.get("_type") == "playlist" or "entries" in info:
        entries = info.get("entries") or []
        out = []
        for e in entries:
            if not e:
                continue
            entry_obj = _entry(e, site)
            if entry_obj:
                out.append(entry_obj)
            if len(out) >= MAX_PLAYLIST:
                break
        if out:
            return out
        single = _entry(info, site)
        return [single] if single else []

    e = _entry(info, site)
    return [e] if e else []


def clean_error(err: str | Exception) -> str:
    """Produces a short, human-readable error description without terminal spam or long URLs."""
    s = str(err).strip()
    s = re.sub(r"^(?:could not resolve|error|[A-Za-z_]+Error):\s*", "", s, flags=re.I)
    s = re.sub(r"^\[[^\]]+\]\s*", "", s)
    low = s.lower()
    if "unviewable" in low or "playlist type is unviewable" in low:
        return "YouTube Mix này cần mở kèm bài hát gốc"
    if "confirm you're not a bot" in low or ("bot" in low and ("sign in" in low or "protect" in low)):
        return "YouTube yêu cầu xác minh bot hoặc video bị giới hạn vùng/độ tuổi"
    if "this video is unavailable" in low or "unavailable" in low:
        return "Video này không khả dụng hoặc đã bị tác giả gỡ trên YouTube"
    if "claimed content" in low or "blocked due to" in low or "copyright" in low:
        return "Video bị chặn bản quyền bởi đơn vị sở hữu"
    if "terminated" in low or ("account" in low and "terminated" in low):
        return "Kênh YouTube đăng video này đã bị khóa tài khoản"
    if "terms of service" in low:
        return "Video bị gỡ do vi phạm điều khoản YouTube"
    if "huỷ" in low or "cancel" in low:
        return "Đã huỷ nạp bài theo yêu cầu"
    if "requested format is not available" in low or "no formats" in low:
        return "Video không khả dụng hoặc định dạng bị hạn chế"
    if "private video" in low:
        return "Video này được đặt ở chế độ riêng tư"
    if "unsupported url" in low:
        return "Đường link không thuộc nguồn được hỗ trợ hoặc sai định dạng"
    if "vip" in low:
        return "Bài này yêu cầu tài khoản VIP của nền tảng nguồn"
    if "timed out" in low or "timeout" in low:
        return "Hết thời gian kết nối tới máy chủ nguồn (timeout)"
    # Strip any URLs, cookies references, or wiki links
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"--cookies[^\s.]*", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:120] if s else "Không thể tải bài từ đường link này"


def download(meta: dict, dest_dir: Path, on_progress: Callable[[float], None] | None = None) -> tuple[Path, dict]:
    """Fetches the best audio of a registered track into dest_dir/source.*"""
    from . import library
    tid = meta.get("id") or ""
    if tid and library.is_cancelled(tid):
        raise RuntimeError("Đã huỷ nạp bài theo yêu cầu")
    site = meta.get("source") or "youtube"
    url = f"https://www.youtube.com/watch?v={meta['id']}" if site == "youtube" else meta["url"]
    if site_of(url) is None:
        raise ValueError("link không thuộc nguồn được hỗ trợ hoặc địa chỉ không hợp lệ")

    def hook(d):
        if tid and library.is_cancelled(tid):
            raise RuntimeError("Đã huỷ nạp bài theo yêu cầu")
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(1.0, d.get("downloaded_bytes", 0) / total))

    dest_dir.mkdir(parents=True, exist_ok=True)
    last_error = None
    from . import cookies as cookie_mgr
    has_cookies = bool(cookie_mgr.get_cookie_file_path()) if site == "youtube" else False
    cookie_passes = [True, False] if has_cookies else [True]

    # YouTube intermittently answers 403 or blocks player response for some clients;
    # cycling client configs ensures datacenter/cloud connectivity.
    format_spec = "bestaudio/b[acodec!=none]/ba/best[acodec!=none]/best"
    for use_cookies in cookie_passes:
        if site == "youtube":
            # With cookies: prioritize default client & web clients that consume session cookies.
            # Without cookies: prioritize lightweight clients (visionos, android_vr).
            clients = (None, ["web"], ["mweb"], ["tv"]) if use_cookies else YOUTUBE_CLIENT_CONFIGS
        else:
            clients = (None,)
        for client in clients:
            if tid and library.is_cancelled(tid):
                raise RuntimeError("Đã huỷ nạp bài theo yêu cầu")
            for stale in dest_dir.glob("source.*"):
                stale.unlink(missing_ok=True)
            opts = _opts(site, use_cookies=use_cookies, format=format_spec, noplaylist=True, outtmpl=str(dest_dir / "source.%(ext)s"),
                         progress_hooks=[hook], retries=3)
            if client:
                opts.setdefault("extractor_args", {}).setdefault("youtube", {})["player_client"] = client
            else:
                if "extractor_args" in opts and "youtube" in opts["extractor_args"]:
                    opts["extractor_args"]["youtube"].pop("player_client", None)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    dur = info.get("duration")
                    if dur and dur > MAX_DURATION_S:
                        raise RuntimeError(f"dài hơn {MAX_DURATION_S // 60} phút ({dur // 60} phút), không thể phân tích phách nhịp")
                    info = ydl.extract_info(url, download=True)
                previews = any("preview" in str(f.get("format_id", "")) for f in info.get("requested_downloads") or [])
                if site == "soundcloud" and (previews or (info.get("duration") or 99) <= 31):
                    raise RuntimeError("SoundCloud chỉ cho nghe thử 30 giây bài này")
                candidate = None
                if info.get("requested_downloads"):
                    p = Path(info["requested_downloads"][0].get("filepath", ""))
                    if p.exists() and p.stat().st_size > 1024:
                        candidate = p
                if not candidate and info.get("_filename"):
                    p = Path(info["_filename"])
                    if p.exists() and p.stat().st_size > 1024:
                        candidate = p
                if not candidate:
                    downloaded = [f for f in dest_dir.glob("source.*") if f.is_file() and f.stat().st_size > 1024 and not f.name.endswith(".part")]
                    if downloaded:
                        candidate = downloaded[0]
                if not candidate:
                    parts = [f for f in dest_dir.glob("source.*.part") if f.is_file() and f.stat().st_size > 1024]
                    if parts:
                        recovered = parts[0].with_suffix("")
                        parts[0].rename(recovered)
                        candidate = recovered

                if not candidate or not candidate.exists() or candidate.stat().st_size <= 1024:
                    if site == "youtube":
                        logger.warning(f"Client {client} không tải được file hợp lệ cho {tid or url}, thử client tiếp theo...")
                        continue
                    raise RuntimeError("không tìm thấy file tải về hoặc file rỗng")

                return candidate, _entry(info, site) or {}
            except yt_dlp.utils.DownloadError as e:
                last_error = e
                msg = str(e)
                if "VIP" in msg:
                    raise RuntimeError(f"bài này chỉ dành cho tài khoản VIP của {SITE_NAMES.get(site, site)}") from None
                if site == "youtube":
                    continue
                raise
        # If all clients failed for this cookie pass, try next pass
    raise last_error
