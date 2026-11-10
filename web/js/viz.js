// The ∞ stage. Every song is one loop: a ring of beats coloured by timbre, with
// its jump chords inside and its exits to other songs as dots outside. When the
// player plans an exit, the loop turns until that exit faces the next song,
// whose loop grows in and touches it there: the two loops make the ∞, and the
// crossing is where the mix happens. After the hand-over the new loop glides
// to the centre and the old one shrinks away.
//
// Each loop is painted in its song's colour (theme.js); the room takes the
// colour of the playing song, and around its loop a halo of the live spectrum
// breathes with the music.

import * as theme from "./theme.js?v=174";
import { stageSync } from "./stage_sync.js?v=174";

const TAU = Math.PI * 2;
const HALO_BANDS = 48;
const HALO_N = 180;
const DOCK_LEAD_S = 14; // dock the confirmed next loop cleanly into infinity only shortly before hand-over
const HALO_COS = new Float32Array(HALO_N + 1);
const HALO_SIN = new Float32Array(HALO_N + 1);
for (let k = 0; k <= HALO_N; k++) {
  const theta = Math.PI + (k / HALO_N) * TAU;
  HALO_COS[k] = Math.cos(theta);
  HALO_SIN[k] = Math.sin(theta);
}
const reduceMQ = typeof matchMedia !== "undefined" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
export const KIND_VI = {
  cut: "Nối thẳng", drop: "Drop vào đoạn mới", blend: "Blend khớp nhịp", fade: "Crossfade",
  echo: "Echo vang", wash: "Reverb wash", riser: "Build-up", flanger: "Flanger", gap: "Ngắt lặng 1 beat",
  brake: "Phanh đĩa", roll: "Cuộn nhịp", spin: "Spinback", gate: "Gate",
  tape: "Tape stop", sweeper: "Filter sweep",
};

// What the bridge does to the tempo and the key, in words: "hai bài cùng
// kéo tempo 6%", "dịch tông +1", "nhịp đôi".
export function bendNote(tr) {
  const notes = [];
  const pre = tr.pre || 1;
  if (Math.abs(pre - 1) > 0.004) notes.push(`hai bài cùng kéo tempo ${Math.round(Math.abs(pre - 1) * 100)}%, giữ tông`);
  else if (tr.rate && Math.abs(tr.rate - 1) > 0.015 && (tr.type === "cut" || tr.type === "drop" || tr.type === "blend")) {
    notes.push(`bài sau ${tr.rate > 1 ? "nhanh" : "chậm"} ${Math.round(Math.abs(tr.rate - 1) * 100)}% lúc vào${tr.keylock ? ", giữ tông" : ""}`);
  }
  if (tr.semis) notes.push(`bài sau dịch tông ${tr.semis > 0 ? "+" : "−"}${Math.abs(tr.semis)}`);
  if (tr.loop) notes.push(`lặp ${Math.round(tr.loop / 4) || 1} ô nhịp của bài trước`);
  if (tr.m === 2) notes.push("bài sau nhịp đôi");
  if (tr.m === 0.5) notes.push("bài sau nửa nhịp");
  if (tr.type === "fade" && tr.seconds) notes.push(`chuyển dần trong ${Math.round(tr.seconds)} giây`);
  if ((tr.mood ?? 0) > 0.9) notes.push("khác mood");
  return notes.join(" · ");
}
const SECOND_RATIO = 0.7; // the next song's loop, relative to the playing one

export function fmt(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function short(t, n = 28) {
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

// YouTube titles carry upload noise ("(Official Audio)", "| Official MV").
// Split them into the song title and artist intelligently, handling both
// "Artist - Title" (Western) and "Title - Artist" (Vietnamese / Remix / Asian) conventions.
const NOISE = /\s*[([]([^)\]]*\b(official\s*(music\s*)?(video|audio|mv|m\/v)?|video\s*clip|lyric(s)?(\s*video)?|audio\s*lyrics?|visuali[sz]er|remaster(ed)?|hd|4k|explicit|mv|m\/v)\b[^)\]]*)[)\]]\s*/gi;
const TRAILING_NOISE = /\s*\|\s*(official|bản ghi|live|mv|audio|video|sáng tác|written by).*$/i;
const TITLE_HINTS = /\b(remix|mashup|lofi|slowed|reverb|acoustic|medley|ost|nhạc\s*phim|hot\s*tik\s*tok|trend\s*tik\s*tok|bản\s*chuẩn|peak\s*tik\s*tok|vinahouse|club\s*mix|extended|dance\s*version)\b/i;
const VN_SENTENCE_WORDS = /\b(anh|em|tôi|mình|ta|ai|người|yêu|thương|nhớ|quên|đau|đi|về|cho|vì|lòng|đời|sao|không|chẳng|gì|nào|đã|đang|sẽ|có|lại|được|mất|chờ|mong)\b/i;

function cleanArtist(s) {
  if (!s) return "";
  const m = s.split(/[\s]*[♫🎶🎼|][\s]*/);
  let res = (m.length > 1 && m[0].trim().length >= 2) ? m[0].trim() : s;
  res = res.replace(/\s*\/\s*(audio\s*)?lyrics?.*$/i, "").trim();
  res = res.replace(/\s*[([](?!.*?\b(ft|feat)\b)[^)\]]*[)\]]/gi, "").trim();
  return res;
}

