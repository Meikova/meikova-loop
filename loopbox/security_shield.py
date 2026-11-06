# -*- coding: utf-8 -*-
"""
Meikova Platform - Universal Security Shield for Meikova Loop
Defense-in-depth protection:
- 5-Strike IP and Account Lockout Tracker against brute-force attacks
- Artificial Timing Delay against side-channel timing analysis
- DNS-Resolving SSRF Validator (blocks private, loopback, and cloud metadata IPs)
- Host Boundary Guard for administrative endpoints (tunnel, cookies, settings)
- Security Headers Middleware (OWASP recommended)
"""

import hashlib
import ipaddress
import logging
import os
import random
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("meikova.loop.security")

# Configuration constants
MAX_FAILED_ATTEMPTS = int(os.environ.get("MEIKOVA_SECURITY_MAX_STRIKES", "5"))
LOCKOUT_DURATION_S = int(os.environ.get("MEIKOVA_SECURITY_LOCKOUT_S", "900"))  # 15 minutes
ADMIN_KEY = os.environ.get("MEIKOVA_LOOP_ADMIN_KEY", "").strip()


class SecurityShield:
    def __init__(self):
        self._lock = threading.Lock()
        # key -> {"strikes": int, "locked_until": float, "last_attempt": float}
        self._attempts: dict[str, dict] = {}

    def _get_keys(self, ip: str, identifier: str) -> list[str]:
        keys = []
        if ip:
            clean_ip = ip.strip()
            keys.append(f"ip:{clean_ip}")
        if identifier:
            clean_id = identifier.strip().lower()
            keys.append(f"id:{clean_id}")
        return keys

    def is_locked_out(self, ip: str, identifier: str = "") -> tuple[bool, int]:
        """Checks if either the IP or the identifier is locked out."""
        now = time.time()
        keys = self._get_keys(ip, identifier)
        with self._lock:
            for k in keys:
                entry = self._attempts.get(k)
                if entry and entry.get("locked_until", 0) > now:
                    remaining = int(entry["locked_until"] - now) + 1
                    return True, remaining
        return False, 0

    def record_failure(self, ip: str, identifier: str = "") -> tuple[int, bool, int]:
        """Records a failed authentication attempt. Returns (strikes, is_locked, remaining_seconds)."""
        now = time.time()
        keys = self._get_keys(ip, identifier)
        max_strikes = 0
        locked = False
        remaining = 0

        with self._lock:
            for k in keys:
                entry = self._attempts.setdefault(k, {"strikes": 0, "locked_until": 0.0, "last_attempt": now})
                # Reset strikes if last attempt was older than lockout duration
                if now - entry["last_attempt"] > LOCKOUT_DURATION_S and entry["locked_until"] <= now:
                    entry["strikes"] = 0

                entry["last_attempt"] = now
                entry["strikes"] += 1
                if entry["strikes"] >= MAX_FAILED_ATTEMPTS:
                    entry["locked_until"] = now + LOCKOUT_DURATION_S
                    locked = True
                    remaining = LOCKOUT_DURATION_S

                if entry["strikes"] > max_strikes:
                    max_strikes = entry["strikes"]

        return max_strikes, locked, remaining

    def record_success(self, ip: str, identifier: str = "") -> None:
        """Resets failed attempt counters upon successful authentication."""
        keys = self._get_keys(ip, identifier)
        with self._lock:
            for k in keys:
                self._attempts.pop(k, None)

    def apply_timing_delay(self, base_ms: float = 300.0, jitter_ms: float = 50.0) -> None:
        """Adds uniform artificial delay to mitigate timing attacks and slow down brute-force."""
        delay = (base_ms + random.uniform(0, jitter_ms)) / 1000.0
        time.sleep(delay)


# Global singleton instance
shield = SecurityShield()


def get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For if behind a proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # First IP in the comma-separated list is the original client
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host.strip()
    return "127.0.0.1"


def is_trusted_host_client(request: Request) -> bool:
    """Verifies if request originated from trusted host environment (localhost, desktop shell, or admin key)."""
    # 1. Check Admin Key header if configured
    req_key = request.headers.get("x-admin-key", "").strip()
    if ADMIN_KEY and req_key and req_key == ADMIN_KEY:
        return True

    # 2. Check Client IP
    ip = get_client_ip(request)
    trusted_ips = {"127.0.0.1", "::1", "localhost", "testclient"}
    if ip in trusted_ips:
        return True

    # Check loopback range
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_loopback:
            return True
    except ValueError:
        pass

    return False


def validate_remote_url(url_str: str, allow_local_temp_for_testing: bool = False) -> str:
    """
    Validates a remote URL against SSRF, LFI, and unauthorized protocols.
    Only allows http/https schemes, and blocks private, loopback, and link-local destinations.
    Strictly forbids file:// schema under all circumstances.
    """
    if not url_str or not isinstance(url_str, str):
        raise ValueError("URL cannot be empty")

    url_str = url_str.strip()
    # 1. Strictly forbid file:// schema
    if url_str.lower().startswith("file://") or url_str.lower().startswith("file:"):
        raise ValueError("Local file system schema (file://) is strictly prohibited")

    # 2. Check for local filesystem paths
    if not (url_str.startswith("http://") or url_str.startswith("https://")):
        if allow_local_temp_for_testing:
            p = Path(url_str)
            allowed_audio_exts = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".webm", ".aac"}
            if p.suffix.lower() in allowed_audio_exts and p.exists():
                try:
                    temp_dir = Path(tempfile.gettempdir()).resolve()
                    if temp_dir in p.resolve().parents or p.resolve().parent == temp_dir:
                        return str(p.resolve())
                except Exception:
                    pass
        raise ValueError("Only http:// and https:// URL schemes are permitted")

    try:
        parsed = urlparse(url_str)
    except Exception as e:
        raise ValueError(f"Invalid URL structure: {e}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Prohibited URL scheme '{scheme}'. Only http and https are permitted.")

    hostname = (parsed.hostname or "").strip().lower().strip("[]")
    if not hostname:
        raise ValueError("URL must contain a valid host")

    # Reject obvious localhost / metadata identifiers
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "169.254.169.254"):
        raise ValueError("Disallowed destination: localhost or cloud metadata host")

    # Resolve hostname via DNS and inspect all resolved IP addresses
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"Failed to resolve host '{hostname}': {e}")

    resolved_ips = {item[4][0] for item in addr_info}
    for resolved_ip in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(resolved_ip)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or resolved_ip == "169.254.169.254"
            ):
                raise ValueError(f"SSRF blocked: Host '{hostname}' resolves to private/reserved IP {resolved_ip}")
        except ValueError as err:
            if "SSRF blocked" in str(err):
                raise
            raise ValueError(f"Invalid resolved IP address: {resolved_ip}")

    return url_str


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        return response
