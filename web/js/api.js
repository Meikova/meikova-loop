import { Track } from "./graph.js?v=174";

// The library this page works on. Hosted, the server opens a fresh one for
// every visit (nothing is kept in the browser, so a reload starts empty); in
// the personal app the session is simply "local".
export const session = { id: null, multiuser: false, limits: {}, key: null };
export let userToken = (typeof localStorage !== "undefined" ? localStorage.getItem("meikova:loop:token") : null) || null;
export let currentUser = null;

export function setUserToken(token) {
  userToken = token;
  if (typeof localStorage !== "undefined") {
    if (token) localStorage.setItem("meikova:loop:token", token);
    else localStorage.removeItem("meikova:loop:token");
  }
}

export function setCurrentUser(user) {
  currentUser = user;
}

export function updateSession(s) {
  if (!s) return;
  if (s.user) currentUser = s.user;
  Object.assign(session, {
    id: s.sid || s.id || session.id,
    multiuser: s.multiuser ?? session.multiuser,
    limits: s.limits || session.limits || {},
    key: s.k ? Uint8Array.from(atob(s.k), (c) => c.charCodeAt(0)) : (s.key || session.key),
  });
}

export async function resetSession() {
  session.id = null;
  session.key = null;
  opening = null;
  return open();
}

let opening = null;
// Called after the server lost the session (it restarted): put the songs back.
export const hooks = { restore: async () => {} };

async function open() {
  if (!opening) {
    const headers = {};
    if (userToken) headers["Authorization"] = `Bearer ${userToken}`;
    opening = fetch("/api/session", { method: "POST", headers })
      .then(async (r) => {
        if (!r.ok) await fail(r);
        return r.json();
      })
      .then((s) => {
        if (s.user) currentUser = s.user;
        return Object.assign(session, {
          id: s.sid,
          multiuser: s.multiuser,
          limits: s.limits || {},
          key: s.k ? Uint8Array.from(atob(s.k), (c) => c.charCodeAt(0)) : null,
        });
      })
      .finally(() => (opening = null));
  }
  return opening;
}

// Hosted, audio arrives scrambled with this session's key (server.keystream):
// the same 4 KiB block, SHA-256 of key + track id + counter, XORed over it.
async function keystream(tid) {
  const t = new TextEncoder().encode(tid);
  const out = new Uint8Array(4096);
  for (let i = 0; i < 128; i++) {
    const msg = new Uint8Array(session.key.length + t.length + 4);
    msg.set(session.key, 0);
    msg.set(t, session.key.length);
    new DataView(msg.buffer).setUint32(session.key.length + t.length, i, false);
    out.set(new Uint8Array(await crypto.subtle.digest("SHA-256", msg)), i * 32);
  }
  return out;
}

async function unscramble(buf, tid, byteOffset = 0) {
  const ks = new Uint32Array((await keystream(tid)).buffer);
  const ksb = new Uint8Array(ks.buffer);
  const u8 = new Uint8Array(buf);
  if ((byteOffset & 3) === 0 && (u8.byteOffset & 3) === 0) {
    const ksOffsetWords = (byteOffset >> 2) & 1023;
    const words = Math.floor(buf.byteLength / 4);
    const data32 = new Uint32Array(buf, 0, words);
    for (let i = 0; i < words; i++) data32[i] ^= ks[(ksOffsetWords + i) & 1023];
    const tailBytes = buf.byteLength - words * 4;
    const tailOffset = byteOffset + words * 4;
    for (let i = 0; i < tailBytes; i++) u8[words * 4 + i] ^= ksb[(tailOffset + i) & 4095];
  } else {
    for (let i = 0; i < u8.length; i++) u8[i] ^= ksb[(byteOffset + i) & 4095];
  }
  return buf;
}

export const ready = () => (session.id ? Promise.resolve(session) : open());

