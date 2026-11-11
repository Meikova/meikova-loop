"""Meikova Continuum Stage, Light & Cluster Speaker Sync Hub.

Manages real-time WebSocket communication between the Master Host (PC player),
Cluster Speaker nodes (PartyBoost / Stereo Pair multi-instance mesh),
Satellite displays (mobile/tablet/TV visualizers), and physical smart lighting systems.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Dict, List, Set
from fastapi import WebSocket

logger = logging.getLogger("loopbox.stage_sync")


class StageSyncHub:
    def __init__(self) -> None:
        self.hosts: Set[WebSocket] = set()
        self.satellites: Set[WebSocket] = set()
        self.audio_satellites: Set[WebSocket] = set()
        self.active_host: WebSocket | None = None
        self.host_last_playing: Dict[int, float] = {}
        self.host_last_seen: Dict[int, float] = {}
        self.host_last_focused: Dict[int, float] = {}

        # Per-WebSocket metadata registry keyed by id(ws)
        self.clients: Dict[int, Dict[str, Any]] = {}
        self._client_seq: int = 0

        # Meikova Cluster Link (PartyBoost / Stereo Pair) state
        self.cluster_enabled: bool = False
        self.cluster_id: str = f"cluster-{secrets.token_hex(3)}"
        self.cluster_mode: str = "party"  # "party" | "stereo_pair"
        self.cluster_master_ws: WebSocket | None = None
        self.cluster_master_volume: float = 1.0
        self.host_align_ms: int = 60

        self.last_telemetry: Dict[str, Any] = {
            "type": "telemetry",
            "track_id": "",
            "title": "Chờ phát nhạc...",
            "artist": "Meikova Loop",
            "mode": "idle",
            "acc": [0.8, 0.1, 40],
            "acc2": [0.8, 0.1, 72],
            "ground": [40, 0.012],
            "fill_a": 0.0,
            "pulse": 0.0,
            "bass": 0.0,
            "peak": 0.0,
            "angle": 0.0,
            "progress": 0.0,
            "bpm": 120,
            "t": int(time.time() * 1000),
        }
        self.smart_lights_callback = None

    @staticmethod
    def clock_ms() -> float:
        """High-resolution monotonic reference clock in milliseconds for NTP audio sync."""
        return round(time.perf_counter() * 1000.0, 3)

    def _build_idle_telemetry(self) -> Dict[str, Any]:
        return {
            "type": "telemetry",
            "track_id": "",
            "title": "Chờ phát nhạc...",
            "artist": "Meikova Loop",
            "mode": "idle",
            "acc": self.last_telemetry.get("acc", [0.8, 0.1, 40]),
            "acc2": self.last_telemetry.get("acc2", [0.8, 0.1, 72]),
            "ground": self.last_telemetry.get("ground", [40, 0.012]),
            "fill_a": 0.0,
            "pulse": 0.0,
            "bass": 0.0,
            "peak": 0.0,
            "angle": 0.0,
            "progress": 0.0,
            "bpm": 120,
            "t": int(time.time() * 1000),
        }

    def register_smart_lights_callback(self, cb) -> None:
        self.smart_lights_callback = cb

    def _ensure_client_meta(self, ws: WebSocket, role: str = "satellite") -> Dict[str, Any]:
        ws_id = id(ws)
        meta = self.clients.get(ws_id)
        if meta is not None:
            return meta
        self._client_seq += 1
        qp = getattr(ws, "query_params", {}) or {}
        qp_cid = str(qp.get("client_id") or "").strip()[:48]
        qp_name = str(qp.get("device_name") or "").strip()[:48]
        qp_type = str(qp.get("device_type") or "").strip()
        default_id = qp_cid or f"node-{self._client_seq}-{secrets.token_hex(2)}"
        default_name = qp_name or (f"Trạm phát #{self._client_seq}" if role == "host" else f"Vệ tinh #{self._client_seq}")
        default_dtype = qp_type if qp_type in ("desktop", "mobile", "tablet") else ("desktop" if role == "host" else "mobile")
        in_cluster = False
        cluster_role = "standalone"
        channel_mode = "stereo"
        if self.cluster_enabled and role == "host":
            in_cluster = True
            if self.cluster_master_ws is None or self.cluster_master_ws not in self.hosts:
                self.cluster_master_ws = ws
                cluster_role = "master"
                channel_mode = "left" if self.cluster_mode == "stereo_pair" else "stereo"
            else:
                cluster_role = "node"
                channel_mode = "right" if self.cluster_mode == "stereo_pair" else "stereo"

        meta = {
            "ws": ws,
            "ws_id": ws_id,
            "client_id": default_id,
            "device_name": default_name,
            "device_type": default_dtype,
            "role": role,
            "in_cluster": in_cluster,
            "cluster_role": cluster_role,
            "channel_mode": channel_mode,
            "volume_trim": 1.0,
            "latency_offset_ms": 0,
            "rtt_ms": 0.0,
            "origin_url": "",
            "connected_at": time.time(),
        }
        self.clients[ws_id] = meta
        return meta

    def _serialize_client_node(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        ws = meta.get("ws")
        return {
            "client_id": meta.get("client_id", ""),
            "device_name": meta.get("device_name", "Thiết bị"),
            "device_type": meta.get("device_type", "desktop"),
            "role": meta.get("role", "host"),
            "in_cluster": bool(meta.get("in_cluster", False)),
            "cluster_role": meta.get("cluster_role", "standalone"),
            "is_master": bool(self.cluster_enabled and ws is not None and ws is self.cluster_master_ws),
            "is_audio_satellite": bool(ws in self.audio_satellites),
            "channel_mode": meta.get("channel_mode", "stereo"),
            "volume_trim": round(float(meta.get("volume_trim", 1.0)), 2),
            "latency_offset_ms": int(meta.get("latency_offset_ms", 0)),
            "rtt_ms": round(float(meta.get("rtt_ms", 0.0)), 1),
            "origin_url": meta.get("origin_url", ""),
        }

    def get_cluster_status(self) -> Dict[str, Any]:
        if self.cluster_master_ws is not None and id(self.cluster_master_ws) not in self.clients:
            self.cluster_master_ws = None

        if self.cluster_enabled and self.cluster_master_ws is None and self.clients:
            # Auto-heal master if previous master disconnected
            for h in list(self.hosts):
                meta = self.clients.get(id(h))
                if meta and meta.get("in_cluster"):
                    self.cluster_master_ws = h
                    meta["cluster_role"] = "master"
                    break
            if self.cluster_master_ws is None and self.hosts:
                first_h = next(iter(self.hosts))
                meta = self.clients.get(id(first_h))
                if meta:
                    self.cluster_master_ws = first_h
                    meta["in_cluster"] = True
                    meta["cluster_role"] = "master"

        nodes_list: List[Dict[str, Any]] = []
        clustered_count = 0
        master_meta: Dict[str, Any] | None = None

        for ws_id, meta in list(self.clients.items()):
            ws = meta.get("ws")
            if ws not in self.hosts and ws not in self.satellites:
                self.clients.pop(ws_id, None)
                continue
            if self.cluster_enabled and ws is self.cluster_master_ws:
                meta["cluster_role"] = "master"
                meta["in_cluster"] = True
                master_meta = meta
            elif self.cluster_enabled and meta.get("in_cluster"):
                meta["cluster_role"] = "node"
            else:
                meta["cluster_role"] = "standalone"
                meta["in_cluster"] = False

            if meta.get("in_cluster"):
                clustered_count += 1
            nodes_list.append(self._serialize_client_node(meta))

        nodes_list.sort(
            key=lambda n: (
                0 if n.get("is_master") else (1 if n.get("in_cluster") else 2),
                0 if n.get("role") == "host" else 1,
                n.get("device_name", ""),
            )
        )

        master_cid = master_meta.get("client_id", "") if master_meta else ""
        return {
            "type": "cluster_state",
            "cluster_enabled": self.cluster_enabled,
            "cluster_id": self.cluster_id,
            "cluster_mode": self.cluster_mode,
            "master_client_id": master_cid,
            "master_id": master_cid,
            "master_name": master_meta.get("device_name", "") if master_meta else "",
            "master_volume": round(float(self.cluster_master_volume), 2),
            "host_align_ms": int(self.host_align_ms),
            "audio_stream_required": bool(
                (self.cluster_enabled and clustered_count >= 2) or len(self.audio_satellites) > 0
            ),
            "nodes_count": clustered_count,
            "total_clients_count": len(nodes_list),
            "satellites_count": len(self.satellites),
            "audio_satellites_count": len(self.audio_satellites),
            "hosts_count": len(self.hosts),
            "nodes": nodes_list,
            "active_telemetry": {
                "track_id": self.last_telemetry.get("track_id", ""),
                "title": self.last_telemetry.get("title", "Chờ phát nhạc..."),
                "artist": self.last_telemetry.get("artist", "Meikova Loop"),
                "mode": self.last_telemetry.get("mode", "idle"),
            },
            "server_clock_ms": self.clock_ms(),
            "t": int(time.time() * 1000),
        }

    def _find_client_meta(self, client_id: str | None = None, ws: WebSocket | None = None) -> Dict[str, Any] | None:
        if ws is not None and id(ws) in self.clients:
            return self.clients[id(ws)]
        if client_id:
            target = str(client_id).strip()
            for meta in self.clients.values():
                if meta.get("client_id") == target:
                    return meta
        return None

    def _apply_cluster_channel_assignments(self, force_reset: bool = False) -> None:
        if not self.cluster_enabled:
            for meta in self.clients.values():
                meta["channel_mode"] = "stereo"
            return

        if self.cluster_mode == "party":
            for meta in self.clients.values():
                if meta.get("in_cluster"):
                    meta["channel_mode"] = "stereo"
        elif self.cluster_mode == "stereo_pair":
            follower_idx = 0
            for meta in self.clients.values():
                if not meta.get("in_cluster"):
                    continue
                if meta.get("ws") is self.cluster_master_ws:
                    if force_reset or meta.get("channel_mode") == "stereo":
                        meta["channel_mode"] = "left"
                else:
                    if force_reset or meta.get("channel_mode") == "stereo":
                        meta["channel_mode"] = "right" if (follower_idx % 2 == 0) else "left"
                    follower_idx += 1

    async def set_cluster_state(
        self,
        enabled: bool,
        mode: str | None = None,
        initiator_ws: WebSocket | None = None,
        initiator_client_id: str | None = None,
        host_align_ms: int | None = None,
        master_volume: float | None = None,
    ) -> Dict[str, Any]:
        prev_mode = self.cluster_mode
        if mode in ("party", "stereo_pair"):
            self.cluster_mode = mode
        if host_align_ms is not None:
            self.host_align_ms = max(0, min(250, int(host_align_ms)))
        if master_volume is not None:
            self.cluster_master_volume = max(0.0, min(1.5, float(master_volume)))

        if enabled:
            self.cluster_enabled = True
            initiator_meta = self._find_client_meta(client_id=initiator_client_id, ws=initiator_ws)
            master_ws = initiator_meta["ws"] if initiator_meta else None
            if master_ws is None:
                if self.cluster_master_ws in self.hosts:
                    master_ws = self.cluster_master_ws
                elif self.active_host in self.hosts:
                    master_ws = self.active_host
                elif self.hosts:
                    master_ws = max(self.hosts, key=lambda h: self.host_last_seen.get(id(h), 0.0))
                elif self.satellites:
                    master_ws = next(iter(self.satellites))

            self.cluster_master_ws = master_ws
            if master_ws in self.hosts:
                self.active_host = master_ws

            for meta in self.clients.values():
                w = meta.get("ws")
                if w is master_ws:
                    meta["in_cluster"] = True
                    meta["cluster_role"] = "master"
                elif w in self.hosts or w in self.audio_satellites or meta.get("in_cluster"):
                    meta["in_cluster"] = True
                    meta["cluster_role"] = "node"

            self._apply_cluster_channel_assignments(force_reset=(prev_mode != self.cluster_mode or True))
        else:
            self.cluster_enabled = False
            self.cluster_master_ws = None
            for meta in self.clients.values():
                meta["in_cluster"] = False
                meta["cluster_role"] = "standalone"
                meta["channel_mode"] = "stereo"

        await self.broadcast_cluster_state()
        await self.broadcast_status()
        return self.get_cluster_status()

    async def configure_node(
        self,
        client_id: str | None = None,
        ws: WebSocket | None = None,
        channel_mode: str | None = None,
        volume_trim: float | None = None,
        latency_offset_ms: int | None = None,
        in_cluster: bool | None = None,
        device_name: str | None = None,
        claim_master: bool = False,
    ) -> Dict[str, Any]:
        meta = self._find_client_meta(client_id=client_id, ws=ws)
        if meta is None:
            return self.get_cluster_status()

        if device_name is not None and str(device_name).strip():
            meta["device_name"] = str(device_name).strip()[:48]
        if channel_mode in ("stereo", "left", "right"):
            meta["channel_mode"] = channel_mode
        if volume_trim is not None:
            meta["volume_trim"] = max(0.0, min(1.5, float(volume_trim)))
        if latency_offset_ms is not None:
            meta["latency_offset_ms"] = max(-100, min(100, int(latency_offset_ms)))
        if in_cluster is not None:
            meta["in_cluster"] = bool(in_cluster)
            if not meta["in_cluster"]:
                meta["cluster_role"] = "standalone"
                if self.cluster_master_ws is meta.get("ws"):
                    self.cluster_master_ws = None
            elif self.cluster_enabled:
                if self.cluster_master_ws is None:
                    self.cluster_master_ws = meta.get("ws")
                    meta["cluster_role"] = "master"
                elif self.cluster_master_ws is not meta.get("ws"):
                    meta["cluster_role"] = "node"

        if claim_master:
            self.cluster_enabled = True
            target_ws = meta.get("ws")
            self.cluster_master_ws = target_ws
            if target_ws in self.hosts:
                self.active_host = target_ws
            meta["in_cluster"] = True
            meta["cluster_role"] = "master"
            for other in self.clients.values():
                if other is not meta and other.get("in_cluster"):
                    other["cluster_role"] = "node"

        await self.broadcast_cluster_state()
        await self.broadcast_status()
        return self.get_cluster_status()

    async def broadcast_cluster_state(self) -> None:
        state_obj = self.get_cluster_status()
        state_str = json.dumps(state_obj)
        all_ws = list(self.hosts | self.satellites)
        for client_ws in all_ws:
            try:
                await client_ws.send_text(state_str)
            except Exception:
                pass

    async def connect(self, ws: WebSocket, role: str = "satellite") -> None:
        await ws.accept()
        meta = self._ensure_client_meta(ws, role=role)
        if role == "host":
            self.hosts.add(ws)
            self.host_last_seen[id(ws)] = time.monotonic()
            if self.cluster_enabled:
                if self.cluster_master_ws is None or id(self.cluster_master_ws) not in self.clients:
                    self.cluster_master_ws = ws
                    meta["in_cluster"] = True
                    meta["cluster_role"] = "master"
                else:
                    meta["in_cluster"] = True
                    meta["cluster_role"] = "node"
                self._apply_cluster_channel_assignments(force_reset=False)
            logger.info("Host client connected to StageSyncHub (Total hosts: %d)", len(self.hosts))
        else:
            self.satellites.add(ws)
            logger.info("Satellite client connected to StageSyncHub (Total satellites: %d)", len(self.satellites))

        # Send latest known telemetry immediately so satellite or cluster node has track context
        if self.last_telemetry:
            try:
                await ws.send_text(json.dumps(self.last_telemetry))
            except Exception:
                pass

        # Send initial cluster state & assigned client identity
        try:
            await ws.send_text(
                json.dumps({
                    "type": "welcome_sync",
                    "assigned_client_id": meta["client_id"],
                    "server_clock_ms": self.clock_ms(),
                    "cluster": self.get_cluster_status(),
                })
            )
        except Exception:
            pass

        await self.broadcast_status()
        await self.broadcast_cluster_state()

    async def disconnect(self, ws: WebSocket, role: str = "satellite") -> None:
        reset_telemetry_str: str | None = None
        ws_id = id(ws)
        self.clients.pop(ws_id, None)

        if role == "host":
            self.hosts.discard(ws)
            self.host_last_playing.pop(ws_id, None)
            self.host_last_seen.pop(ws_id, None)
            self.host_last_focused.pop(ws_id, None)
            if self.cluster_master_ws is ws:
                self.cluster_master_ws = None
            if self.active_host is ws:
                now = time.monotonic()
                replacement = None
                for h in list(self.hosts):
                    if now - self.host_last_playing.get(id(h), 0.0) <= 0.45:
                        replacement = h
                        break
                self.active_host = replacement
                if replacement is None and self.last_telemetry.get("mode") != "idle":
                    self.last_telemetry = self._build_idle_telemetry()
                    reset_telemetry_str = json.dumps(self.last_telemetry)
            logger.info("Host client disconnected from StageSyncHub (Remaining hosts: %d)", len(self.hosts))
        else:
            self.satellites.discard(ws)
            self.audio_satellites.discard(ws)
            if self.cluster_master_ws is ws:
                self.cluster_master_ws = None
            logger.info("Satellite client disconnected from StageSyncHub (Remaining satellites: %d)", len(self.satellites))

        if reset_telemetry_str is not None and self.satellites:
            dead_sats = set()
            for sat in list(self.satellites):
                try:
                    await sat.send_text(reset_telemetry_str)
                except Exception:
                    dead_sats.add(sat)
            if dead_sats:
                self.satellites.difference_update(dead_sats)
                self.audio_satellites.difference_update(dead_sats)

        await self.broadcast_status()
        await self.broadcast_cluster_state()

    async def broadcast_status(self) -> None:
        cluster_nodes_count = sum(
            1
            for m in self.clients.values()
            if m.get("in_cluster") and m.get("cluster_role") == "node"
        )
        status_msg = json.dumps({
            "type": "sync_status",
            "satellites_count": len(self.satellites),
            "audio_satellites_count": len(self.audio_satellites),
            "cluster_enabled": self.cluster_enabled,
            "cluster_mode": self.cluster_mode,
            "cluster_nodes_count": cluster_nodes_count,
            "hosts_count": len(self.hosts),
            "has_host": len(self.hosts) > 0,
            "host_align_ms": self.host_align_ms,
            "server_clock_ms": self.clock_ms(),
            "t": int(time.time() * 1000),
        })
        dead_hosts = set()
        for host in list(self.hosts):
            try:
                await host.send_text(status_msg)
            except Exception:
                dead_hosts.add(host)
        if dead_hosts:
            for dh in dead_hosts:
                self.hosts.discard(dh)
                self.clients.pop(id(dh), None)
                self.host_last_playing.pop(id(dh), None)
                self.host_last_seen.pop(id(dh), None)
                self.host_last_focused.pop(id(dh), None)
                if self.active_host is dh:
                    self.active_host = None
                if self.cluster_master_ws is dh:
                    self.cluster_master_ws = None

        dead_sats = set()
        for sat in list(self.satellites):
            try:
                await sat.send_text(status_msg)
            except Exception:
                dead_sats.add(sat)
        if dead_sats:
            for ds in dead_sats:
                self.clients.pop(id(ds), None)
            self.satellites.difference_update(dead_sats)
            self.audio_satellites.difference_update(dead_sats)

    async def _handle_common_control_message(self, data: Dict[str, Any], ws: WebSocket | None, role: str) -> bool:
        """Handle NTP clock sync, client hello, and cluster management messages from any client."""
        msg_type = data.get("type", "")
        if msg_type == "ping_sync":
            if ws is not None:
                srv_ms = self.clock_ms()
                rtt_report = data.get("rtt_ms")
                if rtt_report is not None and id(ws) in self.clients:
                    try:
                        self.clients[id(ws)]["rtt_ms"] = max(0.0, min(5000.0, float(rtt_report)))
                    except (TypeError, ValueError):
                        pass
                pong = {
                    "type": "pong_sync",
                    "seq": data.get("seq", 0),
                    "t0": data.get("t0", 0),
                    "t1": srv_ms,
                    "t2": self.clock_ms(),
                    "host_align_ms": self.host_align_ms,
                }
                try:
                    await ws.send_text(json.dumps(pong))
                except Exception:
                    pass
            return True

        if msg_type in ("hello", "node_hello"):
            if ws is not None:
                meta = self._ensure_client_meta(ws, role=role)
                cid = str(data.get("client_id") or "").strip()
                if cid:
                    meta["client_id"] = cid[:64]
                dname = str(data.get("device_name") or "").strip()
                if dname:
                    meta["device_name"] = dname[:48]
                dtype = str(data.get("device_type") or "").strip()
                if dtype in ("desktop", "mobile", "tablet"):
                    meta["device_type"] = dtype
                if data.get("origin_url"):
                    meta["origin_url"] = str(data.get("origin_url"))[:128]
                if data.get("channel_mode") in ("stereo", "left", "right") and not self.cluster_enabled:
                    meta["channel_mode"] = data["channel_mode"]
                if data.get("volume_trim") is not None:
                    try:
                        meta["volume_trim"] = max(0.0, min(1.5, float(data["volume_trim"])))
                    except (TypeError, ValueError):
                        pass
                if data.get("latency_offset_ms") is not None:
                    try:
                        meta["latency_offset_ms"] = max(-100, min(100, int(data["latency_offset_ms"])))
                    except (TypeError, ValueError):
                        pass
                if data.get("join_cluster") and self.cluster_enabled:
                    meta["in_cluster"] = True
                    if self.cluster_master_ws is None:
                        self.cluster_master_ws = ws
                        meta["cluster_role"] = "master"
                    elif self.cluster_master_ws is not ws:
                        meta["cluster_role"] = "node"
                    self._apply_cluster_channel_assignments(force_reset=False)
                await self.broadcast_cluster_state()
            return True

        if msg_type == "cluster_toggle":
            enabled = bool(data.get("enabled", not self.cluster_enabled))
            mode = data.get("mode")
            await self.set_cluster_state(
                enabled=enabled,
                mode=mode,
                initiator_ws=ws,
                initiator_client_id=data.get("client_id"),
                host_align_ms=data.get("host_align_ms"),
                master_volume=data.get("master_volume"),
            )
            return True

        if msg_type == "cluster_join":
            if ws is not None:
                meta = self._ensure_client_meta(ws, role=role)
                if not self.cluster_enabled:
                    await self.set_cluster_state(enabled=True, mode=data.get("mode") or self.cluster_mode, initiator_ws=ws)
                else:
                    meta["in_cluster"] = True
                    if self.cluster_master_ws is None:
                        self.cluster_master_ws = ws
                        meta["cluster_role"] = "master"
                    elif self.cluster_master_ws is not ws:
                        meta["cluster_role"] = "node"
                    if data.get("channel_mode") in ("stereo", "left", "right"):
                        meta["channel_mode"] = data["channel_mode"]
                    else:
                        self._apply_cluster_channel_assignments(force_reset=False)
                    await self.broadcast_cluster_state()
                    await self.broadcast_status()
            return True

        if msg_type == "cluster_leave":
            await self.configure_node(
                client_id=data.get("client_id"),
                ws=ws if not data.get("client_id") else None,
                in_cluster=False,
            )
            return True

        if msg_type == "cluster_node_config":
            if data.get("host_align_ms") is not None:
                self.host_align_ms = max(0, min(250, int(data["host_align_ms"])))
            if data.get("master_volume") is not None:
                self.cluster_master_volume = max(0.0, min(1.5, float(data["master_volume"])))
            if data.get("mode") in ("party", "stereo_pair") and data.get("mode") != self.cluster_mode:
                self.cluster_mode = data["mode"]
                self._apply_cluster_channel_assignments(force_reset=True)
            await self.configure_node(
                client_id=data.get("target_client_id") or data.get("client_id"),
                ws=ws if not (data.get("target_client_id") or data.get("client_id")) else None,
                channel_mode=data.get("channel_mode"),
                volume_trim=data.get("volume_trim"),
                latency_offset_ms=data.get("latency_offset_ms"),
                in_cluster=data.get("in_cluster"),
                device_name=data.get("device_name"),
                claim_master=bool(data.get("claim_master", False)),
            )
            return True

        if msg_type == "cluster_claim_master":
            await self.configure_node(
                client_id=data.get("client_id"),
                ws=ws,
                claim_master=True,
            )
            return True

        if msg_type == "same_machine_speaker_sync" and ws is not None:
            sender_ip = getattr(ws.client, "host", "") if getattr(ws, "client", None) else ""
            sender_is_loopback = sender_ip in ("127.0.0.1", "::1", "localhost", "testclient")
            payload_str = json.dumps({
                "type": "same_machine_speaker_sync",
                "clientId": data.get("clientId") or data.get("client_id") or "",
                "suppressMasterSpeaker": bool(data.get("suppressMasterSpeaker", False)),
                "isMutedLocal": bool(data.get("isMutedLocal", False)),
            })
            for meta in list(self.clients.values()):
                target_ws = meta.get("ws")
                if target_ws is None or target_ws is ws:
                    continue
                target_ip = getattr(target_ws.client, "host", "") if getattr(target_ws, "client", None) else ""
                target_is_loopback = target_ip in ("127.0.0.1", "::1", "localhost", "testclient")
                is_same = (sender_is_loopback and target_is_loopback) or (bool(sender_ip) and sender_ip == target_ip)
                if is_same:
                    try:
                        await target_ws.send_text(payload_str)
                    except Exception:
                        pass
            return True

        return False

    async def handle_host_message(self, data: Dict[str, Any], ws: WebSocket | None = None) -> None:
        if await self._handle_common_control_message(data, ws, role="host"):
            return

        msg_type = data.get("type", "telemetry")
        now = time.monotonic()

        if self.active_host is not None and self.hosts and self.active_host not in self.hosts:
            self.active_host = None

        if msg_type == "telemetry":
            if ws is not None:
                ws_id = id(ws)
                self.host_last_seen[ws_id] = now

                # When Cluster Link is active, the designated Cluster Master has exclusive stage authority
                if (
                    self.cluster_enabled
                    and self.cluster_master_ws is not None
                    and self.cluster_master_ws in self.hosts
                    and ws is not self.cluster_master_ws
                ):
                    return

                mode = data.get("mode", "idle")
                has_track = bool(data.get("track_id"))
                is_playing = has_track and mode in ("ring", "playing")
                is_paused = has_track and mode == "paused"
                is_focused = bool(data.get("focused", False))
                if is_focused:
                    self.host_last_focused[ws_id] = now

                if is_playing:
                    self.host_last_playing[ws_id] = now
                    if (
                        self.active_host is not None
                        and self.active_host is not ws
                        and (now - self.host_last_playing.get(id(self.active_host), 0.0)) <= 0.45
                    ):
                        active_focused = (now - self.host_last_focused.get(id(self.active_host), 0.0)) <= 0.45
                        if is_focused and not active_focused:
                            self.active_host = ws
                        else:
                            return
                    else:
                        self.active_host = ws
                elif is_paused:
                    if self.active_host is None:
                        self.active_host = ws
                    elif self.active_host is not ws:
                        active_playing = (now - self.host_last_playing.get(id(self.active_host), 0.0)) <= 0.45
                        if active_playing:
                            return
                        active_focused = (now - self.host_last_focused.get(id(self.active_host), 0.0)) <= 0.45
                        seen_age = now - self.host_last_seen.get(id(self.active_host), 0.0)
                        if is_focused and not active_focused:
                            self.active_host = ws
                        elif seen_age <= 2.0:
                            return
                        else:
                            self.active_host = ws
                else:
                    if self.active_host is ws:
                        self.active_host = None
                        self.host_last_playing.pop(ws_id, None)
                    elif self.active_host is not None:
                        active_playing = (now - self.host_last_playing.get(id(self.active_host), 0.0)) <= 0.45
                        seen_age = now - self.host_last_seen.get(id(self.active_host), 0.0)
                        if active_playing or (seen_age <= 2.0 and not is_focused):
                            return
                        self.active_host = None

            self.last_telemetry = data
            data_str = json.dumps(data)

            # 1. Broadcast to all active satellite devices AND clustered follower nodes
            recipients = set(self.satellites)
            if self.cluster_enabled:
                for meta in self.clients.values():
                    cws = meta.get("ws")
                    if cws is not None and cws is not ws and meta.get("in_cluster") and meta.get("cluster_role") == "node":
                        recipients.add(cws)

            dead_sats = set()
            for target_ws in list(recipients):
                try:
                    await target_ws.send_text(data_str)
                except Exception:
                    if target_ws in self.satellites:
                        dead_sats.add(target_ws)
            if dead_sats:
                self.satellites.difference_update(dead_sats)
                self.audio_satellites.difference_update(dead_sats)
                await self.broadcast_status()

            # 2. Trigger smart physical lighting update if registered
            if self.smart_lights_callback:
                try:
                    self.smart_lights_callback(data)
                except Exception as e:
                    logger.debug("Smart light callback error: %s", e)
        elif msg_type == "audio_chunk":
            if self.active_host is not None and ws is not None and ws is not self.active_host:
                return
            if not self.audio_satellites:
                return
            chunk_str = json.dumps(data)
            dead_sats = set()
            for sat in list(self.audio_satellites):
                try:
                    await sat.send_text(chunk_str)
                except Exception:
                    dead_sats.add(sat)
            if dead_sats:
                self.satellites.difference_update(dead_sats)
                self.audio_satellites.difference_update(dead_sats)
                await self.broadcast_status()
        elif msg_type == "satellite_audio_control":
            enabled = bool(data.get("enabled", False))
            if enabled:
                self.audio_satellites = set(self.satellites)
            else:
                self.audio_satellites.clear()
            if data.get("host_align_ms") is not None:
                self.host_align_ms = max(0, min(250, int(data["host_align_ms"])))
            ctrl_str = json.dumps({
                "type": "satellite_audio_control",
                "enabled": enabled,
                "volume": data.get("volume"),
                "latency_ms": data.get("latency_ms"),
                "host_align_ms": self.host_align_ms,
            })
            dead_sats = set()
            for sat in list(self.satellites):
                try:
                    await sat.send_text(ctrl_str)
                except Exception:
                    dead_sats.add(sat)
            if dead_sats:
                self.satellites.difference_update(dead_sats)
                self.audio_satellites.difference_update(dead_sats)
            await self.broadcast_status()

    async def handle_host_audio(self, audio_bytes: bytes, ws: WebSocket | None = None) -> None:
        """Broadcast binary PCM audio frames from Host/Master to subscribed satellites AND cluster follower nodes."""
        if not audio_bytes:
            return

        cluster_followers: Set[WebSocket] = set()
        if self.cluster_enabled:
            for meta in self.clients.values():
                cws = meta.get("ws")
                if cws is not None and cws is not ws and meta.get("in_cluster") and meta.get("cluster_role") == "node":
                    cluster_followers.add(cws)

        recipients = set(self.audio_satellites) | cluster_followers
        if ws is not None:
            recipients.discard(ws)
        if not recipients:
            return

        if ws is not None:
            now = time.monotonic()
            ws_id = id(ws)
            self.host_last_seen[ws_id] = now
            self.host_last_playing[ws_id] = now
            if (
                self.cluster_enabled
                and self.cluster_master_ws is not None
                and self.cluster_master_ws in self.hosts
                and ws is not self.cluster_master_ws
            ):
                return
            if (
                self.active_host is None
                or self.active_host not in self.hosts
                or (
                    self.active_host is not ws
                    and (now - self.host_last_playing.get(id(self.active_host), 0.0)) > 0.8
                )
            ):
                self.active_host = ws
            elif self.active_host is not ws:
                return

        dead_sats = set()
        for target_ws in list(recipients):
            try:
                await target_ws.send_bytes(audio_bytes)
            except Exception:
                if target_ws in self.satellites:
                    dead_sats.add(target_ws)
        if dead_sats:
            self.satellites.difference_update(dead_sats)
            self.audio_satellites.difference_update(dead_sats)
            await self.broadcast_status()

    async def handle_satellite_message(self, data: Dict[str, Any], ws: WebSocket | None = None) -> None:
        if await self._handle_common_control_message(data, ws, role="satellite"):
            return

        msg_type = data.get("type")
        if msg_type == "audio_subscribe" and ws is not None:
            enabled = bool(data.get("enabled", False))
            if enabled:
                self.audio_satellites.add(ws)
            else:
                self.audio_satellites.discard(ws)
            await self.broadcast_status()
            await self.broadcast_cluster_state()
            return
        if msg_type == "command":
            cmd_str = json.dumps(data)
            target_master = (
                self.cluster_master_ws
                if (self.cluster_enabled and self.cluster_master_ws in self.hosts)
                else self.active_host
            )
            target_hosts = (
                [target_master]
                if target_master is not None and target_master in self.hosts
                else ([max(self.hosts, key=lambda h: self.host_last_seen.get(id(h), 0.0))] if self.hosts else [])
            )
            dead_hosts = set()
            for host in target_hosts:
                try:
                    await host.send_text(cmd_str)
                except Exception:
                    dead_hosts.add(host)
            if dead_hosts:
                for dh in dead_hosts:
                    self.hosts.discard(dh)
                    self.clients.pop(id(dh), None)
                    self.host_last_playing.pop(id(dh), None)
                    self.host_last_seen.pop(id(dh), None)
                    if self.active_host is dh:
                        self.active_host = None
                    if self.cluster_master_ws is dh:
                        self.cluster_master_ws = None


sync_hub = StageSyncHub()
stage_sync_hub = sync_hub
