"""Cookie management for YouTube and other sources in MashLoop.
Parses Netscape / JSON cookie formats and persists to cookies.txt for yt-dlp."""
import json
import logging
import os
import time
from pathlib import Path

from .config import DATA_DIR, ROOT

logger = logging.getLogger(__name__)

COOKIES_PATH = DATA_DIR / "cookies.txt"


def get_cookie_file_path() -> Path | None:
    if COOKIES_PATH.exists() and COOKIES_PATH.stat().st_size > 0:
        return COOKIES_PATH
    root_f = ROOT / "cookies.txt"
    if root_f.exists() and root_f.stat().st_size > 0:
        return root_f
    env_cookies = os.environ.get("YOUTUBE_COOKIES") or os.environ.get("COOKIES_TXT")
    if env_cookies and env_cookies.strip():
        try:
            save_cookies(env_cookies.strip())
            if COOKIES_PATH.exists() and COOKIES_PATH.stat().st_size > 0:
                logger.info("Auto-initialized cookies from environment variable / Space Secret.")
                return COOKIES_PATH
        except Exception as e:
            logger.warning(f"Failed to auto-initialize cookies from environment: {e}")
    return None


def parse_cookies_to_dict(content: str) -> dict:
    """Parses raw cookie content (either JSON or Netscape format) into a structured dictionary."""
    cookies = {}
    stripped = content.strip()
    now_ts = int(time.time())
    default_exp = str(now_ts + 86400 * 365)  # 1 year in future

    # Check if JSON
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            cookies_list = None
            if isinstance(data, list):
                cookies_list = data
            elif isinstance(data, dict):
                cookies_list = data.get("cookies") or data.get("list") or []

            if isinstance(cookies_list, list):
                for cookie in cookies_list:
                    domain = cookie.get("domain", "")
                    if not domain:
                        continue
                    path = cookie.get("path", "/")
                    secure = "TRUE" if cookie.get("secure", False) else "FALSE"

                    exp_val = cookie.get("expirationDate") or cookie.get("expires") or cookie.get("expiration")
                    try:
                        exp_num = int(float(exp_val)) if exp_val is not None else 0
                    except (ValueError, TypeError):
                        exp_num = 0

                    if exp_num <= now_ts:
                        expiration = default_exp
                    else:
                        expiration = str(exp_num)

                    flag = "TRUE" if domain.startswith(".") else "FALSE"
                    name = cookie.get("name", "")
                    value = cookie.get("value", "")
                    key = (domain.lower(), path, name)
                    cookies[key] = {
                        "domain": domain,
                        "flag": flag,
                        "path": path,
                        "secure": secure,
                        "expiration": expiration,
                        "name": name,
                        "value": value,
                    }
                if cookies:
                    return cookies
        except Exception as e:
            logger.warning(f"Failed to parse JSON cookies: {e}")

    # Fallback to Netscape format parser
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain, flag, path, secure, expiration, name, value = parts[:7]
            try:
                exp_num = int(float(expiration)) if expiration else 0
            except (ValueError, TypeError):
                exp_num = 0
            if exp_num <= now_ts:
                expiration = default_exp
            key = (domain.lower(), path, name)
            cookies[key] = {
                "domain": domain,
                "flag": flag,
                "path": path,
                "secure": secure,
                "expiration": expiration,
                "name": name,
                "value": value,
            }
    return cookies


def serialize_netscape_cookies(cookies_dict: dict) -> str:
    """Serializes a dictionary of cookies back into standard Netscape/curl cookiefile format."""
    now_ts = int(time.time())
    default_exp = str(now_ts + 86400 * 365)
    lines = [
        "# Netscape HTTP Cookie File",
        "# http://curl.haxx.se/rfc/cookie_spec.html",
        "# This is a generated file! Do not edit.",
        "",
    ]
    for c in cookies_dict.values():
        exp = c.get("expiration", "0")
        try:
            exp_num = int(float(exp)) if exp else 0
        except (ValueError, TypeError):
            exp_num = 0
        if exp_num <= now_ts:
            exp = default_exp
        lines.append(f"{c['domain']}\t{c['flag']}\t{c['path']}\t{c['secure']}\t{exp}\t{c['name']}\t{c['value']}")
    return "\n".join(lines)


def detect_domains(cookies_dict: dict) -> list[str]:
    domains = set()
    for domain, _, _ in cookies_dict.keys():
        d = domain.lower()
        if "youtube.com" in d or "youtu.be" in d:
            domains.add("YouTube")
        elif "soundcloud.com" in d:
            domains.add("SoundCloud")
        elif "spotify.com" in d:
            domains.add("Spotify")
        elif "facebook.com" in d or "fb.com" in d:
            domains.add("Facebook")
        elif "instagram.com" in d:
            domains.add("Instagram")
        elif "tiktok.com" in d:
            domains.add("TikTok")
        elif "bilibili.com" in d:
            domains.add("Bilibili")
        elif "zingmp3.vn" in d:
            domains.add("Zing MP3")
    return sorted(domains)


def cookie_status() -> dict:
    fpath = get_cookie_file_path()
    if not fpath or not fpath.exists():
        return {"has_cookies": False, "count": 0, "domains": []}
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        parsed = parse_cookies_to_dict(content)
        return {
            "has_cookies": len(parsed) > 0,
            "count": len(parsed),
            "domains": detect_domains(parsed),
        }
    except Exception as e:
        logger.warning(f"Error reading cookie status: {e}")
        return {"has_cookies": False, "count": 0, "domains": [], "error": str(e)}


def save_cookies(content: str) -> dict:
    new_cookies = parse_cookies_to_dict(content)
    if not new_cookies:
        return {"success": False, "message": "Nội dung cookie không hợp lệ (hỗ trợ định dạng Netscape hoặc JSON)."}

    # Merge with existing file if any
    existing = {}
    fpath = COOKIES_PATH if (COOKIES_PATH.exists() and COOKIES_PATH.stat().st_size > 0) else (ROOT / "cookies.txt" if (ROOT / "cookies.txt").exists() else None)
    if fpath and fpath.exists():
        try:
            existing = parse_cookies_to_dict(fpath.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    existing.update(new_cookies)
    serialized = serialize_netscape_cookies(existing)

    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_PATH.write_text(serialized, encoding="utf-8")
    domains = detect_domains(existing)
    return {
        "success": True,
        "message": f"Đã nạp {len(new_cookies)} cookie thành công!",
        "count": len(existing),
        "domains": domains,
    }


def delete_cookies() -> dict:
    deleted = False
    if COOKIES_PATH.exists():
        COOKIES_PATH.unlink(missing_ok=True)
        deleted = True
    root_f = ROOT / "cookies.txt"
    if root_f.exists():
        root_f.unlink(missing_ok=True)
        deleted = True
    return {"success": True, "deleted": deleted}