async function sound(id, kind, kid, retry) {
  await ready();
  const headers = { "X-Session": session.id };
  if (userToken) headers["Authorization"] = `Bearer ${userToken}`;
  const r = await fetch(`/api/tracks/${id}/${kind}`, { headers });
  if (r.status === 410 && retry) {
    await resetSession();
    await hooks.restore();
    return sound(id, kind, kid, false);
  }
  if (!r.ok) await fail(r);
  const ct = r.headers.get("Content-Type") || "";
  if (ct.includes("text/html") || ct.includes("application/json")) {
    throw new Error(`Định dạng âm thanh phản hồi không hợp lệ (${ct})`);
  }
  const buf = await r.arrayBuffer();
  const cr = r.headers.get("Content-Range");
  let byteOffset = 0;
  if (cr) {
    const m = /bytes\s+(\d+)-/i.exec(cr);
    if (m) byteOffset = parseInt(m[1], 10);
  }
  if (r.headers.get("X-Mash") === "1") {
    if (!session.key) {
      await open();
    }
    return unscramble(buf, kid, byteOffset);
  }
  return buf;
}

async function fail(r) {
  let msg = `${r.status}`;
  try {
    msg = (await r.json()).detail || msg;
  } catch (_) {
    /* not json */
  }
  throw new Error(msg);
}

async function json(url, opts = {}, retry = true) {
  await ready();
  const headers = { ...(opts.headers || {}), "X-Session": session.id };
  if (userToken) headers["Authorization"] = `Bearer ${userToken}`;
  const r = await fetch(url, { ...opts, headers });
  if (r.status === 410) {
    session.id = null;
    if (retry) {
      await open();
      await hooks.restore();
      return json(url, opts, false);
    }
  }
  if (!r.ok) await fail(r);
  return r.json();
}

const send = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  tracks: () => json("/api/tracks"),
  search: (q) => json(`/api/search?q=${encodeURIComponent(q)}`),
  add: (text) => json("/api/tracks", send("POST", { text })),
  restore: (ids) => json("/api/tracks", send("POST", { ids }), false),
  patch: (id, data) => json(`/api/tracks/${id}`, send("PATCH", data)),
  remove: (id) => json(`/api/tracks/${id}`, { method: "DELETE" }),
  batch: (ids, action) => json("/api/tracks/batch", send("POST", { ids, action })),
  reanalyze: (id) => json(`/api/tracks/${id}/reanalyze`, { method: "POST" }),
  relink: () => json("/api/relink", { method: "POST" }),
  analysis: (id) => json(`/api/tracks/${id}/analysis`),
  transitions: (id) => json(`/api/tracks/${id}/transitions`),
  lyrics: (id, refresh = false) => json(`/api/tracks/${id}/lyrics${refresh ? "?refresh=true" : ""}`),
  saveLyrics: (id, lrc) => json(`/api/tracks/${id}/lyrics`, send("POST", { lrc })),
  samples: () => json("/api/samples"),
  ingestLocal: (paths) => json("/api/desktop/ingest_local", send("POST", { paths })),
  cookieStatus: () => json("/api/cookies"),
  uploadCookies: (content) => json("/api/cookies", send("POST", { content })),
  deleteCookies: () => json("/api/cookies", { method: "DELETE" }),
  settings: () => json("/api/settings"),
  saveSettings: (data) => json("/api/settings", send("POST", data)),
  playlists: () => json("/api/playlists"),
  savePlaylists: (data) => json("/api/playlists", send("POST", data)),
  storageInfo: () => json("/api/storage/info"),
  storageChange: (path, migrate = true) => json("/api/storage/change", send("POST", { path, migrate })),
  storageReset: () => json("/api/storage/reset", send("POST", {})),
  storageBrowse: () => json("/api/storage/browse", send("POST", {})),
  version: () => json("/api/version"),
  auth: {
    config: () => json("/api/auth/config"),
    register: (username, password, display_name) => json("/api/auth/register", send("POST", { username, password, display_name })),
    login: (username, password) => json("/api/auth/login", send("POST", { username, password })),
    google: (credential) => json("/api/auth/google", send("POST", { credential })),
    me: () => json("/api/auth/me"),
    logout: () => json("/api/auth/logout", send("POST", {})),
    syncGet: () => json("/api/user/sync"),
    syncPost: (data) => json("/api/user/sync", send("POST", data)),
  },
  async audio(id, retry = true) {
    return sound(id, "audio", id, retry);
  },
  // The vocal stem of a sung song (scrambled with its own key, "<id>:v").
  async vocals(id, retry = true) {
    return sound(id, "vocals", `${id}:v`, retry);
  },
  // The file is the request body; XHR because fetch cannot report upload progress.
  async upload(file, onProgress = () => {}) {
    await ready();
    return new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open("POST", "/api/upload");
      x.setRequestHeader("X-Session", session.id);
      if (userToken) x.setRequestHeader("Authorization", `Bearer ${userToken}`);
      x.setRequestHeader("X-Filename", encodeURIComponent(file.name));
      x.setRequestHeader("Content-Type", "application/octet-stream");
      x.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      x.onload = () => {
        let body = null;
        try {
          body = JSON.parse(x.responseText);
        } catch (_) {
          /* not json */
        }
        if (x.status >= 200 && x.status < 300) resolve(body);
        else reject(new Error(body?.detail || `${x.status}`));
      };
      x.onerror = () => reject(new Error("mất kết nối"));
      x.send(file);
    });
  },
};

