"""User Authentication and Multi-Device Library Synchronization.
Supports:
- Local Username/Password registration and login (PBKDF2-HMAC-SHA256)
- Google OAuth 2.0 Identity Services (GIS) 1-click login
- Multi-device sync: user library, playlists, favorites, and settings persisted per user account
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .config import DATA_DIR

logger = logging.getLogger("mashloop.auth")

GOOGLE_CLIENT_ID = "515668723869-066g74dbt8c3b61odfigv6gl3552coj3.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
GOOGLE_PROJECT_ID = "titan-remote-512203"
SESSION_LIFETIME_DAYS = 30
_db_path = DATA_DIR / "auth.db"


def get_google_client_id() -> str:
    """Returns Google Client ID embedded directly in code."""
    return os.environ.get("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID).strip() or GOOGLE_CLIENT_ID


def get_google_client_secret() -> str:
    """Returns Google Client Secret embedded directly in code."""
    return os.environ.get("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET).strip() or GOOGLE_CLIENT_SECRET


def get_google_auth_url(redirect_uri: str, state: str = "") -> str:
    """Generates standard RFC 8252 authorization URL for system browser login."""
    client_id = get_google_client_id()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent select_account",
    }
    if state:
        params["state"] = state
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


def exchange_google_code(code: str, redirect_uri: str) -> dict:
    """Exchanges authorization code for tokens and registers/logs in the user."""
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))
    id_token = token_data.get("id_token")
    if not id_token:
        raise ValueError("Google OAuth token response missing id_token")
    return google_auth(id_token)


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path), timeout=15.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                display_name TEXT,
                password_hash TEXT,
                salt TEXT,
                provider TEXT DEFAULT 'local',
                google_sub TEXT UNIQUE,
                created_at REAL NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_libraries (
                user_id TEXT PRIMARY KEY,
                track_ids TEXT DEFAULT '[]',
                off_ids TEXT DEFAULT '[]',
                playlists TEXT DEFAULT '[]',
                favorites TEXT DEFAULT '[]',
                settings TEXT DEFAULT '{}',
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)
    return conn


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    pwd_bytes = password.encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt, 100_000).hex()


def register_user(username: str, password: str, display_name: str = "") -> dict:
    """Registers a new local account with PBKDF2 hash."""
    clean_username = username.strip().lower()
    if len(clean_username) < 3:
        raise ValueError("Tên đăng nhập phải có ít nhất 3 ký tự")
    if len(password) < 6:
        raise ValueError("Mật khẩu phải có ít nhất 6 ký tự")

    salt_hex = secrets.token_hex(16)
    pwd_hash = _hash_password(password, salt_hex)
    user_id = secrets.token_hex(16)
    now = time.time()
    disp = display_name.strip() or clean_username

    conn = _get_db()
    try:
        with conn:
            conn.execute("""
                INSERT INTO users (id, username, email, display_name, password_hash, salt, provider, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'local', ?)
            """, (user_id, clean_username, clean_username if "@" in clean_username else None, disp, pwd_hash, salt_hex, now))
            # Initialize empty library row
            conn.execute("""
                INSERT INTO user_libraries (user_id, track_ids, off_ids, playlists, favorites, settings, updated_at)
                VALUES (?, '[]', '[]', '[]', '[]', '{}', ?)
            """, (user_id, now))
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError("Tên đăng nhập hoặc email này đã tồn tại")
    conn.close()

    # Create session token
    token = _create_session(user_id)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "username": clean_username,
            "display_name": disp,
            "provider": "local",
        },
    }


def authenticate_user(username: str, password: str) -> dict | None:
    """Authenticates username/password and returns user info + session token."""
    clean_username = username.strip().lower()
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, username, display_name, password_hash, salt, provider
        FROM users WHERE username = ?
    """, (clean_username,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    user_id, uname, disp, stored_hash, salt_hex, provider = row
    if not stored_hash or not salt_hex:
        return None

    computed_hash = _hash_password(password, salt_hex)
    if not secrets.compare_digest(stored_hash, computed_hash):
        return None

    token = _create_session(user_id)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "username": uname,
            "display_name": disp or uname,
            "provider": provider,
        },
    }


