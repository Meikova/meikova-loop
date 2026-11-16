/**
 * Meikova Continuum Stage, Light & Cluster Speaker Sync Client (v174).
 *
 * Handles:
 * 1. Host / Cluster Master Mode: Broadcasts real-time telemetry & timestamped PCM v2 audio to satellites & cluster nodes.
 * 2. Cluster Link (PartyBoost / Stereo Pair): Unifies multiple MashLoop instances (same IP or multi-server LAN) into one speaker system.
 * 3. Zero-Echo Acoustic Sync: NTP clock offset estimation + Host Speaker Delay alignment + L/R/Stereo channel routing matrix.
 * 4. Satellite Mode & Cluster Stage Mirror: Renders 1:1 synchronized dual-ring visualizer & ambient light.
 */
import * as theme from "./theme.js?v=176";
import { Track } from "./graph.js?v=176";
import { api } from "./api.js?v=176";
import { splitTitle } from "./viz.js?v=176";

const escHtml = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

function detectDefaultDeviceInfo() {
  if (typeof navigator === "undefined") {
    return { name: "Trạm phát MashLoop", type: "desktop" };
  }
  const ua = navigator.userAgent || "";
  let type = "desktop";
  let base = "Máy tính";
  if (/iPad|Tablet/i.test(ua)) {
    type = "tablet";
    base = "iPad / Tablet";
  } else if (/iPhone/i.test(ua)) {
    type = "mobile";
    base = "iPhone";
  } else if (/Android/i.test(ua)) {
    type = /Mobile/i.test(ua) ? "mobile" : "tablet";
    base = "Android";
  } else if (/Macintosh|Mac OS X/i.test(ua)) {
    base = "MacBook / Mac";
  } else if (/Windows/i.test(ua)) {
    base = "Windows PC";
  } else if (/Linux/i.test(ua)) {
    base = "Linux PC";
  }
  let suffix = "";
  try {
    let cid = sessionStorage.getItem("ml_cluster_client_id");
    if (!cid) {
      cid = `node-${Math.random().toString(36).slice(2, 6)}`;
      sessionStorage.setItem("ml_cluster_client_id", cid);
    }
    suffix = cid.slice(-3).toUpperCase();
  } catch (_) {
    suffix = String(Math.floor(100 + Math.random() * 900));
  }
  return { name: `${base} · ${suffix}`, type };
}

class StageSyncClient {
  constructor() {
    const isBrowser = typeof window !== "undefined";
    const params = isBrowser ? new URLSearchParams(window.location.search) : new URLSearchParams();
    this.isSatellite = params.get("mode") === "satellite";
    this.role = this.isSatellite ? "satellite" : "host";
    this.ws = null;
    this.connected = false;
    this.reconnectTimer = null;
    this.lastBroadcast = 0;
    this.minInterval = 33; // ~30 FPS throttle
    this.satellitesCount = 0;
    this.audioSatellitesCount = 0;
    this.hasHost = false;

    // Client Identity & Remote Bridge state
    const defInfo = detectDefaultDeviceInfo();
    this.clientId = "";
    this.deviceName = defInfo.name;
    this.deviceType = defInfo.type;
    if (isBrowser) {
      try {
        this.clientId = sessionStorage.getItem("ml_cluster_client_id") || `node-${Math.random().toString(36).slice(2, 8)}`;
        sessionStorage.setItem("ml_cluster_client_id", this.clientId);
        const savedName = localStorage.getItem("ml_cluster_device_name");
        if (savedName && savedName.trim()) {
          this.deviceName = savedName.trim();
        }
      } catch (_) {
        this.clientId = `node-${Math.random().toString(36).slice(2, 8)}`;
      }
    }
    this.remoteServerWsUrl = null;
    this.remoteServerHttpUrl = null;
    this._wantAutoJoinCluster = false;

    // NTP Clock Synchronization state
    this.ntpOffsetMs = 0;
    this.ntpRttMs = 0;
    this.ntpSynced = false;
    this._ntpSamples = [];
    this._ntpSeq = 0;
    this._ntpTimer = null;

    // Meikova Cluster Link (PartyBoost / Stereo Pair) state
    this.clusterEnabled = false;
    this.clusterId = "";
    this.clusterMode = "party"; // "party" | "stereo_pair"
    this.inCluster = false;
    this.clusterRole = "standalone"; // "master" | "node" | "standalone"
    this.clusterMasterId = "";
    this.clusterMasterName = "";
    this.clusterMasterVolume = 1.0;
    this.clusterNodesCount = 0;
    this.clusterNodes = [];
    this.isClusterMirror = false;
    this.myChannelMode = "stereo"; // "stereo" | "left" | "right"
    this.myVolumeTrim = 1.0;
    this.myLatencyOffsetMs = 0; // Fine phase offset (-50ms .. +50ms)
    this.hostAlignMs = 60; // Acoustic alignment horizon in ms

    // Live Multi-room & Cluster Audio Resonance state
    this.hostAudioStreamEnabled = false;
    this.satAudioEnabled = false;
    this.satAudioMuted = false;
    this._filteredDriftSec = 0;
    this.satAudioVol = 1.0;
    this.satLatencyMs = 60;
    this.satAudioCtx = null;
    this.satGainNode = null;
    this.satChannelSplitter = null;
    this.satChannelMerger = null;
    this.satHighPass = null;
    this.satLimiter = null;
    this.satNextPlayTime = 0;
    this._hostAudioTap = null;
    this._satPlayerNode = null;
    this._satPlayerWorkletReady = false;
    this._satPlayerWorkletFailed = false;
    this._satPlayerLoading = false;
    this._satWorkletQueue = [];
    this._localFollowerStates = new Map();
    this.engine = null;
    this.player = null;

    // Same-machine detection & local tab bus
    this.isSameMachine = false;
    this.isLocalHost = false;
    this._localTabBus = null;
    if (isBrowser) {
      const h = window.location.hostname;
      this.isLocalHost = h === "localhost" || h === "127.0.0.1" || h === "::1";
      this.isSameMachine = this.isLocalHost;
      this._initLocalTabBus();
    }

    // Callbacks
    this.onCommand = null;
    this.onStatusChange = null;
    this.onClusterChange = null;

    // Satellite renderer & track sync state
    this.telemetry = null;
    this.wakeLock = null;
    this.trackCache = new Map();
    this.currentTrack = null;
    this.primaryTrack = null;
    this.secondTrack = null;
    this.currentTrackId = null;
    this.loadingTracks = new Set();
    this.viz = null;
    this.enabledIds = [];
    this._idleConfirmTimer = null;
    this._pendingIdleData = null;

    if (isBrowser) {
      this.init();
    }
  }

  get isClusterFollower() {
    return !this.isSatellite && this.clusterEnabled && this.inCluster && this.clusterRole === "node";
  }

  get isClusterMaster() {
    return !this.isSatellite && this.clusterEnabled && this.inCluster && this.clusterRole === "master";
  }

  get isStageMirrorActive() {
    return this.isSatellite || (this.isClusterFollower && this.isClusterMirror);
  }

  get isReceivingStreamAudio() {
    return (this.isSatellite && this.satAudioEnabled) || this.isClusterFollower;
  }

  async ensureTrack(info) {
    if (!info || !info.id) return null;
    const tid = info.id;
    if (this.trackCache.has(tid)) {
      const existing = this.trackCache.get(tid);
      if (existing && existing.analysis) {
        if (info.title && existing.meta) existing.meta.title = info.title;
        if (info.artist && existing.meta) existing.meta.artist = info.artist;
        if (info.bpm && existing.meta) existing.meta.bpm = info.bpm;
        if (info.camelot && existing.meta) existing.meta.camelot = info.camelot;
        return existing;
      }
    }
    if (this.loadingTracks.has(tid)) return null;
    this.loadingTracks.add(tid);
    try {
      const [a, trans] = await Promise.all([
        api.analysis(tid).catch(() => null),
        api.transitions(tid).catch(() => null),
      ]);
      if (a) {
        if (a.mood) theme.registerMood(tid, a.mood);
        const meta = {
          id: tid,
          title: info.title || a.title || tid,
          artist: info.artist || a.artist || "",
          bpm: info.bpm || a.bpm || 120,
          camelot: info.camelot || a.camelot || "",
          duration: a.duration || 0,
          mood: a.mood || null,
          status: "ready",
        };
        const tr = new Track(meta, a, null);
        const transItems = Array.isArray(trans) ? trans : (trans?.items || a.transitions || []);
        tr.transitions = transItems;
        this.trackCache.set(tid, tr);
        if (this.telemetry?.track_id === tid || this.currentTrackId === tid) {
          this.primaryTrack = tr;
          this.currentTrack = tr;
          this._prefetchCandidateTransitions(tr);
          if (this.telemetry && this.isStageMirrorActive) this._syncCenterCaption(this.telemetry, tid);
          if (this.viz) this.viz.invalidate();
        }
        if (this.telemetry?.second?.id === tid || this.secondTrackId === tid) {
          this.secondTrack = tr;
          if (this.viz) this.viz.invalidate();
        }
        return tr;
      }
    } catch (e) {
      console.debug("[StageSync] Error loading track analysis:", e);
    } finally {
      this.loadingTracks.delete(tid);
    }
    return null;
  }

  _prefetchCandidateTransitions(tr) {
    if (!tr || !Array.isArray(tr.transitions) || !tr.transitions.length) return;
    const seen = new Set();
    const sorted = [...tr.transitions].sort((a, b) => (b.q || 0) - (a.q || 0));
    for (const item of sorted) {
      const toId = item?.to;
      if (!toId || toId === tr.id || seen.has(toId)) continue;
      seen.add(toId);
      if (!this.trackCache.has(toId) && !this.loadingTracks.has(toId)) {
        this.ensureTrack({ id: toId });
      }
      if (seen.size >= 4) break;
    }
  }

  _syncCenterCaption(data, primId = null) {
    if (!data || !this.isStageMirrorActive) return;
    const rcTitle = document.getElementById("rc-title");
    const rcKicker = document.getElementById("rc-kicker");
    const rcMeta = document.getElementById("rc-meta");
    const rcCta = document.getElementById("rc-cta");
    if (rcCta && !rcCta.hidden) rcCta.hidden = true;

    const isHtmlIdle = Boolean(
      data.rc_title_html && (
        data.rc_title_html.includes("Chọn một bài") ||
        data.rc_title_html.includes("Thêm một bài") ||
        data.rc_title_html.includes("chưa phát")
      )
    );
    const hasActiveTrackId = Boolean(
      (primId || data.primary?.id || data.track_id) &&
      (data.mode === "ring" || data.mode === "paused" || data.mode === "playing")
    );
    if ((data.rc_title_html && !isHtmlIdle) || (!hasActiveTrackId && (data.rc_kicker_html || data.rc_title_html || data.rc_meta_html))) {
      if (rcKicker && data.rc_kicker_html !== undefined && rcKicker.innerHTML !== data.rc_kicker_html) {
        rcKicker.innerHTML = data.rc_kicker_html;
      }
      if (rcTitle && data.rc_title_html !== undefined && rcTitle.innerHTML !== data.rc_title_html) {
        rcTitle.innerHTML = data.rc_title_html;
      }
      if (rcMeta && data.rc_meta_html !== undefined && rcMeta.innerHTML !== data.rc_meta_html) {
        rcMeta.innerHTML = data.rc_meta_html;
      }
      return;
    }

    const primInfo =
      data.primary ||
      (data.track_id
        ? {
            id: data.track_id,
            title: data.title,
            artist: data.artist,
            bpm: data.bpm,
            camelot: data.camelot,
            key: data.key,
          }
        : null);
    const id = primId || primInfo?.id || null;
    const rawT =
      primInfo?.title ||
      data.title ||
      this.primaryTrack?.meta?.title ||
      this.metas?.find((m) => m.id === id)?.title ||
      id ||
      "";
    const rawA =
      primInfo?.artist ||
      data.artist ||
      this.primaryTrack?.meta?.artist ||
      this.metas?.find((m) => m.id === id)?.artist ||
      "";
    const s = rawT ? splitTitle(rawT, rawA) : { title: "", artist: "" };
    const cleanTitle = s.title || rawT;
    const cleanArtist = s.artist || rawA;
    const isPlayingOrPaused = Boolean(id && (data.mode === "ring" || data.mode === "paused" || data.mode === "playing"));

    if (isPlayingOrPaused && cleanTitle) {
      const bpmStr = Math.round(primInfo?.bpm || data.bpm || this.primaryTrack?.analysis?.bpm || 120);
      const camStr = primInfo?.camelot || data.camelot || this.primaryTrack?.analysis?.camelot || "";
      const keyStr = primInfo?.key || data.key || this.primaryTrack?.analysis?.key || "";
      const newKicker = data.is_transitioning
        ? "ĐANG BLEND"
        : data.locked
          ? "ĐANG PHÁT · LẶP MÃI"
          : "ĐANG PHÁT · CHUỖI";
      const newTitle = cleanTitle;
      const artistSpan = cleanArtist ? `<span class="rc-artist">${escHtml(cleanArtist)}</span>` : "";
      const monoText = [`${bpmStr} BPM`, camStr, keyStr].filter(Boolean).join(" · ");
      const newMetaHtml = `${artistSpan}<span class="mono">${escHtml(monoText)}</span>`;
      if (rcTitle && rcTitle.textContent !== newTitle) rcTitle.textContent = newTitle;
      if (rcKicker && rcKicker.textContent !== newKicker) rcKicker.textContent = newKicker;
      if (rcMeta && rcMeta.innerHTML !== newMetaHtml) rcMeta.innerHTML = newMetaHtml;
    } else if (data.mode === "idle" || !cleanTitle) {
      const newTitle = "Chọn một bài để bắt đầu vòng lặp";
      const newKicker = "HAI VÒNG ĐANG CHỜ";
      const newMeta = "Bấm phát, hoặc nút phát ở một bài trong thư viện";
      if (rcTitle && rcTitle.textContent !== newTitle) rcTitle.textContent = newTitle;
      if (rcKicker && rcKicker.textContent !== newKicker) rcKicker.textContent = newKicker;
      if (rcMeta && rcMeta.textContent !== newMeta) rcMeta.textContent = newMeta;
    }
  }

  async loadTrack(trackId, title, artist, bpm, camelot) {
    if (!trackId) return;
    const tr = await this.ensureTrack({ id: trackId, title, artist, bpm, camelot });
    if (tr) {
      this.currentTrack = tr;
      this.primaryTrack = tr;
      this.currentTrackId = trackId;
      if (this.viz) this.viz.invalidate();
    }
  }

  init() {
    this.connect();
    if (this.isSatellite) {
      document.body.classList.add("is-satellite-mode");
      document.documentElement.classList.add("is-satellite-mode");
      document.body.classList.remove("is-zen");
      this.initSatelliteUI();
      this.requestWakeLock();
      api
        .tracks()
        .then((res) => {
          if (res && res.tracks) {
            theme.setMoods(res.tracks.filter((m) => m.status === "ready"));
            this.enabledIds = res.tracks.filter((m) => m.enabled !== false).map((m) => m.id);
            this.metas = res.tracks;
            if (this.telemetry?.track_id) {
              this.ensureTrack({ id: this.telemetry.track_id }).then((tr) => {
                if (tr) {
                  this.primaryTrack = tr;
                  this.currentTrack = tr;
                  this.currentTrackId = tr.id;
                  if (this.viz) this.viz.invalidate();
                }
              });
            }
            if (this.viz) {
              this.viz.invalidate();
            }
          }
        })
        .catch(() => {});
      requestAnimationFrame(() => {
        window.dispatchEvent(new Event("resize"));
      });
      setTimeout(() => {
        window.dispatchEvent(new Event("resize"));
      }, 120);
    }
  }

  getWsUrl() {
    if (this.remoteServerWsUrl) {
      const sep = this.remoteServerWsUrl.includes("?") ? "&" : "?";
      return `${this.remoteServerWsUrl}${sep}role=${this.role}`;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/api/ws/stage-sync?role=${this.role}`;
  }

  connectToRemoteClusterHost(serverUrl) {
    const raw = String(serverUrl || "").trim();
    if (!raw) return;
    let httpOrigin = raw;
    if (!/^https?:\/\//i.test(httpOrigin) && !/^wss?:\/\//i.test(httpOrigin)) {
      httpOrigin = `http://${httpOrigin}`;
    }
    try {
      const u = new URL(httpOrigin);
      const wsProto = u.protocol === "https:" || u.protocol === "wss:" ? "wss:" : "ws:";
      const httpProto = wsProto === "wss:" ? "https:" : "http:";
      this.remoteServerHttpUrl = `${httpProto}//${u.host}`;
      this.remoteServerWsUrl = `${wsProto}//${u.host}/api/ws/stage-sync`;
      this._wantAutoJoinCluster = true;
      if (this.ws) {
        try {
          this.ws.close();
        } catch (_) {}
        this.ws = null;
      }
      this.connect();
    } catch (e) {
      console.warn("[StageSync] Invalid remote server URL:", raw, e);
    }
  }

  disconnectRemoteClusterHost() {
    this.remoteServerWsUrl = null;
    this.remoteServerHttpUrl = null;
    this._wantAutoJoinCluster = false;
    if (this.ws) {
      try {
        this.ws.close();
      } catch (_) {}
      this.ws = null;
    }
    this.connect();
  }