export const isMobile = typeof navigator !== "undefined" && /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || "");
// Chunked frame-aligned MP3 decoding + adaptive sample rate (32kHz on Desktop >25m,
// 22.05kHz on Mobile >10m) keeps peak C++ AudioBus & AudioBuffer heap well within
// browser limits, supporting up to 60-minute (3600s) tracks on both Desktop and Mobile Web.
export const MAX_SAFE_DURATION_S = 3600;
const STEM_MAX_DURATION_S = 900; // >15m mixes use DSP vocalFilter instead of a second 65MB+ stem buffer
const MAX_CACHE_BYTES = isMobile ? 380 * 1024 * 1024 : 1150 * 1024 * 1024;
const LAME_DECODE_DELAY_SAMPLES = 1105; // 576 LAME encoder delay + 529 MPEG Layer III decoder delay

const MP3_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320];
const MP3_BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160];
const MP3_SR_V1 = [44100, 48000, 32000];
const MP3_SR_V2 = [22050, 24000, 16000];
const MP3_SR_V25 = [11025, 12000, 8000];

export function parseMp3Frames(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const n = bytes.length;
  let pos = 0;

  // Skip leading ID3v2 tag (including optional 10-byte footer when flag 0x10 is set)
  if (n >= 10 && bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33) {
    const flags = bytes[5];
    const tagSize =
      ((bytes[6] & 0x7f) << 21) |
      ((bytes[7] & 0x7f) << 14) |
      ((bytes[8] & 0x7f) << 7) |
      (bytes[9] & 0x7f);
    pos = Math.min(n, 10 + tagSize + (flags & 0x10 ? 10 : 0));
  }

  const frames = [];
  let sampleRate = 44100;
  let samplesPerFrame = 1152;
  let locked = false;

  while (pos + 4 <= n) {
    if (bytes[pos] !== 0xff || (bytes[pos + 1] & 0xe0) !== 0xe0) {
      locked = false;
      pos++;
      continue;
    }
    const b1 = bytes[pos + 1];
    const b2 = bytes[pos + 2];
    const ver = (b1 >> 3) & 0x03; // 3=MPEG1, 2=MPEG2, 0=MPEG2.5
    const layer = (b1 >> 1) & 0x03; // 1=Layer III
    const brIdx = (b2 >> 4) & 0x0f;
    const srIdx = (b2 >> 2) & 0x03;
    const pad = (b2 >> 1) & 0x01;

    if (ver === 1 || layer !== 1 || brIdx === 0 || brIdx === 15 || srIdx === 3) {
      locked = false;
      pos++;
      continue;
    }

    const sr = ver === 3 ? MP3_SR_V1[srIdx] : ver === 2 ? MP3_SR_V2[srIdx] : MP3_SR_V25[srIdx];
    const br = ver === 3 ? MP3_BITRATES_V1_L3[brIdx] : MP3_BITRATES_V2_L3[brIdx];
    const spf = ver === 3 ? 1152 : 576;
    const coeff = ver === 3 ? 144000 : 72000;
    const frameLen = Math.floor((coeff * br) / sr) + pad;
    if (frameLen < 24 || pos + frameLen > n) {
      break;
    }

    if (!locked) {
      const nextPos = pos + frameLen;
      if (nextPos + 2 <= n) {
        const validNextSync = bytes[nextPos] === 0xff && (bytes[nextPos + 1] & 0xe0) === 0xe0;
        const isId3v1 =
          nextPos + 3 <= n &&
          bytes[nextPos] === 0x54 &&
          bytes[nextPos + 1] === 0x41 &&
          bytes[nextPos + 2] === 0x47;
        if (!validNextSync && !isId3v1) {
          pos++;
          continue;
        }
      }
      locked = true;
    }

    if (frames.length === 0) {
      sampleRate = sr;
      samplesPerFrame = spf;
    }
    frames.push({ pos, len: frameLen });
    pos += frameLen;
  }

  let hasInfoHeader = false;
  if (frames.length > 0) {
    const f0 = frames[0];
    const scanEnd = Math.min(n - 4, f0.pos + Math.min(f0.len, 120));
    for (let i = f0.pos + 4; i <= scanEnd; i++) {
      const c0 = bytes[i];
      const c1 = bytes[i + 1];
      const c2 = bytes[i + 2];
      const c3 = bytes[i + 3];
      if (
        (c0 === 0x58 && c1 === 0x69 && c2 === 0x6e && c3 === 0x67) || // "Xing"
        (c0 === 0x49 && c1 === 0x6e && c2 === 0x66 && c3 === 0x6f) || // "Info"
        (c0 === 0x56 && c1 === 0x42 && c2 === 0x52 && c3 === 0x49) // "VBRI"
      ) {
        hasInfoHeader = true;
        break;
      }
    }
  }

  const audioStartIndex = hasInfoHeader && frames.length > 1 ? 1 : 0;
  return {
    frames,
    sampleRate,
    samplesPerFrame,
    hasInfoHeader,
    audioStartIndex,
  };
}