function cleanTitle(s) {
  if (!s) return "";
  let res = s.replace(/\s*\|\s*.*$/, "").trim();
  res = res.replace(/^["'“「『]+|["'”」』]+$/g, "").trim();
  return res;
}

export function splitTitle(raw, channel = "") {
  let s = String(raw || "").trim();
  s = s.replace(NOISE, " ").replace(TRAILING_NOISE, "").replace(/\s+/g, " ").trim();

  const chClean = String(channel || "")
    .replace(/\s*-\s*Topic$/i, "")
    .replace(/(official|music|records|vevo|entertainment|channel|media)$/gi, "")
    .replace(/\b(official|music|records|vevo|entertainment|channel|media)\b/gi, "")
    .trim();

  let sep = s.match(/\s[-–—]\s/);
  if (!sep) {
    sep = s.match(/\s[|]\s/);
  }

  if (!sep) {
    let artist = "";
    let title = s;
    const ft = title.match(/\s\(?(ft\.?|feat\.?|featuring)\s[^)]+\)?$/i);
    if (ft) {
      artist = ft[0].trim().replace(/^\(|\)$/g, "");
      title = title.slice(0, ft.index).trim();
    }
    if (!artist && channel) {
      artist = channel.replace(/\s*-\s*Topic$/i, "").replace(/VEVO$/i, "").trim();
    }
    return { title: cleanTitle(title) || s || raw, artist: cleanArtist(artist) };
  }

  const partA = s.slice(0, sep.index).trim();
  const partB = s.slice(sep.index + sep[0].length).trim();

  let scoreA_is_artist = 0;
  let scoreB_is_artist = 0;

  // Channel matching: an artist name usually matches their official YouTube channel
  if (chClean && chClean.length >= 3) {
    const chLower = chClean.toLowerCase();
    if (partA.toLowerCase().includes(chLower)) scoreA_is_artist += 4;
    if (partB.toLowerCase().includes(chLower)) scoreB_is_artist += 4;
  }

  // Song hints (remix, mashup, acoustic, etc.) strongly indicate a Song Title
  if (TITLE_HINTS.test(partA)) scoreA_is_artist -= 10;
  if (TITLE_HINTS.test(partB)) {
    if (!/\b(cover|ca\s*sĩ|singer|prod|beat)\b/i.test(partB) && !/[♫🎶🎼|]/.test(partB)) {
      scoreB_is_artist -= 3;
    }
  }

  // Artist hints (cover, ca sĩ, song ca, composer, etc.)
  if (/\b(cover|ca\s*sĩ|singer|thể\s*hiện|trình\s*bày|song\s*ca|tam\s*ca|composer|sáng\s*tác|written\s*by|prod(\.|\s*by)|beat(\s*by)?)\b/i.test(partA)) scoreA_is_artist += 4;
  if (/\b(cover|ca\s*sĩ|singer|thể\s*hiện|trình\s*bày|song\s*ca|tam\s*ca|composer|sáng\s*tác|written\s*by|prod(\.|\s*by)|beat(\s*by)?)\b/i.test(partB)) scoreB_is_artist += 4;

  // "ft." or "feat." in part B usually means: MainArtist - SongTitle (ft. GuestArtist)
  if (/\b(ft\.?|feat\.?|featuring)\b/i.test(partB)) scoreA_is_artist += 4;
  if (/\b(ft\.?|feat\.?|featuring)\b/i.test(partA)) scoreB_is_artist += 2;

  // Multiple artist separator (comma, x, +, &)
  if (/,/.test(partB) || /\b(x|\&|\+)\b/i.test(partB)) scoreB_is_artist += 3;
  if (/,/.test(partA) || /\b(x|\&|\+)\b/i.test(partA)) scoreA_is_artist += 1;

  // Trailing lyric notes/quotes in part B (very common in VN remix videos)
  if (/[♫🎶🎼]/.test(partB)) scoreB_is_artist += 5;

  // Clean candidate strings before sentence word inspection
  const candArtistA = cleanArtist(partA);
  const candArtistB = cleanArtist(partB);

  // If candidate artist B is a short clean name and part A is a title
  if (candArtistB.length > 0 && candArtistB.length < 35 && candArtistB.split(/\s+/).length <= 4) {
    scoreB_is_artist += 3;
  }

  // Grammatical clause check on clean parts (sentence words in title vs proper nouns in artist)
  if (VN_SENTENCE_WORDS.test(partA) && !VN_SENTENCE_WORDS.test(candArtistB)) {
    scoreA_is_artist -= 3;
    scoreB_is_artist += 3;
  } else if (!VN_SENTENCE_WORDS.test(candArtistA) && VN_SENTENCE_WORDS.test(partB) && !/[♫🎶🎼|]/.test(partB)) {
    scoreA_is_artist += 3;
    scoreB_is_artist -= 3;
  }

  let title, artist;
  if (scoreA_is_artist > scoreB_is_artist) {
    // Format: "Artist - Title" (Western convention or Artist matched on left)
    artist = cleanArtist(partA);
    title = cleanTitle(partB);
  } else {
    // Format: "Title - Artist" (Vietnamese / Asian / Remix convention, or Artist on right)
    title = cleanTitle(partA);
    artist = cleanArtist(partB);
  }

  // Extract ft. in title only if no artist has been found yet
  if (!artist) {
    const ft = title.match(/\s\(?(ft\.?|feat\.?|featuring)\s[^)]+\)?$/i);
    if (ft) {
      artist = ft[0].trim().replace(/^\(|\)$/g, "");
      title = title.slice(0, ft.index).trim();
    }
  }

  if (!artist && channel) {
    artist = channel.replace(/\s*-\s*Topic$/i, "").replace(/VEVO$/i, "").trim();
  }

  return { title: title || s || raw, artist: artist || "" };
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const easeOut = (x) => 1 - Math.pow(1 - x, 3);
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const wrapAngle = (a) => Math.atan2(Math.sin(a), Math.cos(a));

class Ring {
  constructor(track, role) {
    this.track = track;
    this.role = role;
    this.x = null;
    this.y = null;
    this.r = 0;
    this._layoutR = null;
    this.rot = -Math.PI / 2; // song start at twelve o'clock
    // Which way time runs round the loop: +1 clockwise, -1 counter-clockwise.
    // Neighbours in the ∞ turn opposite ways, so the path through the crossing
    // is one stroke of a figure eight.
    this.dir = 1;
    this.alpha = 0;
    this.fill = 1;
    this.target = null;
    this.layer = null;
    this.layerKey = "";
    this.col = null; // eased toward the song's colour (or the accent while it plays)
  }
}

// The section a beat is in, by its role in the song (structure.roles).
const ROLE_VI = { intro: "Intro", verse: "Verse", chorus: "Điệp khúc", breakdown: "Đoạn lắng", drop: "Drop", outro: "Outro" };

export class Viz {
  constructor(canvas, player, { center, tip, onPick, onSeek, onCaption, onCrossClick } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.player = player;
    this.center = center;
    this.tip = tip;
    this.onPick = onPick || (() => {});
    this.onSeek = onSeek || (() => false);
    this.onCaption = onCaption || (() => {});
    this.onCrossClick = onCrossClick || (() => this.player.forceTransition());
    this._captionId = null;
    this.titles = new Map();
    this.rings = new Map();
    this.primaryId = null;
    this.idle = 1;
    this.pulse = 0;
    this.beatPulse = true;
    this.lastBeatKey = "";
    this.lastEventT = 0;
    this.flashes = [];
    this.ripples = [];
    this.heads = { lead: null, ghost: null };
    this.leadId = null;
    this.lastCross = null;
    this.pointer = null;
    this.hover = null;
    this.armed = null; // touch: an exit tapped once, waiting for the confirming tap
    this.fieldAt = 0;
    this.bands = new Float32Array(HALO_BANDS); // the live spectrum, 0..1, smoothed
    this.bass = 0;
    this.accent = null; // the room's colour as the canvas sees it, eased
    this.secondCol = null;
    this.last = performance.now();
    this._smoothAudioT = null;
    this._lastAudioWall = null;
    this._lastAudioVal = null;
    this._twoHoldUntil = 0;
    this._prewarmedIds = new Set();
    this.ro = new ResizeObserver(() => this._resize());
    if (canvas.parentElement) this.ro.observe(canvas.parentElement);
    window.addEventListener("resize", () => this._resize(), { passive: true });
    window.addEventListener("orientationchange", () => setTimeout(() => this._resize(), 80), { passive: true });
    this._resize();
    this._bindPointer();
    stageSync.viz = this;
    const loop = (now) => {
      try {
        this._frame(now);
      } catch (err) {
        console.error("[Viz] Frame error:", err);
      } finally {
        requestAnimationFrame(loop);
      }
    };
    this.started = true;
    requestAnimationFrame(loop);

    // Continuous heartbeat broadcast from host to satellites, even when host tab is in background/minimized
    if (!stageSync.isSatellite && typeof window !== "undefined") {
      setInterval(() => {
        const now = performance.now();
        if (!stageSync.connected) return;
        const hasActiveTrack = Boolean(this.primaryId || this.player?.cur?.track || this.player?._switchingTrack);
        if (!hasActiveTrack) {
          // Do not broadcast idle telemetry from hidden background tabs; throttle idle keepalives to 1Hz on visible tabs
          if (document.hidden) return;
          if (stageSync.lastBroadcast > 0 && now - stageSync.lastBroadcast < 1000) return;
        }
        if (document.hidden || now - stageSync.lastBroadcast > 48) {
          if (document.hidden || now - this.last > 48) {
            const dt = Math.min(0.1, Math.max(0.016, (now - this.last) / 1000));
            this.last = now;
            const view = this.player?.audible();
            this.mixNow = this._mix(view);
            this._beatPulse(view, dt);
            this._spectrum(dt);
            this._update(view, dt);
            const primary = this.primaryId ? this.rings.get(this.primaryId) : null;
            this._roomColor(primary, view, dt);
            this.heads = this._heads(primary, view, view ? view.now : 0);
            this.capPlace = this._captionPlace(primary, view);
            this.captionTrack = this.capPlace.ring?.track || null;
          }
          this._broadcastHostTelemetry();
        }
      }, 33);
    }
  }

  setTitles(map) {
    this.titles = map;
  }

  invalidate() {
    for (const ring of this.rings.values()) {
      ring.layerKey = "";
      ring.col = null;
    }
    if (this.satellitePrimaryRing) {
      this.satellitePrimaryRing.layerKey = "";
      this.satellitePrimaryRing.col = null;
    }
    if (this.satelliteSecondRing) {
      this.satelliteSecondRing.layerKey = "";
      this.satelliteSecondRing.col = null;
    }
  }

  renderSatellite(telemetry = null) {
    if (!stageSync.isSatellite) return;
    const now = performance.now();
    if (!this.started || (typeof document !== "undefined" && document.hidden) || now - this.last > 80) {
      this._frame(now);
    }
  }

  setBeatPulse(enabled) {
    this.beatPulse = Boolean(enabled);
  }

  setScale(scale) {
    const s = Math.max(0.6, Math.min(1.5, +scale || 1.0));
    if (Math.abs((this.scale || 1.0) - s) > 0.005) {
      const oldScale = this.scale || 1.0;
      this.scale = s;
      const ratio = s / oldScale;
      for (const ring of this.rings.values()) {
        if (ring.r) ring.r *= ratio;
        if (ring._layoutR) ring._layoutR *= ratio;
        if (ring.target?.r) ring.target.r *= ratio;
      }
      this.layerR = null;
      this._resize();
      this.invalidate();
    }
  }

  get reduced() {
    return reduceMQ?.matches ?? false;
  }

  // ------------------------------------------------------------- geometry

  _resize() {
    const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), 3);
    const box = this.canvas.parentElement ? this.canvas.parentElement.getBoundingClientRect() : null;
    let w = Math.round(box?.width || 0);
    let h = Math.round(box?.height || 0);
    if (w < 120 || h < 120) {
      w = Math.max(200, Math.round(window.innerWidth || document.documentElement.clientWidth || 800));
      h = Math.max(200, Math.round(window.innerHeight || document.documentElement.clientHeight || 800));
    }
    const pxW = Math.round(w * dpr);
    const pxH = Math.round(h * dpr);
    const baseR = Math.round(Math.min(w, h) * 0.37 * (this.scale || 1.0));
    if (
      this.w === w &&
      this.h === h &&
      this.dpr === dpr &&
      this.canvas.width === pxW &&
      this.canvas.height === pxH &&
      this.baseR === baseR
    ) {
      return;
    }
    this.w = w;
    this.h = h;
    if (this.canvas.width !== pxW) this.canvas.width = pxW;
    if (this.canvas.height !== pxH) this.canvas.height = pxH;
    if (!stageSync.isSatellite) {
      this.canvas.style.width = `${w}px`;
      this.canvas.style.height = `${h}px`;
    } else {
      if (this.canvas.style.width) this.canvas.style.width = "";
      if (this.canvas.style.height) this.canvas.style.height = "";
    }
    this.ctx.imageSmoothingEnabled = true;
    this.ctx.imageSmoothingQuality = "high";
    this.baseR = baseR;
    // Redraw layers when scale changes by more than 4% (ignore minor container reflow jitter)
    if (dpr !== this.dpr || !this.layerR || Math.abs(this.baseR - this.layerR) / this.layerR > 0.04) {
      this.layerR = this.baseR;
      this.invalidate();
    }
    this.dpr = dpr;
    // Setting the canvas size cleared it: paint now, not at the next frame.
    if (this.started && !this._inFrame) this._frame(performance.now());
  }

  // Where the loops sit: one in the middle, or two touching (side by side on
  // wide stages, stacked as an 8 on tall ones). `swap` (0..1) is how far a
  // blend has got: the weight passes from the playing loop to the next one,
  // and halfway through they are the same size.
  _layout(two, swap = 0) {
    const { w, h } = this;
    const k = SECOND_RATIO;
    const sc = this.scale || 1.0;
    if (!two) return { a: { x: w / 2, y: h / 2, r: Math.min(w, h) * 0.36 * sc } };
    const s = easeInOut(Math.max(0, Math.min(1, swap)));
    const fa = 1 - (1 - k) * s, fb = k + (1 - k) * s;
    if (w >= h * 1.05) {
      const R = Math.min(h * 0.34, (w * 0.84) / (2 * (1 + k))) * sc;
      const x0 = (w - 2 * R * (1 + k)) / 2;
      return {
        a: { x: x0 + fa * R, y: h / 2, r: fa * R, face: 0 },
        b: { x: x0 + 2 * fa * R + fb * R, y: h / 2, r: fb * R, face: Math.PI },
        cross: { x: x0 + 2 * fa * R, y: h / 2 },
      };
    }
    const R = Math.min(w * 0.34, (h * 0.84) / (2 * (1 + k))) * sc;
    const y0 = (h - 2 * R * (1 + k)) / 2;
    return {
      a: { x: w / 2, y: y0 + fa * R, r: fa * R, face: Math.PI / 2 },
      b: { x: w / 2, y: y0 + 2 * fa * R + fb * R, r: fb * R, face: -Math.PI / 2 },
      cross: { x: w / 2, y: y0 + 2 * fa * R },
    };
  }

  _thickness(R) {
    return Math.max(7, R * 0.068);
  }

  // Angle on the ring (before its rotation) for a time in the song.
  _ang(track, t) {
    return (TAU * t) / track.end;
  }

  // Angle on the stage for a time in the song, with the loop's turn and direction.
  _angle(ring, t) {
    return ring.rot + ring.dir * this._ang(ring.track, t);
  }

  _point(ring, t, radius) {
    const a = this._angle(ring, t);
    return [ring.x + radius * Math.cos(a), ring.y + radius * Math.sin(a)];
  }

  // The beat that is playing at time t of a song, and how far into it.
  _beatAt(track, t) {
    const beats = track.beats;
    let lo = 0, hi = beats.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (beats[mid] <= t) lo = mid;
      else hi = mid - 1;
    }
    return { beat: lo, frac: Math.max(0, Math.min(1, (t - beats[lo]) / track.dur[lo])) };
  }

  // ---------------------------------------------------------------- layers

  // Everything about a song that does not move: drawn once, then rotated and
  // scaled as the loop travels.
  _prewarmLayer(track) {
    if (!track || !track.analysis) return;
    const keep = this.player?.settings?.keep ?? 0.6;
    const transLen = track.transitions?.length ?? 0;
    const baseLayerR = this.layerR || this.baseR || 160;
    const key = `${track.id}|${keep}|${transLen}|${baseLayerR.toFixed(1)}|${this.dpr || 1}|${theme.paletteVersion()}`;
    const ring = this._ring(track, this.rings.get(track.id)?.role || "fading");
    if (ring.layerKey !== key) {
      ring.alpha = ring.alpha ?? 0;
      ring.layer = this._buildLayer(track);
      ring.layerKey = key;
    }
  }

  _buildLayer(track, forcedCol = null) {
    const RL = Math.round(this.layerR || this.baseR || 160);
    const th = this._thickness(RL);
    let S = Math.ceil(RL * 2.9);
    if (S % 2 !== 0) S++;
    // Cap offscreen SSAA texture <= 2048px so layer builds never stall frame animation
    const layerScale = Math.min(Math.max((this.dpr || 1) * 1.5, 2), 3, 2048 / S);
    const c = document.createElement("canvas");
    c.width = Math.round(S * layerScale);
    c.height = Math.round(S * layerScale);
    const ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.scale(layerScale, layerScale);
    ctx.translate(S / 2, S / 2);
    const a = track.analysis;
    const maxScore = this.player?.maxScore ? this.player.maxScore(track) : (track.scoreCut ? track.scoreCut(0.6) : 0.2);
    const loudMax = Math.max(...a.loud);
    const loudMin = Math.min(...a.loud);
    const ang = (t) => this._ang(track, t);
    const rin = RL - th / 2 - 3;
    const mood = track.analysis?.mood || track.meta?.mood || null;
    if (mood) theme.registerMood(track.id, mood);
    let hostCol = forcedCol;
    if (!hostCol && stageSync.isSatellite) {
      if (stageSync.telemetry?.track_id === track.id && stageSync.telemetry?.color_a) {
        const colA = stageSync.telemetry.color_a;
        hostCol = { l: colA[0], c: colA[1], h: colA[2] };
      } else if (stageSync.telemetry?.second?.id === track.id && stageSync.telemetry?.color_b) {
        const colB = stageSync.telemetry.color_b;
        hostCol = { l: colB[0], c: colB[1], h: colB[2] };
      }
    }
    const chord = theme.lift(hostCol || theme.accentOf(track.id, mood), 0.04);
    const colors = theme.beatColors(track.id, a.color, mood, hostCol);
    const ink = theme.inkOf(track.id);

    // Helper appending quadratic chord curve directly into current batched path
    const addChord = (a1, a2) => {
      const x1 = rin * Math.cos(a1), y1 = rin * Math.sin(a1);
      const x2 = rin * Math.cos(a2), y2 = rin * Math.sin(a2);
      const sep = Math.abs(wrapAngle(a1 - a2));
      const k = (1 - 0.92 * (sep / Math.PI)) * 0.9;
      ctx.moveTo(x1, y1);
      ctx.quadraticCurveTo(((x1 + x2) / 2) * k, ((y1 + y2) / 2) * k, x2, y2);
    };

    // Jump chords batched by alpha bucket (~9 strokes instead of thousands)
    const edges = [];
    for (let i = 0; i < track.n; i++) for (const e of track.jumps[i]) edges.push([i, e.to, e.score]);
    edges.sort((p, q) => q[2] - p[2]);
    ctx.lineWidth = 1;
    const CHORD_BUCKETS = 8;
    const faintChords = [];
    const okBuckets = Array.from({ length: CHORD_BUCKETS }, () => []);
    for (let idx = 0; idx < edges.length; idx++) {
      const [i, j, s] = edges[idx];
      if (s <= maxScore) {
        const w = 1 - s / Math.max(maxScore, 0.01);
        const bi = Math.min(CHORD_BUCKETS - 1, Math.max(0, Math.floor(w * CHORD_BUCKETS)));
        okBuckets[bi].push(i, j);
      } else {
        faintChords.push(i, j);
      }
    }
    if (faintChords.length) {
      ctx.strokeStyle = theme.css(ink, 0.03);
      ctx.beginPath();
      const totalPairs = faintChords.length >> 1;
      const step = totalPairs > 700 ? Math.ceil(totalPairs / 700) : 1;
      for (let p = 0; p < totalPairs; p += step) {
        const i = faintChords[p * 2], j = faintChords[p * 2 + 1];
        addChord(ang(track.beats[i] + track.dur[i]), ang(track.beats[j]));
      }
      ctx.stroke();
    }
    for (let bi = 0; bi < CHORD_BUCKETS; bi++) {
      const bkt = okBuckets[bi];
      if (!bkt.length) continue;
      ctx.strokeStyle = theme.css(chord, 0.08 + 0.42 * ((bi + 0.5) / CHORD_BUCKETS));
      ctx.beginPath();
      const totalPairs = bkt.length >> 1;
      const step = totalPairs > 450 ? Math.ceil(totalPairs / 450) : 1;
      for (let p = 0; p < totalPairs; p += step) {
        const i = bkt[p * 2], j = bkt[p * 2 + 1];
        addChord(ang(track.beats[i] + track.dur[i]), ang(track.beats[j]));
      }
      ctx.stroke();
    }

    // Dust: batched into 2 alpha groups per beat instead of individual arc+fill calls
    const rnd = seeded(track.n * 7919 + Math.round(track.end * 13));
    for (let b = 0; b < track.n; b++) {
      const lv = (a.loud[b] - loudMin) / Math.max(1, loudMax - loudMin);
      const count = 2 + Math.round(8 * lv);
      ctx.fillStyle = colors[b];
      const hiPts = [];
      const loPts = [];
      for (let k = 0; k < count; k++) {
        const t = track.beats[b] + rnd() * track.dur[b];
        const spread = (rnd() + rnd() + rnd() - 1.5) / 1.5;
        const r = RL + spread * th * 2.1;
        const theta = ang(t);
        const x = r * Math.cos(theta);
        const y = r * Math.sin(theta);
        const al = 0.12 + 0.4 * rnd() * (1 - Math.abs(spread));
        const rad = 0.5 + rnd() * 0.9;
        (al >= 0.28 ? hiPts : loPts).push(x, y, rad);
      }
      if (loPts.length) {
        ctx.globalAlpha = 0.19;
        ctx.beginPath();
        for (let p = 0; p < loPts.length; p += 3) {
          const x = loPts[p], y = loPts[p + 1], rad = loPts[p + 2];
          ctx.moveTo(x + rad, y);
          ctx.arc(x, y, rad, 0, TAU);
        }
        ctx.fill();
      }
      if (hiPts.length) {
        ctx.globalAlpha = 0.36;
        ctx.beginPath();
        for (let p = 0; p < hiPts.length; p += 3) {
          const x = hiPts[p], y = hiPts[p + 1], rad = hiPts[p + 2];
          ctx.moveTo(x + rad, y);
          ctx.arc(x, y, rad, 0, TAU);
        }
        ctx.fill();
      }
    }

    // Beat segments.
    for (let b = 0; b < track.n; b++) {
      const lv = (a.loud[b] - loudMin) / Math.max(1, loudMax - loudMin);
      ctx.globalAlpha = 0.3 + 0.7 * lv;
      ctx.strokeStyle = colors[b];
      ctx.lineWidth = th * (a.pos[b] === 0 ? 1 : 0.78);
      ctx.beginPath();
      ctx.arc(0, 0, RL, ang(track.beats[b]), ang(track.beats[b] + track.dur[b]) + 0.002);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // The dial: a hairline tick every 15 s, longer on the minute (single batched stroke).
    const r0 = RL + th / 2 + 8;
    ctx.strokeStyle = theme.css(ink, 0.22);
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let t = 0; t <= track.end; t += 15) {
      const long = Math.round(t) % 60 === 0;
      const thA = ang(t), cs = Math.cos(thA), sn = Math.sin(thA);
      ctx.moveTo(r0 * cs, r0 * sn);
      ctx.lineTo((r0 + (long ? 7 : 3.5)) * cs, (r0 + (long ? 7 : 3.5)) * sn);
    }
    ctx.stroke();

    // Section starts, just inside the dial (single batched stroke).
    ctx.strokeStyle = theme.css(ink, 0.55);
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (const s of a.sections) {
      const thS = ang(track.beats[s]), cs = Math.cos(thS), sn = Math.sin(thS);
      ctx.moveTo((RL + th / 2 + 1) * cs, (RL + th / 2 + 1) * sn);
      ctx.lineTo((RL + th / 2 + 5) * cs, (RL + th / 2 + 5) * sn);
    }
    ctx.stroke();

    // Exits to other songs (those the chain may take).
    const exitR = this._exitRadius(RL);
    for (const tr of track.transitions) {
      if (!this._shown(track, tr)) continue;
      const t = this._exitTime(track, tr);
      if (t === null) continue;
      const thE = ang(t);
      ctx.fillStyle = theme.css(theme.songColor(tr.to), 0.4 + 0.55 * tr.q);
      ctx.beginPath();
      ctx.arc(exitR * Math.cos(thE), exitR * Math.sin(thE), tr.type === "cut" ? 4 : 3.1, 0, TAU);
      ctx.fill();
    }
    return { canvas: c, S, RL, th };
  }

  _exitRadius(R) {
    return R + this._thickness(R) / 2 + 21;
  }

  // The moment in the song where a transition leaves it.
  _exitTime(track, tr) {
    const beat = tr.type === "blend" ? tr.a : tr.i + 1;
    if (beat < 0 || beat >= track.n) return null;
    return track.beats[beat];
  }

  _entryTime(track, tr) {
    const beat = tr.type === "blend" ? tr.b : tr.j;
    if (beat == null || beat < 0 || beat >= track.n) return track.beats[0];
    return track.beats[beat];
  }

  _chordPath(ctx, rin, a1, a2) {
    const x1 = rin * Math.cos(a1), y1 = rin * Math.sin(a1);
    const x2 = rin * Math.cos(a2), y2 = rin * Math.sin(a2);
    let sep = Math.abs(wrapAngle(a1 - a2));
    const k = (1 - 0.92 * (sep / Math.PI)) * 0.9;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.quadraticCurveTo(((x1 + x2) / 2) * k, ((y1 + y2) / 2) * k, x2, y2);
  }

  // A chord in stage coordinates, following the ring's position and rotation.
  _chordWorld(ctx, ring, i, j) {
    const T = ring.track;
    const s = ring.r / this.layerR;
    const rin = (this.layerR - this._thickness(this.layerR) / 2 - 3) * s;
    ctx.save();
    const px = Math.round(ring.x * this.dpr) / this.dpr;
    const py = Math.round(ring.y * this.dpr) / this.dpr;
    ctx.translate(px, py);
    ctx.rotate(ring.rot);
    ctx.scale(1, ring.dir);
    this._chordPath(ctx, rin, this._ang(T, T.beats[i] + T.dur[i]), this._ang(T, T.beats[j]));
    ctx.restore();
  }

  // ----------------------------------------------------------------- state

  // The mix (a blend or an effect) the listener is hearing. The scheduler runs
  // a lookahead ahead of the speakers and lets go of a mix before its end is
  // heard; the stage holds on to it until then, so the next loop does not dim
  // and come back at every hand-over.
  _mix(view) {
    const p = this.player;
    const live = p.blend || p.fx;
    if (live) {
      const blend = live === p.blend;
      this.held = { m: live, blend, end: blend ? live.times[live.L] : live.times[live.times.length - 1] };
    } else if (this.held && (!view || view.now >= this.held.end)) {
      this.held = null;
    }
    return this.held;
  }

  _roles(view) {
    const p = this.player;
    const primary = view?.entry.track || (p.cur ? p.cur.track : null);
    let second = null;
    let secondTr = null;
    let placeholder = null;
    // A mix is scheduled a lookahead before it is heard, and the plan is gone
    // by then: the mix itself keeps the next loop on stage from that moment.
    const mx = this.mixNow;
    if (p.plan) this.lastPlan = p.plan;
    if (mx && primary && primary.id === mx.m.A.id) {
      second = mx.m.B;
      secondTr = mx.m.tr;
    } else if (p.cur && primary && p.cur.track.id !== primary.id && p.history.at(-1)?.via !== "start") {
      // Same for a cut, a drop or a fade: the scheduler is already in the
      // next song while the listener is still in this one. Keep the ∞ until
      // the light gets to the crossing.
      second = p.cur.track;
      const tr = this.lastPlan?.tr;
      secondTr = tr && tr.to === second.id ? tr : null;
    } else if (p.plan && primary && p.plan.from === primary.id) {
      secondTr = p.plan.tr;
      const etaLeft = (view && Number.isFinite(p.plan.eta)) ? (p.plan.eta - view.now) : 0;
      if (p.plan.target && !p.plan._layerPrewarmed) {
        p.plan._layerPrewarmed = true;
        this._prewarmLayer(p.plan.target);
      }
      if (p.plan.picked) {
        p.plan._docked = true;
        if (p.plan.target) second = p.plan.target;
        else placeholder = p.plan.tr.to;
      } else if (p.plan.target && p.plan.ready && (p.urgent || etaLeft <= DOCK_LEAD_S)) {
        p.plan._docked = true;
        second = p.plan.target;
      } else if (p.plan._docked && p.plan.target) {
        second = p.plan.target;
      }
    }
    return { primary, second, secondTr, placeholder };
  }

  _ring(track, role) {
    let ring = this.rings.get(track.id);
    if (!ring) {
      ring = new Ring(track, role);
      this.rings.set(track.id, ring);
    }
    ring.track = track;
    ring.role = role;
    return ring;
  }

  _update(view, dt) {
    const { primary, second, secondTr, placeholder } = this._roles(view);
    const nowWall = performance.now();
    const rawTwo = !!(second || placeholder);
    if (rawTwo) {
      this._twoHoldUntil = nowWall + 1100;
    } else if (this.mixNow || this.player?.settings?.mode !== "chain" || !primary) {
      this._twoHoldUntil = 0;
    }
    // Layout hysteresis: if a docked 2-ring plan drops momentarily before transition,
    // hold two-ring geometry briefly while searching for the replacement so it never pumps.
    const two = rawTwo || (nowWall < (this._twoHoldUntil || 0));
    const swapProg = (second && (this.mixNow || (this.player.cur && primary && this.player.cur.track.id !== primary.id)))
      ? this._mixProgress(view)
      : 0;
    const L = this._layout(two, swapProg);
    const k = this.reduced ? 1 : 1 - Math.exp(-dt / 0.22);
    const kLayout = this.reduced ? 1 : 1 - Math.exp(-dt / 0.36);
    const kRot = this.reduced ? 1 : 1 - Math.exp(-dt / 0.3);

    this.idle += ((primary ? 0 : 1) - this.idle) * (this.reduced ? 1 : 1 - Math.exp(-dt / 0.25));

    if (primary && primary.id !== this.primaryId) {
      // A new song is playing: the one before it leaves the stage.
      const before = this.primaryId ? this.rings.get(this.primaryId) : null;
      if (before) before.role = "leaving";
      const fresh = !this.rings.has(primary.id);
      const ring = this._ring(primary, "primary");
      if (fresh) {
        if (before) {
          const L2 = this._layout(true, 0);
          if (before.x !== null && before.y !== null) {
            const br = before._layoutR || before.r;
            before.x += (L2.a.x - before.x) * 0.28;
            before.y += (L2.a.y - before.y) * 0.28;
            before._layoutR = br + (L2.a.r - br) * 0.28;
            before.r = before._layoutR;
          }
          ring.x = L2.b.x + (L2.b.x - L2.a.x) * 0.15;
          ring.y = L2.b.y + (L2.b.y - L2.a.y) * 0.15;
          ring.r = L2.b.r * 0.65;
          ring._layoutR = ring.r;
          ring.alpha = 0.25;
          ring.fill = 1;
          ring.dir = -before.dir;
        } else {
          ring.x = L.a.x;
          ring.y = L.a.y;
          ring.r = L.a.r;
          ring._layoutR = ring.r;
          ring.fill = this.reduced ? 1 : 0; // the very first loop sweeps in
        }
      }
      this.primaryId = primary.id;
    }
    if (!primary && this.primaryId) {
      const ring = this.rings.get(this.primaryId);
      if (ring) ring.role = "leaving";
      this.primaryId = null;
    }

    for (const ring of this.rings.values()) if (ring.role === "second" || ring.role === "ghost") ring.role = "fading";

    if (primary) {
      const ring = this._ring(primary, "primary");
      ring.target = { ...L.a, alpha: 1 };
      if (two && secondTr) {
        // Turn the loop so the exit beat faces the next song.
        const t = this._exitTime(primary, secondTr);
        if (t !== null) ring.target.rot = L.a.face - ring.dir * this._ang(primary, t);
      }
      if (second) {
        const sr = this._ring(second, "second");
        // The next loop runs the other way round (set while it is still
        // faint, never on a loop the listener is watching).
        if (sr.alpha < 0.3) sr.dir = -ring.dir;
        const rot = secondTr ? L.b.face - sr.dir * this._ang(second, this._entryTime(second, secondTr)) : sr.rot;
        if (sr.x === null) {
          sr.x = L.b.x + (L.b.x - L.a.x) * 0.25;
          sr.y = L.b.y + (L.b.y - L.a.y) * 0.25;
          sr.r = L.b.r * 0.6;
          sr._layoutR = sr.r;
          sr.rot = rot;
          sr.alpha = 0;
        }
        sr.target = { ...L.b, rot, alpha: 1 };
      }
    }
    this.placeholder = placeholder ? { id: placeholder, ...L.b, tr: secondTr } : null;
    this.cross = two ? L.cross : null;

    for (const [id, ring] of this.rings) {
      const baseR = ring._layoutR || ring.r;
      if (ring.role === "leaving" || ring.role === "fading") {
        const away = ring.role === "leaving";
        ring.target = {
          x: ring.x + (away ? -0.02 * this.w : 0),
          y: ring.y,
          r: baseR * (away ? 0.985 : 0.99),
          alpha: 0,
        };
      }
      const tg = ring.target;
      if (!tg) continue;
      if (ring.x === null || ring._layoutR === null) {
        if (ring.x === null) {
          ring.x = tg.x;
          ring.y = tg.y;
        }
        ring._layoutR = tg.r;
      }
      ring.x += (tg.x - ring.x) * kLayout;
      ring.y += (tg.y - ring.y) * kLayout;
      ring._layoutR += (tg.r - ring._layoutR) * kLayout;
      const pulseAmt = (this.beatPulse !== false && !this.reduced)
        ? (ring.role === "primary" ? 1 : 0.6) * (0.044 * (this.pulse || 0) + 0.017 * (this.bass || 0))
        : 0;
      ring.r = ring._layoutR * (1 + pulseAmt);
      const fadeK = this.reduced ? Math.min(1, dt / 0.16) : k;
      ring.alpha += (tg.alpha - ring.alpha) * fadeK;
      if (tg.rot !== undefined) ring.rot += wrapAngle(tg.rot - ring.rot) * kRot;
      // The playing loop wears the room's accent; the others their own colour.
      const mood = ring.track.analysis?.mood || ring.track.meta?.mood || null;
      const want = ring.role === "primary" ? theme.accentOf(ring.track.id, mood) : theme.songColor(ring.track.id, mood);
      ring.col = theme.ease(ring.col, want, this.reduced ? 1 : 1 - Math.exp(-dt / 0.5));
      if (ring.fill < 1) ring.fill = Math.min(1, ring.fill + dt / 1.2);
      if ((ring.role === "leaving" || ring.role === "fading") && ring.alpha < 0.02) this.rings.delete(id);
    }
  }

  // ----------------------------------------------------------------- frame

  _frame(now) {
    if (this._inFrame) return;
    this._inFrame = true;
    try {
      if (stageSync.isSatellite) {
        const box = this.canvas.parentElement ? this.canvas.parentElement.getBoundingClientRect() : null;
        if (box && box.width >= 120 && box.height >= 120) {
          const targetW = Math.round(box.width);
          const targetH = Math.round(box.height);
          if (Math.abs(targetW - this.w) > 2 || Math.abs(targetH - this.h) > 2) {
            this._resize();
          }
        }
      }

      const dt = Math.min(0.1, (now - this.last) / 1000);
      this.last = now;
      const ctx = this.ctx;

      if (stageSync.isStageMirrorActive) {
        const sx = this.canvas.width / this.w;
        const sy = this.canvas.height / this.h;
        ctx.setTransform(sx, 0, 0, sy, 0, 0);
        ctx.clearRect(0, 0, this.w, this.h);
        this._drawSatelliteStage(ctx, now, stageSync.telemetry, dt);
        return;
      }

      const view = this.player.audible();

      // Wall-clock interpolation to smooth out AudioContext hardware buffer quantization
      let effectiveNow = view ? view.now : 0;
      if (view && typeof view.now === "number") {
        const rate = view.entry?.rate || 1;
        if (this._smoothAudioT === null || Math.abs(view.now - this._smoothAudioT) > 0.3) {
          this._smoothAudioT = view.now;
          this._lastAudioWall = now;
          this._lastAudioVal = view.now;
        } else {
          const dtWall = Math.min(0.1, Math.max(0, (now - (this._lastAudioWall || now)) / 1000));
          this._lastAudioWall = now;
          this._smoothAudioT += dtWall * rate;
          const drift = view.now - this._smoothAudioT;
          this._smoothAudioT += drift * 0.15;
        }
        effectiveNow = this._smoothAudioT;
      } else {
        this._smoothAudioT = null;
        this._lastAudioWall = null;
      }

      this.mixNow = this._mix(view);
      this._beatPulse(view, dt);
      this._spectrum(dt);
      this._update(view, dt);

      const sx = this.canvas.width / this.w;
      const sy = this.canvas.height / this.h;
      ctx.setTransform(sx, 0, 0, sy, 0, 0);
      ctx.clearRect(0, 0, this.w, this.h);

      const primary = this.primaryId ? this.rings.get(this.primaryId) : null;
      this._roomColor(primary, view, dt);
      if (this.idle > 0.01) this._drawIdle(ctx, now, this.idle);

      this.heads = this._heads(primary, view, effectiveNow);
      this._trackCrossing(now);
      this.capPlace = this._captionPlace(primary, view);
      this.captionTrack = this.capPlace.ring?.track || null;
      this._broadcastHostTelemetry();

      this._drawLights(ctx, primary);
      if (this.heads.lead && !this.reduced) this._drawHalo(ctx, this.heads.lead);

      // Back to front: leaving, the next song, the playing song.
      const order = [...this.rings.values()].sort((a, b) => (a.role === "primary") - (b.role === "primary"));
      for (const ring of order) this._drawRing(ctx, ring);
      if (this.placeholder) this._drawPlaceholder(ctx, this.placeholder, now);
      if (this.cross && primary && primary.alpha > 0.4) this._drawCross(ctx, view, now);

      if (primary && view) this._drawLive(ctx, primary, view, now);
      this._drawHover(ctx);
      this._placeCenter(this.capPlace);
      this._updateField(primary, now);
    } finally {
      this._inFrame = false;
    }
  }

  // Where the light is. On the playing loop, until a blend reaches the
  // crossing: from there it runs on round the next loop, and the playing loop
  // keeps a ghost of it that fades as that song fades out.
  _heads(primary, view, effectiveNow) {
    if (!primary || !view) return { lead: null, ghost: null };
    const curNow = (effectiveNow !== undefined && effectiveNow !== null) ? effectiveNow : view.now;
    const T = primary.track;
    const e = view.entry;
    const rate = e.rate || 1;
    let span = T.dur[e.beat];
    const tl = this.player?.timeline;
    if (tl && view.index !== undefined && view.index + 1 < tl.length) {
      const nextE = tl[view.index + 1];
      if (nextE && (nextE.track === e.track || nextE.track?.id === e.track?.id) && nextE.t > e.t) {
        span = (nextE.t - e.t) * rate;
      }
    }
    const frac = span > 0 ? Math.max(0, Math.min(1, ((curNow - e.t) * rate) / span)) : 0;
    const onA = this._head(primary, e.beat, frac);
    const b = this.mixNow?.blend ? this.mixNow.m : null;
    const sr = b && curNow >= b.times[0] ? this.rings.get(b.B.id) : null;
    if (!sr || sr.role !== "second" || sr.alpha < 0.05) return { lead: onA, ghost: null };
    let k = 0;
    while (k + 1 < b.times.length && b.times[k + 1] <= curNow) k++;
    k = Math.min(k, b.L - 1);
    const spanB = b.times[k + 1] - b.times[k];
    const f = spanB > 0 ? Math.max(0, Math.min(1, (curNow - b.times[k]) / spanB)) : 0;
    // tB holds B's audio time at each master beat, whatever the beat ratio.
    const at = this._beatAt(sr.track, b.tB[k] + f * (b.tB[k + 1] - b.tB[k]));
    return { lead: this._head(sr, at.beat, at.frac), ghost: { ...onA, alpha: 1 - this._mixProgress(view) } };
  }

  _head(ring, beat, frac) {
    const T = ring.track;
    return { ring, beat, frac, angle: this._angle(ring, T.beats[beat] + frac * T.dur[beat]) };
  }

  // The caption sits in the loop that has the song: the playing one, or the
  // next one once a blend is past halfway (where the bass changes hands). It
  // dips out and back in as it crosses over.
  _captionPlace(primary, view) {
    const b = this.mixNow?.blend ? this.mixNow.m : null;
    const sr = b ? this.rings.get(b.B.id) : null;
    if (!primary || !sr || sr.role !== "second") return { ring: primary, dip: 1 };
    const k = this._mixProgress(view);
    return { ring: k >= 0.5 ? sr : primary, dip: Math.min(1, Math.abs(k - 0.5) * 8) };
  }

  _drawSatelliteStage(ctx, now, t, dt = 0.016) {
    const w = this.w, h = this.h;
    const kEase = this.reduced ? 1 : 1 - Math.exp(-dt / 0.22);
    const kLayout = this.reduced ? 1 : 1 - Math.exp(-dt / 0.36);
    const kRot = this.reduced ? 1 : 1 - Math.exp(-dt / 0.3);

    if (!t || t.mode === "idle") {
      if (this.primaryId) {
        const ring = this.rings.get(this.primaryId);
        if (ring) ring.role = "leaving";
        this.primaryId = null;
      }
      for (const ring of this.rings.values()) {
        if (ring.role === "second" || ring.role === "ghost") ring.role = "fading";
      }
      this.idle += (1 - this.idle) * (this.reduced ? 1 : 1 - Math.exp(-dt / 0.25));
      this.accent = t?.acc ? { l: t.acc[0], c: t.acc[1], h: t.acc[2] } : theme.idleAccent();
      this._drawIdle(ctx, now, this.idle);
      for (const [id, ring] of this.rings) {
        const away = ring.role === "leaving";
        ring.target = {
          x: ring.x + (away ? -0.02 * w : 0),
          y: ring.y,
          r: ring.r * (away ? 0.985 : 0.99),
          alpha: 0,
        };
        const tg = ring.target;
        ring.x += (tg.x - ring.x) * kEase;
        ring.y += (tg.y - ring.y) * kEase;
        ring.r += (tg.r - ring.r) * kEase;
        ring.alpha += (tg.alpha - ring.alpha) * kEase;
        if (ring.alpha < 0.02) this.rings.delete(id);
        else if (ring.track?.analysis) this._drawRing(ctx, ring);
      }
      this._placeCenter(null);
      if (now - this.fieldAt >= 100) {
        this.fieldAt = now;
        const root = document.documentElement.style;
        root.setProperty("--key-x", "38%");
        root.setProperty("--key-y", "45%");
        root.setProperty("--key-r-px", `${Math.round(this.baseR || 200)}px`);
        root.setProperty("--fill-x", "62%");
        root.setProperty("--fill-y", "45%");
        root.setProperty("--fill-r-px", `${Math.round((this.baseR || 200) * 0.85)}px`);
      }
      return;
    }

    const pulse = Math.min(1.4, t.pulse || 0);
    const bass = Math.min(1.4, t.bass || 0);
    this.pulse = pulse;
    this.bass = bass;
    if (Array.isArray(t.bands) && t.bands.length) {
      const n = Math.min(this.bands.length, t.bands.length);
      for (let i = 0; i < n; i++) {
        this.bands[i] = t.bands[i];
      }
    } else if (t.mode === "paused") {
      for (let i = 0; i < this.bands.length; i++) this.bands[i] *= 0.85;
    }

    const progress = Math.max(0, Math.min(1, t.progress || 0));
    const swapProg = t.swap_prog !== undefined ? Math.max(0, Math.min(1, t.swap_prog)) : progress;
    const primaryTrack = stageSync.primaryTrack;
    const two = Boolean(t.two ?? (t.second || t.placeholder || t.is_transitioning));
    const secondTrack = (two && !t.placeholder && t.second?.id && stageSync.secondTrack?.id === t.second.id)
      ? stageSync.secondTrack
      : null;
    const L = this._layout(two, swapProg);

    this.idle += (0 - this.idle) * (this.reduced ? 1 : 1 - Math.exp(-dt / 0.25));
    if (t.acc) {
      const targetAcc = { l: t.acc[0], c: t.acc[1], h: t.acc[2] };
      this.accent = theme.ease(this.accent, targetAcc, this.reduced ? 1 : 1 - Math.exp(-dt / 0.35));
    }
    if (this.idle > 0.01 && primaryTrack) this._drawIdle(ctx, now, this.idle);

    // 1. Unified Ring State Machine ("primary", "second", "leaving", "fading") matching Host _update 1:1
    if (primaryTrack && primaryTrack.id !== this.primaryId) {
      const before = this.primaryId ? this.rings.get(this.primaryId) : null;
      if (before) before.role = "leaving";
      const fresh = !this.rings.has(primaryTrack.id);
      const ring = this._ring(primaryTrack, "primary");
      if (fresh) {
        if (before) {
          const L2 = this._layout(true, 0);
          if (before.x !== null && before.y !== null) {
            const br = before._layoutR || before.r;
            before.x += (L2.a.x - before.x) * 0.28;
            before.y += (L2.a.y - before.y) * 0.28;
            before._layoutR = br + (L2.a.r - br) * 0.28;
            before.r = before._layoutR;
          }
          ring.x = L2.b.x + (L2.b.x - L2.a.x) * 0.15;
          ring.y = L2.b.y + (L2.b.y - L2.a.y) * 0.15;
          ring.r = L2.b.r * 0.65;
          ring._layoutR = ring.r;
          ring.alpha = 0.25;
          ring.fill = 1;
          ring.dir = -before.dir;
        } else {
          ring.x = L.a.x;
          ring.y = L.a.y;
          ring.r = L.a.r;
          ring._layoutR = ring.r;
          ring.alpha = 1;
          ring.fill = this.reduced || (t.primary?.fill ?? 1) >= 0.98 ? 1 : 0;
        }
      } else if (before && before.x !== null && Math.hypot(before.x - L.a.x, before.y - L.a.y) < L.a.r * 0.12) {
        const L2 = this._layout(true, 0);
        const br = before._layoutR || before.r;
        before.x += (L2.a.x - before.x) * 0.22;
        before.y += (L2.a.y - before.y) * 0.22;
        before._layoutR = br + (L2.a.r - br) * 0.22;
        before.r = before._layoutR;
      }
      this.primaryId = primaryTrack.id;
    }

    for (const ring of this.rings.values()) {
      if (ring.role === "second" || ring.role === "ghost") ring.role = "fading";
    }

    let primRing = null;
    let secRing = null;
    const trackMatchesTelemetry = Boolean(primaryTrack && (!t.track_id || primaryTrack.id === t.track_id));

    if (primaryTrack) {
      primRing = this._ring(primaryTrack, "primary");
      if (trackMatchesTelemetry) {
        const rawPrimRot = t.primary?.rot !== undefined ? t.primary.rot : (t.rot !== undefined ? t.rot : -Math.PI / 2);
        const targetPrimRot = (two && t.face_a !== undefined && L.a.face !== undefined)
          ? L.a.face + (rawPrimRot - t.face_a)
          : rawPrimRot;
        primRing.dir = t.primary?.dir !== undefined ? t.primary.dir : (t.dir !== undefined ? t.dir : primRing.dir);
        if (primRing.rot === undefined || primRing.rot === null) primRing.rot = targetPrimRot;
        primRing.target = { ...L.a, rot: targetPrimRot, alpha: 1 };
      } else {
        primRing.target = { ...L.a, rot: primRing.target?.rot ?? primRing.rot ?? -Math.PI / 2, alpha: 1 };
      }

      if (secondTrack && two && L.b) {
        secRing = this._ring(secondTrack, "second");
        if (secRing.alpha < 0.3) {
          secRing.dir = t.second?.dir !== undefined ? t.second.dir : -primRing.dir;
        }
        const rawSecRot = t.second?.rot !== undefined ? t.second.rot : -Math.PI / 2;
        const targetSecRot = (t.face_b !== undefined && L.b.face !== undefined)
          ? L.b.face + (rawSecRot - t.face_b)
          : rawSecRot;
        if (secRing.x === null) {
          secRing.x = L.b.x + (L.b.x - L.a.x) * 0.25;
          secRing.y = L.b.y + (L.b.y - L.a.y) * 0.25;
          secRing.r = L.b.r * 0.6;
          secRing._layoutR = secRing.r;
          secRing.rot = targetSecRot;
          secRing.alpha = 0;
        }
        secRing.target = { ...L.b, rot: targetSecRot, alpha: 1 };
      }
    }

    for (const [id, ring] of this.rings) {
      const baseR = ring._layoutR || ring.r;
      if (ring.role === "leaving" || ring.role === "fading") {
        const away = ring.role === "leaving";
        ring.target = {
          x: ring.x + (away ? -0.02 * w : 0),
          y: ring.y,
          r: baseR * (away ? 0.985 : 0.99),
          alpha: 0,
        };
      }
      const tg = ring.target;
      if (!tg) continue;
      if (ring.x === null || ring._layoutR === null) {
        if (ring.x === null) {
          ring.x = tg.x;
          ring.y = tg.y;
        }
        ring._layoutR = tg.r;
      }
      ring.x += (tg.x - ring.x) * kLayout;
      ring.y += (tg.y - ring.y) * kLayout;
      ring._layoutR += (tg.r - ring._layoutR) * kLayout;
      const pulseAmt = (this.beatPulse !== false && !this.reduced)
        ? (ring.role === "primary" ? 1 : 0.6) * (0.044 * (this.pulse || 0) + 0.017 * (this.bass || 0))
        : 0;
      ring.r = ring._layoutR * (1 + pulseAmt);
      const fadeK = this.reduced ? Math.min(1, dt / 0.16) : kEase;
      ring.alpha += (tg.alpha - ring.alpha) * fadeK;
      if (tg.rot !== undefined) ring.rot += wrapAngle(tg.rot - ring.rot) * kRot;
      const mood = ring.track.analysis?.mood || ring.track.meta?.mood || null;
      let want;
      if (ring.role === "primary" && trackMatchesTelemetry && t.color_a) {
        want = { l: t.color_a[0], c: t.color_a[1], h: t.color_a[2] };
      } else if (ring.role === "second" && t.color_b) {
        want = { l: t.color_b[0], c: t.color_b[1], h: t.color_b[2] };
      } else {
        want = ring.role === "primary" ? theme.accentOf(ring.track.id, mood) : theme.songColor(ring.track.id, mood);
      }
      ring.col = theme.ease(ring.col, want, this.reduced ? 1 : 1 - Math.exp(-dt / 0.5));
      if (ring.fill < 1) ring.fill = Math.min(1, ring.fill + dt / 1.2);
      if ((ring.role === "leaving" || ring.role === "fading") && ring.alpha < 0.02) this.rings.delete(id);
    }

    // 2. Draw soft background light pools under all active/leaving loops (exact _drawLights)
    const gain = theme.glowGain();
    this._drawLights(ctx, primRing);

    // Smooth wall-clock interpolation between 30 FPS telemetry frames for 60/120 FPS glide
    const elapsed = (t.mode === "ring" && t._recvAt)
      ? Math.min(0.12, Math.max(0, (now - t._recvAt) / 1000))
      : 0;
    const leadRing = (t.lead_head?.on === "second" && secRing) ? secRing : primRing;
    const leadRingId = leadRing?.track?.id || (t.track_id || "prim");
    const leadBeat = t.lead_head?.beat ?? t.beat ?? 0;
    const leadFrac = t.lead_head?.frac ?? t.frac ?? 0;
    const leadDur = Math.max(30, leadRing?.track?.end || primaryTrack?.end || 180);
    let targetAng;
    if (leadRing && (leadRing === secRing || trackMatchesTelemetry) && t.lead_head?.rel_angle !== undefined) {
      targetAng = leadRing.rot + t.lead_head.rel_angle + (leadRing.dir || 1) * ((TAU * elapsed) / leadDur);
    } else if (leadRing && (leadRing === secRing || trackMatchesTelemetry) && leadRing.track?.beats?.length) {
      const T = leadRing.track;
      let bIdx = Math.max(0, Math.min(T.beats.length - 1, leadBeat));
      const beatDur = (T.dur && T.dur[bIdx] > 0.05) ? T.dur[bIdx] : (60 / Math.max(40, t.bpm || 120));
      let interpF = leadFrac + (elapsed / beatDur);
      while (interpF >= 1 && bIdx + 1 < T.beats.length) {
        interpF -= 1;
        bIdx++;
      }
      const curBeatDur = (T.dur && T.dur[bIdx] > 0.05) ? T.dur[bIdx] : beatDur;
      const audioT = T.beats[bIdx] + Math.min(1, interpF) * curBeatDur;
      targetAng = this._angle(leadRing, audioT);
    } else if (this._satSmoothAng !== undefined && !trackMatchesTelemetry && leadRing) {
      targetAng = this._satSmoothAng + (leadRing.dir || 1) * ((TAU * dt) / leadDur);
    } else {
      const baseAng = t.angle !== undefined ? t.angle : ((leadRing?.rot || 0) + leadFrac * TAU);
      targetAng = baseAng + (leadRing?.dir || 1) * ((TAU * elapsed) / leadDur);
    }

    if (this._satSmoothAng === undefined || this._satSmoothTrackId !== leadRingId || t.mode !== "ring") {
      this._satSmoothAng = targetAng;
      this._satSmoothTrackId = leadRingId;
    } else {
      const diff = wrapAngle(targetAng - this._satSmoothAng);
      if (Math.abs(diff) > 0.2) {
        this._satSmoothAng = targetAng;
      } else {
        this._satSmoothAng = wrapAngle(this._satSmoothAng + diff * Math.min(1, dt * 18));
      }
    }
    const ang = this._satSmoothAng;

    // 4. Live Spectrum Halo around the active lead loop (moves to secRing during blend, matching Host)
    if (leadRing && leadRing.track?.analysis && !this.reduced) {
      this._drawHalo(ctx, { ring: leadRing, angle: ang, beat: leadBeat, frac: leadFrac });
    }

    // 5. Draw complete high-fidelity rings (leaving, fading, second, primary) or dashed placeholder ("ĐANG TẢI") matching Host 1:1
    const capOnSec = Boolean(t.cap_on === "second" && secRing && secRing.track?.analysis);
    this.capPlace = { ring: capOnSec ? secRing : primRing, dip: t.cap_dip ?? 1 };

    const order = [...this.rings.values()].sort((a, b) => (a.role === "primary") - (b.role === "primary"));
    for (const ring of order) {
      if (ring.track?.analysis) {
        this._drawRing(ctx, ring);
      }
    }

    if (two && L.b && (t.placeholder?.id || (t.second?.id && !secRing))) {
      this._drawPlaceholder(ctx, { id: t.placeholder?.id || t.second.id, ...L.b }, now);
    }
    if (!primRing && t.track_id) {
      this._drawPlaceholder(ctx, { id: t.track_id, x: L.a.x, y: L.a.y, r: L.a.r }, now);
    }

    // 6. Draw Crossing Glow, Progress Ring & Transition Visuals (exact replica of Host _drawCross)
    if (two && L.cross && primRing && primRing.alpha > 0.4) {
      const c = L.cross;
      const k = progress;
      const ca = primRing.col || this.accent || theme.idleAccent();
      const cb = secRing?.col || (t.color_b ? { l: t.color_b[0], c: t.color_b[1], h: t.color_b[2] } : ca);
      const mid = t.acc ? { l: t.acc[0], c: t.acc[1], h: t.acc[2] } : ca;
      const breathe = this.reduced ? 0.5 : 0.5 + 0.5 * Math.sin(now / 420);
      const R = (16 + 26 * k) * (1 + 0.25 * bass);
      const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R * 2.2);
      g.addColorStop(0, theme.css(theme.lift(mid, 0.12), 0.6 + 0.3 * k));
      g.addColorStop(0.35, theme.css(mid, (0.18 + 0.12 * breathe) * gain));
      g.addColorStop(1, theme.css(mid, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(c.x, c.y, R * 2.2, 0, TAU);
      ctx.fill();
      ctx.fillStyle = theme.css(theme.lift(mid, 0.3));
      ctx.beginPath();
      ctx.arc(c.x, c.y, 2.6 + 1.2 * k, 0, TAU);
      ctx.fill();
      if (k > 0) {
        const start = -Math.PI / 2;
        const cg = ctx.createConicGradient ? ctx.createConicGradient(start, c.x, c.y) : null;
        if (cg) {
          cg.addColorStop(0, theme.css(theme.lift(ca, 0.06), 0.95));
          cg.addColorStop(Math.max(0.01, k), theme.css(theme.lift(theme.mix(ca, cb, k), 0.06), 0.95));
          cg.addColorStop(1, theme.css(cb, 0.95));
        }
        ctx.strokeStyle = cg || theme.css(theme.lift(mid, 0.06), 0.9);
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(c.x, c.y, 11, start, start + TAU * k);
        ctx.stroke();
        ctx.lineCap = "butt";
      }

      const trType = t.tr_type || t.plan?.type || "blend";
      if (trType === "riser" || trType === "sweeper") {
        ctx.save();
        ctx.translate(c.x, c.y);
        ctx.rotate((now / 180) * (1 + 2 * k));
        for (let s = 0; s < 6; s++) {
          const angS = (s * TAU) / 6;
          const dist = (8 + 22 * k) * (1 + 0.15 * Math.sin(now / 120 + s));
          ctx.fillStyle = theme.css(theme.lift(cb, 0.25), 0.85 * (0.3 + 0.7 * k));
          ctx.beginPath();
          ctx.arc(Math.cos(angS) * dist, Math.sin(angS) * dist, 1.8 + k, 0, TAU);
          ctx.fill();
        }
        ctx.restore();
      } else if (trType === "echo" || trType === "wash") {
        for (let wIdx = 1; wIdx <= 3; wIdx++) {
          const pWave = ((now / 600 + wIdx * 0.33) % 1);
          ctx.strokeStyle = theme.css(theme.lift(mid, 0.18), (1 - pWave) * 0.45 * (0.3 + 0.7 * k));
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.arc(c.x, c.y, (12 + 38 * pWave) * (1 + 0.15 * bass), 0, TAU);
          ctx.stroke();
        }
      } else if (trType === "drop" || trType === "cut") {
        const shock = (0.5 + 0.5 * Math.sin(now / 100)) * bass;
        ctx.strokeStyle = theme.css(theme.lift(ca, 0.35), (0.4 + 0.6 * shock) * (0.4 + 0.6 * k));
        ctx.lineWidth = 2 + shock * 2.5;
        ctx.beginPath();
        ctx.arc(c.x, c.y, R * 1.35, 0, TAU);
        ctx.stroke();
      } else {
        const auraG = ctx.createRadialGradient(c.x, c.y, 2, c.x, c.y, R * 1.8);
        auraG.addColorStop(0, theme.css(theme.lift(mid, 0.2), 0.45 * (1 + breathe * 0.3)));
        auraG.addColorStop(1, theme.css(mid, 0));
        ctx.fillStyle = auraG;
        ctx.beginPath();
        ctx.arc(c.x, c.y, R * 1.8, 0, TAU);
        ctx.fill();
      }
      this._lastSatCross = { x: c.x, y: c.y, at: now };
    }

    // 7. Draw Live Jump Chords, Planned Route & Glowing Playheads (lead + ghost, exact replica of Host _drawLive)
    if (primRing && primRing.track?.analysis) {
      const T = primRing.track;
      const col = primRing.col || (T?.id ? theme.accentOf(T.id) : theme.idleAccent());
      const white = theme.lift(col, 0.3);
      if (Array.isArray(t.flashes)) {
        for (const [fi, fj, ageMs] of t.flashes) {
          const a = Math.max(0, 1 - (ageMs + elapsed * 1000) / 900);
          if (a > 0.02 && fi < T.n && fj < T.n) {
            ctx.strokeStyle = theme.css(white, 0.9 * a);
            ctx.lineWidth = 2.4;
            this._chordWorld(ctx, primRing, fi, fj);
            ctx.stroke();
          }
        }
      }
      if (t.plan && t.plan.from === T.id) {
        ctx.save();
        ctx.strokeStyle = theme.css(theme.lift(theme.mix(col, theme.songColor(t.plan.to || T.id), 0.35), 0.1), 0.88);
        ctx.lineWidth = 1.8;
        ctx.setLineDash([5, 6]);
        ctx.lineDashOffset = this.reduced ? 0 : -now / 40;
        if (Array.isArray(t.plan.jumps)) {
          for (const [src, dst] of t.plan.jumps) {
            if (src < T.n && dst < T.n) {
              this._chordWorld(ctx, primRing, src, dst);
              ctx.stroke();
            }
          }
        }
        ctx.restore();
        const exitT = this._exitTime(T, t.plan);
        if (exitT !== null) {
          const [ex, ey] = this._point(primRing, exitT, this._exitRadius(primRing.r));
          const pWave = this.reduced ? 0.6 : 0.5 + 0.5 * Math.sin(now / 200);
          ctx.strokeStyle = theme.css(theme.lift(theme.songColor(t.plan.to || T.id), 0.06), 0.5 + 0.5 * pWave);
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(ex, ey, 7 + 3 * pWave, 0, TAU);
          ctx.stroke();
        }
      }
    }

    if (t.ghost_head && t.ghost_head.alpha > 0.02) {
      const ghostRing = (t.ghost_head.on === "second" && secRing) ? secRing : primRing;
      if (ghostRing && ghostRing.track?.analysis) {
        const gDur = Math.max(30, ghostRing.track.end || 180);
        const gAng = ghostRing.rot + (t.ghost_head.rel_angle ?? 0) + (ghostRing.dir || 1) * ((TAU * elapsed) / gDur);
        this._drawHead(ctx, { ring: ghostRing, angle: gAng, beat: t.ghost_head.beat ?? 0, frac: t.ghost_head.frac ?? 0 }, t.ghost_head.alpha * 0.7, false);
      }
    }
    if (leadRing && leadRing.track?.analysis) {
      this._drawHead(ctx, { ring: leadRing, angle: ang, beat: leadBeat, frac: leadFrac }, 1, true);
    }
    this._drawRipples(ctx, now);

    // Trigger ripple ONLY once when lead light crosses into a new song (matching Host _trackCrossing)
    if (leadRingId && this._lastSatLeadId && leadRingId !== this._lastSatLeadId) {
      const cross = this._lastSatCross && now - this._lastSatCross.at < 600 ? this._lastSatCross : null;
      if (cross && !this.reduced) {
        const col = leadRing?.col || theme.songColor(leadRingId);
        this.ripples.push({ x: cross.x, y: cross.y, t0: now, col });
      }
    }
    this._lastSatLeadId = leadRingId || null;

    // 8. Position center titles & update ambient light field on Satellite
    this._drawHover(ctx);
    this._placeCenter(this.capPlace);
    if (now - this.fieldAt >= 100) {
      this.fieldAt = now;
      const root = document.documentElement.style;
      const rect = this.canvas.getBoundingClientRect();
      const vw = window.innerWidth || 1;
      const vh = window.innerHeight || 1;
      if (primRing && primRing.x !== null && primRing.y !== null) {
        root.setProperty("--key-x", `${(((rect.left + primRing.x) / vw) * 100).toFixed(1)}%`);
        root.setProperty("--key-y", `${(((rect.top + primRing.y) / vh) * 100).toFixed(1)}%`);
        root.setProperty("--key-r-px", `${Math.round(primRing.r)}px`);
      }
      const fillPlace = secRing || (two && L.b ? L.b : null);
      if (fillPlace && fillPlace.x !== null && fillPlace.y !== null) {
        root.setProperty("--fill-x", `${(((rect.left + fillPlace.x) / vw) * 100).toFixed(1)}%`);
        root.setProperty("--fill-y", `${(((rect.top + fillPlace.y) / vh) * 100).toFixed(1)}%`);
        root.setProperty("--fill-r-px", `${Math.round(fillPlace.r || (primRing ? primRing.r * 0.7 : 180))}px`);
      }
    }
  }

  _drawSatelliteHead(ctx, cx, cy, r, ang, acc, pulse) {
    const hx = cx + Math.cos(ang) * r;
    const hy = cy + Math.sin(ang) * r;
    const col = acc ? { l: acc[0], c: acc[1], h: acc[2] } : theme.idleAccent();
    const th = this._thickness(r);
    const glow = Math.max(18, r * 0.11) * (1 + 0.3 * pulse + 0.35 * (this.bass || 0)) * Math.sqrt(theme.glowGain());

    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    const g = ctx.createRadialGradient(hx, hy, 0, hx, hy, glow * 2);
    g.addColorStop(0, theme.css(theme.lift(col, 0.18), 0.85));
    g.addColorStop(0.35, theme.css(theme.lift(col, 0.08), 0.35));
    g.addColorStop(1, theme.css(col, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(hx, hy, glow * 2, 0, TAU);
    ctx.fill();

    const coronaR = Math.max(7, Math.min(14, th * 0.65)) * (1 + 0.15 * pulse);
    const cg = ctx.createRadialGradient(hx, hy, 0, hx, hy, coronaR);
    cg.addColorStop(0, "rgba(255, 255, 255, 0.95)");
    cg.addColorStop(0.45, theme.css(theme.lift(col, 0.28), 0.85));
    cg.addColorStop(1, theme.css(col, 0));
    ctx.fillStyle = cg;
    ctx.beginPath();
    ctx.arc(hx, hy, coronaR, 0, TAU);
    ctx.fill();

    ctx.globalCompositeOperation = "source-over";
    const coreR = Math.max(3, Math.min(5, th * 0.24));
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(hx, hy, coreR, 0, TAU);
    ctx.fill();
    ctx.restore();
  }

  _beatPulse(view, dt) {
    this.pulse *= Math.exp(-Math.min(0.06, dt) / 0.24);
    if (!view || this.reduced) return;
    const key = `${view.entry.track.id}:${view.entry.beat}`;
    if (key !== this.lastBeatKey) {
      this.lastBeatKey = key;
      const pos = view.entry.track.analysis.pos[view.entry.beat];
      this.pulse = Math.max(this.pulse, pos === 0 ? 1 : 0.52);
    }
  }

  // How the mix is going: 0 before the hand-over starts, 1 once the next song has it.
  _mixProgress(view) {
    const mx = this.mixNow;
    if (!view || !mx || view.now < mx.m.times[0]) return 0;
    return Math.min(1, (view.now - mx.m.times[0]) / Math.max(1e-3, mx.end - mx.m.times[0]));
  }

  // The room's colour: the playing song's, passing into the next song's as
  // the mix goes on. The page gets the same colour through CSS (_updateField).
  _roomColor(primary, view, dt) {
    const second = [...this.rings.values()].find((r) => r.role === "second");
    const nextId = second?.track.id || this.placeholder?.id || null;
    const a = primary ? theme.accentOf(primary.track.id) : theme.idleAccent();
    const target = nextId ? theme.mix(a, theme.accentOf(nextId), this._mixProgress(view)) : a;
    const k = this.reduced ? 1 : 1 - Math.exp(-dt / 0.6);
    this.accent = theme.ease(this.accent, target, k);
    this.secondCol = nextId ? theme.ease(this.secondCol, theme.songColor(nextId), k) : null;
    this.nextId = nextId;
  }

  // The live spectrum, from the analyser after the master bus. Log-spaced
  // bands, a gentle tilt so the highs register, and the volume knob taken
  // back out so the halo shows the music, not the listening level.
  _spectrum(dt) {
    const eng = this.player.engine;
    const an = eng?.analyser;
    const live = an && this.player.playing && !this.reduced;
    const rel = 1 - Math.exp(-dt / 0.2);
    if (!live) {
      for (let i = 0; i < HALO_BANDS; i++) this.bands[i] *= 1 - rel;
      this.bass *= 1 - rel;
      return;
    }
    if (!this._fbuf || this._fbuf.length !== an.frequencyBinCount) {
      this._fbuf = new Float32Array(an.frequencyBinCount);
      const hz = an.context.sampleRate / an.fftSize;
      const lo = Math.log(40), hi = Math.log(14000);
      this._edges = [];
      for (let i = 0; i <= HALO_BANDS; i++) {
        const f = Math.exp(lo + ((hi - lo) * i) / HALO_BANDS);
        this._edges.push(Math.min(an.frequencyBinCount - 1, Math.max(1, Math.round(f / hz))));
      }
      this._centre = Array.from({ length: HALO_BANDS }, (_, i) => Math.exp(lo + ((hi - lo) * (i + 0.5)) / HALO_BANDS));
    }
    an.getFloatFrequencyData(this._fbuf);
    if (!this._avg) this._avg = new Float32Array(HALO_BANDS);
    const comp = -20 * Math.log10(Math.max(1e-3, eng.master.gain.value));
    const att = 1 - Math.exp(-dt / 0.035);
    const slow = 1 - Math.exp(-dt / 1.6);
    let bass = 0, nb = 0;
    for (let i = 0; i < HALO_BANDS; i++) {
      const b0 = this._edges[i], b1 = Math.max(b0 + 1, this._edges[i + 1]);
      let s = 0;
      for (let j = b0; j < b1; j++) s += Math.pow(10, this._fbuf[j] / 10);
      const db = 10 * Math.log10(s / (b1 - b0) + 1e-12) + comp + 3 * Math.log2(this._centre[i] / 150);
      const level = Math.max(0, Math.min(1, (db + 72) / 44));
      // A dense mix keeps every band near the top: show a little of the
      // level and mostly what rises above the band's own recent average,
      // so the halo hits with the kick and the snare instead of standing still.
      this._avg[i] += (level - this._avg[i]) * slow;
      const v = Math.max(0, Math.min(1, 0.4 * level + 2.2 * (level - this._avg[i])));
      this.bands[i] += (v - this.bands[i]) * (v > this.bands[i] ? att : rel);
      if (this._centre[i] < 160) {
        bass += this.bands[i];
        nb++;
      }
    }
    this.bass = nb ? bass / nb : 0;
  }

  // The halo: the spectrum drawn around the playing loop, mirrored about the
  // playhead, lows at the playhead and highs on the far side. The music seems
  // to come out of the loop where it is being played.
  _drawHalo(ctx, head) {
    const ring = head.ring;
    if (ring.alpha < 0.05 || ring.fill < 1) return;
    let peak = 0;
    for (let i = 0; i < HALO_BANDS; i++) peak = Math.max(peak, this.bands[i]);
    if (peak < 0.02) return;
    const T = ring.track;
    const a0 = head.angle;
    const th = this._thickness(ring.r);
    const r0 = ring.r + th / 2 + 1;
    const H = ring.r * 0.1 * Math.min(1.3, theme.glowGain());
    const N = HALO_N;
    const amp = (k) => {
      const u = 1 - Math.abs((k / N) * 2 - 1); // 1 at the playhead, 0 opposite
      const x = (1 - u) * (HALO_BANDS - 1);
      const i = Math.floor(x), f = x - i;
      const v = this.bands[i] * (1 - f) + (this.bands[Math.min(HALO_BANDS - 1, i + 1)] || 0) * f;
      return v * v * (0.55 + 0.45 * u);
    };
    const col = ring.col || (T?.id ? theme.accentOf(T.id) : theme.idleAccent());
    const hi = theme.lift(col, 0.1);
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = ring.alpha;
    // A soft breath of light under the hairlines.
    const g = ctx.createRadialGradient(ring.x, ring.y, r0, ring.x, ring.y, r0 + H);
    g.addColorStop(0, theme.css(col, 0.16));
    g.addColorStop(1, theme.css(col, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    const cosA0 = Math.cos(a0), sinA0 = Math.sin(a0);
    for (let k = 0; k <= N; k++) {
      const cosTh = HALO_COS[k], sinTh = HALO_SIN[k];
      const ca = cosA0 * cosTh - sinA0 * sinTh;
      const sa = sinA0 * cosTh + cosA0 * sinTh;
      const r = r0 + amp(k) * H;
      const x = ring.x + r * ca, y = ring.y + r * sa;
      if (k) ctx.lineTo(x, y);
      else ctx.moveTo(x, y);
    }
    ctx.arc(ring.x, ring.y, r0, a0 + Math.PI + TAU, a0 + Math.PI, true);
    ctx.closePath();
    ctx.fill();
    // The spectrum itself: hairlines, like the dial's ticks, grouped by
    // brightness so the whole halo costs four strokes.
    ctx.lineWidth = 1.2;
    ctx.lineCap = "round";
    const groups = [[], [], [], []];
    for (let k = 0; k < N; k++) {
      const v = amp(k);
      if (v < 0.015) continue;
      const cosTh = HALO_COS[k], sinTh = HALO_SIN[k];
      const ca = cosA0 * cosTh - sinA0 * sinTh;
      const sa = sinA0 * cosTh + cosA0 * sinTh;
      groups[Math.min(3, Math.floor(v * 4))].push(ca, sa, v);
    }
    for (let q = 0; q < 4; q++) {
      const bars = groups[q];
      if (!bars.length) continue;
      ctx.strokeStyle = theme.css(hi, 0.3 + 0.18 * q);
      ctx.beginPath();
      for (let i = 0; i < bars.length; i += 3) {
        const c = bars[i], s = bars[i + 1], v = bars[i + 2];
        ctx.moveTo(ring.x + (r0 + 2) * c, ring.y + (r0 + 2) * s);
        ctx.lineTo(ring.x + (r0 + 3 + v * H) * c, ring.y + (r0 + 3 + v * H) * s);
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  _drawLights(ctx, primary) {
    const gain = theme.glowGain();
    for (const ring of this.rings.values()) {
      if (ring.alpha < 0.02 || ring.x === null || !ring.col) continue;
      const isP = ring === primary;
      const base = (isP ? 0.07 + 0.05 * this.pulse + 0.09 * this.bass : 0.07) * gain;

      const edgeDist = Math.min(ring.x, this.w - ring.x, ring.y, this.h - ring.y);
      const maxSafeR = Math.max(20, edgeDist - 6);
      const rOuter = Math.min(ring.r * 1.35, maxSafeR);
      const rInner = Math.min(ring.r * 0.25, rOuter * 0.4);

      const g = ctx.createRadialGradient(ring.x, ring.y, rInner, ring.x, ring.y, rOuter);
      g.addColorStop(0, theme.css(ring.col, base * ring.alpha));
      g.addColorStop(0.45, theme.css(ring.col, base * ring.alpha * 0.4));
      g.addColorStop(0.78, theme.css(ring.col, base * ring.alpha * 0.08));
      g.addColorStop(1, theme.css(ring.col, 0));

      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(ring.x, ring.y, rOuter, 0, TAU);
      ctx.fill();
    }
  }

  _drawRing(ctx, ring) {
    if (ring.alpha < 0.01 || ring.x === null) return;
    const keep = this.player?.settings?.keep ?? 0.6;
    const transLen = ring.track?.transitions?.length ?? 0;
    const baseLayerR = this.layerR || this.baseR || ring.r || 160;
    let satForcedCol = null;
    if (stageSync.isStageMirrorActive) {
      const t = stageSync.telemetry;
      if (ring.role === "primary" && t?.color_a && (!t.track_id || ring.track?.id === t.track_id)) {
        satForcedCol = { l: t.color_a[0], c: t.color_a[1], h: t.color_a[2] };
      } else if (ring.role === "second" && t?.color_b) {
        satForcedCol = { l: t.color_b[0], c: t.color_b[1], h: t.color_b[2] };
      } else if (ring.col) {
        satForcedCol = ring.col;
      }
    }
    const satHueKey = satForcedCol ? `|h${Math.round(satForcedCol.h / 2)}` : "";
    const key = `${ring.track.id}|${keep}|${transLen}|${baseLayerR.toFixed(1)}|${this.dpr || 1}|${theme.paletteVersion()}${satHueKey}`;
    if (ring.layerKey !== key) {
      ring.layer = this._buildLayer(ring.track, satForcedCol);
      ring.layerKey = key;
    }
    const L = ring.layer;
    let s = ring.r / L.RL;
    if (Math.abs(s - 1) < 0.003) s = 1;
    ctx.save();
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.globalAlpha = Math.min(1, ring.alpha);
    const px = Math.round(ring.x * this.dpr) / this.dpr;
    const py = Math.round(ring.y * this.dpr) / this.dpr;
    ctx.translate(px, py);
    ctx.rotate(ring.rot);
    ctx.scale(s, s * ring.dir);
    if (ring.fill < 1) {
      const f = easeOut(ring.fill);
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, L.S, 0, TAU * f);
      ctx.closePath();
      ctx.clip();
    }
    ctx.drawImage(L.canvas, -L.S / 2, -L.S / 2, L.S, L.S);
    ctx.restore();

    // A soft dark pool in the middle of the loop that holds the caption keeps
    // it readable over the chords (contrast, rulebook A2.1).
    if (ring === this.capPlace?.ring) {
      const a = ring.alpha * this.capPlace.dip;
      const gr = theme.ground(ring.col || theme.accentOf(ring.track.id));
      const pool = { l: 0.15, c: gr.c, h: gr.h };
      const g = ctx.createRadialGradient(ring.x, ring.y, 0, ring.x, ring.y, ring.r * 0.72);
      g.addColorStop(0, theme.css(pool, 0.86 * a));
      g.addColorStop(0.62, theme.css(pool, 0.62 * a));
      g.addColorStop(1, theme.css(pool, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(ring.x, ring.y, ring.r * 0.72, 0, TAU);
      ctx.fill();
    }

    // Minute labels stay upright while the loop turns.
    if (ring.role === "primary" && ring.alpha > 0.3 && ring.fill >= 1) {
      ctx.save();
      ctx.globalAlpha = ring.alpha * 0.7;
      ctx.fillStyle = theme.css(theme.inkOf(ring.track.id), 0.7);
      const baseR = ring._layoutR || ring.r;
      ctx.font = `400 ${Math.max(9, Math.min(11, baseR * 0.04))}px "JetBrains Mono", monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const rLab = ring.r + this._thickness(ring.r) / 2 + 8 * s + 18;
      for (let m = 1; m * 60 < ring.track.end - 8; m++) {
        const [x, y] = this._point(ring, m * 60, rLab);
        ctx.fillText(`${m}:00`, x, y);
      }
      ctx.restore();
    }
  }

  _drawPlaceholder(ctx, ph, now) {
    ctx.save();
    ctx.strokeStyle = theme.css(theme.songColor(ph.id), 0.55);
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 7]);
    ctx.lineDashOffset = this.reduced ? 0 : -now / 60;
    ctx.beginPath();
    ctx.arc(ph.x, ph.y, ph.r, 0, TAU);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = theme.css(theme.inkOf(ph.id), 0.6);
    ctx.font = '400 11px "JetBrains Mono", monospace';
    ctx.textAlign = "center";
    ctx.fillText("ĐANG TẢI", ph.x, ph.y + 4);
    ctx.restore();
  }

  // The crossing: where the two loops touch, the mix glows in both colours,
  // and its progress ring turns from this song's colour into the next one's.
  _drawCross(ctx, view, now) {
    const c = this.cross;
    const k = this._mixProgress(view);
    const primary = this.rings.get(this.primaryId);
    const ca = primary?.col || this.accent;
    const cb = this.secondCol || ca;
    const mid = this.accent || ca;
    const breathe = this.reduced ? 0.5 : 0.5 + 0.5 * Math.sin(now / 420);
    const R = (16 + 26 * k) * (1 + 0.25 * this.bass);
    const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R * 2.2);
    g.addColorStop(0, theme.css(theme.lift(mid, 0.12), 0.6 + 0.3 * k));
    g.addColorStop(0.35, theme.css(mid, (0.18 + 0.12 * breathe) * theme.glowGain()));
    g.addColorStop(1, theme.css(mid, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(c.x, c.y, R * 2.2, 0, TAU);
    ctx.fill();
    ctx.fillStyle = theme.css(theme.lift(mid, 0.3));
    ctx.beginPath();
    ctx.arc(c.x, c.y, 2.6 + 1.2 * k, 0, TAU);
    ctx.fill();
    if (k > 0) {
      const start = -Math.PI / 2;
      const cg = ctx.createConicGradient ? ctx.createConicGradient(start, c.x, c.y) : null;
      if (cg) {
        cg.addColorStop(0, theme.css(theme.lift(ca, 0.06), 0.95));
        cg.addColorStop(Math.max(0.01, k), theme.css(theme.lift(theme.mix(ca, cb, k), 0.06), 0.95));
        cg.addColorStop(1, theme.css(cb, 0.95));
      }
      ctx.strokeStyle = cg || theme.css(theme.lift(mid, 0.06), 0.9);
      ctx.lineWidth = 2;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.arc(c.x, c.y, 11, start, start + TAU * k);
      ctx.stroke();
      ctx.lineCap = "butt";
    }

    // Specialized visual transitions by mix type
    const secondTr = this._roles(view).secondTr;
    const trType = secondTr?.type || (this.mixNow?.blend ? "blend" : "fade");

    if (trType === "riser" || trType === "sweeper") {
      ctx.save();
      ctx.translate(c.x, c.y);
      ctx.rotate((now / 180) * (1 + 2 * k));
      for (let s = 0; s < 6; s++) {
        const ang = (s * TAU) / 6;
        const dist = (8 + 22 * k) * (1 + 0.15 * Math.sin(now / 120 + s));
        ctx.fillStyle = theme.css(theme.lift(cb, 0.25), 0.85 * (0.3 + 0.7 * k));
        ctx.beginPath();
        ctx.arc(Math.cos(ang) * dist, Math.sin(ang) * dist, 1.8 + k, 0, TAU);
        ctx.fill();
      }
      ctx.restore();
    } else if (trType === "echo" || trType === "wash") {
      for (let w = 1; w <= 3; w++) {
        const pulse = ((now / 600 + w * 0.33) % 1);
        ctx.strokeStyle = theme.css(theme.lift(mid, 0.18), (1 - pulse) * 0.45 * (0.3 + 0.7 * k));
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(c.x, c.y, (12 + 38 * pulse) * (1 + 0.15 * this.bass), 0, TAU);
        ctx.stroke();
      }
    } else if (trType === "drop" || trType === "cut") {
      const shock = (0.5 + 0.5 * Math.sin(now / 100)) * this.bass;
      ctx.strokeStyle = theme.css(theme.lift(ca, 0.35), (0.4 + 0.6 * shock) * (0.4 + 0.6 * k));
      ctx.lineWidth = 2 + shock * 2.5;
      ctx.beginPath();
      ctx.arc(c.x, c.y, R * 1.35, 0, TAU);
      ctx.stroke();
    } else {
      // Ethereal glowing aura for fade / blend
      const auraG = ctx.createRadialGradient(c.x, c.y, 2, c.x, c.y, R * 1.8);
      auraG.addColorStop(0, theme.css(theme.lift(mid, 0.2), 0.45 * (1 + breathe * 0.3)));
      auraG.addColorStop(1, theme.css(mid, 0));
      ctx.fillStyle = auraG;
      ctx.beginPath();
      ctx.arc(c.x, c.y, R * 1.8, 0, TAU);
      ctx.fill();
    }

    // Harmonic Camelot Badge at crossing point
    const second = [...this.rings.values()].find((r) => r.role === "second");
    if (primary && second && second.alpha > 0.25) {
      const keyA = primary.track?.analysis?.key_camelot;
      const keyB = second.track?.analysis?.key_camelot;
      if (keyA && keyB) {
        const isHover = this.hover?.kind === "cross";
        const badgeY = c.y + (this.w >= this.h * 1.05 ? 28 : 30);
        ctx.save();
        ctx.font = `600 10px "JetBrains Mono", monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const text = `${keyA} ⇄ ${keyB}`;
        const tw = ctx.measureText(text).width;
        const bw = Math.max(60, tw + 14);
        const bh = 18;
        ctx.fillStyle = theme.css(theme.ground(mid), isHover ? 0.95 : 0.8);
        ctx.strokeStyle = theme.css(theme.lift(mid, 0.25), isHover ? 0.95 : 0.5);
        ctx.lineWidth = isHover ? 1.5 : 1;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(c.x - bw / 2, badgeY - bh / 2, bw, bh, 9);
        else ctx.rect(c.x - bw / 2, badgeY - bh / 2, bw, bh);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = theme.css(theme.lift(mid, 0.45), isHover ? 1 : 0.9);
        ctx.fillText(text, c.x, badgeY);
        ctx.restore();
      }
    }
  }

  _drawLive(ctx, ring, view, now) {
    const T = ring.track;
    const p = this.player;

    // New audible events start a flash along the jump that was taken.
    for (const ev of p.recentEvents(this.lastEventT)) {
      if (ev.kind === "jump" && ev.track === T) this.flashes.push({ i: ev.from, j: ev.beat, t0: now });
    }
    this.lastEventT = view.now;
    this.flashes = this.flashes.filter((f) => now - f.t0 < 900);
    const col = ring.col || (T?.id ? theme.accentOf(T.id) : theme.idleAccent());
    const white = theme.lift(col, 0.3);
    for (const f of this.flashes) {
      const a = 1 - (now - f.t0) / 900;
      ctx.strokeStyle = theme.css(white, 0.9 * a);
      ctx.lineWidth = 2.4;
      this._chordWorld(ctx, ring, f.i, f.j);
      ctx.stroke();
    }

    // The route the player will take to the planned exit: a bright thread
    // that turns toward the next song's colour.
    const plan = p.plan;
    if (plan && plan.from === T.id) {
      ctx.save();
      ctx.strokeStyle = theme.css(theme.lift(theme.mix(col, theme.songColor(plan.tr.to), 0.35), 0.1), 0.88);
      ctx.lineWidth = 1.8;
      ctx.setLineDash([5, 6]);
      ctx.lineDashOffset = this.reduced ? 0 : -now / 40;
      for (const [src, dst] of plan.jumps) {
        this._chordWorld(ctx, ring, src, dst);
        ctx.stroke();
      }
      ctx.restore();
      const t = this._exitTime(T, plan.tr);
      if (t !== null) {
        const [x, y] = this._point(ring, t, this._exitRadius(ring.r));
        const pulse = this.reduced ? 0.6 : 0.5 + 0.5 * Math.sin(now / 200);
        ctx.strokeStyle = theme.css(theme.lift(theme.songColor(plan.tr.to), 0.06), 0.5 + 0.5 * pulse);
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, 7 + 3 * pulse, 0, TAU);
        ctx.stroke();
      }
    }

    // The light, and the ghost it leaves on the song it has crossed out of.
    const { lead, ghost } = this.heads;
    if (ghost && ghost.alpha > 0.02) this._drawHead(ctx, ghost, ghost.alpha * 0.7, false);
    if (lead) this._drawHead(ctx, lead, 1, true);
    this._drawRipples(ctx, now);
  }

  // A playhead: a pure optical point of light on the loop with an ambient
  // bloom and a crisp core, identical across Host and Satellite stages.
  _drawHead(ctx, h, alpha, full) {
    const ring = h.ring;
    if (!ring || ring.x === null || ring.y === null) return;
    const T = ring?.track;
    const col = ring.col || (T?.id ? theme.accentOf(T.id) : theme.idleAccent());
    const hx = ring.x + ring.r * Math.cos(h.angle), hy = ring.y + ring.r * Math.sin(h.angle);
    const a = Math.min(1, ring.alpha ?? 1) * alpha;
    const pulse = Math.min(1.2, this.pulse || 0);
    const bass = Math.min(1.2, this.bass || 0);
    ctx.save();
    ctx.globalAlpha = a;
    if (full) {
      const glow = (15 + 7 * pulse + 9 * bass) * Math.sqrt(theme.glowGain());
      const g = ctx.createRadialGradient(hx, hy, 0, hx, hy, glow * 2);
      g.addColorStop(0, theme.css(theme.lift(col, 0.14), 0.88));
      g.addColorStop(0.4, theme.css(theme.lift(col, 0.06), 0.32));
      g.addColorStop(1, theme.css(col, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(hx, hy, glow * 2, 0, TAU);
      ctx.fill();
    }
    const coreGlowR = (full ? 6.5 : 4.2) * (1 + 0.12 * pulse);
    const cg = ctx.createRadialGradient(hx, hy, 0, hx, hy, coreGlowR);
    cg.addColorStop(0, "rgba(255, 255, 255, 0.95)");
    cg.addColorStop(0.5, theme.css(theme.lift(col, 0.35), 0.85));
    cg.addColorStop(1, theme.css(col, 0));
    ctx.fillStyle = cg;
    ctx.beginPath();
    ctx.arc(hx, hy, coreGlowR, 0, TAU);
    ctx.fill();

    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(hx, hy, full ? 2.8 : 2.0, 0, TAU);
    ctx.fill();
    ctx.restore();
  }

  // The moment the light crosses into the next loop, the crossing rings out
  // once in the next song's colour.
  _trackCrossing(now) {
    const lead = this.heads.lead;
    const id = lead ? lead.ring.track.id : null;
    // A cut or a fade hands over in the frame where the ∞ comes apart, so
    // the crossing is remembered for a moment.
    const cross = this.lastCross && now - this.lastCross.at < 300 ? this.lastCross : null;
    if (id && this.leadId && id !== this.leadId && cross && !this.reduced) {
      this.ripples.push({ x: cross.x, y: cross.y, t0: now, col: lead.ring.col || theme.songColor(id) });
    }
    this.leadId = id;
    if (this.cross) this.lastCross = { ...this.cross, at: now };
  }

  _drawRipples(ctx, now) {
    this.ripples = this.ripples.filter((r) => now - r.t0 < 1100);
    for (const r of this.ripples) {
      const u = (now - r.t0) / 1100;
      const e = easeOut(u);
      ctx.strokeStyle = theme.css(theme.lift(r.col, 0.2), 0.85 * (1 - u));
      ctx.lineWidth = 2.5 * (1 - u) + 0.5;
      ctx.beginPath();
      ctx.arc(r.x, r.y, 8 + 62 * e, 0, TAU);
      ctx.stroke();

      // Second harmonic ripple wave
      ctx.strokeStyle = theme.css(theme.lift(r.col, 0.35), 0.45 * (1 - u * u));
      ctx.lineWidth = 1.4 * (1 - u);
      ctx.beginPath();
      ctx.arc(r.x, r.y, 4 + 38 * e, 0, TAU);
      ctx.stroke();
    }
  }

  // ------------------------------------------------------------------ idle
  //
  // The waiting instrument, before any song plays: the ∞ as two ghost loops,
  // each made like a real one (faint beats whose weight follows a loudness
  // contour, a stippled halo of dust), the left in the room's colour, the
  // right in a colour drifting round the mood wheel: a song still to come.
  // They breathe slowly; jump chords come and go inside them; a light runs
  // the ∞ with a tail and a few sparks, takes each loop's colour as it crosses
  // the middle, and leaves a ripple there. Under the pointer the path glows.
  // Reduced motion: the same picture, still.

  // A little above the middle: the caption hangs under it, and the two weigh as one.
  _idleGeom() {
    const sc = this.scale || 1.0;
    const a = Math.round(Math.min(this.w * 0.36, this.h * 0.95) * sc);
    return { a, cx: Math.round(this.w / 2), cy: Math.round(this.h * 0.42), th: Math.max(3, Math.round(a * 0.024)) };
  }

  // A point of the lemniscate (u: 0..2π; the right loop where cos u > 0, the
  // crossing at u = ±π/2), and the unit normal there.
  _idlePt(g, u) {
    const s = Math.sin(u), c = Math.cos(u);
    const d = 1 + s * s;
    return [g.cx + (g.a * c) / d, g.cy + (g.a * s * c) / d];
  }

  _idleNormal(g, u) {
    const [x1, y1] = this._idlePt(g, u - 0.002), [x2, y2] = this._idlePt(g, u + 0.002);
    const len = Math.hypot(x2 - x1, y2 - y1) || 1;
    return [-(y2 - y1) / len, (x2 - x1) / len];
  }

  // The colour of the loop still to come: the mood theme's wheel turning
  // slowly (once in 90 s) from a third of the way round the room's colour;
  // the amber preset keeps its one colour.
  _idleSecond(colA, t) {
    if (theme.themeName() === "amber") return colA;
    return theme.fit({ l: colA.l, c: Math.max(colA.c, 0.1), h: (colA.h + 110 + 360 * ((t / 90) % 1)) % 360 });
  }

  // One ghost loop drawn once (redrawn when its colour has moved a few degrees).
  _idleLayer(side, col) {
    const st = this.idleSt;
    const layerScale = Math.min(Math.max(Math.round(this.dpr * 2), 2), 4);
    const sc = (this.scale || 1.0).toFixed(2);
    const key = `${this.w}x${this.h}@${layerScale}|${Math.round(col.h / 3)}|${col.l.toFixed(2)}|${theme.themeName()}|${sc}`;
    const have = st.layers[side];
    if (have && have.key === key) return have.canvas;
    const g = this._idleGeom();
    const c = have?.canvas || document.createElement("canvas");
    c.width = Math.round(this.w * layerScale);
    c.height = Math.round(this.h * layerScale);
    const ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.setTransform(layerScale, 0, 0, layerScale, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);
    const rnd = seeded(side > 0 ? 7741 : 3319);
    const N = 112; // beats round the loop
    const u0 = side > 0 ? -Math.PI / 2 : Math.PI / 2;
    let walk = 0.5;
    for (let i = 0; i < N; i++) {
      const ua = u0 + (Math.PI * i) / N, ub = u0 + (Math.PI * (i + 1)) / N;
      walk = Math.max(0, Math.min(1, walk + (rnd() - 0.5) * 0.3));
      // Thin to nothing toward the crossing, where the two loops meet.
      const end = Math.pow(Math.sin((Math.PI * (i + 0.5)) / N), 0.6);
      const loud = (0.3 + 0.7 * walk) * end;
      const tone = { l: col.l - 0.05 + 0.1 * rnd(), c: col.c, h: col.h + (rnd() - 0.5) * 26 };
      ctx.strokeStyle = theme.css(tone, 0.12 + 0.42 * loud);
      ctx.lineWidth = g.th * (i % 4 === 0 ? 1 : 0.74) * (0.7 + 0.3 * end);
      ctx.beginPath();
      for (let q = 0; q <= 3; q++) {
        const [x, y] = this._idlePt(g, ua + ((ub - ua) * q) / 3 - (q === 3 ? 0.002 : 0));
        if (q) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
      }
      ctx.stroke();
      const count = 2 + Math.round(7 * loud);
      ctx.fillStyle = theme.css(tone);
      for (let k = 0; k < count; k++) {
        const u = ua + rnd() * (ub - ua);
        const [x, y] = this._idlePt(g, u);
        const [nx, ny] = this._idleNormal(g, u);
        const spread = (rnd() + rnd() + rnd() - 1.5) / 1.5;
        const off = spread * g.th * 2.6;
        ctx.globalAlpha = (0.1 + 0.4 * rnd() * (1 - Math.abs(spread))) * end;
        ctx.beginPath();
        ctx.arc(x + nx * off, y + ny * off, 0.5 + rnd() * 0.9, 0, TAU);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
    st.layers[side] = { key, canvas: c };
    return c;
  }

  // Jump chords inside a loop: each lives 9-15 s, fading in and out, then
  // comes back between two other points of the same loop.
  _idleChord(side, t) {
    const span = 0.5 + Math.random() * 1.6;
    const ua = (side > 0 ? -Math.PI / 2 : Math.PI / 2) + 0.25 + Math.random() * (Math.PI - 0.5 - span);
    return { side, ua, ub: ua + span, t0: t, life: 9 + Math.random() * 6 };
  }

  _drawIdle(ctx, now, alpha) {
    const g = this._idleGeom();
    const t = now / 1000;
    const still = this.reduced;
    const st = this.idleSt || (this.idleSt = { layers: {}, chords: [], sparks: [], ripples: [], lastCos: null, lastT: t });
    if (!st.chords.length) {
      for (const side of [-1, 1]) {
        for (let k = 0; k < 6; k++) {
          const ch = this._idleChord(side, t);
          ch.t0 -= Math.random() * ch.life; // already under way, not all at once
          st.chords.push(ch);
        }
      }
    }
    const colA = this.accent || theme.idleAccent();
    const colB = this._idleSecond(colA, still ? 0 : t);
    const loopCol = (side) => (side > 0 ? colB : colA);
    // The light's colour along the ∞: one loop's, then the other's across the middle.
    const colAt = (u) => theme.mix(colA, colB, clamp01(0.5 + 3 * Math.cos(u)));
    const breath = still ? 0.5 : 0.5 - 0.5 * Math.cos((TAU * t) / 4.8);

    ctx.save();
    // The two ghost loops, breathing.
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.globalAlpha = alpha * (0.76 + 0.24 * breath);
    for (const side of [-1, 1]) ctx.drawImage(this._idleLayer(side, loopCol(side)), 0, 0, this.w, this.h);

    // The path itself, a hairline.
    ctx.globalAlpha = alpha;
    ctx.lineWidth = 1;
    for (const side of [-1, 1]) {
      ctx.strokeStyle = theme.css(theme.lift(loopCol(side), 0.12), 0.18);
      ctx.beginPath();
      const u0 = side > 0 ? -Math.PI / 2 : Math.PI / 2;
      for (let i = 0; i <= 120; i++) {
        const [x, y] = this._idlePt(g, u0 + (Math.PI * i) / 120);
        if (i) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
      }
      ctx.stroke();
    }

    // Jump chords, curving in toward the loop's middle.
    for (let k = 0; k < st.chords.length; k++) {
      let ch = st.chords[k];
      if (!still && t - ch.t0 > ch.life) ch = st.chords[k] = this._idleChord(ch.side, t);
      const life = still ? 0.5 : (t - ch.t0) / ch.life;
      const o = Math.sin(Math.PI * clamp01(life));
      if (o < 0.02) continue;
      const [x1, y1] = this._idlePt(g, ch.ua), [x2, y2] = this._idlePt(g, ch.ub);
      const mx = g.cx + ch.side * g.a * 0.52, my = g.cy;
      ctx.strokeStyle = theme.css(theme.lift(loopCol(ch.side), 0.06), 0.15 * o);
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.quadraticCurveTo(mx + ((x1 + x2) / 2 - mx) * 0.2, my + ((y1 + y2) / 2 - my) * 0.2, x2, y2);
      ctx.stroke();
    }

    // Under the pointer, the nearest stretch of the path lights up.
    if (this.pointer && !still) {
      let best = null;
      for (let i = 0; i < 240; i++) {
        const u = (TAU * i) / 240;
        const [x, y] = this._idlePt(g, u);
        const d = Math.hypot(x - this.pointer.x, y - this.pointer.y);
        if (!best || d < best.d) best = { d, x, y, u };
      }
      if (best.d < 70) {
        const k = 1 - best.d / 70;
        const glow = ctx.createRadialGradient(best.x, best.y, 0, best.x, best.y, 40);
        glow.addColorStop(0, theme.css(theme.lift(colAt(best.u), 0.1), 0.35 * k));
        glow.addColorStop(1, theme.css(colAt(best.u), 0));
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(best.x, best.y, 40, 0, TAU);
        ctx.fill();
      }
    }

    // The light: once round the ∞ in 8 s, its tail fading and thinning.
    const uH = still ? 0.6 : (t / 8) * TAU;
    const TAIL = 64;
    let prev = this._idlePt(g, uH);
    for (let k = 1; k <= TAIL; k++) {
      const u = uH - k * 0.016;
      const p = this._idlePt(g, u);
      const f = 1 - k / TAIL;
      ctx.strokeStyle = theme.css(colAt(u), 0.75 * f * f);
      ctx.lineWidth = 0.6 + 2.6 * f;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(prev[0], prev[1]);
      ctx.lineTo(p[0], p[1]);
      ctx.stroke();
      prev = p;
    }
    const [hx, hy] = this._idlePt(g, uH);
    const colH = colAt(uH);
    const halo = ctx.createRadialGradient(hx, hy, 0, hx, hy, 30);
    halo.addColorStop(0, theme.css(theme.lift(colH, 0.14), 0.9));
    halo.addColorStop(0.35, theme.css(colH, 0.35));
    halo.addColorStop(1, theme.css(colH, 0));
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(hx, hy, 30, 0, TAU);
    ctx.fill();
    ctx.fillStyle = theme.css(theme.lift(colH, 0.18));
    ctx.beginPath();
    ctx.arc(hx, hy, 2.4, 0, TAU);
    ctx.fill();

    if (!still) {
      const dt = Math.min(0.1, Math.max(0, t - st.lastT));
      st.lastT = t;
      // A few sparks shed by the light, drifting just off the path.
      if (Math.random() < dt * 12 && st.sparks.length < 24) {
        const [nx, ny] = this._idleNormal(g, uH);
        const side = Math.random() < 0.5 ? -1 : 1;
        const v = 3 + Math.random() * 7;
        st.sparks.push({ x: hx, y: hy, vx: nx * v * side + (Math.random() - 0.5) * 3, vy: ny * v * side + (Math.random() - 0.5) * 3,
          t0: t, col: colH });
      }
      // A ripple where the light crosses the middle (every 4 s).
      const cs = Math.cos(uH);
      if (st.lastCos != null && Math.sign(cs) !== Math.sign(st.lastCos)) st.ripples.push({ t0: t, col: colH });
      st.lastCos = cs;
      for (const s of st.sparks) {
        s.x += s.vx * dt;
        s.y += s.vy * dt;
      }
      st.sparks = st.sparks.filter((s) => t - s.t0 < 1);
      st.ripples = st.ripples.filter((r) => t - r.t0 < 1.6);
      for (const s of st.sparks) {
        const f = 1 - (t - s.t0);
        ctx.fillStyle = theme.css(theme.lift(s.col, 0.1), 0.45 * f);
        ctx.beginPath();
        ctx.arc(s.x, s.y, 0.3 + 0.8 * f, 0, TAU);
        ctx.fill();
      }
      for (const r of st.ripples) {
        const e = easeOut((t - r.t0) / 1.6);
        ctx.strokeStyle = theme.css(theme.lift(r.col, 0.1), 0.32 * (1 - e));
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, 6 + 58 * e, 0, TAU);
        ctx.stroke();
      }
    }
    ctx.restore();
    // The caption hangs from just under the ∞ (its lowest point is a / 2√2,
    // plus the dust around it), whatever its height.
    this.idleCaptionY = g.cy + g.a * 0.354 + 3 * g.th + 22;
  }

  // ---------------------------------------------------------------- caption

  _placeCenter(place) {
    const el = this.center;
    if (!el) return;
    const ring = place?.ring || null;
    const trackId = ring?.track?.id || null;
    if (trackId !== this._captionId) {
      this._captionId = trackId;
      if (!stageSync.isStageMirrorActive) {
        this.onCaption(); // the page writes the new song's title before it fades in
      }
    }
    let x, y, w, size, o;
    if (ring && ring.alpha > 0.05) {
      const rCap = ring._layoutR || ring.r;
      x = ring.x;
      y = ring.y;
      w = rCap * 1.32;
      size = Math.max(15, Math.min(38, rCap * 0.125));
      o = Math.min(1, ring.alpha * (ring.fill < 1 ? easeOut(ring.fill) : 1)) * place.dip;
    } else {
      x = this.w / 2;
      y = Math.min(this.h - 60, this.idleCaptionY || this.h * 0.78);
      w = Math.min(this.w * 0.8, 520);
      size = Math.max(16, Math.min(28, this.w * 0.03));
      o = 1;
    }
    const mode = ring ? "ring" : "idle";
    const key = `${mode}|${x.toFixed(1)}|${y.toFixed(1)}|${w.toFixed(0)}|${size.toFixed(1)}|${o.toFixed(2)}`;
    if (key === this._centerKey) return;
    this._centerKey = key;
    el.style.setProperty("--rc-x", `${x}px`);
    el.style.setProperty("--rc-y", `${y}px`);
    el.style.setProperty("--rc-w", `${w}px`);
    el.style.setProperty("--rc-size", `${size}px`);
    el.style.setProperty("--rc-o", o.toFixed(2));
    el.dataset.mode = mode;
    // Small loops (phones, the ∞ layout) keep the title and drop the details.
    el.dataset.size = ring && ring.r < 125 ? "s" : "m";
  }

  // The page's light field follows the loops (atmospheric field, ~10 updates/s).
  _updateField(primary, now) {
    if (now - this.fieldAt < 100) return;
    this.fieldAt = now;
    const root = document.documentElement.style;
    const rect = this.canvas.getBoundingClientRect();
    const vw = window.innerWidth || 1;
    const vh = window.innerHeight || 1;
    if (primary && primary.x !== null && primary.y !== null) {
      root.setProperty("--key-x", `${(((rect.left + primary.x) / vw) * 100).toFixed(1)}%`);
      root.setProperty("--key-y", `${(((rect.top + primary.y) / vh) * 100).toFixed(1)}%`);
      root.setProperty("--key-r-px", `${Math.round(primary.r)}px`);
    }
    const second = [...this.rings.values()].find((r) => r.role === "second");
    const place = second || this.placeholder;
    if (place && place.x !== null && place.y !== null) {
      root.setProperty("--fill-x", `${(((rect.left + place.x) / vw) * 100).toFixed(1)}%`);
      root.setProperty("--fill-y", `${(((rect.top + place.y) / vh) * 100).toFixed(1)}%`);
      root.setProperty("--fill-r-px", `${Math.round(place.r || (primary ? primary.r * 0.7 : 180))}px`);
    }
    // CSS eases these over a second or so; the targets go out unsmoothed.
    const view = this.player.audible();
    const a = primary ? theme.accentOf(primary.track.id) : theme.idleAccent();
    const target = this.nextId ? theme.mix(a, theme.accentOf(this.nextId), this._mixProgress(view)) : a;
    const second2 = this.nextId ? theme.songColor(this.nextId) : null;
    theme.applyPage(target, second2, this.nextId ? 0.1 * theme.glowGain() : 0);
    root.setProperty("--pulse", Math.min(1.4, 0.6 * this.pulse + 0.9 * this.bass).toFixed(2));

    // Continuously broadcast real-time telemetry to satellite screens & lighting
    this._broadcastHostTelemetry();
  }

  _broadcastHostTelemetry() {
    if (stageSync.isSatellite || stageSync.isClusterFollower) return;
    const view = this.player?.audible();
    const primary = this.primaryId ? this.rings.get(this.primaryId) : null;
    const activeTrack =
      (primary && primary.track) ||
      (this.player?.cur ? this.player.cur.track : null) ||
      (this.player?._switchingTrack && this.player._switchingTrack.analysis ? this.player._switchingTrack : null);
    const second = [...this.rings.values()].find((r) => r.role === "second");
    const nextId = second?.track.id || this.placeholder?.id || null;
    const activeMood = activeTrack?.analysis?.mood || activeTrack?.meta?.mood || null;
    const nextMood = second?.track?.analysis?.mood || second?.track?.meta?.mood || null;
    const a = activeTrack ? theme.accentOf(activeTrack.id, activeMood) : theme.idleAccent();
    const target = nextId ? theme.mix(a, theme.accentOf(nextId, nextMood), this._mixProgress(view)) : a;
    const second2 = nextId ? theme.songColor(nextId, nextMood) : null;
    const g = theme.ground(target);

    const uiScaleVal = parseFloat(document.documentElement.style.getPropertyValue("--ui-scale")) || 1.0;
    const sVolEl = document.getElementById("s-vol");
    const btnMuteEl = document.getElementById("btn-mute");
    const btnKhoEl = document.getElementById("btn-kho");
    const btnRecEl = document.getElementById("btn-record");
    const btnMicEl = document.getElementById("btn-karaoke-mic");
    const btnTimerEl = document.getElementById("btn-timer");
    const btnNightEl = document.getElementById("btn-night");
    const sLyricsEl = document.getElementById("s-lyrics");
    const lyricsBox = document.getElementById("ambient-lyrics");
    const lyricsOn = sLyricsEl ? Boolean(sLyricsEl.checked) : true;
    const lyricsVisible = Boolean(lyricsOn && lyricsBox && !lyricsBox.hidden);
    const commonCfg = {
      app_ver: "v174",
      focused: typeof document !== "undefined" && typeof document.hasFocus === "function" ? document.hasFocus() : false,
      theme: theme.themeName(),
      glow: theme.getGlow(),
      viz_scale: this.scale || 1.0,
      ui_scale: uiScaleVal,
      beat_pulse: this.beatPulse !== false,
      keep: this.player?.settings?.keep ?? 0.6,
      night: document.body.classList.contains("is-night"),
      night_visible: btnNightEl ? !btnNightEl.hidden : false,
      locked: this.player?.settings?.mode === "single",
      kho_visible: btnKhoEl ? !btnKhoEl.hidden : false,
      kho_pressed: btnKhoEl?.getAttribute("aria-pressed") === "true",
      recording: btnRecEl?.getAttribute("aria-pressed") === "true",
      rec_label: document.getElementById("record-label")?.textContent || "Thu âm",
      vocal_mode: this.player?.vocalMode || "full",
      vocal_label: document.getElementById("vocal-mode-label")?.textContent || "Gốc",
      mic_active: btnMicEl?.dataset.active === "true",
      timer_active: btnTimerEl?.getAttribute("data-active") === "true",
      timer_badge: document.getElementById("timer-badge")?.textContent || "Tắt",
      eq_mode: this.player?.engine?.eqMode || "flat",
      eq_badge: document.getElementById("eq-badge")?.textContent || "Chuẩn",
      volume: sVolEl ? +sVolEl.value : (this.player?.engine?.master?.gain?.value ?? 0.85),
      muted: btnMuteEl?.dataset.muted === "true",
      vol_level: btnMuteEl?.dataset.level || "high",
      next_html: document.getElementById("next-info")?.innerHTML || "",
      ro_tl_html: document.getElementById("ro-tl")?.innerHTML || "",
      ro_tr_html: document.getElementById("ro-tr")?.innerHTML || "",
      history_html: document.getElementById("history")?.innerHTML || "",
      rc_kicker_html: document.getElementById("rc-kicker")?.innerHTML || "",
      rc_title_html: document.getElementById("rc-title")?.innerHTML || "",
      rc_meta_html: document.getElementById("rc-meta")?.innerHTML || "",
      lyrics_enabled: lyricsOn,
      lyric_prev: lyricsVisible ? (document.getElementById("lyric-line-prev")?.textContent || "") : "",
      lyric_cur: lyricsVisible ? (document.getElementById("lyric-line-cur")?.textContent || "") : "",
      lyric_next: lyricsVisible ? (document.getElementById("lyric-line-next")?.textContent || "") : "",
    };

    if (activeTrack) {
      const primRingObj = primary || (this.rings.get(activeTrack.id) || {
        x: this.w / 2, y: this.h / 2, r: this.baseR || 160, rot: -Math.PI / 2, dir: 1, alpha: 1, fill: 1
      });
      const leadAngle = this.heads?.lead?.angle ?? primRingObj.rot ?? 0;
      const compactBands = this.bands ? Array.from(this.bands.slice(0, HALO_BANDS)).map((v) => Math.round(v * 1000) / 1000) : [];
      const s = splitTitle(activeTrack.meta?.title || activeTrack.title || activeTrack.id, activeTrack.meta?.channel || "");
      const primTitle = s.title || activeTrack.meta?.title || activeTrack.id;
      const primArtist = s.artist || activeTrack.meta?.artist || "";
      const primBpm = activeTrack.meta?.bpm || activeTrack.analysis?.bpm || 120;
      const primCamelot = activeTrack.meta?.camelot || activeTrack.analysis?.camelot || "";
      const primKey = activeTrack.analysis?.key || activeTrack.meta?.key || "";
      const secondTrack = second?.track || null;
      const s2 = secondTrack ? splitTitle(secondTrack.meta?.title || secondTrack.title || secondTrack.id, secondTrack.meta?.channel || "") : null;
      const secondTitle = s2 ? (s2.title || secondTrack.id) : "";
      const secondArtist = s2 ? (s2.artist || secondTrack.meta?.artist || "") : "";
      const secondBpm = secondTrack ? (secondTrack.meta?.bpm || secondTrack.analysis?.bpm || 120) : 120;
      const secondCamelot = secondTrack ? (secondTrack.meta?.camelot || secondTrack.analysis?.camelot || "") : "";

      const enabledIds = this.player?.metas ? this.player.metas.filter((m) => m.enabled !== false).map((m) => m.id) : [];
      const nowPerf = performance.now();
      const activeFlashes = Array.isArray(this.flashes)
        ? this.flashes
            .filter((f) => nowPerf - f.t0 < 900)
            .slice(-4)
            .map((f) => [f.i, f.j, Math.round(nowPerf - f.t0)])
        : [];
      const activePlan = (this.player?.plan && this.player.plan.from === activeTrack.id && this.player.plan.tr)
        ? {
            from: this.player.plan.from,
            to: this.player.plan.tr.to,
            type: this.player.plan.tr.type,
            a: this.player.plan.tr.a,
            b: this.player.plan.tr.b,
            i: this.player.plan.tr.i,
            j: this.player.plan.tr.j,
            jumps: this.player.plan.jumps ? Array.from(this.player.plan.jumps) : [],
          }
        : null;

      const roles = this._roles(view);
      const two = Boolean(this.cross || second || this.placeholder);
      const mixProg = view ? this._mixProgress(view) : 0;
      const swapProg = (second && (this.mixNow || (this.player?.cur && activeTrack && this.player.cur.track.id !== activeTrack.id)))
        ? mixProg
        : 0;
      const hostL = this._layout(two, swapProg);
      const trType = roles.secondTr?.type || (this.mixNow?.blend ? "blend" : "fade");
      const leadRing = this.heads?.lead?.ring || primRingObj;
      const leadIsSecond = Boolean(second && leadRing === second);
      const ghostRing = this.heads?.ghost?.ring || null;

      const isPaused = !this.player?.playing;
      stageSync.broadcastTelemetry({
        type: "telemetry",
        mode: isPaused ? "paused" : "ring",
        ...commonCfg,
        track_id: activeTrack.id,
        title: primTitle,
        artist: primArtist,
        bpm: primBpm,
        camelot: primCamelot,
        key: primKey,
        enabled_ids: enabledIds,
        flashes: activeFlashes,
        plan: activePlan,
        two,
        swap_prog: swapProg,
        face_a: hostL.a?.face ?? 0,
        face_b: hostL.b?.face ?? 0,
        tr_type: trType,
        placeholder: this.placeholder ? { id: this.placeholder.id } : null,
        prefetch_ids: Array.isArray(this.player?.prefetchIds) ? this.player.prefetchIds.slice(0, 4) : [],
        lead_head: this.heads?.lead ? {
          on: leadIsSecond ? "second" : "primary",
          beat: this.heads.lead.beat ?? 0,
          frac: this.heads.lead.frac ?? 0,
          angle: this.heads.lead.angle ?? 0,
          rel_angle: (this.heads.lead.angle ?? 0) - (leadRing?.rot ?? 0),
        } : null,
        ghost_head: (this.heads?.ghost && this.heads.ghost.alpha > 0.02) ? {
          on: (second && ghostRing === second) ? "second" : "primary",
          beat: this.heads.ghost.beat ?? 0,
          frac: this.heads.ghost.frac ?? 0,
          angle: this.heads.ghost.angle ?? 0,
          rel_angle: (this.heads.ghost.angle ?? 0) - (ghostRing?.rot ?? 0),
          alpha: this.heads.ghost.alpha ?? 0,
        } : null,
        cap_on: (second && this.capPlace?.ring === second) ? "second" : "primary",
        cap_dip: this.capPlace?.dip ?? 1,
        acc: [target.l, target.c, target.h],
        acc2: second2 ? [second2.l, second2.c, second2.h] : [target.l, target.c, target.h],
        color_a: [a.l, a.c, a.h],
        color_b: second2 ? [second2.l, second2.c, second2.h] : null,
        is_transitioning: Boolean(nextId && second2),
        progress: mixProg,
        ground: [g.h, g.c],
        fill_a: nextId ? 0.1 * theme.glowGain() : 0,
        pulse: isPaused ? 0 : (this.pulse || 0),
        bass: isPaused ? 0 : (this.bass || 0),
        peak: isPaused ? 0 : (this.bands ? Math.max(...this.bands) : 0),
        bands: compactBands,
        angle: leadAngle,
        rot: primRingObj.rot,
        dir: primRingObj.dir,
        beat: this.heads?.lead?.beat ?? 0,
        frac: this.heads?.lead?.frac ?? 0,
        primary: {
          id: activeTrack.id,
          title: primTitle,
          artist: primArtist,
          bpm: primBpm,
          camelot: primCamelot,
          key: primKey,
          x_rel: primRingObj.x / Math.max(1, this.w),
          y_rel: primRingObj.y / Math.max(1, this.h),
          r_rel: primRingObj.r / Math.max(1, Math.min(this.w, this.h)),
          rot: primRingObj.rot,
          dir: primRingObj.dir,
          alpha: primRingObj.alpha,
          fill: primRingObj.fill,
        },
        second: secondTrack ? {
          id: secondTrack.id,
          title: secondTitle,
          artist: secondArtist,
          bpm: secondBpm,
          camelot: secondCamelot,
          x_rel: second.x / Math.max(1, this.w),
          y_rel: second.y / Math.max(1, this.h),
          r_rel: second.r / Math.max(1, Math.min(this.w, this.h)),
          rot: second.rot,
          dir: second.dir,
          alpha: second.alpha,
          fill: second.fill,
        } : null,
        cross: this.cross ? {
          x_rel: this.cross.x / Math.max(1, this.w),
          y_rel: this.cross.y / Math.max(1, this.h),
        } : null,
        t: Date.now()
      });
    } else {
      stageSync.broadcastTelemetry({
        type: "telemetry",
        track_id: null,
        title: "",
        artist: "",
        mode: "idle",
        ...commonCfg,
        acc: [a.l, a.c, a.h],
        acc2: [a.l, a.c, a.h],
        color_a: [a.l, a.c, a.h],
        color_b: null,
        is_transitioning: false,
        progress: 0,
        ground: [g.h, g.c],
        fill_a: 0,
        pulse: 0,
        bass: 0,
        peak: 0,
        bands: [],
        angle: 0,
        rot: -Math.PI / 2,
        dir: 1,
        beat: 0,
        frac: 0,
        bpm: 120,
        camelot: "",
        primary: null,
        second: null,
        cross: null,
        t: Date.now()
      });
    }
  }

  // ------------------------------------------------------------- pointer

  _bindPointer() {
    const c = this.canvas;
    const pos = (e) => {
      const r = c.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top, type: e.pointerType };
    };
    c.addEventListener("pointermove", (e) => {
      this.pointer = pos(e);
    });
    c.addEventListener("pointerleave", () => {
      this.pointer = null;
      this.hover = null;
      this.armed = null;
      this._showTip(null);
    });
    c.addEventListener("pointerup", (e) => {
      const p = pos(e);
      this.pointer = p;
      const hit = this._hitTest(p.x, p.y);
      if (hit?.kind === "cross") {
        this.onCrossClick?.();
        this.pickFeedback = { kind: "cross", ok: true, at: performance.now(), x: hit.x, y: hit.y };
        this.hover = null;
        if (p.type !== "mouse") this.pointer = null;
        return;
      }
      if (hit?.kind === "beat" && this._seekable(hit)) {
        // A beat of the playing song: play from there (on a touch screen,
        // the first tap shows where, a second tap on the ring goes).
        if (p.type !== "mouse" && this.armed !== "seek") {
          this.armed = "seek";
          this.hover = hit;
          return;
        }
        this.armed = null;
        const ok = this.onSeek(hit.ring.track, hit.beat);
        this.pickFeedback = { kind: "seek", ok, at: performance.now(), x: hit.x, y: hit.y, t: hit.ring.track.beats[hit.beat] };
        this.hover = null;
        if (p.type !== "mouse") this.pointer = null;
        return;
      }
      if (hit?.kind !== "exit") {
        this.armed = null;
        if (p.type !== "mouse") this.hover = hit;
        return;
      }
      if (p.type !== "mouse" && this.armed !== hit.tr) {
        // First tap on a touch screen shows where the exit leads.
        this.armed = hit.tr;
        this.hover = hit;
        return;
      }
      this.armed = null;
      const ok = this.onPick(hit.tr);
      this.pickFeedback = { kind: "pick", ok, at: performance.now(), tr: hit.tr, x: hit.x, y: hit.y };
      this.hover = null;
      if (p.type !== "mouse") this.pointer = null;
    });
  }

  _hitTest(px, py) {
    const crossPt = stageSync.isStageMirrorActive ? this._lastSatCross : this.cross;
    if (crossPt && (!stageSync.isStageMirrorActive || performance.now() - crossPt.at < 200)) {
      const d = Math.hypot(px - crossPt.x, py - crossPt.y);
      if (d < 34) return { kind: "cross", x: crossPt.x, y: crossPt.y, d };
    }
    const primary = this.primaryId ? this.rings.get(this.primaryId) : null;
    if (!primary || primary.alpha < 0.5 || !primary.track?.beats?.length) return null;
    const T = primary.track;
    const rx = this._exitRadius(primary.r);
    let best = null;
    for (const tr of T.transitions || []) {
      if (!this._shown(T, tr)) continue;
      const t = this._exitTime(T, tr);
      if (t === null) continue;
      const [x, y] = this._point(primary, t, rx);
      const d = Math.hypot(px - x, py - y);
      if (d < 12 && (!best || d < best.d)) best = { kind: "exit", tr, x, y, d };
    }
    if (best) return best;
    const secList = [...this.rings.values()].filter((r) => r.role === "second");
    for (const ring of [primary, ...secList]) {
      const dx = px - ring.x, dy = py - ring.y;
      const d = Math.hypot(dx, dy);
      const th = this._thickness(ring.r);
      if (Math.abs(d - ring.r) > th * 1.5) continue;
      let a = ((Math.atan2(dy, dx) - ring.rot) * ring.dir) % TAU;
      if (a < 0) a += TAU;
      const t = (a / TAU) * ring.track.end;
      return { kind: "beat", ring, beat: this._beatAt(ring.track, t).beat, t, x: px, y: py };
    }
    return null;
  }

  _drawHover(ctx) {
    if (this.pointer && this.pointer.type === "mouse") this.hover = this._hitTest(this.pointer.x, this.pointer.y);
    const h = this.hover;
    this.canvas.style.cursor = h?.kind === "exit" || h?.kind === "cross" || (h?.kind === "beat" && this._seekable(h)) ? "pointer" : "";
    const fb = this.pickFeedback && performance.now() - this.pickFeedback.at < 1800 ? this.pickFeedback : null;
    // Right after a pick the loop turns under the pointer; the confirmation
    // wins over whatever beat slides beneath it, unless another exit is hovered.
    if (fb && !(h && h.kind === "exit" && h.tr !== fb.tr)) {
      this._showTip(this._feedbackHtml(), fb.x, fb.y);
      return;
    }
    if (!h) {
      this._showTip(null);
      return;
    }
    if (h.kind === "cross") {
      const primary = this.primaryId ? this.rings.get(this.primaryId) : null;
      const second = [...this.rings.values()].find((r) => r.role === "second");
      const keyA = primary?.track.analysis.key_camelot || "";
      const keyB = second?.track.analysis.key_camelot || "";
      const fit = (keyA && keyB) ? `${keyA} ⇄ ${keyB}` : "Điểm giao ∞";
      const html = `<b>Điểm giao hòa âm</b> → <span class="k">${fit}</span><small>Bấm để chuyển bài ngay lập tức</small>`;
      this._showTip(html, h.x, h.y);
      return;
    }
    if (h.kind === "beat") {
      const ring = h.ring;
      const T = ring.track;
      const hi = theme.lift(ring.col || theme.accentOf(T.id), 0.12);
      ctx.strokeStyle = theme.css(hi, 0.95);
      ctx.lineWidth = 1.6;
      const limit = this.player.maxScore(T);
      const outs = T.jumps[h.beat].filter((e) => e.score <= limit || e.bridge);
      for (const e of outs) {
        this._chordWorld(ctx, ring, h.beat, e.to);
        ctx.stroke();
      }
      const a1 = this._angle(ring, T.beats[h.beat]);
      const a2 = this._angle(ring, T.beats[h.beat] + T.dur[h.beat]);
      ctx.strokeStyle = theme.css(hi, 0.9);
      ctx.lineWidth = this._thickness(ring.r) + 8;
      ctx.beginPath();
      ctx.arc(ring.x, ring.y, ring.r, a1, a2, ring.dir < 0);
      ctx.stroke();
      const name = esc(short(this.titles.get(T.id) || T.meta.title || "", 34));
      const n = outs.length;
      const role = this._roleAt(T, h.beat);
      const action = !this._seekable(h) ? ""
        : this.armed === "seek" ? "<small>Chạm lần nữa để phát từ đây</small>" : "<small>Bấm để phát từ đây</small>";
      this._showTip(
        `<span class="mono">${fmt(T.beats[h.beat])}</span>${role ? ` · ${role}` : ""} · ${n ? `${n} nhánh nhảy` : "không có nhánh"}` +
          `<small>${name}</small>${action}`,
        h.x, h.y,
      );
      return;
    }
    // Exit dot.
    ctx.strokeStyle = theme.css(theme.lift(theme.songColor(h.tr.to), 0.2), 0.95);
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(h.x, h.y, 8, 0, TAU);
    ctx.stroke();
    const tr = h.tr;
    const title = esc(short(this.titles.get(tr.to) || tr.to, 36));
    const action = this.armed === tr ? "Chạm lần nữa để chuyển ở điểm này" : "Bấm để chuyển ở điểm này";
    const note = bendNote(tr);
    this._showTip(
      `<b>${KIND_VI[tr.type] || tr.type}</b> → <span class="dot" style="--c:${theme.css(theme.songColor(tr.to))}"></span>${title}<br><span class="mono">khớp ${Math.round(tr.q * 100)}%</span>` +
        `${note ? `<small>${esc(note)}</small>` : ""}<small>${action}</small>`,
      h.x, h.y,
    );
  }

  // A beat the listener may play from: on the playing song's ring.
  _seekable(hit) {
    if (stageSync.isStageMirrorActive) {
      const prim = this.primaryId ? this.rings.get(this.primaryId) : null;
      return hit.ring === prim && Boolean(hit.ring?.track?.beats?.length);
    }
    return hit.ring.track === this.player.cur?.track;
  }

  _roleAt(T, beat) {
    const roles = T.analysis.roles || [];
    let r = null;
    for (const s of roles) if (s.start <= beat) r = s.role;
    return ROLE_VI[r] || "";
  }

  _feedbackHtml() {
    const f = this.pickFeedback;
    if (f.kind === "cross") {
      return `<b>Chuyển ngay tức thì</b><small>Đang vào bài kế tiếp ở điểm gần nhất</small>`;
    }
    if (f.kind === "seek") {
      if (f.ok) return `<b>Phát từ <span class="mono">${fmt(f.t)}</span></b><small>Vào ngay ở nhịp kế tiếp</small>`;
      return this.player.seekError === "busy"
        ? `<b>Đang chuyển sang bài khác</b><small>Chọn lại khi bài sau đã vào hẳn</small>`
        : `<b>Chưa có bài nào đang phát</b>`;
    }
    if (f.ok) return `<b>Đã chọn điểm nối này</b><small>Vòng đang xoay về phía bài kế tiếp</small>`;
    return {
      busy: `<b>Đang chuyển sang bài khác</b><small>Chọn lại khi bài sau đã vào hẳn</small>`,
      unreachable: `<b>Không đi tới được điểm này</b><small>Từ chỗ đang phát không có đường tới: chọn chấm khác</small>`,
      soon: `<b>Điểm này tới quá sát</b><small>Cần vài giây chuẩn bị: chọn chấm xa hơn một chút</small>`,
    }[this.player.pickError] || `<b>Điểm này không còn dùng được</b><small>Chọn chấm khác</small>`;
  }

  // Exits shown on a ring: those the chain may take now.
  _shown(track, tr) {
    if (stageSync.isStageMirrorActive) {
      if (stageSync.enabledIds && stageSync.enabledIds.length > 0) {
        return stageSync.enabledIds.includes(tr.to) && tr.to !== track.id;
      }
      return Boolean(tr && tr.to !== track.id);
    }
    return this.player.canTake ? this.player.canTake(track, tr) : true;
  }

  _showTip(html, x = 0, y = 0) {
    const tip = this.tip;
    if (!tip) return;
    if (!html) {
      if (!tip.hidden) tip.hidden = true;
      return;
    }
    if (tip.innerHTML !== html) tip.innerHTML = html;
    tip.hidden = false;
    const w = tip.offsetWidth, hgt = tip.offsetHeight;
    const left = Math.max(8, Math.min(this.w - w - 8, x + 16));
    const top = Math.max(8, Math.min(this.h - hgt - 8, y - hgt - 14));
    tip.style.setProperty("--tip-x", `${left}px`);
    tip.style.setProperty("--tip-y", `${top}px`);
  }
}