  connect() {
    if (typeof WebSocket === "undefined") return;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      this.ws = new WebSocket(this.getWsUrl());
      this.ws.binaryType = "arraybuffer";
      this.ws.onopen = () => {
        this.connected = true;
        this._sendHello();
        this._startNtpSyncLoop();
        if (this.isSatellite && this.satAudioEnabled) {
          this._sendAudioSubscribe(true);
        }
        if (this._wantAutoJoinCluster) {
          this._wantAutoJoinCluster = false;
          this.joinCluster();
        }
        this.updateBadge();
      };

      this.ws.onmessage = (e) => {
        if (e.data instanceof ArrayBuffer) {
          if (this.isReceivingStreamAudio) this.handleAudioPacket(e.data);
          return;
        }
        if (typeof Blob !== "undefined" && e.data instanceof Blob) {
          if (this.isReceivingStreamAudio) {
            e.data.arrayBuffer().then((ab) => this.handleAudioPacket(ab)).catch(() => {});
          }
          return;
        }
        try {
          const data = JSON.parse(e.data);
          this.handleMessage(data);
        } catch (err) {
          console.debug("[StageSync] Parse error:", err);
        }
      };

      this.ws.onclose = () => {
        this.connected = false;
        this._stopNtpSyncLoop();
        this.updateBadge();
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.connected = false;
        this.ws?.close();
      };
    } catch (err) {
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 2000);
  }

  _sendHello() {
    if (!this.connected || this.ws?.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(
        JSON.stringify({
          type: "hello",
          client_id: this.clientId,
          device_name: this.deviceName,
          device_type: this.deviceType,
          origin_url: typeof window !== "undefined" ? window.location.origin : "",
          channel_mode: this.myChannelMode,
          volume_trim: this.myVolumeTrim,
          latency_offset_ms: this.myLatencyOffsetMs,
          join_cluster: Boolean(this._wantAutoJoinCluster),
        })
      );
    } catch (_) {}
  }

  // --- NTP Clock Synchronization (Zero-Echo Acoustic Phase Lock) ---
  _sendNtpPing() {
    if (!this.connected || this.ws?.readyState !== WebSocket.OPEN) return;
    const t0 = typeof performance !== "undefined" ? performance.now() : Date.now();
    this._ntpSeq += 1;
    try {
      this.ws.send(
        JSON.stringify({
          type: "ping_sync",
          seq: this._ntpSeq,
          t0,
          rtt_ms: this.ntpRttMs || 0,
        })
      );
    } catch (_) {}
  }

  _startNtpSyncLoop() {
    this._stopNtpSyncLoop();
    this._ntpSamples = [];
    // Rapid 4-sample burst on connect to lock clock offset within <500ms
    this._sendNtpPing();
    setTimeout(() => this._sendNtpPing(), 120);
    setTimeout(() => this._sendNtpPing(), 260);
    setTimeout(() => this._sendNtpPing(), 450);
    this._ntpTimer = setInterval(() => {
      this._sendNtpPing();
    }, 6000);
  }

  _stopNtpSyncLoop() {
    if (this._ntpTimer) {
      clearInterval(this._ntpTimer);
      this._ntpTimer = null;
    }
  }

  _handlePongSync(data) {
    const t3 = typeof performance !== "undefined" ? performance.now() : Date.now();
    const t0 = Number(data.t0) || 0;
    const t1 = Number(data.t1) || 0;
    const t2 = Number(data.t2) || t1;
    if (!t0 || !t1) return;

    const rtt = Math.max(0.2, (t3 - t0) - Math.max(0, t2 - t1));
    const offset = ((t1 - t0) + (t2 - t3)) * 0.5;
    this._ntpSamples.push({ rtt, offset });
    if (this._ntpSamples.length > 7) {
      this._ntpSamples.shift();
    }
    // Pick the lowest-RTT sample for minimum queueing noise
    const sortedByRtt = [...this._ntpSamples].sort((a, b) => a.rtt - b.rtt);
    const best = sortedByRtt[0];
    this.ntpOffsetMs = best.offset;
    this.ntpRttMs = Math.round(best.rtt * 10) / 10;
    this.ntpSynced = true;

    if (typeof data.host_align_ms === "number") {
      this.hostAlignMs = Math.max(0, Math.min(250, data.host_align_ms));
      this._syncHostSpeakerDelay();
    }

    const rttBadge = document.getElementById("sat-ntp-rtt-badge");
    if (rttBadge) {
      rttBadge.textContent = `Ping ${Math.max(1, Math.round(this.ntpRttMs))}ms`;
    }
  }

  handleMessage(data) {
    if (!data || typeof data !== "object") return;

    if (data.type === "memory_pressure") {
      const state = String(data.state || "normal").toLowerCase();
      if (typeof this.onMemoryPressure === "function") {
        try { this.onMemoryPressure(state, data); } catch (_) {}
      }
      if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
        try {
          window.dispatchEvent(new CustomEvent("memorypressure", {
            detail: { state, telemetry: data, source: "ws" }
          }));
        } catch (_) {}
      }
      return;
    }

    if (data.type === "pong_sync") {
      this._handlePongSync(data);
      return;
    }

    if (data.type === "same_machine_speaker_sync") {
      if (data.clientId !== this.clientId) {
        this.isSameMachine = true;
        this._localFollowerStates.set(data.clientId, {
          suppressMasterSpeaker: Boolean(data.suppressMasterSpeaker),
          isMutedLocal: Boolean(data.isMutedLocal),
          at: Date.now(),
        });
        if (this.isClusterMaster && this.engine) {
          let anySolo = false;
          for (const st of this._localFollowerStates.values()) {
            if (Date.now() - st.at < 15000 && st.suppressMasterSpeaker) {
              anySolo = true;
              break;
            }
          }
          this.engine.setLocalSpeakerMuted(anySolo);
          this._syncMasterEffectiveChannels();
        }
      }
      return;
    }

    if (data.type === "welcome_sync") {
      if (data.cluster) {
        this._applyClusterState(data.cluster);
      }
      return;
    }

    if (data.type === "cluster_state") {
      this._applyClusterState(data);
      return;
    }

    if (data.type === "sync_status") {
      this.satellitesCount = data.satellites_count ?? 0;
      this.audioSatellitesCount = data.audio_satellites_count ?? 0;
      this.clusterNodesCount = data.cluster_nodes_count ?? this.clusterNodesCount;
      this.hasHost = data.has_host ?? false;
      if (typeof data.host_align_ms === "number") {
        this.hostAlignMs = data.host_align_ms;
      }
      if (!this.isSatellite) {
        this.hostAudioStreamEnabled = this.audioSatellitesCount > 0 || (this.isClusterMaster && this.clusterNodesCount > 0);
        this._syncHostSpeakerDelay();
      } else {
        if (this.satAudioEnabled && this.audioSatellitesCount === 0) {
          this._sendAudioSubscribe(true);
        }
        if (!this.hasHost && this.telemetry && this.telemetry.mode !== "idle") {
          if (this._idleConfirmTimer) {
            clearTimeout(this._idleConfirmTimer);
            this._idleConfirmTimer = null;
          }
          this._pendingIdleData = null;
          this.telemetry = {
            type: "telemetry",
            mode: "idle",
            track_id: null,
            title: "",
            artist: "",
            primary: null,
            second: null,
            placeholder: null,
            next_html: "",
            ro_tl_html: "",
            ro_tr_html: "",
            lyric_prev: "",
            lyric_cur: "",
            lyric_next: "",
            _recvAt: typeof performance !== "undefined" ? performance.now() : Date.now(),
          };
          this.applySatelliteTelemetry(this.telemetry);
        }
      }
      this.updateBadge();
      if (this.onStatusChange) this.onStatusChange(data);
      return;
    }

    if (this.isSatellite && data.type === "satellite_audio_control") {
      if (typeof data.volume === "number") this.setSatelliteAudioVolume(data.volume);
      if (typeof data.latency_ms === "number") this.setSatelliteAudioLatency(data.latency_ms);
      if (typeof data.host_align_ms === "number") this.hostAlignMs = data.host_align_ms;
      if (data.enabled !== undefined) this.setSatelliteAudioEnabled(Boolean(data.enabled), false);
      return;
    }

    if ((this.isSatellite || this.isClusterFollower) && data.type === "telemetry") {
      const isIdle = !data.track_id || data.mode === "idle";
      if (!isIdle) {
        if (this._idleConfirmTimer) {
          clearTimeout(this._idleConfirmTimer);
          this._idleConfirmTimer = null;
        }
        this._pendingIdleData = null;
        data._recvAt = typeof performance !== "undefined" ? performance.now() : Date.now();
        this.telemetry = data;
        if (this.isStageMirrorActive) {
          this.applySatelliteTelemetry(data);
        } else {
          this._updateClusterMemberBanner();
        }
      } else if (!this.hasHost || !this.primaryTrack) {
        if (this._idleConfirmTimer) {
          clearTimeout(this._idleConfirmTimer);
          this._idleConfirmTimer = null;
        }
        this._pendingIdleData = null;
        data._recvAt = typeof performance !== "undefined" ? performance.now() : Date.now();
        this.telemetry = data;
        if (this.isStageMirrorActive) {
          this.applySatelliteTelemetry(data);
        } else {
          this._updateClusterMemberBanner();
        }
      } else {
        this._pendingIdleData = data;
        if (!this._idleConfirmTimer) {
          this._idleConfirmTimer = setTimeout(() => {
            this._idleConfirmTimer = null;
            const pending = this._pendingIdleData;
            this._pendingIdleData = null;
            if (pending && (this.isSatellite || this.isClusterFollower)) {
              pending._recvAt = typeof performance !== "undefined" ? performance.now() : Date.now();
              this.telemetry = pending;
              if (this.isStageMirrorActive) {
                this.applySatelliteTelemetry(pending);
              } else {
                this._updateClusterMemberBanner();
              }
            }
          }, 180);
        }
      }
    } else if (!this.isSatellite && data.type === "command") {
      if (this.onCommand) this.onCommand(data);
    }
  }

  _initLocalTabBus() {
    if (typeof BroadcastChannel === "undefined") return;
    try {
      this._localTabBus = new BroadcastChannel("ml_local_cluster_bus");
      this._localTabBus.onmessage = (ev) => {
        const msg = ev.data;
        if (!msg || typeof msg !== "object") return;
        if (msg.type === "master_announce" && msg.clientId !== this.clientId) {
          this.isSameMachine = true;
          if (this.isClusterFollower) {
            this._updateClusterMemberBanner();
          }
        } else if (msg.type === "follower_speaker_status" && msg.clientId !== this.clientId) {
          this.isSameMachine = true;
          this._localFollowerStates.set(msg.clientId, {
            suppressMasterSpeaker: Boolean(msg.suppressMasterSpeaker),
            isMutedLocal: Boolean(msg.isMutedLocal),
            at: Date.now(),
          });
          if (this.isClusterMaster && this.engine) {
            // Check if ANY same-machine follower wants solo speaker output
            let anySolo = false;
            for (const st of this._localFollowerStates.values()) {
              if (Date.now() - st.at < 15000 && st.suppressMasterSpeaker) {
                anySolo = true;
                break;
              }
            }
            this.engine.setLocalSpeakerMuted(anySolo);
            this._syncMasterEffectiveChannels();
          }
        }
      };

      // Periodically announce master / same-machine follower state across local tabs
      setInterval(() => {
        if (!this._localTabBus) return;
        if (this.isClusterMaster || (this.engine && this.player?.playing)) {
          this._localTabBus.postMessage({
            type: "master_announce",
            clientId: this.clientId,
            playing: Boolean(this.player?.playing),
          });
        }
        if (this.isClusterFollower && this.isSameMachine) {
          this._localTabBus.postMessage({
            type: "follower_speaker_status",
            clientId: this.clientId,
            suppressMasterSpeaker: !this.satAudioMuted,
            isMutedLocal: Boolean(this.satAudioMuted),
          });
        }
      }, 1000);

      if (typeof window !== "undefined") {
        window.addEventListener("beforeunload", () => {
          if (this._localTabBus && !this.satAudioMuted && this.isClusterFollower) {
            try {
              this._localTabBus.postMessage({
                type: "follower_speaker_status",
                clientId: this.clientId,
                suppressMasterSpeaker: false,
              });
            } catch (_) {}
          }
        });
      }
    } catch (_) {}
  }

  _syncMasterEffectiveChannels() {
    if (!this.engine) return;
    if (this.isClusterMaster) {
      // Determine if all followers in cluster are muted same-machine tabs
      const followers = this.clusterNodes.filter((n) => n.in_cluster && !n.is_master);
      const hasRemoteActiveFollower = followers.some((n) => {
        const localSt = this._localFollowerStates.get(n.client_id);
        return !(localSt && (Date.now() - localSt.at < 15000) && localSt.isMutedLocal);
      });
      // When all followers are local muted tabs on this same machine, play full stereo so user never loses L or R ear!
      const effMode = (this.isSameMachine && !hasRemoteActiveFollower) ? "stereo" : this.myChannelMode;
      const isDiscrete = this.isSameMachine || this.deviceType === "desktop";
      this.engine.setOutputChannelMode(effMode, isDiscrete);
      this.engine.setSpeakerTrim(this.myVolumeTrim * this.clusterMasterVolume);
    } else {
      this.engine.setOutputChannelMode("stereo", false);
      this.engine.setSpeakerTrim(1.0);
    }
  }

  setFollowerAudioMuted(muted = true) {
    this.satAudioMuted = Boolean(muted);
    if (!this.satAudioMuted) {
      this._unlockSatAudio(true);
    }
    this._syncSatEffectiveGain();
    if (this._satPlayerNode) {
      try {
        const effMode = (this.isSameMachine && !this.satAudioMuted) ? "stereo" : this.myChannelMode;
        this._satPlayerNode.port.postMessage({
          type: "config",
          muted: Boolean(this.satAudioMuted && this.isClusterFollower),
          channelMode: effMode,
          isDiscrete: this.isSameMachine || this.deviceType === "desktop",
        });
      } catch (_) {}
    }
    this._updateClusterMemberBanner();
    if (this._localTabBus && this.isSameMachine) {
      try {
        this._localTabBus.postMessage({
          type: "follower_speaker_status",
          clientId: this.clientId,
          suppressMasterSpeaker: !this.satAudioMuted,
          isMutedLocal: Boolean(this.satAudioMuted),
        });
      } catch (_) {}
    }
    if (this.ws?.readyState === WebSocket.OPEN && (this.isSameMachine || this.isLocalHost)) {
      try {
        this.ws.send(JSON.stringify({
          type: "same_machine_speaker_sync",
          clientId: this.clientId,
          suppressMasterSpeaker: !this.satAudioMuted,
          isMutedLocal: Boolean(this.satAudioMuted),
        }));
      } catch (_) {}
    }
  }

  // --- Cluster Link State & Role Transitions ---
  _applyClusterState(state) {
    if (!state) return;
    const wasFollower = this.isClusterFollower;

    this.clusterEnabled = Boolean(state.cluster_enabled);
    this.clusterId = state.cluster_id || "";
    this.clusterMode = state.cluster_mode || "party";
    this.clusterMasterId = state.master_client_id || "";
    this.clusterMasterName = state.master_name || "Chủ tọa";
    this.clusterMasterVolume = typeof state.master_volume === "number" ? state.master_volume : 1.0;
    if (typeof state.host_align_ms === "number") {
      this.hostAlignMs = state.host_align_ms;
    }
    this.clusterNodes = Array.isArray(state.nodes) ? state.nodes : [];
    this.clusterNodesCount = state.nodes_count ?? this.clusterNodes.filter((n) => n.in_cluster).length;

    const me = this.clusterNodes.find((n) => n.client_id === this.clientId);
    if (me) {
      this.inCluster = Boolean(me.in_cluster);
      this.clusterRole = me.cluster_role || (me.is_master ? "master" : me.in_cluster ? "node" : "standalone");
      this.myChannelMode = me.channel_mode || "stereo";
      this.myVolumeTrim = typeof me.volume_trim === "number" ? me.volume_trim : 1.0;
      this.myLatencyOffsetMs = typeof me.latency_offset_ms === "number" ? me.latency_offset_ms : 0;
    } else {
      this.inCluster = false;
      this.clusterRole = "standalone";
      this.myChannelMode = "stereo";
    }

    const nowFollower = this.isClusterFollower;

    // Apply channel routing & gain trim on local Engine (when Master/Standalone) or Satellite Audio Context (when Follower/Satellite)
    if (this.engine) {
      this._syncMasterEffectiveChannels();
      this._syncHostSpeakerDelay();
    }

    this._applySatChannelMatrix(this.myChannelMode);
    this._syncSatEffectiveGain();

    if (!wasFollower && nowFollower) {
      // Transitioned into Cluster Follower Node: pause any local standalone playback & activate cluster receiver
      if (this.player?.playing) {
        try {
          this.player.pause();
        } catch (_) {}
      }
      // On same machine, default satAudioMuted to true to prevent acoustic comb filtering / echo!
      if (this.isSameMachine || this.isLocalHost) {
        this.satAudioMuted = true;
        if (this._localTabBus) {
          try {
            this._localTabBus.postMessage({
              type: "follower_speaker_status",
              clientId: this.clientId,
              suppressMasterSpeaker: false,
              isMutedLocal: true,
            });
          } catch (_) {}
        }
      } else {
        this.satAudioMuted = false;
      }
      this._unlockSatAudio(false);
    } else if (wasFollower && !nowFollower) {
      // Left cluster or promoted to Master: exit stage mirror if active
      if (this.isClusterMirror) {
        this.setClusterMirrorMode(false);
      }
      this.satNextPlayTime = 0;
      if (this._localTabBus && this.isSameMachine) {
        try {
          this._localTabBus.postMessage({
            type: "follower_speaker_status",
            clientId: this.clientId,
            suppressMasterSpeaker: false,
          });
        } catch (_) {}
      }
    }

    this._updateClusterMemberBanner();
    this.updateBadge();
    if (this.onClusterChange) {
      this.onClusterChange(state);
    }
  }

  _syncHostSpeakerDelay() {
    if (!this.engine || typeof this.engine.setSpeakerSyncDelay !== "function") return;
    if (this.shouldStreamAudio()) {
      this.engine.setSpeakerSyncDelay(this.hostAlignMs);
    } else {
      this.engine.setSpeakerSyncDelay(0);
    }
  }

  setClusterMirrorMode(enabled) {
    this.isClusterMirror = Boolean(enabled);
    const active = this.isClusterMirror && this.isClusterFollower;
    document.body.classList.toggle("is-cluster-mirror", active);
    document.documentElement.classList.toggle("is-cluster-mirror", active);
    if (active && this.telemetry) {
      this.applySatelliteTelemetry(this.telemetry);
    } else if (!active && this.viz) {
      this.viz.invalidate();
    }
    this._updateClusterMemberBanner();
    window.dispatchEvent(new Event("resize"));
  }

  _channelLabelText(mode) {
    if (mode === "left") return "LOA TRÁI · L";
    if (mode === "right") return "LOA PHẢI · R";
    return "STEREO · L+R";
  }

  _updateClusterMemberBanner() {
    const banner = document.getElementById("cluster-member-banner");
    if (!banner) return;
    if (!this.isClusterFollower) {
      banner.hidden = true;
      document.body.classList.remove("has-cluster-banner");
      return;
    }
    banner.hidden = false;
    document.body.classList.add("has-cluster-banner");

    const titleEl = document.getElementById("cluster-banner-title");
    const subEl = document.getElementById("cluster-banner-sub");
    const chBadge = document.getElementById("cluster-banner-channel");
    const audioToggleBtn = document.getElementById("btn-cluster-audio-toggle");
    const audioToggleTxt = document.getElementById("cluster-audio-toggle-text");
    const mirrorBtn = document.getElementById("btn-cluster-stage-mirror");
    const mirrorBtnTxt = document.getElementById("cluster-stage-mirror-text");
    const unlockBtn = document.getElementById("btn-cluster-audio-unlock");

    const masterName = this.clusterMasterName || "Máy chính";
    const trackTitle = this.telemetry?.title || "Đang đồng bộ âm thanh thời gian thực";
    if (titleEl) {
      titleEl.textContent = `Đang trong Cụm Loa của ${masterName}`;
    }
    if (subEl) {
      subEl.textContent = trackTitle;
    }
    if (chBadge) {
      chBadge.textContent = this._channelLabelText(this.myChannelMode);
      chBadge.dataset.channel = this.myChannelMode;
    }
    if (audioToggleBtn && audioToggleTxt) {
      const isMuted = Boolean(this.satAudioMuted);
      audioToggleBtn.classList.toggle("is-muted", isMuted);
      audioToggleBtn.classList.toggle("is-active", !isMuted);
      audioToggleBtn.setAttribute("aria-pressed", String(!isMuted));
      if (isMuted) {
        audioToggleTxt.textContent = this.isSameMachine ? "Loa: Tắt (Cùng máy)" : "Loa: Tắt";
        audioToggleBtn.title = this.isSameMachine
          ? "Đang tắt tiếng để tránh trùng âm thanh trên cùng máy · Bấm để nghe thử riêng tab này"
          : "Bật tiếng loa cho thiết bị này";
      } else {
        audioToggleTxt.textContent = "Loa: Bật";
        audioToggleBtn.title = this.isSameMachine
          ? "Đang phát qua tab này (Máy chính tự tắt loa) · Bấm để tắt tiếng"
          : "Tắt tiếng loa thiết bị này";
      }
    }
    if (mirrorBtnTxt) {
      mirrorBtnTxt.textContent = this.isClusterMirror ? "Thu nhỏ" : "Toàn cảnh";
    }
    if (mirrorBtn) {
      mirrorBtn.classList.toggle("is-active", this.isClusterMirror);
      mirrorBtn.setAttribute("aria-pressed", String(this.isClusterMirror));
    }
    if (unlockBtn) {
      const needsUnlock = !this.satAudioMuted && (!this.satAudioCtx || this.satAudioCtx.state !== "running");
      unlockBtn.hidden = !needsUnlock;
    }
  }

  toggleCluster({ enabled, mode, host_align_ms, master_volume } = {}) {
    const nextEnabled = enabled !== undefined ? Boolean(enabled) : !this.clusterEnabled;
    const nextMode = mode || this.clusterMode || "party";
    if (this.connected && this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(
          JSON.stringify({
            type: "cluster_toggle",
            enabled: nextEnabled,
            mode: nextMode,
            client_id: this.clientId,
            host_align_ms: host_align_ms ?? this.hostAlignMs,
            master_volume: master_volume ?? this.clusterMasterVolume,
          })
        );
        return;
      } catch (_) {}
    }
    fetch("/api/cluster/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: nextEnabled,
        mode: nextMode,
        client_id: this.clientId,
        host_align_ms: host_align_ms ?? this.hostAlignMs,
        master_volume: master_volume ?? this.clusterMasterVolume,
      }),
    }).catch(() => {});
  }

  joinCluster(channelMode = null) {
    this._unlockSatAudio(true);
    if (this.connected && this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(
          JSON.stringify({
            type: "cluster_join",
            client_id: this.clientId,
            channel_mode: channelMode,
          })
        );
      } catch (_) {}
    }
  }

  leaveCluster(targetClientId = null) {
    const cid = targetClientId || this.clientId;
    if (cid === this.clientId && this.isClusterMirror) {
      this.setClusterMirrorMode(false);
    }
    if (this.connected && this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(
          JSON.stringify({
            type: "cluster_leave",
            client_id: cid,
          })
        );
      } catch (_) {}
    }
  }

  updateClusterNodeConfig(opts = {}) {
    if (opts.device_name && (!opts.target_client_id || opts.target_client_id === this.clientId)) {
      this.deviceName = String(opts.device_name).trim().slice(0, 48);
      try {
        localStorage.setItem("ml_cluster_device_name", this.deviceName);
      } catch (_) {}
    }
    if (this.connected && this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(
          JSON.stringify({
            type: "cluster_node_config",
            client_id: opts.target_client_id || opts.client_id || this.clientId,
            target_client_id: opts.target_client_id || opts.client_id || this.clientId,
            channel_mode: opts.channel_mode,
            volume_trim: opts.volume_trim,
            latency_offset_ms: opts.latency_offset_ms,
            in_cluster: opts.in_cluster,
            device_name: opts.device_name,
            claim_master: opts.claim_master,
            mode: opts.mode,
            host_align_ms: opts.host_align_ms,
            master_volume: opts.master_volume,
          })
        );
        return;
      } catch (_) {}
    }
    fetch("/api/cluster/node/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: opts.target_client_id || opts.client_id || this.clientId,
        channel_mode: opts.channel_mode,
        volume_trim: opts.volume_trim,
        latency_offset_ms: opts.latency_offset_ms,
        in_cluster: opts.in_cluster,
        device_name: opts.device_name,
        claim_master: Boolean(opts.claim_master),
        mode: opts.mode,
        host_align_ms: opts.host_align_ms,
        master_volume: opts.master_volume,
      }),
    }).catch(() => {});
  }

  claimClusterMaster() {
    this.updateClusterNodeConfig({
      target_client_id: this.clientId,
      claim_master: true,
    });
  }

  updateBadge() {
    const badge = document.getElementById("stage-sync-badge");
    const openBtn = document.getElementById("btn-stage-sync-modal");
    if (badge) {
      if (this.satellitesCount > 0) {
        badge.hidden = false;
        badge.textContent = String(this.satellitesCount);
        if (openBtn) {
          openBtn.classList.add("has-satellites");
          openBtn.setAttribute("title", `Đồng bộ Ánh sáng & Màn hình Vệ tinh (${this.satellitesCount} vệ tinh đang kết nối)`);
        }
      } else {
        badge.hidden = true;
        badge.textContent = "0";
        if (openBtn) {
          openBtn.classList.remove("has-satellites");
          openBtn.setAttribute("title", "Đồng bộ Ánh sáng & Màn hình Vệ tinh (S)");
        }
      }
    }

    // Update Topbar Cluster Link button & badge (#btn-nav-cluster, #cluster-count-badge)
    const clusterBtn = document.getElementById("btn-nav-cluster");
    const clusterBadge = document.getElementById("cluster-count-badge");
    const activeNodes = this.clusterNodes.filter((n) => n.in_cluster).length;
    if (clusterBtn) {
      clusterBtn.classList.toggle("is-active", this.clusterEnabled && this.inCluster);
      clusterBtn.setAttribute("aria-pressed", String(Boolean(this.clusterEnabled && this.inCluster)));
    }
    if (clusterBadge) {
      if (this.clusterEnabled && activeNodes > 0) {
        clusterBadge.hidden = false;
        clusterBadge.textContent = String(activeNodes);
      } else {
        clusterBadge.hidden = true;
        clusterBadge.textContent = "0";
      }
    }

    const statusEl = document.getElementById("sync-sat-connected-status");
    if (statusEl) {
      statusEl.textContent =
        this.satellitesCount > 0
          ? `Thiết bị vệ tinh kết nối: ${this.satellitesCount}${this.audioSatellitesCount > 0 ? ` (${this.audioSatellitesCount} bật loa)` : ""}`
          : "Chưa có thiết bị vệ tinh kết nối";
    }
    const hostAudioToggle = document.getElementById("btn-toggle-sat-audio");
    const hostAudioDesc = document.getElementById("sat-audio-status-desc");
    const audioActive = this.audioSatellitesCount > 0 || this.hostAudioStreamEnabled;
    if (hostAudioToggle) {
      hostAudioToggle.classList.toggle("is-active", audioActive);
      hostAudioToggle.setAttribute("aria-pressed", String(audioActive));
    }
    if (hostAudioDesc) {
      hostAudioDesc.textContent =
        this.audioSatellitesCount > 0
          ? `Đang phát trực tiếp Live Mix sang ${this.audioSatellitesCount} loa vệ tinh (Đồng bộ Zero-Echo NTP)`
          : "Truyền trực tiếp bản phối Live Mix (DJ Blend, EQ, Karaoke) sang loa thiết bị vệ tinh";
    }
    const satCountBadge = document.getElementById("satellite-count-badge");
    if (satCountBadge) {
      satCountBadge.textContent = this.satellitesCount > 0 ? String(this.satellitesCount) : "0";
    }
    const satStatusBadge = document.getElementById("sat-status-badge");
    if (satStatusBadge) {
      if (this.connected) {
        satStatusBadge.textContent = this.hasHost ? "Vệ tinh · Đang phát" : "Vệ tinh · Chờ Host";
        satStatusBadge.style.color = "var(--accent)";
      } else {
        satStatusBadge.textContent = "Mất kết nối...";
        satStatusBadge.style.color = "#f87171";
      }
    }
  }

  // --- Multi-room & Cluster Live Audio Resonance (Host Streamer & Satellite/Node Player) ---
  shouldStreamAudio() {
    const hasClusterListeners =
      this.isClusterMaster && this.clusterNodes.some((n) => n.in_cluster && !n.is_master);
    return (
      !this.isSatellite &&
      !this.isClusterFollower &&
      this.connected &&
      this.ws?.readyState === WebSocket.OPEN &&
      (this.audioSatellitesCount > 0 || this.hostAudioStreamEnabled || hasClusterListeners)
    );
  }

  _sendAudioSubscribe(enabled) {
    if (!this.isSatellite || !this.connected || this.ws?.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(JSON.stringify({ type: "audio_subscribe", enabled: Boolean(enabled) }));
      this._lastSubSentAt = Date.now();
    } catch (_) {}
  }

  attachHostEngine(engine, player) {
    this.engine = engine;
    this.player = player;
    if (this.isSatellite || !engine?.ctx || !engine?.analyser || this._hostAudioTap) return;
    try {
      const ctx = engine.ctx;
      const bufSize = 1024;
      const targetSr = Math.round(ctx.sampleRate || 44100);

      const sendPcmBlock = (inL, inR) => {
        const streaming = this.shouldStreamAudio() && Boolean(player?.playing);
        this._syncHostSpeakerDelay();
        if (!streaming) return;
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        if (this.ws.bufferedAmount > 49152) return; // Prevent backpressure queue buildup

        const nowPerf = typeof performance !== "undefined" ? performance.now() : Date.now();
        const serverCaptureMs = nowPerf + (this.ntpOffsetMs || 0);

        // 16-byte PCM v2 Header + 1024 frames stereo Int16 (4096 bytes) = 4112 bytes
        const packetBuf = new ArrayBuffer(16 + bufSize * 4);
        const headerView = new DataView(packetBuf, 0, 16);
        const pcmView = new Int16Array(packetBuf, 16, bufSize * 2);

        headerView.setUint8(0, 0x4d); // 'M'
        headerView.setUint8(1, 0x4c); // 'L'
        headerView.setUint8(2, 2);    // version 2 (with Float64 NTP timestamp)
        headerView.setUint8(3, 2);    // 2 channels
        headerView.setUint32(4, targetSr, true);
        headerView.setFloat64(8, serverCaptureMs, true);

        let outIdx = 0;
        for (let i = 0; i < bufSize; i++) {
          // Soft-knee tanh saturation prevents digital square-wave hard clipping
          const sL = Math.tanh(inL[i] || 0);
          const sR = Math.tanh(inR[i] || 0);
          pcmView[outIdx++] = sL < 0 ? Math.round(sL * 0x8000) : Math.round(sL * 0x7fff);
          pcmView[outIdx++] = sR < 0 ? Math.round(sR * 0x8000) : Math.round(sR * 0x7fff);
        }
        try {
          this.ws.send(packetBuf);
        } catch (_) {}
      };

      const setupScriptProcessorFallback = () => {
        if (this._hostAudioTap) return;
        try {
          const proc = ctx.createScriptProcessor(bufSize, 2, 2);
          const zeroGain = ctx.createGain();
          zeroGain.gain.setValueAtTime(0, ctx.currentTime);
          engine.analyser.connect(proc);
          proc.connect(zeroGain);
          zeroGain.connect(ctx.destination);
          proc.onaudioprocess = (ev) => {
            const inL = ev.inputBuffer.getChannelData(0);
            const inR = ev.inputBuffer.numberOfChannels > 1 ? ev.inputBuffer.getChannelData(1) : inL;
            sendPcmBlock(inL, inR);
          };
          this._hostAudioTap = { proc, zeroGain };
        } catch (err) {
          console.debug("[StageSync] ScriptProcessor error:", err);
        }
      };

      if (typeof AudioWorkletNode === "function" && ctx.audioWorklet) {
        const workletCode = `
          class MLStreamCaptureProcessor extends AudioWorkletProcessor {
            constructor() {
              super();
              this.bufSize = 1024;
              this.bufL = new Float32Array(this.bufSize);
              this.bufR = new Float32Array(this.bufSize);
              this.pos = 0;
            }
            process(inputs) {
              const input = inputs[0];
              if (!input || !input[0]) return true;
              const inL = input[0];
              const inR = input.length > 1 ? input[1] : inL;
              const len = inL.length;
              for (let i = 0; i < len; i++) {
                this.bufL[this.pos] = inL[i];
                this.bufR[this.pos] = inR[i];
                this.pos++;
                if (this.pos >= this.bufSize) {
                  const lCopy = this.bufL.slice(0);
                  const rCopy = this.bufR.slice(0);
                  this.port.postMessage({ l: lCopy, r: rCopy }, [lCopy.buffer, rCopy.buffer]);
                  this.pos = 0;
                }
              }
              return true;
            }
          }
          registerProcessor("ml-stream-capture", MLStreamCaptureProcessor);
        `;
        const blob = new Blob([workletCode], { type: "application/javascript" });
        const blobUrl = URL.createObjectURL(blob);
        ctx.audioWorklet.addModule(blobUrl).then(() => {
          URL.revokeObjectURL(blobUrl);
          const workletNode = new AudioWorkletNode(ctx, "ml-stream-capture", {
            numberOfInputs: 1,
            numberOfOutputs: 1,
            channelCount: 2,
            outputChannelCount: [2],
          });
          const silentTapGain = ctx.createGain();
          silentTapGain.gain.setValueAtTime(0, ctx.currentTime);
          engine.analyser.connect(workletNode);
          workletNode.connect(silentTapGain);
          silentTapGain.connect(ctx.destination);
          workletNode.port.onmessage = (ev) => {
            if (ev.data?.l && ev.data?.r) {
              sendPcmBlock(ev.data.l, ev.data.r);
            }
          };
          this._hostAudioTap = { workletNode };
        }).catch((err) => {
          console.debug("[StageSync] AudioWorklet fallback to ScriptProcessor:", err);
          setupScriptProcessorFallback();
        });
      } else {
        setupScriptProcessorFallback();
      }
    } catch (err) {
      console.debug("[StageSync] attachHostEngine error:", err);
    }
  }

  setHostAudioControl({ enabled, volume, latency_ms, host_align_ms } = {}) {
    if (this.isSatellite) return;
    if (enabled !== undefined) this.hostAudioStreamEnabled = Boolean(enabled);
    if (typeof host_align_ms === "number") {
      this.hostAlignMs = Math.max(0, Math.min(250, host_align_ms));
    } else if (typeof latency_ms === "number") {
      this.hostAlignMs = Math.max(0, Math.min(250, latency_ms));
    }
    this._syncHostSpeakerDelay();
    if (this.connected && this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(
          JSON.stringify({
            type: "satellite_audio_control",
            enabled: this.hostAudioStreamEnabled,
            volume,
            latency_ms,
            host_align_ms: this.hostAlignMs,
          })
        );
      } catch (_) {}
    }
    this.updateBadge();
  }

  _initSatSilenceAnchor() {
    if (this._satSilenceAudio || typeof document === "undefined") return this._satSilenceAudio;
    try {
      const a = document.createElement("audio");
      a.loop = true;
      a.playsInline = true;
      a.setAttribute("playsinline", "");
      a.setAttribute("webkit-playsinline", "");
      a.setAttribute("x-webkit-airplay", "allow");
      a.volume = 0.01;
      a.preload = "auto";
      a.src = "/audio/silence.mp3";
      a.style.position = "fixed";
      a.style.width = "1px";
      a.style.height = "1px";
      a.style.opacity = "0.01";
      a.style.pointerEvents = "none";
      a.style.zIndex = "-1";
      document.body.appendChild(a);
      this._satSilenceAudio = a;
    } catch (_) {}
    return this._satSilenceAudio;
  }

  _applySatChannelMatrix(mode = "stereo") {
    if (!this.satChannelSplitter || !this.satChannelMerger) return;
    try {
      this.satChannelSplitter.disconnect();
    } catch (_) {}
    const isDiscrete = this.isSameMachine || this.deviceType === "desktop";
    if (mode === "left") {
      if (isDiscrete) {
        this.satChannelSplitter.connect(this.satChannelMerger, 0, 0);
      } else {
        this.satChannelSplitter.connect(this.satChannelMerger, 0, 0);
        this.satChannelSplitter.connect(this.satChannelMerger, 0, 1);
      }
    } else if (mode === "right") {
      if (isDiscrete) {
        this.satChannelSplitter.connect(this.satChannelMerger, 1, 1);
      } else {
        this.satChannelSplitter.connect(this.satChannelMerger, 1, 0);
        this.satChannelSplitter.connect(this.satChannelMerger, 1, 1);
      }
    } else {
      this.satChannelSplitter.connect(this.satChannelMerger, 0, 0);
      this.satChannelSplitter.connect(this.satChannelMerger, 1, 1);
    }
  }

  _syncSatEffectiveGain() {
    if (!this.satGainNode || !this.satAudioCtx) return;
    if (this.satAudioMuted && this.isClusterFollower) {
      this.satGainNode.gain.cancelScheduledValues(this.satAudioCtx.currentTime);
      this.satGainNode.gain.setTargetAtTime(0, this.satAudioCtx.currentTime, 0.015);
      return;
    }
    const base = this.isClusterFollower ? 1.0 : this.satAudioVol;
    const clusterScale = this.inCluster ? (this.myVolumeTrim * this.clusterMasterVolume) : 1.0;
    const effective = Math.max(0, Math.min(2.0, base * clusterScale));
    this.satGainNode.gain.cancelScheduledValues(this.satAudioCtx.currentTime);
    this.satGainNode.gain.setTargetAtTime(effective, this.satAudioCtx.currentTime, 0.015);
  }

  _ensureSatAudioCtx() {
    if (!this.satAudioCtx && typeof window !== "undefined") {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        try {
          this.satAudioCtx = new AC({ sampleRate: 44100, latencyHint: "interactive" });
        } catch (_) {
          try {
            this.satAudioCtx = new AC({ latencyHint: "interactive" });
          } catch (_) {
            this.satAudioCtx = new AC();
          }
        }
        this.satChannelSplitter = this.satAudioCtx.createChannelSplitter(2);
        this.satChannelMerger = this.satAudioCtx.createChannelMerger(2);
        this.satGainNode = this.satAudioCtx.createGain();

        // Filter DC sub-rumble (< 20Hz)
        this.satHighPass = this.satAudioCtx.createBiquadFilter();
        this.satHighPass.type = "highpass";
        this.satHighPass.frequency.value = 20;
        this.satHighPass.Q.value = 0.707;

        // Output brickwall limiter prevents speaker distortion at high trim/volume
        this.satLimiter = this.satAudioCtx.createDynamicsCompressor();
        this.satLimiter.threshold.value = -0.8;
        this.satLimiter.knee.value = 3.0;
        this.satLimiter.ratio.value = 20.0;
        this.satLimiter.attack.value = 0.002;
        this.satLimiter.release.value = 0.08;

        this._applySatChannelMatrix(this.myChannelMode);
        this.satChannelMerger.connect(this.satHighPass);
        this.satHighPass.connect(this.satGainNode);
        this.satGainNode.connect(this.satLimiter);
        this.satLimiter.connect(this.satAudioCtx.destination);
        this._syncSatEffectiveGain();
        this.satAudioCtx.addEventListener?.("statechange", () => {
          this._updateSatelliteAudioUI();
          this._updateClusterMemberBanner();
        });
        this._initSatPlayerWorklet(this.satAudioCtx);
      }
    }
    if (this.satAudioCtx && this.satAudioCtx.state !== "running") {
      this.satAudioCtx.resume().catch(() => {});
    }
    return this.satAudioCtx;
  }

  _initSatPlayerWorklet(ctx) {
    if (!ctx || this._satPlayerLoading || this._satPlayerWorkletReady || this._satPlayerWorkletFailed) return;
    if (typeof AudioWorkletNode !== "function" || !ctx.audioWorklet) {
      this._satPlayerWorkletFailed = true;
      return;
    }
    this._satPlayerLoading = true;
    const playerWorkletCode = `
      class MLStreamPlayerProcessor extends AudioWorkletProcessor {
        constructor() {
          super();
          this.capacity = 32768;
          this.mask = this.capacity - 1;
          this.bufL = new Float32Array(this.capacity);
          this.bufR = new Float32Array(this.capacity);
          this.writeIdx = 0;
          this.readIdx = 0;
          this.readFrac = 0.0;
          this.available = 0;
          this.targetBuffered = 3840;
          this.srcSr = 44100;
          this.outSr = sampleRate || 44100;
          this.isMuted = false;
          this.channelMode = "stereo";
          this.isDiscrete = false;
          this.fadeSamples = 64;
          this.curFade = 0;
          this.wasStarved = true;

          this.port.onmessage = (ev) => {
            const msg = ev.data;
            if (!msg) return;
            if (msg.type === "push") {
              const pcm = msg.pcm;
              const chs = msg.channels || 2;
              const frames = msg.frames || Math.floor(pcm.length / chs);
              if (msg.srcSr) this.srcSr = msg.srcSr;
              const inv = 1 / 32768;
              let pIdx = 0;
              if (chs > 1) {
                for (let i = 0; i < frames; i++) {
                  this.bufL[this.writeIdx] = pcm[pIdx++] * inv;
                  this.bufR[this.writeIdx] = pcm[pIdx++] * inv;
                  this.writeIdx = (this.writeIdx + 1) & this.mask;
                }
              } else {
                for (let i = 0; i < frames; i++) {
                  const s = pcm[pIdx++] * inv;
                  this.bufL[this.writeIdx] = s;
                  this.bufR[this.writeIdx] = s;
                  this.writeIdx = (this.writeIdx + 1) & this.mask;
                }
              }
              this.available += frames;
              const maxAllowed = Math.min(this.capacity - 512, Math.max(8192, this.targetBuffered * 3));
              if (this.available > maxAllowed) {
                const trim = this.available - this.targetBuffered;
                this.readIdx = (this.readIdx + trim) & this.mask;
                this.available -= trim;
                this.curFade = 0;
              }
              if (this.wasStarved && this.available >= Math.min(this.targetBuffered, 768)) {
                this.wasStarved = false;
                this.curFade = 0;
              }
            } else if (msg.type === "config") {
              if (typeof msg.target === "number") this.targetBuffered = msg.target;
              if (msg.channelMode) this.channelMode = msg.channelMode;
              if (typeof msg.isDiscrete === "boolean") this.isDiscrete = msg.isDiscrete;
              if (typeof msg.muted === "boolean") this.isMuted = msg.muted;
            }
          };
        }

        process(inputs, outputs) {
          const output = outputs[0];
          if (!output || !output[0]) return true;
          const outL = output[0];
          const outR = output.length > 1 ? output[1] : outL;
          const len = outL.length;

          if (this.isMuted || this.wasStarved || this.available < 128) {
            outL.fill(0);
            if (outR !== outL) outR.fill(0);
            if (this.available < 128) this.wasStarved = true;
            return true;
          }

          const drift = this.available - this.targetBuffered;
          const rateNudge = Math.max(0.992, Math.min(1.008, 1.0 + (drift * 0.000008)));
          const step = (this.srcSr / this.outSr) * rateNudge;

          const mode = this.channelMode;
          const discrete = this.isDiscrete;
          const mask = this.mask;

          for (let i = 0; i < len; i++) {
            if (this.available <= 2) {
              const fadeOutLen = Math.min(32, len - i);
              const lastL = i > 0 ? outL[i - 1] : 0;
              const lastR = (i > 0 && outR !== outL) ? outR[i - 1] : lastL;
              for (let k = 0; k < fadeOutLen; k++) {
                const factor = 0.5 * (1 + Math.cos(Math.PI * (k / fadeOutLen)));
                outL[i + k] = lastL * factor;
                if (outR !== outL) outR[i + k] = lastR * factor;
              }
              for (let k = i + fadeOutLen; k < len; k++) {
                outL[k] = 0;
                if (outR !== outL) outR[k] = 0;
              }
              this.wasStarved = true;
              break;
            }

            const i0 = this.readIdx;
            const i1 = (i0 + 1) & mask;
            const frac = this.readFrac;

            let sL = this.bufL[i0] + frac * (this.bufL[i1] - this.bufL[i0]);
            let sR = this.bufR[i0] + frac * (this.bufR[i1] - this.bufR[i0]);

            if (this.curFade < this.fadeSamples) {
              const factor = 0.5 * (1 - Math.cos(Math.PI * (this.curFade / this.fadeSamples)));
              sL *= factor;
              sR *= factor;
              this.curFade++;
            }

            if (mode === "left") {
              outL[i] = sL;
              outR[i] = discrete ? 0 : sL;
            } else if (mode === "right") {
              outL[i] = discrete ? 0 : sR;
              outR[i] = sR;
            } else {
              outL[i] = sL;
              outR[i] = sR;
            }

            this.readFrac += step;
            const adv = Math.floor(this.readFrac);
            if (adv > 0) {
              this.readFrac -= adv;
              this.readIdx = (this.readIdx + adv) & mask;
              this.available -= adv;
            }
          }
          return true;
        }
      }
      registerProcessor("ml-stream-player", MLStreamPlayerProcessor);
    `;
    try {
      const pBlob = new Blob([playerWorkletCode], { type: "application/javascript" });
      const pUrl = URL.createObjectURL(pBlob);
      ctx.audioWorklet.addModule(pUrl).then(() => {
        URL.revokeObjectURL(pUrl);
        this._satPlayerNode = new AudioWorkletNode(ctx, "ml-stream-player", {
          numberOfInputs: 0,
          numberOfOutputs: 1,
          outputChannelCount: [2],
        });
        this._satPlayerNode.connect(this.satHighPass || this.satGainNode || ctx.destination);
        this._satPlayerWorkletReady = true;
        this._satPlayerLoading = false;
        if (this._satWorkletQueue?.length) {
          const queued = this._satWorkletQueue.splice(0);
          for (const pkt of queued) {
            this._pushToSatWorklet(pkt.channels, pkt.sampleRate, pkt.pcm, pkt.frames);
          }
        }
      }).catch((err) => {
        console.debug("[StageSync] AudioWorklet player fallback:", err);
        this._satPlayerWorkletFailed = true;
        this._satPlayerLoading = false;
      });
    } catch (e) {
      this._satPlayerWorkletFailed = true;
      this._satPlayerLoading = false;
    }
  }

  _pushToSatWorklet(channels, sampleRate, pcm, frames) {
    if (!this._satPlayerNode) return;
    const targetBuffered = Math.max(
      1024,
      Math.min(16384, Math.round((((this.hostAlignMs || 60) + (this.myLatencyOffsetMs || 0)) / 1000) * sampleRate))
    );
    const effMode = (this.isSameMachine && !this.satAudioMuted) ? "stereo" : this.myChannelMode;
    const isDiscrete = Boolean(this.isSameMachine || this.deviceType === "desktop");
    const isMuted = Boolean(this.satAudioMuted && this.isClusterFollower);
    const configKey = `${targetBuffered}|${effMode}|${isDiscrete}|${isMuted}`;
    if (this._lastSatWorkletConfigKey !== configKey) {
      this._lastSatWorkletConfigKey = configKey;
      this._satPlayerNode.port.postMessage({
        type: "config",
        target: targetBuffered,
        channelMode: effMode,
        isDiscrete,
        muted: isMuted,
      });
    }
    const pcmCopy = new Int16Array(pcm);
    this._satPlayerNode.port.postMessage(
      {
        type: "push",
        pcm: pcmCopy,
        channels,
        frames,
        srcSr: sampleRate,
      },
      [pcmCopy.buffer]
    );
  }

  _unlockSatAudio(fromUserGesture = false) {
    if (typeof window === "undefined") return null;
    try {
      if (typeof navigator !== "undefined" && navigator.audioSession && navigator.audioSession.type !== "playback") {
        navigator.audioSession.type = "playback";
      }
    } catch (_) {}

    const ctx = this._ensureSatAudioCtx();
    if (!ctx) return null;

    if (fromUserGesture) {
      try {
        window.loopbox?.engine?.unlockAudio?.();
      } catch (_) {}
      const anchor = this._initSatSilenceAnchor();
      if (anchor && anchor.paused) {
        anchor.play().catch(() => {});
      }
      try {
        if (ctx.state !== "running") {
          ctx.resume().catch(() => {});
        }
        const silentBuf = ctx.createBuffer(1, 1, ctx.sampleRate || 44100);
        const src = ctx.createBufferSource();
        src.buffer = silentBuf;
        src.connect(this.satGainNode || ctx.destination);
        src.start(0);
      } catch (_) {}
    }
    this._updateClusterMemberBanner();
    return ctx;
  }

  setSatelliteAudioEnabled(enabled, notifyServer = true, fromUserGesture = false) {
    this.satAudioEnabled = Boolean(enabled);
    if (this.satAudioEnabled) {
      const ctx = this._unlockSatAudio(fromUserGesture);
      if (ctx && ctx.state === "running") {
        this.satNextPlayTime = ctx.currentTime + (this.hostAlignMs || 60) / 1000;
      } else {
        this.satNextPlayTime = 0;
      }
    } else {
      this.satNextPlayTime = 0;
      this._pendingAudioPackets = [];
      if (this._satSilenceAudio && !this._satSilenceAudio.paused) {
        try {
          this._satSilenceAudio.pause();
        } catch (_) {}
      }
    }
    if (notifyServer) {
      this._sendAudioSubscribe(this.satAudioEnabled);
    }
    this._updateSatelliteAudioUI();
  }

  setSatelliteAudioVolume(vol) {
    this.satAudioVol = Math.max(0, Math.min(1.5, Number(vol) || 0));
    this._syncSatEffectiveGain();
    this._updateSatelliteAudioUI();
  }

  setSatelliteAudioLatency(ms) {
    // Supports both fine phase offset (-50..+50ms) and legacy buffer values
    const val = Math.round(Number(ms) || 0);
    if (val >= -60 && val <= 60) {
      this.myLatencyOffsetMs = val;
      this.satLatencyMs = Math.max(15, this.hostAlignMs + val);
    } else {
      this.satLatencyMs = Math.max(15, Math.min(250, val));
      this.myLatencyOffsetMs = this.satLatencyMs - this.hostAlignMs;
    }
    this._updateSatelliteAudioUI();
  }

  _updateSatelliteAudioUI() {
    const wrap = document.getElementById("sat-audio-wrap");
    const pill = document.getElementById("btn-sat-audio");
    const label = document.getElementById("sat-audio-label");
    const badge = document.getElementById("sat-audio-state-badge");
    const swBtn = document.getElementById("btn-sat-audio-switch");
    const swTxt = document.getElementById("sat-audio-switch-text");
    const volSlider = document.getElementById("s-sat-local-vol");
    const volNum = document.getElementById("sat-vol-num");
    const latSlider = document.getElementById("s-sat-local-lat");
    const latNum = document.getElementById("sat-lat-num");

    const ctxRunning = !this.satAudioCtx || this.satAudioCtx.state === "running";
    const statusText = !this.satAudioEnabled
      ? "Tắt"
      : ctxRunning
        ? "Đang phát · Zero-Echo"
        : "Chạm bật tiếng";

    if (wrap) wrap.classList.toggle("is-active", this.satAudioEnabled);
    if (pill) pill.setAttribute("aria-pressed", String(this.satAudioEnabled));
    if (label) {
      label.textContent = !this.satAudioEnabled
        ? "Loa Vệ tinh: Tắt"
        : ctxRunning
          ? "Loa Vệ tinh: Đang phát"
          : "Loa Vệ tinh: Chạm bật tiếng";
    }
    if (badge) {
      badge.textContent = statusText;
      badge.classList.toggle("is-on", this.satAudioEnabled);
    }
    if (swBtn) swBtn.classList.toggle("is-active", this.satAudioEnabled);
    if (swTxt) swTxt.textContent = this.satAudioEnabled ? "Tắt Loa Vệ tinh" : "Bật Loa Vệ tinh";
    if (volSlider) {
      if (document.activeElement !== volSlider) volSlider.value = String(this.satAudioVol);
      const volPct = Math.max(0, Math.min(100, (this.satAudioVol / 1.5) * 100));
      volSlider.style.setProperty("--v", `${volPct.toFixed(1)}%`);
    }
    if (volNum) volNum.textContent = `${Math.round(this.satAudioVol * 100)}%`;
    if (latSlider) {
      const minVal = parseFloat(latSlider.min || "-50");
      const maxVal = parseFloat(latSlider.max || "50");
      const curVal = minVal < 0 ? this.myLatencyOffsetMs : this.satLatencyMs;
      if (document.activeElement !== latSlider) latSlider.value = String(curVal);
      const latPct = Math.max(0, Math.min(100, ((curVal - minVal) / Math.max(1, maxVal - minVal)) * 100));
      latSlider.style.setProperty("--v", `${latPct.toFixed(1)}%`);
      if (latNum) {
        latNum.textContent = minVal < 0 ? `${curVal > 0 ? "+" : ""}${curVal}ms` : `${curVal}ms`;
      }
    }
  }

  _schedulePcmPacket(ctx, channels, srcSr, pcm, frames, serverCaptureMs = 0) {
    if (this.satAudioMuted && this.isClusterFollower) return;

    // Use Web Audio native polyphase resampler (zero-distortion browser hardware resampling)
    const audioBuf = ctx.createBuffer(channels, frames, srcSr);
    const ch0 = audioBuf.getChannelData(0);
    const ch1 = channels > 1 ? audioBuf.getChannelData(1) : null;
    const inv = 1 / 32768;

    if (ch1) {
      for (let i = 0, j = 0; i < frames; i++, j += 2) {
        ch0[i] = pcm[j] * inv;
        ch1[i] = pcm[j + 1] * inv;
      }
    } else {
      for (let i = 0; i < frames; i++) {
        ch0[i] = pcm[i] * inv;
      }
    }

    const now = ctx.currentTime;
    let targetLeadSec = Math.max(0.022, Math.min(0.25, ((this.hostAlignMs || 60) + (this.myLatencyOffsetMs || 0)) / 1000));

    if (serverCaptureMs > 0 && this.ntpSynced) {
      const nowServerMs = (typeof performance !== "undefined" ? performance.now() : Date.now()) + this.ntpOffsetMs;
      const packetAgeMs = Math.max(0, Math.min(250, nowServerMs - serverCaptureMs));
      const remainingMs = (this.hostAlignMs || 60) + (this.myLatencyOffsetMs || 0) - packetAgeMs;
      targetLeadSec = Math.max(0.022, Math.min(0.25, remainingMs / 1000));
    }

    const idealPlayTime = now + targetLeadSec;
    let isUnderrun = false;

    // Buffer scheduling state
    if (!this.satNextPlayTime || this.satNextPlayTime < now + 0.010) {
      // True underrun (startup or audio pipeline starved):
      this.satNextPlayTime = Math.max(now + 0.018, idealPlayTime);
      this._filteredDriftSec = 0;
      isUnderrun = true;
    }

    // Measure time difference between where playback is and where ideal target is
    const rawDriftSec = idealPlayTime - this.satNextPlayTime;

    // Apply low-pass EMA filter (alpha = 0.06) to reject high-frequency packet jitter (1-10ms fluctuations)
    this._filteredDriftSec = (this._filteredDriftSec ?? 0) * 0.94 + rawDriftSec * 0.06;

    // Only if drift is massive (>75ms, e.g. latency slider dragged), perform hard resync
    if (Math.abs(this._filteredDriftSec) > 0.075) {
      this.satNextPlayTime = idealPlayTime;
      this._filteredDriftSec = 0;
      isUnderrun = true;
    }

    // Smooth varispeed pitch-lock: adjust playbackRate within +/-1.2% (zero audible pitch change, continuous sample-exact chaining)
    // Positive drift = behind schedule -> play slightly faster (rate > 1.0)
    // Negative drift = ahead of schedule -> play slightly slower (rate < 1.0)
    const rateNudge = Math.max(0.988, Math.min(1.012, 1.0 + (this._filteredDriftSec * 0.12)));

    // Micro 1.5ms (64 samples) fade-in on underrun recovery to prevent start pop
    if (isUnderrun) {
      const declickLen = Math.min(64, frames);
      for (let i = 0; i < declickLen; i++) {
        const factor = i / declickLen;
        ch0[i] *= factor;
        if (ch1) ch1[i] *= factor;
      }
    }

    const src = ctx.createBufferSource();
    src.buffer = audioBuf;
    src.playbackRate.value = rateNudge;
    src.connect(this.satChannelSplitter || this.satGainNode || ctx.destination);

    // Contiguous scheduling: start precisely where previous buffer finished!
    src.start(this.satNextPlayTime);
    this.satNextPlayTime += (audioBuf.duration / rateNudge);
  }

  handleAudioPacket(arrayBuffer) {
    if (!this.isReceivingStreamAudio || !arrayBuffer || arrayBuffer.byteLength < 12) return;
    this._lastAudioRxAt = Date.now();
    const ctx = this._ensureSatAudioCtx();
    if (!ctx) return;

    const header = new DataView(arrayBuffer, 0, Math.min(16, arrayBuffer.byteLength));
    if (header.getUint8(0) !== 0x4d || header.getUint8(1) !== 0x4c) return;
    const version = header.getUint8(2) || 1;
    const channels = Math.max(1, Math.min(2, header.getUint8(3) || 2));
    const sampleRate = Math.max(8000, Math.min(96000, header.getUint32(4, true) || 22050));

    const headerBytes = version >= 2 && arrayBuffer.byteLength >= 18 ? 16 : 8;
    const serverCaptureMs = headerBytes === 16 ? header.getFloat64(8, true) : 0;
    const sampleCount = Math.floor((arrayBuffer.byteLength - headerBytes) / 2);
    if (sampleCount <= 0) return;

    const pcm = new Int16Array(arrayBuffer, headerBytes, sampleCount);
    const frames = Math.floor(pcm.length / channels);
    if (frames <= 0) return;

    if (ctx.state !== "running") {
      if (!this._pendingAudioPackets) this._pendingAudioPackets = [];
      this._pendingAudioPackets.push({ channels, sampleRate, pcm: new Int16Array(pcm), frames, serverCaptureMs });
      if (this._pendingAudioPackets.length > 3) {
        this._pendingAudioPackets.shift();
      }
      this._updateSatelliteAudioUI();
      this._updateClusterMemberBanner();
      return;
    }

    if (this._satPlayerWorkletReady && this._satPlayerNode) {
      if (this._pendingAudioPackets?.length) {
        const queued = this._pendingAudioPackets.splice(0);
        for (const pkt of queued) {
          this._pushToSatWorklet(pkt.channels, pkt.sampleRate, pkt.pcm, pkt.frames);
        }
      }
      this._pushToSatWorklet(channels, sampleRate, pcm, frames);
      return;
    }

    if (this._satPlayerLoading && !this._satPlayerWorkletFailed) {
      if (!this._satWorkletQueue) this._satWorkletQueue = [];
      this._satWorkletQueue.push({ channels, sampleRate, pcm: new Int16Array(pcm), frames });
      if (this._satWorkletQueue.length > 6) this._satWorkletQueue.shift();
      return;
    }

    if (this._pendingAudioPackets?.length) {
      const queued = this._pendingAudioPackets.splice(0);
      for (const pkt of queued) {
        this._schedulePcmPacket(ctx, pkt.channels, pkt.sampleRate, pkt.pcm, pkt.frames, pkt.serverCaptureMs);
      }
    }

    this._schedulePcmPacket(ctx, channels, sampleRate, pcm, frames, serverCaptureMs);
  }

  // --- Host Broadcasting ---
  broadcastTelemetry(payload) {
    if (!this.connected || this.isSatellite || this.isClusterFollower) return;
    const now = performance.now();
    if (now - this.lastBroadcast < this.minInterval) return;
    this.lastBroadcast = now;

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(payload));
      } catch (e) {
        // drop frame on send error
      }
    }
  }

  // --- Satellite & Cluster Mirror Stage Rendering ---
  applySatelliteTelemetry(data) {
    if (!this.isStageMirrorActive) return;
    const root = document.documentElement.style;

    if (data.enabled_ids) {
      this.enabledIds = data.enabled_ids;
    }

    // 0. Theme, Glow, Scale & Chord Density sync from Host
    if (data.theme && data.theme !== theme.themeName()) {
      theme.setTheme(data.theme);
      if (this.viz) this.viz.invalidate();
    }
    let glowChanged = false;
    if (data.glow !== undefined && Math.abs(theme.getGlow() - data.glow) > 0.005) {
      theme.setGlow(data.glow);
      glowChanged = true;
      if (this.viz) this.viz.invalidate();
    }
    if (data.viz_scale !== undefined && this.viz && Math.abs((this.viz.scale || 1.0) - data.viz_scale) > 0.005) {
      this.viz.setScale(data.viz_scale);
    }
    if (data.beat_pulse !== undefined && this.viz && typeof this.viz.setBeatPulse === "function") {
      this.viz.setBeatPulse(data.beat_pulse);
    }
    if (data.ui_scale !== undefined && Math.abs((this._lastUiScale || 1.0) - data.ui_scale) > 0.005) {
      this._lastUiScale = data.ui_scale;
      root.setProperty("--ui-scale", String(data.ui_scale));
      root.fontSize = `${16 * data.ui_scale}px`;
      if (this.viz && typeof this.viz._resize === "function") this.viz._resize();
    }
    if (
      data.keep !== undefined &&
      this.viz?.player?.settings &&
      Math.abs((this.viz.player.settings.keep || 0.575) - data.keep) > 0.005
    ) {
      this.viz.player.settings.keep = data.keep;
      this.viz.invalidate();
    }
    if (data.night !== undefined) {
      const isNight = Boolean(data.night);
      if (document.body.classList.contains("is-night") !== isNight) {
        document.body.classList.toggle("is-night", isNight);
        glowChanged = true;
        if (this.viz) this.viz.invalidate();
      }
    }

    // 1. Color and neon light properties via theme.applyPage
    if (data.acc) {
      const accSig = `${data.acc[0].toFixed(3)},${data.acc[1].toFixed(3)},${data.acc[2].toFixed(1)}|${data.acc2 ? `${data.acc2[0].toFixed(3)},${data.acc2[1].toFixed(3)},${data.acc2[2].toFixed(1)}` : ""}|${(data.fill_a || 0).toFixed(2)}`;
      if (glowChanged || this._lastColorSig !== accSig) {
        this._lastColorSig = accSig;
        const primary = { l: data.acc[0], c: data.acc[1], h: data.acc[2] };
        const second = data.acc2 ? { l: data.acc2[0], c: data.acc2[1], h: data.acc2[2] } : primary;
        theme.applyPage(primary, second, data.fill_a || 0);
      }
    }

    // 2. Audio-reactive pulse
    const pulseVal = Math.min(1.4, 0.6 * (data.pulse || 0) + 0.9 * (data.bass || 0));
    root.setProperty("--pulse", pulseVal.toFixed(2));

    // 3. Sync primary & second tracks on satellite / cluster mirror
    const LOCAL_APP_VER = 176;
    const remoteVerNum = typeof data.app_ver === "string" ? parseInt(data.app_ver.replace(/^v/i, ""), 10) : 0;
    if (remoteVerNum > LOCAL_APP_VER && typeof window !== "undefined" && !this._reloadingVer) {
      const guardKey = `ml_reloaded_v${remoteVerNum}`;
      const lastTry = Number(typeof sessionStorage !== "undefined" ? sessionStorage.getItem(guardKey) : 0);
      if (!lastTry || Date.now() - lastTry > 15000) {
        try {
          sessionStorage?.setItem?.(guardKey, String(Date.now()));
        } catch (_) {}
        this._reloadingVer = true;
        window.location.reload();
        return;
      }
    }

    const primInfo =
      data.primary ||
      (data.track_id
        ? {
            id: data.track_id,
            title: data.title,
            artist: data.artist,
            bpm: data.bpm,
            camelot: data.camelot,
            key: data.key,
          }
        : null);

    if (primInfo?.id && data.mode !== "idle") {
      const cached = this.trackCache.get(primInfo.id);
      if (cached && cached.analysis) {
        if (this.primaryTrack !== cached) {
          this.primaryTrack = cached;
          this.currentTrack = cached;
          this.currentTrackId = primInfo.id;
          this._prefetchCandidateTransitions(cached);
          if (this.viz) {
            this.viz.invalidate();
          }
        }
      } else {
        this.currentTrackId = primInfo.id;
        if (!this.loadingTracks.has(primInfo.id)) {
          this.ensureTrack(primInfo).then((tr) => {
            if (tr && (this.telemetry?.track_id === primInfo.id || this.currentTrackId === primInfo.id)) {
              this.primaryTrack = tr;
              this.currentTrack = tr;
              this.currentTrackId = primInfo.id;
              this._prefetchCandidateTransitions(tr);
              if (this.telemetry) this._syncCenterCaption(this.telemetry, primInfo.id);
              if (this.viz) {
                this.viz.invalidate();
              }
            }
          });
        }
      }
    } else {
      this.currentTrackId = null;
      this.primaryTrack = null;
      this.currentTrack = null;
    }

    if (data.second?.id) {
      const cachedSec = this.trackCache.get(data.second.id);
      if (cachedSec && cachedSec.analysis) {
        if (this.secondTrack !== cachedSec) {
          this.secondTrack = cachedSec;
          this.secondTrackId = data.second.id;
          if (this.viz) {
            this.viz.invalidate();
          }
        }
      } else {
        if (!this.loadingTracks.has(data.second.id)) {
          this.ensureTrack(data.second).then((tr) => {
            if (tr) {
              this.secondTrack = tr;
              this.secondTrackId = data.second.id;
              if (this.viz) {
                this.viz.invalidate();
              }
            }
          });
        }
      }
    } else {
      this.secondTrackId = null;
      this.secondTrack = null;
    }

    const preloadId = data.placeholder?.id || data.plan?.to || null;
    if (preloadId && !this.trackCache.has(preloadId) && !this.loadingTracks.has(preloadId)) {
      this.ensureTrack({ id: preloadId });
    }
    if (Array.isArray(data.prefetch_ids)) {
      for (const pid of data.prefetch_ids.slice(0, 4)) {
        if (pid && !this.trackCache.has(pid) && !this.loadingTracks.has(pid)) {
          this.ensureTrack({ id: pid });
        }
      }
    }

    const readyForCaption =
      !primInfo?.id ||
      data.mode === "idle" ||
      !this.primaryTrack ||
      this.primaryTrack.id === primInfo.id ||
      data.cap_on === "second";
    if (readyForCaption) {
      this._syncCenterCaption(data, primInfo?.id);
    }

    const isRoIdle = Boolean(
      data.ro_tl_html && (data.ro_tl_html.includes("chưa phát") || data.ro_tr_html?.includes("chưa có vòng nào"))
    );
    const hasActiveStageTrack = Boolean(primInfo?.id && (data.mode === "ring" || data.mode === "paused" || data.mode === "playing"));
    if (data.ro_tl_html !== undefined && (!hasActiveStageTrack || !isRoIdle)) {
      const roTl = document.getElementById("ro-tl");
      if (roTl && roTl.innerHTML !== data.ro_tl_html) roTl.innerHTML = data.ro_tl_html;
    } else if (hasActiveStageTrack) {
      const roTl = document.getElementById("ro-tl");
      const rawT = primInfo?.title || data.title || this.primaryTrack?.meta?.title || "";
      const s = rawT ? splitTitle(rawT, primInfo?.artist || data.artist || "") : { title: "", artist: "" };
      if (roTl && s.title) {
        const modeTag = data.locked ? "LẶP" : "CHUỖI";
        const newTl = `<b>${modeTag}</b> // ${escHtml(s.artist ? `${s.artist} · ` : "")}${escHtml(s.title)}`;
        if (roTl.innerHTML !== newTl) roTl.innerHTML = newTl;
      }
    }
    if (data.ro_tr_html !== undefined && (!hasActiveStageTrack || !isRoIdle)) {
      const roTr = document.getElementById("ro-tr");
      if (roTr && roTr.innerHTML !== data.ro_tr_html) roTr.innerHTML = data.ro_tr_html;
    } else if (hasActiveStageTrack) {
      const roTr = document.getElementById("ro-tr");
      const bpmVal = Math.round(primInfo?.bpm || data.bpm || this.primaryTrack?.analysis?.bpm || 120);
      const camVal = primInfo?.camelot || data.camelot || this.primaryTrack?.analysis?.camelot || "";
      const secVal = Math.max(0, Math.round(data.pos ?? data.now ?? 0));
      const mm = Math.floor(secVal / 60);
      const ss = String(secVal % 60).padStart(2, "0");
      const camBadge = camVal ? `<span class="badge-camelot">${escHtml(camVal)}</span> · ` : "";
      const newTr = `<span class="mono">∞ ${mm}:${ss}</span><span class="ro-stats"> · ${camBadge}${bpmVal} BPM</span>`;
      if (roTr && roTr.innerHTML !== newTr) roTr.innerHTML = newTr;
    }
    if (data.next_html !== undefined) {
      const nextInfo = document.getElementById("next-info");
      if (nextInfo && nextInfo.innerHTML !== data.next_html) nextInfo.innerHTML = data.next_html;
    }
    if (data.history_html !== undefined) {
      const histEl = document.getElementById("history");
      if (histEl && histEl.dataset.html !== data.history_html) {
        histEl.dataset.html = data.history_html;
        histEl.innerHTML = data.history_html;
        histEl.scrollLeft = histEl.scrollWidth;
      }
    }

    const isPlaying = data.mode === "ring";
    const hasTrack = Boolean(primInfo?.id && (data.mode === "ring" || data.mode === "paused"));
    const playBtn = document.getElementById("btn-play");
    if (playBtn) {
      const wantState = isPlaying ? "pause" : "play";
      if (playBtn.dataset.state !== wantState) {
        playBtn.dataset.state = wantState;
        playBtn.setAttribute("aria-label", isPlaying ? "Tạm dừng" : "Phát");
      }
      if (playBtn.disabled) playBtn.disabled = false;
    }
    const jumpBtn = document.getElementById("btn-jump");
    if (jumpBtn && jumpBtn.disabled !== !hasTrack) jumpBtn.disabled = !hasTrack;
    const nextBtn = document.getElementById("btn-next");
    if (nextBtn && nextBtn.disabled !== !hasTrack) nextBtn.disabled = !hasTrack;

    const lockBtn = document.getElementById("btn-lock");
    if (lockBtn) {
      const lockedStr = String(Boolean(data.locked));
      if (lockBtn.getAttribute("aria-pressed") !== lockedStr) {
        lockBtn.setAttribute("aria-pressed", lockedStr);
      }
      if (lockBtn.disabled !== !hasTrack) lockBtn.disabled = !hasTrack;
    }

    const khoBtn = document.getElementById("btn-kho");
    if (khoBtn && data.kho_visible !== undefined) {
      const wantHidden = !data.kho_visible;
      if (khoBtn.hidden !== wantHidden) khoBtn.hidden = wantHidden;
      if (khoBtn.disabled !== (!hasTrack && wantHidden)) khoBtn.disabled = !hasTrack && wantHidden;
      const pressedStr = String(Boolean(data.kho_pressed));
      if (khoBtn.getAttribute("aria-pressed") !== pressedStr) {
        khoBtn.setAttribute("aria-pressed", pressedStr);
      }
    }

    const recBtn = document.getElementById("btn-record");
    if (recBtn && data.recording !== undefined) {
      const recStr = String(Boolean(data.recording));
      if (recBtn.getAttribute("aria-pressed") !== recStr) recBtn.setAttribute("aria-pressed", recStr);
      const recLabel = document.getElementById("record-label");
      if (recLabel && data.rec_label && recLabel.textContent !== data.rec_label) {
        recLabel.textContent = data.rec_label;
      }
    }

    const vocalBtn = document.getElementById("btn-vocal-mode");
    if (vocalBtn && data.vocal_mode) {
      if (vocalBtn.dataset.mode !== data.vocal_mode) vocalBtn.dataset.mode = data.vocal_mode;
      const vocalLbl = document.getElementById("vocal-mode-label");
      if (vocalLbl && data.vocal_label && vocalLbl.textContent !== data.vocal_label) {
        vocalLbl.textContent = data.vocal_label;
      }
    }

    const micBtn = document.getElementById("btn-karaoke-mic");
    if (micBtn && data.mic_active !== undefined) {
      const micStr = String(Boolean(data.mic_active));
      if (micBtn.dataset.active !== micStr) {
        micBtn.dataset.active = micStr;
        micBtn.setAttribute("aria-pressed", micStr);
      }
    }

    const timerBtn = document.getElementById("btn-timer");
    if (timerBtn && data.timer_active !== undefined) {
      if (data.timer_active) {
        if (timerBtn.getAttribute("data-active") !== "true") timerBtn.setAttribute("data-active", "true");
      } else if (timerBtn.hasAttribute("data-active")) {
        timerBtn.removeAttribute("data-active");
      }
      const timerBadge = document.getElementById("timer-badge");
      if (timerBadge && data.timer_badge && timerBadge.textContent !== data.timer_badge) {
        timerBadge.textContent = data.timer_badge;
      }
    }

    const nightBtn = document.getElementById("btn-night");
    if (nightBtn) {
      if (data.night_visible !== undefined) {
        const wantHidden = !data.night_visible;
        if (nightBtn.hidden !== wantHidden) nightBtn.hidden = wantHidden;
      }
      if (data.night !== undefined) {
        const nightStr = String(Boolean(data.night));
        if (nightBtn.getAttribute("aria-pressed") !== nightStr) {
          nightBtn.setAttribute("aria-pressed", nightStr);
        }
      }
    }

    const eqBtn = document.getElementById("btn-eq");
    if (eqBtn && data.eq_mode) {
      const eqActive = String(data.eq_mode !== "flat");
      if (eqBtn.getAttribute("data-active") !== eqActive) {
        eqBtn.setAttribute("data-active", eqActive);
        eqBtn.setAttribute("aria-pressed", eqActive);
      }
      const eqBadge = document.getElementById("eq-badge");
      if (eqBadge && data.eq_badge && eqBadge.textContent !== data.eq_badge) {
        eqBadge.textContent = data.eq_badge;
      }
      document.querySelectorAll(".eq-opt").forEach((b) => b.classList.toggle("on", b.dataset.eq === data.eq_mode));
    }

    const muteBtn = document.getElementById("btn-mute");
    if (muteBtn) {
      if (data.muted !== undefined && muteBtn.dataset.muted !== String(data.muted)) {
        muteBtn.dataset.muted = String(data.muted);
      }
      if (data.vol_level && muteBtn.dataset.level !== data.vol_level) {
        muteBtn.dataset.level = data.vol_level;
      }
    }

    const sVol = document.getElementById("s-vol");
    if (sVol && data.volume !== undefined && document.activeElement !== sVol) {
      const curVal = parseFloat(sVol.value);
      if (Math.abs(curVal - data.volume) > 0.005) {
        sVol.value = data.volume;
        const pct = Math.max(0, Math.min(100, (data.volume / 1.5) * 100));
        sVol.style.setProperty("--v", `${pct.toFixed(1)}%`);
        const vVol = document.getElementById("v-vol");
        if (vVol) vVol.textContent = `${Math.round(data.volume * 100)}%`;
        if (data.volume > 1.0) {
          const k = Math.min(1, (data.volume - 1.0) / 0.5);
          const crimson = `oklch(${0.72 - 0.27 * k} ${0.15 + 0.1 * k} ${65 - 41 * k})`;
          sVol.style.setProperty("--vol-color", crimson);
          sVol.style.setProperty(
            "--vol-track",
            `linear-gradient(90deg, var(--accent) 0%, var(--accent) 66.7%, ${crimson} ${pct.toFixed(1)}%, var(--ink-3) ${pct.toFixed(1)}%)`
          );
        } else {
          sVol.style.removeProperty("--vol-color");
          sVol.style.setProperty(
            "--vol-track",
            `linear-gradient(90deg, var(--accent) 0%, var(--accent) ${pct.toFixed(1)}%, var(--ink-3) ${pct.toFixed(1)}%)`
          );
        }
      }
    }

    const lyricsBox = document.getElementById("ambient-lyrics");
    if (lyricsBox && data.lyrics_enabled !== undefined) {
      const hasAnyLine = Boolean(data.lyric_prev || data.lyric_cur || data.lyric_next);
      const wantHidden = !data.lyrics_enabled || !hasAnyLine;
      if (lyricsBox.hidden !== wantHidden) lyricsBox.hidden = wantHidden;
      if (!wantHidden) {
        const lPrev = document.getElementById("lyric-line-prev");
        const lCur = document.getElementById("lyric-line-cur");
        const lNext = document.getElementById("lyric-line-next");
        if (lPrev && lPrev.textContent !== (data.lyric_prev || "")) lPrev.textContent = data.lyric_prev || "";
        if (lCur && lCur.textContent !== (data.lyric_cur || "")) lCur.textContent = data.lyric_cur || "";
        if (lNext && lNext.textContent !== (data.lyric_next || "")) lNext.textContent = data.lyric_next || "";
      }
    }
    this._updateClusterMemberBanner();
  }

  sendCommand(action, value = null) {
    if (!this.connected || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(JSON.stringify({ type: "command", action, value }));
    } catch (e) {
      console.debug("[StageSync] sendCommand error:", e);
    }
  }

  async requestWakeLock() {
    if ("wakeLock" in navigator) {
      try {
        this.wakeLock = await navigator.wakeLock.request("screen");
        document.addEventListener("visibilitychange", async () => {
          if (this.wakeLock !== null && document.visibilityState === "visible") {
            this.wakeLock = await navigator.wakeLock.request("screen");
          }
        });
      } catch (err) {
        console.debug("Wake Lock error:", err);
      }
    }
  }

  initSatelliteUI() {
    const rcTitle = document.getElementById("rc-title");
    const rcKicker = document.getElementById("rc-kicker");
    const rcMeta = document.getElementById("rc-meta");
    const rcCta = document.getElementById("rc-cta");
    if (rcCta) rcCta.hidden = true;
    if (rcKicker) rcKicker.textContent = "HAI VÒNG ĐANG CHỜ";
    if (rcTitle) rcTitle.textContent = "Chọn một bài để bắt đầu vòng lặp";
    if (rcMeta) rcMeta.textContent = "Bấm phát, hoặc nút phát ở một bài trong thư viện";
    const roTl = document.getElementById("ro-tl");
    if (roTl) roTl.innerHTML = "<b>MEIKOVA LOOP</b> // chuỗi · chưa phát";
    const roTr = document.getElementById("ro-tr");
    if (roTr) roTr.innerHTML = '<span class="mono">∞ 0:00</span><span class="ro-stats"> · chưa có vòng nào</span>';
    const playBtn = document.getElementById("btn-play");
    if (playBtn) playBtn.disabled = false;

    const satAudioBtn = document.getElementById("btn-sat-audio");
    const satCfgBtn = document.getElementById("btn-sat-audio-cfg");
    const satPopover = document.getElementById("sat-audio-popover");
    const satSwitch = document.getElementById("btn-sat-audio-switch");
    const satVolSlider = document.getElementById("s-sat-local-vol");
    const satLatSlider = document.getElementById("s-sat-local-lat");

    const toggleSatAudio = () => {
      if (this.satAudioEnabled && this.satAudioCtx && this.satAudioCtx.state !== "running") {
        this._unlockSatAudio(true);
        this._sendAudioSubscribe(true);
        this._updateSatelliteAudioUI();
        return;
      }
      this.setSatelliteAudioEnabled(!this.satAudioEnabled, true, true);
    };

    satAudioBtn?.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSatAudio();
    });

    satSwitch?.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSatAudio();
    });

    satCfgBtn?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (this.satAudioEnabled) {
        this._unlockSatAudio(true);
      }
      if (!satPopover) return;
      const isHidden = satPopover.hidden;
      satPopover.hidden = !isHidden;
      satCfgBtn.setAttribute("aria-expanded", String(isHidden));
    });

    satVolSlider?.addEventListener("input", () => {
      if (this.satAudioEnabled) {
        this._unlockSatAudio(true);
      }
      this.setSatelliteAudioVolume(parseFloat(satVolSlider.value));
    });

    satLatSlider?.addEventListener("input", () => {
      if (this.satAudioEnabled) {
        this._unlockSatAudio(true);
      }
      this.setSatelliteAudioLatency(parseInt(satLatSlider.value, 10));
    });

    const unlockIfSatAudioActive = () => {
      if (this.satAudioEnabled || this.isClusterFollower) {
        this._unlockSatAudio(true);
      }
    };

    document.addEventListener("click", (e) => {
      if (satPopover && !satPopover.hidden && !e.target.closest("#sat-audio-wrap")) {
        satPopover.hidden = true;
        satCfgBtn?.setAttribute("aria-expanded", "false");
      }
      unlockIfSatAudioActive();
    });

    document.addEventListener("pointerdown", unlockIfSatAudioActive, { passive: true });
    document.addEventListener("touchend", unlockIfSatAudioActive, { passive: true });

    setInterval(() => {
      if (!this.satAudioEnabled) return;
      if (this.telemetry && this.telemetry.mode === "ring") {
        const silentMs = this._lastAudioRxAt ? Date.now() - this._lastAudioRxAt : 99999;
        if (silentMs > 1500) {
          this._sendAudioSubscribe(true);
        }
      }
    }, 1500);

    this._updateSatelliteAudioUI();
  }
}