def verify_google_credential(credential: str) -> dict | None:
    """Verifies Google ID Token JWT.
    First tries online validation via Google's tokeninfo API for full security,
    with fallback to JWT payload decode.
    """
    if not credential:
        return None

    # 1. Try Google OAuth2 tokeninfo endpoint
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(credential)}"
        req = urllib.request.Request(url, headers={"User-Agent": "MashLoop-Auth"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "email": data.get("email"),
                    "name": data.get("name") or data.get("email", "").split("@")[0],
                    "sub": data.get("sub"),
                    "picture": data.get("picture"),
                }
    except Exception as e:
        logger.debug("Google tokeninfo verification network fallback: %s", e)

    # 2. Local JWT payload extraction
    try:
        parts = credential.split(".")
        if len(parts) >= 2:
            payload_raw = parts[1]
            # Handle URL-safe base64 padding
            payload_raw += "=" * ((4 - len(payload_raw) % 4) % 4)
            payload_json = base64.urlsafe_b64decode(payload_raw).decode("utf-8")
            payload = json.loads(payload_json)
            email = payload.get("email")
            if email:
                return {
                    "email": email,
                    "name": payload.get("name") or email.split("@")[0],
                    "sub": payload.get("sub"),
                    "picture": payload.get("picture"),
                }
    except Exception as ex:
        logger.warning("Failed to decode Google JWT payload: %s", ex)

    return None


def google_auth(credential: str) -> dict:
    """Authenticates or auto-registers a user from Google ID token."""
    g_info = verify_google_credential(credential)
    if not g_info or not g_info.get("email"):
        raise ValueError("Google Token không hợp lệ hoặc đã hết hạn")

    email = g_info["email"].strip().lower()
    disp_name = g_info.get("name") or email.split("@")[0]
    google_sub = g_info.get("sub") or email
    now = time.time()

    conn = _get_db()
    cur = conn.cursor()
    # Check if user already exists by google_sub or email
    cur.execute("SELECT id, username, display_name FROM users WHERE google_sub = ? OR username = ?", (google_sub, email))
    row = cur.fetchone()

    if row:
        user_id, uname, disp = row
        # Update google_sub if linking existing username
        with conn:
            conn.execute("UPDATE users SET google_sub = ?, display_name = ? WHERE id = ?", (google_sub, disp_name, user_id))
    else:
        user_id = secrets.token_hex(16)
        with conn:
            conn.execute("""
                INSERT INTO users (id, username, email, display_name, provider, google_sub, created_at)
                VALUES (?, ?, ?, ?, 'google', ?, ?)
            """, (user_id, email, email, disp_name, google_sub, now))
            conn.execute("""
                INSERT INTO user_libraries (user_id, track_ids, off_ids, playlists, favorites, settings, updated_at)
                VALUES (?, '[]', '[]', '[]', '[]', '{}', ?)
            """, (user_id, now))

    conn.close()

    token = _create_session(user_id)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user_id,
            "username": email,
            "display_name": disp_name,
            "provider": "google",
            "picture": g_info.get("picture"),
        },
    }


def create_session(user_id: str) -> str:
    token = secrets.token_hex(32)
    now = time.time()
    expires_at = now + (SESSION_LIFETIME_DAYS * 86400)
    conn = _get_db()
    with conn:
        conn.execute("""
            INSERT INTO user_sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (token, user_id, now, expires_at))
    conn.close()
    return token


_create_session = create_session



def validate_token(token: str) -> dict | None:
    """Validates session token and returns active user dictionary."""
    if not token or len(token) < 16:
        return None

    now = time.time()
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.username, u.email, u.display_name, u.provider, s.expires_at
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
    """, (token,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    user_id, uname, email, disp, provider, expires_at = row
    if now > expires_at:
        with conn:
            conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.close()
        return None

    conn.close()
    return {
        "id": user_id,
        "username": uname,
        "email": email,
        "display_name": disp or uname,
        "provider": provider,
    }


def delete_session(token: str) -> bool:
    """Logs out by deleting the session token."""
    if not token:
        return False
    conn = _get_db()
    with conn:
        conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
    conn.close()
    return True


def get_user_library(user_id: str) -> dict:
    """Fetches user's persistent library, playlists, favorites, and settings."""
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT track_ids, off_ids, playlists, favorites, settings, updated_at
        FROM user_libraries WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {
            "track_ids": [],
            "off_ids": [],
            "playlists": [],
            "favorites": [],
            "settings": {},
            "updated_at": 0,
        }

    track_ids_str, off_ids_str, pl_str, fav_str, set_str, updated_at = row
    try:
        track_ids = json.loads(track_ids_str or "[]")
    except Exception:
        track_ids = []
    try:
        off_ids = json.loads(off_ids_str or "[]")
    except Exception:
        off_ids = []
    try:
        playlists = json.loads(pl_str or "[]")
    except Exception:
        playlists = []
    try:
        favorites = json.loads(fav_str or "[]")
    except Exception:
        favorites = []
    try:
        settings = json.loads(set_str or "{}")
    except Exception:
        settings = {}

    return {
        "track_ids": track_ids,
        "off_ids": off_ids,
        "playlists": playlists,
        "favorites": favorites,
        "settings": settings,
        "updated_at": updated_at,
    }


def save_user_library(
    user_id: str,
    track_ids: list[str] | None = None,
    off_ids: list[str] | None = None,
    playlists: list | None = None,
    favorites: list | None = None,
    settings: dict | None = None,
    merge_tracks: bool = False,
) -> dict:
    """Updates or merges user's library and multi-device state."""
    current = get_user_library(user_id)
    now = time.time()

    if track_ids is not None:
        if merge_tracks:
            merged = list(dict.fromkeys(current["track_ids"] + track_ids))
            current["track_ids"] = merged
        else:
            current["track_ids"] = list(dict.fromkeys(track_ids))

    if off_ids is not None:
        current["off_ids"] = list(set(off_ids))

    if playlists is not None:
        current["playlists"] = playlists

    if favorites is not None:
        current["favorites"] = favorites

    if settings is not None:
        current["settings"] = {**current.get("settings", {}), **settings}

    conn = _get_db()
    with conn:
        conn.execute("""
            INSERT INTO user_libraries (user_id, track_ids, off_ids, playlists, favorites, settings, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                track_ids = excluded.track_ids,
                off_ids = excluded.off_ids,
                playlists = excluded.playlists,
                favorites = excluded.favorites,
                settings = excluded.settings,
                updated_at = excluded.updated_at
        """, (
            user_id,
            json.dumps(current["track_ids"]),
            json.dumps(current["off_ids"]),
            json.dumps(current["playlists"]),
            json.dumps(current["favorites"]),
            json.dumps(current["settings"]),
            now,
        ))
    conn.close()

    current["updated_at"] = now
    return current


def get_all_users_track_ids() -> set[str]:
    """Returns a set of all track IDs stored across all user libraries to protect from eviction."""
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT track_ids FROM user_libraries")
    res = set()
    for (row,) in cur.fetchall():
        try:
            for tid in json.loads(row or "[]"):
                res.add(tid)
        except Exception:
            pass
    conn.close()
    return res

