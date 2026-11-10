"""Meikova Cluster Link — Zero-Config LAN Server Discovery (UDP Broadcast Beacon).

Allows multiple independent instances of `python -m loopbox.server` on the same LAN
to automatically discover each other and link into a unified speaker cluster (PartyBoost)
without requiring central configuration.
"""
from __future__ import annotations

import json
import logging
import secrets
import socket
import threading
import time
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger("loopbox.cluster_discovery")

BEACON_UDP_PORT = 8766
BEACON_INTERVAL_SEC = 3.0
PEER_TTL_SEC = 10.5


def _detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.3)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


class ClusterBeaconManager:
    """Manages UDP broadcast beacons and LAN peer table for Meikova Cluster Link."""

    def __init__(self, beacon_port: int = BEACON_UDP_PORT, http_port: int = 8765, port: int | None = None) -> None:
        self.server_id: str = f"srv-{secrets.token_hex(4)}"
        self.hostname: str = socket.gethostname() or "Meikova-Host"
        self.http_port: int = int(port or http_port or 8765)
        self.beacon_port: int = beacon_port
        self._lock = threading.Lock()
        self._peers: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._status_provider: Callable[[], Dict[str, Any]] | None = None
        self._tx_thread: threading.Thread | None = None
        self._rx_thread: threading.Thread | None = None

    def set_status_provider(self, provider: Callable[[], Dict[str, Any]]) -> None:
        self._status_provider = provider

    def get_local_info(self) -> Dict[str, Any]:
        lan_ip = _detect_lan_ip()
        extra: Dict[str, Any] = {}
        if self._status_provider:
            try:
                extra = self._status_provider() or {}
            except Exception:
                extra = {}
        return {
            "app": "meikova_loop",
            "server_id": self.server_id,
            "name": extra.get("server_name") or self.hostname,
            "hostname": self.hostname,
            "ip": lan_ip,
            "port": self.http_port,
            "url": f"http://{lan_ip}:{self.http_port}",
            "ws_url": f"ws://{lan_ip}:{self.http_port}/api/ws/stage-sync",
            "cluster_enabled": bool(extra.get("cluster_enabled", False)),
            "cluster_id": extra.get("cluster_id") or "",
            "cluster_mode": extra.get("cluster_mode") or "party",
            "nodes_count": int(extra.get("nodes_count", 0)),
            "active_title": extra.get("active_title") or "",
            "timestamp": int(time.time() * 1000),
        }

    def start(self, http_port: int = 8765, status_provider: Callable[[], Dict[str, Any]] | None = None) -> None:
        self.http_port = int(http_port or 8765)
        if status_provider is not None:
            self._status_provider = status_provider
        if self._running:
            return
        self._running = True
        self._rx_thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="cluster-beacon-rx"
        )
        self._tx_thread = threading.Thread(
            target=self._broadcast_loop, daemon=True, name="cluster-beacon-tx"
        )
        self._rx_thread.start()
        self._tx_thread.start()

    def stop(self) -> None:
        self._running = False

    def ingest_beacon_payload(self, payload: Dict[str, Any], sender_ip: str | None = None) -> bool:
        """Process a decoded JSON beacon packet and update peer table."""
        if not isinstance(payload, dict) or payload.get("app") != "meikova_loop":
            return False
        peer_id = str(payload.get("server_id") or "").strip()
        if not peer_id or peer_id == self.server_id:
            return False

        ip = str(payload.get("ip") or sender_ip or "").strip()
        if ip in ("", "0.0.0.0", "127.0.0.1") and sender_ip and sender_ip not in ("0.0.0.0",):
            ip = sender_ip
        try:
            port = int(payload.get("port") or 8765)
        except (TypeError, ValueError):
            port = 8765
        if not ip:
            return False

        now = time.monotonic()
        url = f"http://{ip}:{port}"
        ws_url = f"ws://{ip}:{port}/api/ws/stage-sync"
        entry = {
            "server_id": peer_id,
            "name": str(payload.get("name") or payload.get("hostname") or f"MashLoop ({ip})")[:64],
            "hostname": str(payload.get("hostname") or ip)[:64],
            "ip": ip,
            "port": port,
            "url": url,
            "ws_url": ws_url,
            "cluster_enabled": bool(payload.get("cluster_enabled", False)),
            "cluster_id": str(payload.get("cluster_id") or ""),
            "cluster_mode": str(payload.get("cluster_mode") or "party"),
            "nodes_count": int(payload.get("nodes_count") or 0),
            "active_title": str(payload.get("active_title") or "")[:120],
            "last_seen": now,
            "manual": False,
        }
        with self._lock:
            existing = self._peers.get(peer_id)
            if existing and existing.get("manual"):
                entry["manual"] = True
            self._peers[peer_id] = entry
        return True

    def add_manual_peer(self, address: str, port: int = 8765, name: str | None = None) -> Dict[str, Any]:
        raw = (address or "").strip()
        if not raw:
            raise ValueError("CLUSTER_INVALID_PEER_ADDRESS")

        parsed_host = raw
        parsed_port = int(port or 8765)
        scheme = "http"
        ws_scheme = "ws"

        if "://" in raw:
            u = urlparse(raw)
            parsed_host = u.hostname or ""
            if u.port:
                parsed_port = int(u.port)
            if u.scheme in ("https", "wss"):
                scheme = "https"
                ws_scheme = "wss"
        elif ":" in raw:
            host_part, port_part = raw.rsplit(":", 1)
            parsed_host = host_part.strip()
            try:
                parsed_port = int(port_part.strip())
            except ValueError:
                pass

        if not parsed_host:
            raise ValueError("CLUSTER_INVALID_PEER_ADDRESS")

        peer_id = f"manual-{parsed_host}-{parsed_port}"
        default_url = f"{scheme}://{parsed_host}:{parsed_port}" if parsed_port not in (80, 443) else f"{scheme}://{parsed_host}"
        ws_url = f"{ws_scheme}://{parsed_host}:{parsed_port}/api/ws/stage-sync" if parsed_port not in (80, 443) else f"{ws_scheme}://{parsed_host}/api/ws/stage-sync"

        entry = {
            "server_id": peer_id,
            "name": (name or f"Máy chủ {parsed_host}:{parsed_port}").strip()[:64],
            "hostname": parsed_host,
            "ip": parsed_host,
            "port": parsed_port,
            "url": default_url,
            "ws_url": ws_url,
            "cluster_enabled": True,
            "cluster_id": "",
            "cluster_mode": "party",
            "nodes_count": 1,
            "active_title": "",
            "last_seen": time.monotonic(),
            "manual": True,
        }
        with self._lock:
            self._peers[peer_id] = entry
        return dict(entry)

    def remove_peer(self, peer_id_or_address: str) -> bool:
        target = (peer_id_or_address or "").strip()
        if not target:
            return False
        with self._lock:
            if target in self._peers:
                self._peers.pop(target, None)
                return True
            for pid, p in list(self._peers.items()):
                ip_port = f"{p.get('ip')}:{p.get('port')}"
                if target in (p.get("ip"), ip_port, p.get("url"), p.get("ws_url")):
                    self._peers.pop(pid, None)
                    return True
        return False

    def get_active_peers(self) -> List[Dict[str, Any]]:
        now = time.monotonic()
        active: List[Dict[str, Any]] = []
        expired: List[str] = []
        with self._lock:
            for pid, p in self._peers.items():
                age = now - float(p.get("last_seen", 0.0))
                if not p.get("manual") and age > PEER_TTL_SEC:
                    expired.append(pid)
                    continue
                item = dict(p)
                item["age_sec"] = round(max(0.0, age), 1)
                item.pop("last_seen", None)
                active.append(item)
            for pid in expired:
                self._peers.pop(pid, None)
        active.sort(key=lambda x: (not x.get("cluster_enabled", False), x.get("name", "")))
        return active

    def _broadcast_loop(self) -> None:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.5)
        except Exception as e:
            logger.debug("Cluster beacon TX socket init failed: %s", e)
            return

        try:
            while self._running:
                try:
                    info = self.get_local_info()
                    raw = json.dumps(info).encode("utf-8")
                    targets = {("255.255.255.255", self.beacon_port)}
                    lan_ip = info.get("ip", "")
                    if lan_ip and "." in lan_ip and not lan_ip.startswith("127."):
                        parts = lan_ip.split(".")
                        if len(parts) == 4:
                            targets.add((f"{parts[0]}.{parts[1]}.{parts[2]}.255", self.beacon_port))
                    for target in targets:
                        try:
                            sock.sendto(raw, target)
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(BEACON_INTERVAL_SEC)
        finally:
            try:
                if sock:
                    sock.close()
            except Exception:
                pass

    def _listen_loop(self) -> None:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
            sock.bind(("0.0.0.0", self.beacon_port))
            sock.settimeout(1.0)
        except Exception as e:
            logger.debug("Cluster beacon RX socket bind on %d skipped: %s", self.beacon_port, e)
            return

        try:
            while self._running:
                try:
                    data, addr = sock.recvfrom(4096)
                    if not data:
                        continue
                    payload = json.loads(data.decode("utf-8", errors="ignore"))
                    sender_ip = addr[0] if addr else None
                    self.ingest_beacon_payload(payload, sender_ip=sender_ip)
                except socket.timeout:
                    continue
                except Exception:
                    continue
        finally:
            try:
                if sock:
                    sock.close()
            except Exception:
                pass


cluster_beacon = ClusterBeaconManager()