export const stageSync =
  (typeof window !== "undefined" && window.__meikovaStageSyncSingleton) || new StageSyncClient();
if (typeof window !== "undefined") {
  window.__meikovaStageSyncSingleton = stageSync;
}

export function initStageSyncControls({ player, engine } = {}) {
  const modal = document.getElementById("modalStageSync");
  const openBtn = document.getElementById("btn-stage-sync-modal");
  const closeBtn = document.getElementById("btnCloseStageSync");
  const tabSat = document.getElementById("tab-btn-sat");
  const tabLights = document.getElementById("tab-btn-lights");
  const paneSat = document.getElementById("pane-sat");
  const paneLights = document.getElementById("pane-lights");

  if (!stageSync.isSatellite && engine && player) {
    stageSync.attachHostEngine(engine, player);
  }

  // Unlock cluster follower audio automatically on any user gesture
  const unlockClusterOnGesture = () => {
    if (stageSync.isClusterFollower) {
      stageSync._unlockSatAudio(true);
    }
  };
  document.addEventListener("pointerdown", unlockClusterOnGesture, { passive: true });

  // Wire Cluster Member Banner controls (#cluster-member-banner)
  const mirrorBtn = document.getElementById("btn-cluster-stage-mirror");
  const leaveBtn = document.getElementById("btn-cluster-leave");
  const unlockClusterBtn = document.getElementById("btn-cluster-audio-unlock");
  const audioToggleBtn = document.getElementById("btn-cluster-audio-toggle");
  const openClusterFromBannerBtn = document.getElementById("btn-cluster-banner-config");

  audioToggleBtn?.addEventListener("click", () => {
    stageSync.setFollowerAudioMuted(!stageSync.satAudioMuted);
  });

  mirrorBtn?.addEventListener("click", () => {
    stageSync._unlockSatAudio(true);
    stageSync.setClusterMirrorMode(!stageSync.isClusterMirror);
  });

  leaveBtn?.addEventListener("click", () => {
    stageSync.leaveCluster();
  });

  unlockClusterBtn?.addEventListener("click", () => {
    stageSync._unlockSatAudio(true);
  });

  openClusterFromBannerBtn?.addEventListener("click", () => {
    document.getElementById("btn-nav-cluster")?.click();
  });

  // Wire Cluster Link Modal (#modalClusterLink & #btn-nav-cluster)
  initClusterModalControls();

  if (!modal || !openBtn) return;

  // Remote command handler on Host
  stageSync.onCommand = async (cmd) => {
    if (!player || !cmd) return;
    const act = cmd.action;
    const val = cmd.value;
    if (act === "toggle_pause") {
      document.getElementById("btn-play")?.click();
      await new Promise((r) => setTimeout(r, 16));
    } else if (act === "jump") {
      document.getElementById("btn-jump")?.click();
    } else if (act === "next") {
      document.getElementById("btn-next")?.click();
    } else if (act === "switch_kho") {
      document.getElementById("btn-kho")?.click();
    } else if (act === "toggle_lock") {
      document.getElementById("btn-lock")?.click();
    } else if (act === "toggle_record") {
      document.getElementById("btn-record")?.click();
    } else if (act === "cycle_vocal") {
      document.getElementById("btn-vocal-mode")?.click();
    } else if (act === "toggle_mic") {
      document.getElementById("btn-mic-toggle-switch")?.click();
    } else if (act === "set_timer") {
      const opt = document.querySelector(`.timer-opt[data-timer="${val}"]`);
      opt?.click();
    } else if (act === "toggle_night") {
      document.getElementById("btn-night")?.click();
    } else if (act === "set_eq") {
      const opt = document.querySelector(`.eq-opt[data-eq="${val}"]`);
      opt?.click();
    } else if (act === "toggle_mute") {
      document.getElementById("btn-mute")?.click();
    } else if (act === "toggle_lyrics") {
      document.getElementById("zen-btn-lyrics")?.click();
    } else if (act === "set_volume" && typeof val === "number") {
      const sVol = document.getElementById("s-vol");
      if (sVol) {
        sVol.value = val;
        sVol.dispatchEvent(new Event("input", { bubbles: true }));
      }
    } else if (act === "seek" && typeof val === "number") {
      player.seek(val);
    } else if (act === "force_transition") {
      player.forceTransition();
    } else if (act === "pick_exit" && val && typeof val === "object") {
      player.planTransition(val);
    }
    stageSync.lastBroadcast = 0;
    stageSync.viz?._broadcastHostTelemetry?.();
  };

  stageSync.onStatusChange = (status) => {
    const statusEl = document.getElementById("sync-sat-connected-status");
    if (statusEl) {
      const aCount = status.audio_satellites_count ?? 0;
      statusEl.textContent = `Thiết bị vệ tinh kết nối: ${status.satellites_count ?? 0}${aCount > 0 ? ` (${aCount} bật loa)` : ""}`;
    }
  };

  const hostAudioBtn = document.getElementById("btn-toggle-sat-audio");
  const hostLatSlider = document.getElementById("s-sat-latency");
  const hostLatVal = document.getElementById("v-sat-latency");

  hostAudioBtn?.addEventListener("click", () => {
    const nextState = !(stageSync.audioSatellitesCount > 0 || stageSync.hostAudioStreamEnabled);
    stageSync.setHostAudioControl({
      enabled: nextState,
      host_align_ms: hostLatSlider ? parseInt(hostLatSlider.value, 10) : 60,
    });
  });

  hostLatSlider?.addEventListener("input", () => {
    const ms = parseInt(hostLatSlider.value, 10) || 60;
    if (hostLatVal) hostLatVal.textContent = `${ms}ms`;
    stageSync.setHostAudioControl({
      enabled: stageSync.audioSatellitesCount > 0 || stageSync.hostAudioStreamEnabled,
      host_align_ms: ms,
    });
  });

  // Dynamic Smart Lights & Multi-Vendor RGB Discovery + Manual Connect inside #pane-lights
  const devicesListEl = document.getElementById("lights-devices-list");
  const activeBadgeEl = document.getElementById("lights-active-badge");
  const discoverySubEl = document.getElementById("lights-discovery-sub");
  const scanBtn = document.getElementById("btn-scan-lights");
  const scanBtnText = document.getElementById("btn-scan-lights-text");
  const protoPillsWrap = document.getElementById("lights-proto-pills");
  const protoHintEl = document.getElementById("lights-proto-hint");
  const wledIpInputEl = document.getElementById("input-wled-ip");
  const lightPortInput = document.getElementById("input-light-port");
  const lightLedsInput = document.getElementById("input-light-leds");
  const lightLedsField = document.getElementById("field-light-leds");
  const lightNameInput = document.getElementById("input-light-name");
  const addDeviceBtn = document.getElementById("btn-add-light-device");
  const manualFeedbackEl = document.getElementById("lights-manual-feedback");

  let selectedProto = "wled_ddp";
  let lastDevicesSig = "";
  let didInitialLanScan = false;

  const showManualFeedback = (msg, isErr = false) => {
    if (!manualFeedbackEl) return;
    manualFeedbackEl.textContent = msg;
    manualFeedbackEl.classList.toggle("is-error", isErr);
    manualFeedbackEl.hidden = !msg;
    if (msg) {
      clearTimeout(showManualFeedback._t);
      showManualFeedback._t = setTimeout(() => {
        manualFeedbackEl.hidden = true;
      }, 4200);
    }
  };

  const categoryIconSvg = (cat) => {
    if (cat === "keyboard") {
      return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M18 13h.01M8 16h8"/></svg>`;
    }
    if (cat === "bulb") {
      return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6m-4 4h2M12 2a7 7 0 0 0-7 7c0 2.5 1.5 4.5 3 6h8c1.5-1.5 3-3.5 3-6a7 7 0 0 0-7-7z"/></svg>`;
    }
    if (cat === "controller") {
      return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>`;
    }
    return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h16M4 6h16M4 18h16"/><circle cx="8" cy="6" r="1.5" fill="currentColor"/><circle cx="16" cy="12" r="1.5" fill="currentColor"/><circle cx="11" cy="18" r="1.5" fill="currentColor"/></svg>`;
  };

  const connectionLabel = (conn) => {
    if (conn === "hardware") return "PHẦN CỨNG";
    if (conn === "lan") return "MẠNG LAN";
    return "THỦ CÔNG";
  };

  const renderLightsStatus = (lightsRes, forceRender = false) => {
    if (!lightsRes) return;
    const devs = Array.isArray(lightsRes.devices) ? lightsRes.devices : [];
    const hostDisplay = lightsRes.host_system?.display_name || "";
    const activeCount = lightsRes.active_devices_count ?? devs.filter((d) => d.enabled && d.online !== false).length;

    if (activeBadgeEl) {
      activeBadgeEl.textContent = devs.length > 0 ? `${activeCount}/${devs.length} đang bật` : "0 thiết bị";
      activeBadgeEl.classList.toggle("is-on", activeCount > 0);
    }
    if (discoverySubEl) {
      discoverySubEl.textContent = hostDisplay
        ? `Máy chủ: ${hostDisplay} · Tự động nhận diện phần cứng & đèn thông minh LAN`
        : "Tự động nhận diện phần cứng RGB trên máy & đèn thông minh trong mạng LAN";
    }

    if (!devicesListEl) return;
    const rgbArr = Array.isArray(lightsRes.last_rgb) && lightsRes.last_rgb.length === 3 ? lightsRes.last_rgb : null;
    const liveRgbCss = rgbArr ? `rgb(${rgbArr[0]}, ${rgbArr[1]}, ${rgbArr[2]})` : "";
    const sig = JSON.stringify(devs.map((d) => [d.id, d.name, d.enabled, d.online, d.detail, d.protocol_label]));
    if (!forceRender && sig === lastDevicesSig) {
      if (liveRgbCss) {
        devicesListEl.querySelectorAll(".light-device-card.is-enabled .light-status-dot.is-online").forEach((dot) => {
          dot.style.background = liveRgbCss;
          dot.style.boxShadow = `0 0 8px ${liveRgbCss}`;
        });
      }
      return;
    }
    lastDevicesSig = sig;

    if (devs.length === 0) {
      devicesListEl.innerHTML = `
        <div class="lights-empty-state">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9"/>
            <path d="M12 8v4m0 4h.01"/>
          </svg>
          <div class="lights-empty-text">
            <strong>Chưa phát hiện thiết bị RGB hay đèn thông minh tự động</strong>
            <span>Bấm <b>Quét thiết bị</b> để tìm trên mạng Wi-Fi / OpenRGB, hoặc nhập địa chỉ kết nối thủ công bên dưới.</span>
          </div>
        </div>
      `;
      return;
    }

    devicesListEl.innerHTML = devs
      .map((d) => {
        const isOn = Boolean(d.enabled);
        const isOnline = d.online !== false;
        const canRemove = d.connection === "manual";
        return `
          <div class="light-device-card ${isOn ? "is-enabled" : ""} ${isOnline ? "" : "is-offline"}" data-device-id="${escHtml(d.id)}">
            <div class="light-device-icon" aria-hidden="true">${categoryIconSvg(d.category)}</div>
            <div class="light-device-info">
              <div class="light-device-title-row">
                <span class="light-status-dot ${isOnline ? "is-online" : "is-offline"}" style="${isOn && isOnline && liveRgbCss ? `background:${liveRgbCss};box-shadow:0 0 8px ${liveRgbCss};` : ""}" title="${isOnline ? "Sẵn sàng · Màu đồng bộ trực tiếp" : "Chưa phản hồi"}"></span>
                <span class="light-device-name">${escHtml(d.name)}</span>
              </div>
              <div class="light-device-sub-row">
                <span class="light-device-badge mono">${escHtml(connectionLabel(d.connection))} · ${escHtml(d.protocol_label || d.protocol)}</span>
                <span class="light-device-detail">${escHtml(d.detail || d.address || "")}</span>
              </div>
            </div>
            <div class="light-device-actions">
              <button type="button" class="btn-light-icon btn-light-ping" data-device-id="${escHtml(d.id)}" title="Nháy thử thiết bị này" aria-label="Nháy thử thiết bị">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              </button>
              ${
                canRemove
                  ? `<button type="button" class="btn-light-icon btn-light-remove" data-device-id="${escHtml(d.id)}" title="Ngắt & xóa thiết bị thủ công" aria-label="Xóa thiết bị">
                      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>`
                  : ""
              }
              <button type="button" class="tunnel-toggle-switch btn-light-toggle ${isOn ? "is-active" : ""}" data-device-id="${escHtml(d.id)}" aria-pressed="${isOn ? "true" : "false"}" aria-label="Bật/Tắt đồng bộ thiết bị">
                <span class="switch-handle"></span>
              </button>
            </div>
          </div>
        `;
      })
      .join("");
  };

  devicesListEl?.addEventListener("click", async (e) => {
    const toggleBtn = e.target.closest(".btn-light-toggle");
    if (toggleBtn) {
      const devId = toggleBtn.dataset.deviceId;
      if (!devId) return;
      const next = toggleBtn.getAttribute("aria-pressed") !== "true";
      toggleBtn.classList.toggle("is-active", next);
      toggleBtn.setAttribute("aria-pressed", String(next));
      try {
        const r = await fetch("/api/lights/devices/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: devId, enabled: next }),
        });
        if (r.ok) renderLightsStatus(await r.json(), true);
      } catch (_) {}
      return;
    }

    const pingBtn = e.target.closest(".btn-light-ping");
    if (pingBtn) {
      const devId = pingBtn.dataset.deviceId;
      if (!devId) return;
      pingBtn.classList.add("is-flashing");
      setTimeout(() => pingBtn.classList.remove("is-flashing"), 450);
      fetch("/api/lights/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ r: 255, g: 145, b: 40, device_id: devId }),
      }).catch(() => {});
      return;
    }

    const removeBtn = e.target.closest(".btn-light-remove");
    if (removeBtn) {
      const devId = removeBtn.dataset.deviceId;
      if (!devId) return;
      try {
        const r = await fetch("/api/lights/devices/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: devId }),
        });
        if (r.ok) renderLightsStatus(await r.json(), true);
      } catch (_) {}
    }
  });

  const runLightsScan = async () => {
    if (!scanBtn || scanBtn.disabled) return;
    scanBtn.disabled = true;
    scanBtn.classList.add("is-scanning");
    if (scanBtnText) scanBtnText.textContent = "Đang quét...";
    try {
      const r = await fetch("/api/lights/scan", { method: "POST" });
      if (r.ok) {
        const st = await r.json();
        renderLightsStatus(st, true);
      }
    } catch (_) {
    } finally {
      scanBtn.disabled = false;
      scanBtn.classList.remove("is-scanning");
      if (scanBtnText) scanBtnText.textContent = "Quét thiết bị";
    }
  };

  scanBtn?.addEventListener("click", runLightsScan);

  protoPillsWrap?.addEventListener("click", (e) => {
    const pill = e.target.closest(".lights-proto-pill");
    if (!pill) return;
    protoPillsWrap.querySelectorAll(".lights-proto-pill").forEach((b) => b.classList.remove("is-active"));
    pill.classList.add("is-active");
    selectedProto = pill.dataset.proto || "wled_ddp";
    if (protoHintEl && pill.dataset.hint) protoHintEl.textContent = pill.dataset.hint;
    if (lightPortInput && pill.dataset.port) lightPortInput.value = pill.dataset.port;
    if (lightLedsInput && pill.dataset.leds) lightLedsInput.value = pill.dataset.leds;
    if (lightLedsField) {
      const showLeds = selectedProto === "wled_ddp" || selectedProto === "openrgb";
      lightLedsField.hidden = !showLeds;
    }
    if (wledIpInputEl) {
      wledIpInputEl.placeholder = selectedProto === "openrgb" ? "127.0.0.1" : "192.168.1.50";
      if (selectedProto === "openrgb" && !wledIpInputEl.value.trim()) {
        wledIpInputEl.value = "127.0.0.1";
      }
    }
  });

  const submitManualDevice = async () => {
    const addr = wledIpInputEl?.value?.trim() || "";
    if (!addr) {
      showManualFeedback("Vui lòng nhập địa chỉ IP hoặc Host của thiết bị (ví dụ: 192.168.1.50)", true);
      wledIpInputEl?.focus();
      return;
    }
    const port = parseInt(lightPortInput?.value || "4048", 10) || 4048;
    const ledCount = parseInt(lightLedsInput?.value || "60", 10) || 60;
    const customName = lightNameInput?.value?.trim() || "";
    if (addDeviceBtn) addDeviceBtn.disabled = true;
    try {
      const r = await fetch("/api/lights/devices/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          protocol: selectedProto,
          address: addr,
          port,
          led_count: ledCount,
          name: customName,
          enabled: true,
        }),
      });
      const data = await r.json().catch(() => null);
      if (!r.ok) {
        showManualFeedback(data?.detail || "Không thể kết nối thiết bị", true);
        return;
      }
      renderLightsStatus(data, true);
      if (lightNameInput) lightNameInput.value = "";
      showManualFeedback(`Đã thêm và kích hoạt thiết bị tại ${addr}:${port}`);
    } catch (_) {
      showManualFeedback("Lỗi kết nối máy chủ khi thêm thiết bị", true);
    } finally {
      if (addDeviceBtn) addDeviceBtn.disabled = false;
    }
  };

  addDeviceBtn?.addEventListener("click", submitManualDevice);
  wledIpInputEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitManualDevice();
    }
  });
  lightNameInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitManualDevice();
    }
  });

  document.querySelectorAll(".color-pill-btn[data-color]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const parts = (btn.dataset.color || "").split(",").map((n) => parseInt(n.trim(), 10));
      if (parts.length === 3 && parts.every((n) => !Number.isNaN(n))) {
        fetch("/api/lights/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ r: parts[0], g: parts[1], b: parts[2] }),
        }).catch(() => {});
      }
    });
  });

  // Tab switching
  tabSat?.addEventListener("click", () => {
    tabSat.classList.add("is-active");
    tabLights?.classList.remove("is-active");
    paneSat.hidden = false;
    paneLights.hidden = true;
  });

  tabLights?.addEventListener("click", () => {
    tabLights.classList.add("is-active");
    tabSat?.classList.remove("is-active");
    paneLights.hidden = false;
    paneSat.hidden = true;
    if (!didInitialLanScan) {
      didInitialLanScan = true;
      runLightsScan();
    }
  });

  const loadSyncData = async () => {
    try {
      const [roomRes, lightsRes] = await Promise.all([
        fetch("/api/sync/room-info").then((r) => (r.ok ? r.json() : null)),
        fetch("/api/lights/status").then((r) => (r.ok ? r.json() : null)),
      ]);

      if (roomRes) {
        const satUrlEl = document.getElementById("sync-satellite-url");
        const satUrlInput = document.getElementById("sync-satellite-url-input");
        const qrImgEl = document.getElementById("sync-qr-img");
        const statusEl = document.getElementById("sync-sat-connected-status");

        if (satUrlEl) satUrlEl.textContent = roomRes.satellite_url;
        if (satUrlInput) satUrlInput.value = roomRes.satellite_url;
        if (qrImgEl) {
          const qrSrc =
            roomRes.qr_code || roomRes.qr_url || `/api/qr?data=${encodeURIComponent(roomRes.satellite_url || "")}`;
          qrImgEl.src = qrSrc;
        }
        if (statusEl) {
          const sCount = roomRes.satellites_count ?? 0;
          const aCount = roomRes.audio_satellites_count ?? 0;
          statusEl.textContent =
            sCount > 0
              ? `Thiết bị vệ tinh kết nối: ${sCount}${aCount > 0 ? ` (${aCount} bật loa)` : ""}`
              : "Chưa có thiết bị vệ tinh kết nối";
        }
      }

      if (lightsRes) {
        renderLightsStatus(lightsRes, false);
      }
    } catch (e) {
      console.warn("Failed to load sync data:", e);
    }
  };

  let syncPollTimer = null;
  const startModalPolling = () => {
    if (!syncPollTimer) {
      syncPollTimer = setInterval(loadSyncData, 1500);
    }
  };
  const stopModalPolling = () => {
    if (syncPollTimer) {
      clearInterval(syncPollTimer);
      syncPollTimer = null;
    }
  };

  openBtn.addEventListener("click", () => {
    loadSyncData();
    modal.showModal();
    startModalPolling();
  });

  closeBtn?.addEventListener("click", () => {
    stopModalPolling();
    modal.close();
  });

  modal.addEventListener("close", () => {
    stopModalPolling();
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      stopModalPolling();
      modal.close();
    }
  });

  const copyBtn = document.getElementById("btn-copy-sat-url");
  copyBtn?.addEventListener("click", async () => {
    const satUrlInput = document.getElementById("sync-satellite-url-input");
    const satUrlEl = document.getElementById("sync-satellite-url");
    const satUrl = (satUrlInput?.value || satUrlEl?.textContent || "").trim();
    if (satUrl && !satUrl.startsWith("Đang")) {
      try {
        await navigator.clipboard.writeText(satUrl);
        const label = copyBtn.querySelector("span");
        if (label) {
          const originalText = label.textContent;
          label.textContent = "Đã chép!";
          setTimeout(() => (label.textContent = originalText), 1800);
        }
      } catch (err) {
        if (satUrlInput) {
          satUrlInput.select();
          document.execCommand("copy");
        }
      }
    }
  });

  const testOpenBtn = document.getElementById("btn-open-sat-test");
  testOpenBtn?.addEventListener("click", () => {
    const satUrlInput = document.getElementById("sync-satellite-url-input");
    const satUrlEl = document.getElementById("sync-satellite-url");
    const satUrl = (satUrlInput?.value || satUrlEl?.textContent || "").trim();
    if (satUrl && !satUrl.startsWith("Đang")) {
      window.open(satUrl, "_blank");
    }
  });
}