function _allocateAudioBufferWithFallback(ctx, totalDurationSec, preferredSr, preferredCh) {
  const candidates = [
    { ch: preferredCh, sr: preferredSr },
    { ch: preferredCh, sr: Math.min(preferredSr, 32000) },
    { ch: preferredCh, sr: 22050 },
    { ch: 1, sr: 22050 },
  ];
  let lastErr = null;
  for (const cand of candidates) {
    const length = Math.max(1, Math.round(totalDurationSec * cand.sr));
    try {
      const buf = ctx.createBuffer(cand.ch, length, cand.sr);
      return buf;
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error("Unable to allocate AudioBuffer");
}

export async function decodeTrackAudio(ctx, arrayBuffer, opts = {}) {
  const durationSec = Number(opts.durationSec) || 0;
  const byteLength = arrayBuffer?.byteLength || 0;
  const longThresholdSec = isMobile ? 600 : 900;
  const byteThreshold = isMobile ? 14 * 1024 * 1024 : 20 * 1024 * 1024;
  const mustChunk = Boolean(opts.forceChunked) || durationSec > longThresholdSec || byteLength > byteThreshold;

  if (!mustChunk) {
    try {
      return await ctx.decodeAudioData(arrayBuffer.slice(0));
    } catch (_) {
      // Fall through to chunked / lower-rate decode if monolithic decode fails
    }
  }

  const parsed = parseMp3Frames(new Uint8Array(arrayBuffer));
  const { frames, sampleRate: mp3Sr, samplesPerFrame, hasInfoHeader, audioStartIndex } = parsed;
  const totalAudioFrames = frames.length - audioStartIndex;

  // Non-MP3 container (WAV/FLAC/AAC/OGG) fallback when monolithic decode failed
  if (totalAudioFrames < 32) {
    const fallbackSr = opts.forceSampleRate || (isMobile ? 22050 : 32000);
    if (typeof OfflineAudioContext !== "undefined") {
      const off = new OfflineAudioContext(isMobile ? 1 : 2, 1, fallbackSr);
      return await off.decodeAudioData(arrayBuffer.slice(0));
    }
    return await ctx.decodeAudioData(arrayBuffer.slice(0));
  }

  const totalDurationSec = (totalAudioFrames * samplesPerFrame) / mp3Sr;
  const preferredSr =
    opts.forceSampleRate ||
    (isMobile ? 22050 : durationSec > 1500 || totalDurationSec > 1500 ? 32000 : ctx.sampleRate || mp3Sr || 44100);
  const preferredCh = opts.forceChannels || (isMobile && (durationSec > 1800 || totalDurationSec > 1800) ? 1 : 2);

  const outBuf = _allocateAudioBufferWithFallback(ctx, totalDurationSec, preferredSr, preferredCh);
  const outSr = outBuf.sampleRate;
  const outCh = outBuf.numberOfChannels;
  const maxFramesPerChunk = Math.max(64, Number(opts.maxFramesPerChunk) || 9000); // ~3.9 mins per chunk

  const decodeSlice = async (sliceAb) => {
    if (typeof OfflineAudioContext !== "undefined" && outSr !== ctx.sampleRate) {
      const off = new OfflineAudioContext(outCh, 1, outSr);
      return await off.decodeAudioData(sliceAb);
    }
    return await ctx.decodeAudioData(sliceAb);
  };

  let writePos = 0;
  let chunkIdx = 0;
  for (let startFrame = audioStartIndex; startFrame < frames.length; startFrame += maxFramesPerChunk) {
    const endFrame = Math.min(frames.length, startFrame + maxFramesPerChunk);
    const isFirst = startFrame === audioStartIndex;
    const warmFrames = isFirst ? 0 : Math.min(3, startFrame - audioStartIndex);
    const sliceStartByte = isFirst ? 0 : frames[startFrame - warmFrames].pos;
    const lookaheadIdx = Math.min(frames.length - 1, endFrame);
    const sliceEndByte = frames[lookaheadIdx].pos + frames[lookaheadIdx].len;

    const sliceAb = arrayBuffer.slice(sliceStartByte, sliceEndByte);
    const dec = await decodeSlice(sliceAb);

    const skipSamples = isFirst
      ? hasInfoHeader
        ? 0
        : Math.round((LAME_DECODE_DELAY_SAMPLES * outSr) / mp3Sr)
      : Math.round(((warmFrames * samplesPerFrame + LAME_DECODE_DELAY_SAMPLES) * outSr) / mp3Sr);

    const chunkFrames = endFrame - startFrame;
    const expectedSamples = Math.round((chunkFrames * samplesPerFrame * outSr) / mp3Sr);
    const wantSamples = Math.min(expectedSamples, outBuf.length - writePos);
    const availSamples = Math.max(0, Math.min(wantSamples, dec.length - skipSamples));

    if (availSamples > 0) {
      for (let c = 0; c < outCh; c++) {
        const srcCh = dec.getChannelData(Math.min(c, dec.numberOfChannels - 1));
        const sub = srcCh.subarray(skipSamples, skipSamples + availSamples);
        if (typeof outBuf.copyToChannel === "function") {
          outBuf.copyToChannel(sub, c, writePos);
        } else {
          outBuf.getChannelData(c).set(sub, writePos);
        }
      }
    }

    writePos += wantSamples;
    chunkIdx++;
    if (chunkIdx % 3 === 0 && startFrame + maxFramesPerChunk < frames.length) {
      await new Promise((r) => setTimeout(r, 0));
    }
  }

  return outBuf;
}

// Fetches and decodes tracks, keeping a few decoded buffers in memory
// (a 4-minute song is ~85 MB of float samples).
export class Loader extends EventTarget {
  constructor(engine, keep = isMobile ? 2 : 3) {
    super();
    this.engine = engine;
    // Keep at most 2 decoded songs on mobile RAM (Jetsam safety), up to 3 on Desktop
    const maxKeep = isMobile ? 2 : 3;
    this.keep = Math.max(1, Math.min(maxKeep, keep));
    this.cache = new Map(); // id -> {promise, track, used}
    this.metas = new Map();
    this.protect = () => [];
  }

  isOversized(meta) {
    if (!meta || !meta.duration) return false;
    return meta.duration > MAX_SAFE_DURATION_S;
  }

  canLoadStems(id) {
    const meta = this.metas.get(id);
    if (!meta?.stems || this.isOversized(meta)) return false;
    return (meta.duration || 0) <= STEM_MAX_DURATION_S;
  }

  setMetas(list) {
    this.metas = new Map(list.map((m) => [m.id, m]));
  }

  readyCount() {
    let n = 0;
    for (const m of this.metas.values()) if (m.status === "ready") n++;
    return n;
  }

  has(id) {
    return Boolean(this.cache.get(id)?.track?.buffer);
  }

  get(id) {
    const hit = this.cache.get(id);
    if (hit) {
      if (hit.track && !hit.track.buffer) {
        this.cache.delete(id);
      } else {
        hit.used = performance.now();
        return hit.promise;
      }
    }
    if (!this.loadingIds) this.loadingIds = new Set();
    this.loadingIds.add(id);
    const meta = this.metas.get(id) || { id, title: id };
    if ((meta.duration || 0) > 900) {
      // Proactively free un-protected cached tracks before allocating a long mix buffer
      this._evict(1, id);
    }
    const entry = { track: null, used: performance.now() };
    entry.promise = (async () => {
      if (this.isOversized(meta)) {
        const mins = Math.round(meta.duration / 60);
        const limitMins = Math.round(MAX_SAFE_DURATION_S / 60);
        throw new Error(`Bài quá dài (${mins} phút, giới hạn ${limitMins} phút) không thể nạp vào bộ nhớ trình duyệt`);
      }
      const [analysis, audio, trans] = await Promise.all([api.analysis(id), api.audio(id), api.transitions(id)]);
      const durationSec = meta.duration || analysis?.duration || 0;
      const buffer = await decodeTrackAudio(this.engine.ctx, audio, { durationSec });
      const track = new Track(meta, analysis, buffer);
      track.transitions = trans.items;
      track.onward = trans.onward || null; // each destination's own best ways on
      entry.track = track;
      entry.used = performance.now();
      this._evict(this.keep, id);
      return track;
    })();
    entry.promise.catch(() => this.cache.delete(id));
    entry.promise.finally(() => this.loadingIds?.delete(id));
    this.cache.set(id, entry);
    this._evict(this.keep, id);
    return entry.promise;
  }

  // New pairs were linked in this library: every loaded song re-reads its exits.
  refreshAll() {
    for (const e of this.cache.values()) if (e.track) this.refreshTransitions(e.track);
  }

  async refreshTransitions(track) {
    try {
      const { items, onward } = await api.transitions(track.id);
      track.transitions = items;
      track.onward = onward || null;
      this.dispatchEvent(new CustomEvent("transitions", { detail: track }));
    } catch (_) {
      /* keep the old list */
    }
  }

  // The vocal stem of a loaded song, decoded (null when it has none), kept as
  // long as the song: fetched only for a transition that hands over by layers.
  vocals(id) {
    if (!this.canLoadStems(id)) return Promise.resolve(null);
    const meta = this.metas.get(id);
    const hit = this.cache.get(id);
    if (hit?.vocals) return hit.vocals;
    const p = (async () => {
      const raw = await api.vocals(id);
      return decodeTrackAudio(this.engine.ctx, raw, { durationSec: meta?.duration || 0 });
    })();
    p.catch(() => {
      const e = this.cache.get(id);
      if (e && e.vocals === p) e.vocals = null;
    });
    if (hit) hit.vocals = p;
    return p;
  }

  drop(id) {
    const entry = this.cache.get(id);
    if (entry) entry.vocals = null;
    this.cache.delete(id);
  }

  _bufferBytes(entry) {
    const buf = entry?.track?.buffer;
    if (!buf) return 0;
    return (buf.length || 0) * (buf.numberOfChannels || 2) * 4;
  }

  _totalCachedBytes() {
    let sum = 0;
    for (const e of this.cache.values()) sum += this._bufferBytes(e);
    return sum;
  }

  _evict(maxKeep = this.keep, pinnedId = null) {
    const keep = new Set(this.protect());
    if (pinnedId) keep.add(pinnedId);
    if (this.loadingIds) {
      for (const lid of this.loadingIds) keep.add(lid);
    }
    const order = [...this.cache.entries()]
      .filter(([id, e]) => !keep.has(id) && e.track)
      .sort((a, b) => a[1].used - b[1].used);
    while ((this.cache.size > maxKeep || this._totalCachedBytes() > MAX_CACHE_BYTES) && order.length) {
      const [dropId, entry] = order.shift();
      if (entry) entry.vocals = null;
      this.cache.delete(dropId);
    }
  }
}