function initClusterModalControls() {
  const modal = document.getElementById("modalClusterLink");
  const openBtn = document.getElementById("btn-nav-cluster");
  const closeBtn = document.getElementById("btnCloseClusterLink");
  if (!modal || !openBtn) return;

  const masterToggle = document.getElementById("btn-cluster-master-toggle");
  const statusPill = document.getElementById("cluster-modal-status-pill");
  const modePartyBtn = document.getElementById("btn-cluster-mode-party");
  const modeStereoBtn = document.getElementById("btn-cluster-mode-stereo");
  const masterVolSlider = document.getElementById("s-cluster-master-vol");
  const masterVolVal = document.getElementById("v-cluster-master-vol");
  const alignSlider = document.getElementById("s-cluster-align-ms");
  const alignVal = document.getElementById("v-cluster-align-ms");
  const deviceNameInput = document.getElementById("input-cluster-device-name");
  const saveNameBtn = document.getElementById("btn-save-cluster-name");
  const nodesListEl = document.getElementById("cluster-nodes-list");
  const nodesCountBadge = document.getElementById("cluster-nodes-count-badge");
  const lanPeersListEl = document.getElementById("cluster-lan-peers-list");
  const peerIpInput = document.getElementById("input-cluster-peer-ip");
  const addPeerBtn = document.getElementById("btn-add-cluster-peer");
  const peerFeedbackEl = document.getElementById("cluster-peer-feedback");
  const remoteBridgeBar = document.getElementById("cluster-remote-bridge-bar");
  const remoteBridgeText = document.getElementById("cluster-remote-bridge-text");
  const disconnectBridgeBtn = document.getElementById("btn-disconnect-remote-bridge");

  if (deviceNameInput) {
    deviceNameInput.value = stageSync.deviceName || "";
  }

  const showPeerFeedback = (msg, isErr = false) => {
    if (!peerFeedbackEl) return;
    peerFeedbackEl.textContent = msg;
    peerFeedbackEl.classList.toggle("is-error", isErr);
    peerFeedbackEl.hidden = !msg;
    if (msg) {
      clearTimeout(showPeerFeedback._t);
      showPeerFeedback._t = setTimeout(() => {
        peerFeedbackEl.hidden = true;
      }, 4000);
    }
  };

  const deviceTypeSvg = (dtype) => {
    if (dtype === "mobile") {
      return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2" width="12" height="20" rx="2.5"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`;
    }
    if (dtype === "tablet") {
      return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="16" height="20" rx="2.5"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`;
    }
    return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;
  };

  const renderClusterModal = (lanPeers = null) => {
    const enabled = stageSync.clusterEnabled;
    const mode = stageSync.clusterMode || "party";
    const nodes = stageSync.clusterNodes || [];
    const activeNodes = nodes.filter((n) => n.in_cluster).length;

    if (masterToggle) {
      masterToggle.classList.toggle("is-active", enabled);
      masterToggle.setAttribute("aria-pressed", String(enabled));
    }
    if (statusPill) {
      statusPill.textContent = enabled
        ? `Đang hợp nhất · ${activeNodes} loa`
        : "Độc lập từng máy";
      statusPill.classList.toggle("is-on", enabled);
    }
    if (modePartyBtn) {
      modePartyBtn.classList.toggle("is-active", mode === "party");
      modePartyBtn.setAttribute("aria-pressed", String(mode === "party"));
    }
    if (modeStereoBtn) {
      modeStereoBtn.classList.toggle("is-active", mode === "stereo_pair");
      modeStereoBtn.setAttribute("aria-pressed", String(mode === "stereo_pair"));
    }
    if (masterVolSlider && document.activeElement !== masterVolSlider) {
      masterVolSlider.value = String(stageSync.clusterMasterVolume);
      const pct = Math.max(0, Math.min(100, (stageSync.clusterMasterVolume / 1.5) * 100));
      masterVolSlider.style.setProperty("--v", `${pct.toFixed(1)}%`);
    }
    if (masterVolVal) {
      masterVolVal.textContent = `${Math.round(stageSync.clusterMasterVolume * 100)}%`;
    }
    if (alignSlider && document.activeElement !== alignSlider) {
      alignSlider.value = String(stageSync.hostAlignMs);
      const pct = Math.max(0, Math.min(100, (stageSync.hostAlignMs / 150) * 100));
      alignSlider.style.setProperty("--v", `${pct.toFixed(1)}%`);
    }
    if (alignVal) {
      alignVal.textContent = `${stageSync.hostAlignMs}ms`;
    }
    if (nodesCountBadge) {
      nodesCountBadge.textContent = `${activeNodes}/${nodes.length} trong cụm`;
      nodesCountBadge.classList.toggle("is-on", activeNodes > 0);
    }
    if (remoteBridgeBar) {
      if (stageSync.remoteServerHttpUrl) {
        remoteBridgeBar.hidden = false;
        if (remoteBridgeText) {
          remoteBridgeText.textContent = `Đang nối trực tiếp tới Cụm Loa tại ${stageSync.remoteServerHttpUrl}`;
        }
      } else {
        remoteBridgeBar.hidden = true;
      }
    }

    if (nodesListEl) {
      if (nodes.length === 0) {
        nodesListEl.innerHTML = `
          <div class="lights-empty-state">
            <div class="lights-empty-text">
              <strong>Đang khởi tạo danh sách trạm phát...</strong>
              <span>Mở thêm tab hoặc truy cập địa chỉ IP máy chính từ thiết bị khác để liên kết Cụm Loa.</span>
            </div>
          </div>
        `;
      } else {
        nodesListEl.innerHTML = nodes
          .map((n) => {
            const isMe = n.client_id === stageSync.clientId;
            const isMaster = Boolean(n.is_master);
            const inCluster = Boolean(n.in_cluster);
            const ch = n.channel_mode || "stereo";
            const volPct = Math.round((n.volume_trim ?? 1.0) * 100);
            const rttStr = n.rtt_ms > 0 ? `${Math.round(n.rtt_ms)}ms` : "LAN";
            const roleBadge = isMaster
              ? "CHỦ TỌA · MASTER"
              : inCluster
                ? "THÀNH VIÊN CỤM"
                : "ĐỘC LẬP";

            return `
              <div class="cluster-node-card ${inCluster ? "is-in-cluster" : ""} ${isMaster ? "is-master" : ""}" data-client-id="${escHtml(n.client_id)}">
                <div class="cluster-node-top">
                  <div class="light-device-icon" aria-hidden="true">${deviceTypeSvg(n.device_type)}</div>
                  <div class="cluster-node-meta">
                    <div class="cluster-node-title-row">
                      <span class="light-status-dot is-online"></span>
                      <span class="cluster-node-name">${escHtml(n.device_name)}${isMe ? ' <em class="cluster-me-tag">(Máy này)</em>' : ""}</span>
                    </div>
                    <div class="cluster-node-sub-row">
                      <span class="light-device-badge mono ${isMaster ? "is-master-badge" : ""}">${roleBadge}</span>
                      <span class="cluster-node-ping mono">Ping ${escHtml(rttStr)}</span>
                    </div>
                  </div>
                  <div class="cluster-node-top-actions">
                    ${
                      inCluster && !isMaster
                        ? `<button type="button" class="cluster-mini-btn btn-node-claim-master" data-client-id="${escHtml(n.client_id)}" title="Chuyển quyền Chủ tọa phát nhạc cho thiết bị này">Chủ tọa</button>`
                        : ""
                    }
                    <button type="button" class="tunnel-toggle-switch btn-node-cluster-toggle ${inCluster ? "is-active" : ""}" data-client-id="${escHtml(n.client_id)}" aria-pressed="${inCluster ? "true" : "false"}" title="${inCluster ? "Rời khỏi cụm loa" : "Đưa thiết bị này vào cụm loa"}">
                      <span class="switch-handle"></span>
                    </button>
                  </div>
                </div>
                <div class="cluster-node-controls">
                  <div class="cluster-channel-group" role="group" aria-label="Kênh âm thanh">
                    <button type="button" class="cluster-ch-btn ${ch === "left" ? "is-active" : ""}" data-client-id="${escHtml(n.client_id)}" data-ch="left" title="Chỉ phát kênh Loa Trái (Left)">Trái (L)</button>
                    <button type="button" class="cluster-ch-btn ${ch === "stereo" ? "is-active" : ""}" data-client-id="${escHtml(n.client_id)}" data-ch="stereo" title="Phát đầy đủ 2 kênh Stereo (L+R)">Stereo</button>
                    <button type="button" class="cluster-ch-btn ${ch === "right" ? "is-active" : ""}" data-client-id="${escHtml(n.client_id)}" data-ch="right" title="Chỉ phát kênh Loa Phải (Right)">Phải (R)</button>
                  </div>
                  <div class="cluster-node-vol-wrap">
                    <input type="range" class="cluster-node-vol-slider" data-client-id="${escHtml(n.client_id)}" min="0" max="1.5" step="0.02" value="${n.volume_trim ?? 1.0}" style="--v: ${Math.min(100, ((n.volume_trim ?? 1.0) / 1.5) * 100).toFixed(1)}%" aria-label="Âm lượng riêng của loa" />
                    <span class="cluster-node-vol-num mono">${volPct}%</span>
                  </div>
                </div>
              </div>
            `;
          })
          .join("");
      }
    }

    if (lanPeersListEl && Array.isArray(lanPeers)) {
      if (lanPeers.length === 0) {
        lanPeersListEl.innerHTML = `
          <div class="cluster-lan-empty">
            Chưa phát hiện máy chủ MashLoop độc lập nào khác trong mạng LAN (Tự động tìm qua UDP cổng 8766 hoặc nhập IP bên dưới).
          </div>
        `;
      } else {
        lanPeersListEl.innerHTML = lanPeers
          .map((p) => {
            const isConnectedBridge = stageSync.remoteServerHttpUrl === p.url;
            return `
              <div class="cluster-peer-row" data-ws-url="${escHtml(p.ws_url)}" data-http-url="${escHtml(p.url)}">
                <div class="cluster-peer-info">
                  <strong>${escHtml(p.name)}</strong>
                  <span class="mono">${escHtml(p.ip)}:${escHtml(p.port)} · ${p.cluster_enabled ? "Đang bật Cụm Loa" : "Độc lập"}${p.active_title ? ` · ${escHtml(p.active_title)}` : ""}</span>
                </div>
                <button type="button" class="btn-secondary cluster-peer-join-btn ${isConnectedBridge ? "is-active" : ""}" data-http-url="${escHtml(p.url)}">
                  ${isConnectedBridge ? "Đang liên kết" : "Nối vào Cụm này"}
                </button>
              </div>
            `;
          })
          .join("");
      }
    }
  };

  const refreshClusterFromServer = async () => {
    try {
      const r = await fetch("/api/cluster/status");
      if (r.ok) {
        const data = await r.json();
        stageSync._applyClusterState(data);
        renderClusterModal(data.lan_peers || []);
      }
    } catch (_) {
      renderClusterModal();
    }
  };

  stageSync.onClusterChange = () => {
    if (modal.open) {
      renderClusterModal();
    }
  };

  masterToggle?.addEventListener("click", () => {
    stageSync._unlockSatAudio(true);
    stageSync.toggleCluster({ enabled: !stageSync.clusterEnabled });
  });

  modePartyBtn?.addEventListener("click", () => {
    stageSync._unlockSatAudio(true);
    if (!stageSync.clusterEnabled) {
      stageSync.toggleCluster({ enabled: true, mode: "party" });
    } else {
      stageSync.updateClusterNodeConfig({ mode: "party" });
    }
  });

  modeStereoBtn?.addEventListener("click", () => {
    stageSync._unlockSatAudio(true);
    if (!stageSync.clusterEnabled) {
      stageSync.toggleCluster({ enabled: true, mode: "stereo_pair" });
    } else {
      stageSync.updateClusterNodeConfig({ mode: "stereo_pair" });
    }
  });

  masterVolSlider?.addEventListener("input", () => {
    const v = parseFloat(masterVolSlider.value) || 1.0;
    const pct = Math.max(0, Math.min(100, (v / 1.5) * 100));
    masterVolSlider.style.setProperty("--v", `${pct.toFixed(1)}%`);
    if (masterVolVal) masterVolVal.textContent = `${Math.round(v * 100)}%`;
    stageSync.clusterMasterVolume = v;
    stageSync._syncSatEffectiveGain();
    stageSync.updateClusterNodeConfig({ master_volume: v });
  });

  alignSlider?.addEventListener("input", () => {
    const ms = parseInt(alignSlider.value, 10) || 0;
    const pct = Math.max(0, Math.min(100, (ms / 150) * 100));
    alignSlider.style.setProperty("--v", `${pct.toFixed(1)}%`);
    if (alignVal) alignVal.textContent = `${ms}ms`;
    stageSync.hostAlignMs = ms;
    stageSync._syncHostSpeakerDelay();
    stageSync.updateClusterNodeConfig({ host_align_ms: ms });
  });

  const saveDeviceName = () => {
    const name = deviceNameInput?.value?.trim();
    if (!name) return;
    stageSync.updateClusterNodeConfig({
      target_client_id: stageSync.clientId,
      device_name: name,
    });
  };

  saveNameBtn?.addEventListener("click", saveDeviceName);
  deviceNameInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveDeviceName();
    }
  });

  nodesListEl?.addEventListener("click", (e) => {
    const chBtn = e.target.closest(".cluster-ch-btn");
    if (chBtn) {
      const cid = chBtn.dataset.clientId;
      const ch = chBtn.dataset.ch;
      if (cid && ch) {
        stageSync.updateClusterNodeConfig({
          target_client_id: cid,
          channel_mode: ch,
        });
      }
      return;
    }

    const toggleNodeBtn = e.target.closest(".btn-node-cluster-toggle");
    if (toggleNodeBtn) {
      const cid = toggleNodeBtn.dataset.clientId;
      const nextIn = toggleNodeBtn.getAttribute("aria-pressed") !== "true";
      if (cid) {
        if (nextIn && !stageSync.clusterEnabled) {
          stageSync.toggleCluster({ enabled: true });
        } else {
          stageSync.updateClusterNodeConfig({
            target_client_id: cid,
            in_cluster: nextIn,
          });
        }
      }
      return;
    }

    const claimBtn = e.target.closest(".btn-node-claim-master");
    if (claimBtn) {
      const cid = claimBtn.dataset.clientId;
      if (cid) {
        stageSync.updateClusterNodeConfig({
          target_client_id: cid,
          claim_master: true,
        });
      }
    }
  });

  nodesListEl?.addEventListener("input", (e) => {
    const slider = e.target.closest(".cluster-node-vol-slider");
    if (!slider) return;
    const cid = slider.dataset.clientId;
    const v = parseFloat(slider.value) || 0;
    const pct = Math.max(0, Math.min(100, (v / 1.5) * 100));
    slider.style.setProperty("--v", `${pct.toFixed(1)}%`);
    const numEl = slider.parentElement?.querySelector(".cluster-node-vol-num");
    if (numEl) numEl.textContent = `${Math.round(v * 100)}%`;
    if (cid) {
      stageSync.updateClusterNodeConfig({
        target_client_id: cid,
        volume_trim: v,
      });
    }
  });

  lanPeersListEl?.addEventListener("click", (e) => {
    const joinBtn = e.target.closest(".cluster-peer-join-btn");
    if (!joinBtn) return;
    const httpUrl = joinBtn.dataset.httpUrl;
    if (!httpUrl) return;
    stageSync._unlockSatAudio(true);
    stageSync.connectToRemoteClusterHost(httpUrl);
    renderClusterModal();
  });

  disconnectBridgeBtn?.addEventListener("click", () => {
    stageSync.disconnectRemoteClusterHost();
    refreshClusterFromServer();
  });

  const submitManualPeer = async () => {
    const raw = peerIpInput?.value?.trim() || "";
    if (!raw) {
      showPeerFeedback("Vui lòng nhập IP:Port của máy chủ MashLoop khác trong mạng LAN (ví dụ: 192.168.1.25:8765)", true);
      peerIpInput?.focus();
      return;
    }
    try {
      const r = await fetch("/api/cluster/peers/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: raw }),
      });
      const data = await r.json().catch(() => null);
      if (!r.ok || !data?.peer) {
        showPeerFeedback(data?.detail || "Địa chỉ máy chủ không hợp lệ", true);
        return;
      }
      if (peerIpInput) peerIpInput.value = "";
      stageSync._unlockSatAudio(true);
      stageSync.connectToRemoteClusterHost(data.peer.url);
      renderClusterModal(data.lan_peers || []);
      showPeerFeedback(`Đã kết nối trực tiếp vào Cụm Loa tại ${data.peer.url}`);
    } catch (_) {
      showPeerFeedback("Không thể kết nối tới máy chủ", true);
    }
  };

  addPeerBtn?.addEventListener("click", submitManualPeer);
  peerIpInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitManualPeer();
    }
  });

  let clusterPollTimer = null;
  const startClusterPolling = () => {
    if (!clusterPollTimer) {
      clusterPollTimer = setInterval(refreshClusterFromServer, 2000);
    }
  };
  const stopClusterPolling = () => {
    if (clusterPollTimer) {
      clearInterval(clusterPollTimer);
      clusterPollTimer = null;
    }
  };

  openBtn.addEventListener("click", () => {
    if (deviceNameInput && !deviceNameInput.value) {
      deviceNameInput.value = stageSync.deviceName || "";
    }
    refreshClusterFromServer();
    modal.showModal();
    startClusterPolling();
  });

  closeBtn?.addEventListener("click", () => {
    stopClusterPolling();
    modal.close();
  });

  modal.addEventListener("close", stopClusterPolling);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      stopClusterPolling();
      modal.close();
    }
  });
}
