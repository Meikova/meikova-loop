// The ∞ stage. Every song is one loop: a ring of beats coloured by timbre, with
// its jump chords inside and its exits to other songs as dots outside. When the
// player plans an exit, the loop turns until that exit faces the next song,
// whose loop grows in and touches it there: the two loops make the ∞, and the
// crossing is where the mix happens. After the hand-over the new loop glides
// to the centre and the old one shrinks away.

const TAU = Math.PI * 2;
const reduceMQ = matchMedia("(prefers-reduced-motion: reduce)");
export const KIND_VI = {
  cut: "Nối thẳng", drop: "Drop vào đoạn mới", blend: "Blend khớp nhịp", fade: "Crossfade",
  echo: "Echo vang", brake: "Phanh đĩa", roll: "Cuộn nhịp",
};

// What the bridge does to the tempo, in words: "nắn nhịp 5%", "nhịp đôi".
export function bendNote(tr) {
  const notes = [];
  const pre = tr.pre || 1;
  if (Math.abs(pre - 1) > 0.004) notes.push(`hai bài cùng nắn nhịp ${Math.round(Math.abs(pre - 1) * 100)}%`);
  else if (tr.rate && Math.abs(tr.rate - 1) > 0.015 && (tr.type === "cut" || tr.type === "drop" || tr.type === "blend")) {
    notes.push(`bài sau ${tr.rate > 1 ? "nhanh" : "chậm"} ${Math.round(Math.abs(tr.rate - 1) * 100)}% lúc vào`);
  }
  if (tr.m === 2) notes.push("bài sau nhịp đôi");
  if (tr.m === 0.5) notes.push("bài sau nửa nhịp");
  if (tr.type === "fade" && tr.seconds) notes.push(`chuyển dần trong ${Math.round(tr.seconds)} giây`);
  if ((tr.mood ?? 0) > 0.9) notes.push("khác mood");
  return notes.join(" · ");
}
const SECOND_RATIO = 0.7; // the next song's loop, relative to the playing one

export function trackHue(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h % 360;
}

export function fmt(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function short(t, n = 28) {
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

// YouTube titles carry upload noise ("(Official Audio)", "| Official MV").
// Split them into the song and the artist so the song can be the display line.
const NOISE = /\s*[([]([^)\]]*\b(official|audio|video|lyrics?|mv|m\/v|visuali[sz]er|remaster(ed)?|hd|4k|explicit)\b[^)\]]*)[)\]]\s*/gi;
export function splitTitle(raw, channel = "") {
  let s = String(raw || "").replace(NOISE, " ").replace(/\s*\|\s*official.*$/i, "").replace(/\s+/g, " ").trim();
  let artist = "";
  let title = s;
  const sep = s.match(/\s[-–—|]\s/);
  if (sep) {
    artist = s.slice(0, sep.index).trim();
    title = s.slice(sep.index + sep[0].length).trim();
  }
  const ft = title.match(/\s\(?(ft\.?|feat\.?|featuring)\s[^)]+\)?$/i);
  if (ft) {
    artist = `${artist || ""} ${ft[0].trim().replace(/^\(|\)$/g, "")}`.trim();
    title = title.slice(0, ft.index).trim();
  }
  if (!artist && channel) artist = channel.replace(/\s*-\s*Topic$/i, "").replace(/VEVO$/i, "").trim();
  return { title: title || s || raw, artist };
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
const wrapAngle = (a) => Math.atan2(Math.sin(a), Math.cos(a));

class Ring {
  constructor(track, role) {
    this.track = track;
    this.role = role;
    this.x = null;
    this.y = null;
    this.r = 0;
    this.rot = -Math.PI / 2; // song start at twelve o'clock
    this.alpha = 0;
    this.fill = 1;
    this.target = null;
    this.layer = null;
    this.layerKey = "";
  }
}

export class Viz {
  constructor(canvas, player, { center, tip, onPick } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.player = player;
    this.center = center;
    this.tip = tip;
    this.onPick = onPick || (() => {});
    this.titles = new Map();
    this.rings = new Map();
    this.primaryId = null;
    this.idle = 1;
    this.pulse = 0;
    this.lastBeatKey = "";
    this.lastEventT = 0;
    this.flashes = [];
    this.pointer = null;
    this.hover = null;
    this.armed = null; // touch: an exit tapped once, waiting for the confirming tap
    this.fieldAt = 0;
    this.last = performance.now();
    this.ro = new ResizeObserver(() => this._resize());
    this.ro.observe(canvas.parentElement);
    this._resize();
    this._bindPointer();
    const loop = (now) => {
      this._frame(now);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  setTitles(map) {
    this.titles = map;
  }

  invalidate() {
    for (const ring of this.rings.values()) ring.layerKey = "";
  }

  get reduced() {
    return reduceMQ.matches;
  }

  // ------------------------------------------------------------- geometry

  _resize() {
    const box = this.canvas.parentElement.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = Math.max(200, box.width);
    this.h = Math.max(200, box.height);
    this.dpr = dpr;
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.baseR = Math.min(this.w, this.h) * 0.37;
    this.invalidate();
  }

  // Where the loops sit: one in the middle, or two touching (side by side on
  // wide stages, stacked as an 8 on tall ones).
  _layout(two) {
    const { w, h } = this;
    const k = SECOND_RATIO;
    if (!two) return { a: { x: w / 2, y: h / 2, r: Math.min(w, h) * 0.37 } };
    if (w >= h * 1.05) {
      const R = Math.min(h * 0.37, (w * 0.86) / (2 * (1 + k)));
      const x0 = (w - 2 * R * (1 + k)) / 2;
      return {
        a: { x: x0 + R, y: h / 2, r: R, face: 0 },
        b: { x: x0 + 2 * R + k * R, y: h / 2, r: k * R, face: Math.PI },
        cross: { x: x0 + 2 * R, y: h / 2 },
      };
    }
    const R = Math.min(w * 0.37, (h * 0.86) / (2 * (1 + k)));
    const y0 = (h - 2 * R * (1 + k)) / 2;
    return {
      a: { x: w / 2, y: y0 + R, r: R, face: Math.PI / 2 },
      b: { x: w / 2, y: y0 + 2 * R + k * R, r: k * R, face: -Math.PI / 2 },
      cross: { x: w / 2, y: y0 + 2 * R },
    };
  }

  _thickness(R) {
    return Math.max(7, R * 0.068);
  }

  // Angle on the ring (before its rotation) for a time in the song.
  _ang(track, t) {
    return (TAU * t) / track.end;
  }

  _point(ring, t, radius) {
    const a = ring.rot + this._ang(ring.track, t);
    return [ring.x + radius * Math.cos(a), ring.y + radius * Math.sin(a)];
  }

  // ---------------------------------------------------------------- layers

  // Everything about a song that does not move: drawn once, then rotated and
  // scaled as the loop travels.
  _buildLayer(track) {
    const RL = this.baseR;
    const th = this._thickness(RL);
    const S = Math.ceil(RL * 2.6);
    const c = document.createElement("canvas");
    c.width = Math.round(S * this.dpr);
    c.height = Math.round(S * this.dpr);
    const ctx = c.getContext("2d");
    ctx.scale(this.dpr, this.dpr);
    ctx.translate(S / 2, S / 2);
    const a = track.analysis;
    const maxScore = this.player.maxScore(track);
    const loudMax = Math.max(...a.loud);
    const loudMin = Math.min(...a.loud);
    const ang = (t) => this._ang(track, t);
    const at = (t, r) => [r * Math.cos(ang(t)), r * Math.sin(ang(t))];
    const rin = RL - th / 2 - 3;

    // Jump chords, weakest first so the best sit on top.
    const edges = [];
    for (let i = 0; i < track.n; i++) for (const e of track.jumps[i]) edges.push([i, e.to, e.score]);
    edges.sort((p, q) => q[2] - p[2]);
    ctx.lineWidth = 1;
    for (const [i, j, s] of edges) {
      const ok = s <= maxScore;
      ctx.strokeStyle = ok ? `rgba(246, 196, 120, ${(0.08 + 0.42 * (1 - s / Math.max(maxScore, 0.01))).toFixed(3)})` : "rgba(255,240,220,0.03)";
      this._chordPath(ctx, rin, ang(track.beats[i] + track.dur[i]), ang(track.beats[j]));
      ctx.stroke();
    }

    // Dust: the ring is made of matter, denser where the song is loud.
    const rnd = seeded(track.n * 7919 + Math.round(track.end * 13));
    for (let b = 0; b < track.n; b++) {
      const lv = (a.loud[b] - loudMin) / Math.max(1, loudMax - loudMin);
      const count = 2 + Math.round(9 * lv);
      ctx.fillStyle = a.color[b];
      for (let k = 0; k < count; k++) {
        const t = track.beats[b] + rnd() * track.dur[b];
        const spread = (rnd() + rnd() + rnd() - 1.5) / 1.5; // roughly normal, -1..1
        const r = RL + spread * th * 2.1;
        const [x, y] = at(t, r);
        ctx.globalAlpha = 0.12 + 0.4 * rnd() * (1 - Math.abs(spread));
        ctx.beginPath();
        ctx.arc(x, y, 0.5 + rnd() * 0.9, 0, TAU);
        ctx.fill();
      }
    }

    // Beat segments.
    for (let b = 0; b < track.n; b++) {
      const lv = (a.loud[b] - loudMin) / Math.max(1, loudMax - loudMin);
      ctx.globalAlpha = 0.3 + 0.7 * lv;
      ctx.strokeStyle = a.color[b];
      ctx.lineWidth = th * (a.pos[b] === 0 ? 1 : 0.78);
      ctx.beginPath();
      ctx.arc(0, 0, RL, ang(track.beats[b]), ang(track.beats[b] + track.dur[b]) + 0.002);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // The dial: a hairline tick every 15 s, longer on the minute.
    const r0 = RL + th / 2 + 8;
    ctx.strokeStyle = "rgba(240, 225, 200, 0.22)";
    ctx.lineWidth = 1;
    for (let t = 0; t <= track.end; t += 15) {
      const long = Math.round(t) % 60 === 0;
      const [x1, y1] = at(t, r0);
      const [x2, y2] = at(t, r0 + (long ? 7 : 3.5));
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    // Section starts, just inside the dial.
    ctx.strokeStyle = "rgba(255, 244, 228, 0.55)";
    ctx.lineWidth = 1.4;
    for (const s of a.sections) {
      const [x1, y1] = at(track.beats[s], RL + th / 2 + 1);
      const [x2, y2] = at(track.beats[s], RL + th / 2 + 5);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    // Exits to other songs.
    for (const tr of track.transitions) {
      const t = this._exitTime(track, tr);
      if (t === null) continue;
      const [x, y] = at(t, this._exitRadius(RL));
      ctx.fillStyle = `hsla(${trackHue(tr.to)}, 78%, 66%, ${(0.4 + 0.55 * tr.q).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(x, y, tr.type === "cut" ? 4 : 3.1, 0, TAU);
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
    const s = ring.r / this.baseR;
    const rin = (this.baseR - this._thickness(this.baseR) / 2 - 3) * s;
    ctx.save();
    ctx.translate(ring.x, ring.y);
    ctx.rotate(ring.rot);
    this._chordPath(ctx, rin, this._ang(T, T.beats[i] + T.dur[i]), this._ang(T, T.beats[j]));
    ctx.restore();
  }

  // ----------------------------------------------------------------- state

  _roles(view) {
    const p = this.player;
    const primary = view?.entry.track || null;
    let second = null;
    let secondTr = null;
    let placeholder = null;
    const b = p.blend;
    const f = p.fx;
    if (b && view && view.now >= b.times[0] && primary && primary.id === b.A.id) {
      second = b.B;
      secondTr = b.tr;
    } else if (f && primary && primary.id === f.A.id) {
      second = f.B;
      secondTr = f.tr;
    } else if (p.plan && primary && p.plan.from === primary.id) {
      secondTr = p.plan.tr;
      if (p.plan.target) second = p.plan.target;
      else placeholder = p.plan.tr.to;
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
    const two = !!(second || placeholder);
    const L = this._layout(two);
    const k = this.reduced ? 1 : 1 - Math.exp(-dt / 0.22);
    const kRot = this.reduced ? 1 : 1 - Math.exp(-dt / 0.3);

    this.idle += ((primary ? 0 : 1) - this.idle) * (this.reduced ? 1 : 1 - Math.exp(-dt / 0.25));

    if (primary && primary.id !== this.primaryId) {
      // A new song is playing: the one before it leaves the stage.
      const before = this.primaryId ? this.rings.get(this.primaryId) : null;
      if (before) before.role = "leaving";
      const fresh = !this.rings.has(primary.id);
      const ring = this._ring(primary, "primary");
      if (fresh) {
        ring.x = L.a.x;
        ring.y = L.a.y;
        ring.r = L.a.r;
        ring.fill = this.reduced || before ? 1 : 0; // the very first loop sweeps in
        if (before) ring.r = L.a.r * 0.7;
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
        if (t !== null) ring.target.rot = L.a.face - this._ang(primary, t);
      }
      if (second) {
        const sr = this._ring(second, "second");
        const entry = this._entryTime(second, secondTr);
        const rot = L.b.face - this._ang(second, entry);
        if (sr.x === null) {
          sr.x = L.b.x + (L.b.x - L.a.x) * 0.25;
          sr.y = L.b.y + (L.b.y - L.a.y) * 0.25;
          sr.r = L.b.r * 0.6;
          sr.rot = rot;
          sr.alpha = 0;
        }
        sr.target = { ...L.b, rot, alpha: 1 };
      }
    }
    this.placeholder = placeholder ? { id: placeholder, ...L.b, tr: secondTr } : null;
    this.cross = two ? L.cross : null;

    for (const [id, ring] of this.rings) {
      if (ring.role === "leaving" || ring.role === "fading") {
        const away = ring.role === "leaving";
        ring.target = {
          x: ring.x + (away ? -0.02 * this.w : 0),
          y: ring.y,
          r: ring.r * (away ? 0.985 : 0.99),
          alpha: 0,
        };
      }
      const tg = ring.target;
      if (!tg) continue;
      if (ring.x === null) {
        ring.x = tg.x;
        ring.y = tg.y;
        ring.r = tg.r;
      }
      ring.x += (tg.x - ring.x) * k;
      ring.y += (tg.y - ring.y) * k;
      ring.r += (tg.r - ring.r) * k;
      const fadeK = this.reduced ? Math.min(1, dt / 0.16) : k;
      ring.alpha += (tg.alpha - ring.alpha) * fadeK;
      if (tg.rot !== undefined) ring.rot += wrapAngle(tg.rot - ring.rot) * kRot;
      if (ring.fill < 1) ring.fill = Math.min(1, ring.fill + dt / 1.2);
      if ((ring.role === "leaving" || ring.role === "fading") && ring.alpha < 0.02) this.rings.delete(id);
    }
  }

  // ----------------------------------------------------------------- frame

  _frame(now) {
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    const ctx = this.ctx;
    const view = this.player.audible();
    this._update(view, dt);

    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);

    this._beatPulse(view, dt);
    if (this.idle > 0.01) this._drawIdle(ctx, now, this.idle);

    const primary = this.primaryId ? this.rings.get(this.primaryId) : null;
    this._drawLights(ctx, primary);

    // Back to front: leaving, the next song, the playing song.
    const order = [...this.rings.values()].sort((a, b) => (a.role === "primary") - (b.role === "primary"));
    for (const ring of order) this._drawRing(ctx, ring);
    if (this.placeholder) this._drawPlaceholder(ctx, this.placeholder, now);
    if (this.cross && primary && primary.alpha > 0.4) this._drawCross(ctx, view, now);

    if (primary && view) this._drawLive(ctx, primary, view, now);
    const b = this.player.blend;
    if (b && view && view.now >= b.times[0]) {
      const sr = this.rings.get(b.B.id);
      if (sr) this._drawBlendHead(ctx, sr, b, view.now);
    }
    this._drawHover(ctx);
    this._placeCenter(primary);
    this._updateField(primary, now);
  }

  _beatPulse(view, dt) {
    this.pulse *= Math.exp(-dt / 0.22);
    if (!view || this.reduced) return;
    const key = `${view.entry.track.id}:${view.entry.beat}`;
    if (key !== this.lastBeatKey) {
      this.lastBeatKey = key;
      const pos = view.entry.track.analysis.pos[view.entry.beat];
      this.pulse = Math.max(this.pulse, pos === 0 ? 1 : 0.5);
    }
  }

  _drawLights(ctx, primary) {
    for (const ring of this.rings.values()) {
      if (ring.alpha < 0.02 || ring.x === null) continue;
      const isP = ring === primary;
      const hue = isP ? null : trackHue(ring.track.id);
      const base = isP ? 0.07 + 0.07 * this.pulse : 0.07;
      const g = ctx.createRadialGradient(ring.x, ring.y, ring.r * 0.2, ring.x, ring.y, ring.r * 1.55);
      const col = isP ? `rgba(246, 184, 92, ${base * ring.alpha})` : `hsla(${hue}, 70%, 60%, ${base * ring.alpha})`;
      g.addColorStop(0, col);
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(ring.x - ring.r * 1.6, ring.y - ring.r * 1.6, ring.r * 3.2, ring.r * 3.2);
    }
  }

  _drawRing(ctx, ring) {
    if (ring.alpha < 0.01 || ring.x === null) return;
    const key = `${ring.track.id}|${this.player.settings.keep}|${ring.track.transitions.length}|${this.baseR.toFixed(1)}`;
    if (ring.layerKey !== key) {
      ring.layer = this._buildLayer(ring.track);
      ring.layerKey = key;
    }
    const L = ring.layer;
    const s = ring.r / L.RL;
    ctx.save();
    ctx.globalAlpha = Math.min(1, ring.alpha);
    ctx.translate(ring.x, ring.y);
    ctx.rotate(ring.rot);
    ctx.scale(s, s);
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

    // A soft dark pool in the middle of the playing loop keeps its caption
    // readable over the chords (contrast, rulebook A2.1).
    if (ring.role === "primary") {
      const g = ctx.createRadialGradient(ring.x, ring.y, 0, ring.x, ring.y, ring.r * 0.72);
      g.addColorStop(0, `rgba(20, 16, 12, ${0.86 * ring.alpha})`);
      g.addColorStop(0.62, `rgba(20, 16, 12, ${0.62 * ring.alpha})`);
      g.addColorStop(1, "rgba(20, 16, 12, 0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(ring.x, ring.y, ring.r * 0.72, 0, TAU);
      ctx.fill();
    }

    // Minute labels stay upright while the loop turns.
    if (ring.role === "primary" && ring.alpha > 0.3 && ring.fill >= 1) {
      ctx.save();
      ctx.globalAlpha = ring.alpha * 0.7;
      ctx.fillStyle = "rgba(240, 225, 200, 0.7)";
      ctx.font = `400 ${Math.max(9, Math.min(11, ring.r * 0.04))}px "JetBrains Mono", monospace`;
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
    const hue = trackHue(ph.id);
    ctx.save();
    ctx.strokeStyle = `hsla(${hue}, 70%, 65%, 0.55)`;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 7]);
    ctx.lineDashOffset = this.reduced ? 0 : -now / 60;
    ctx.beginPath();
    ctx.arc(ph.x, ph.y, ph.r, 0, TAU);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(240, 225, 200, 0.6)";
    ctx.font = '400 11px "JetBrains Mono", monospace';
    ctx.textAlign = "center";
    ctx.fillText("ĐANG TẢI", ph.x, ph.y + 4);
    ctx.restore();
  }

  // The crossing: where the two loops touch, the mix glows.
  _drawCross(ctx, view, now) {
    const c = this.cross;
    const b = this.player.blend;
    const f = this.player.fx;
    let k = 0;
    if (b && view && view.now >= b.times[0]) k = Math.min(1, (view.now - b.times[0]) / (b.times[b.L] - b.times[0]));
    else if (f && view && view.now >= f.times[0]) {
      k = Math.min(1, (view.now - f.times[0]) / (f.times[f.times.length - 1] - f.times[0]));
    }
    const breathe = this.reduced ? 0.5 : 0.5 + 0.5 * Math.sin(now / 420);
    const R = 16 + 26 * k;
    const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R * 2.2);
    g.addColorStop(0, `rgba(255, 214, 150, ${0.55 + 0.35 * k})`);
    g.addColorStop(0.35, `rgba(246, 184, 92, ${0.18 + 0.12 * breathe})`);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(c.x, c.y, R * 2.2, 0, TAU);
    ctx.fill();
    ctx.fillStyle = "#fff4e0";
    ctx.beginPath();
    ctx.arc(c.x, c.y, 2.6 + 1.2 * k, 0, TAU);
    ctx.fill();
    if (k > 0) {
      ctx.strokeStyle = "rgba(255, 214, 150, 0.9)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(c.x, c.y, 11, -Math.PI / 2, -Math.PI / 2 + TAU * k);
      ctx.stroke();
    }
  }

  _drawLive(ctx, ring, view, now) {
    const T = ring.track;
    const { entry } = view;
    const p = this.player;
    const th = this._thickness(ring.r);

    // New audible events start a flash along the jump that was taken.
    for (const ev of p.recentEvents(this.lastEventT)) {
      if (ev.kind === "jump" && ev.track === T) this.flashes.push({ i: ev.from, j: ev.beat, t0: now });
    }
    this.lastEventT = view.now;
    this.flashes = this.flashes.filter((f) => now - f.t0 < 900);
    for (const f of this.flashes) {
      const a = 1 - (now - f.t0) / 900;
      ctx.strokeStyle = `rgba(255, 246, 232, ${(0.9 * a).toFixed(3)})`;
      ctx.lineWidth = 2.4;
      this._chordWorld(ctx, ring, f.i, f.j);
      ctx.stroke();
    }

    // The route the player will take to the planned exit: an amber thread.
    const plan = p.plan;
    if (plan && plan.from === T.id) {
      ctx.save();
      ctx.strokeStyle = "rgba(255, 200, 120, 0.85)";
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
        ctx.strokeStyle = `hsla(${trackHue(plan.tr.to)}, 85%, 72%, ${0.5 + 0.5 * pulse})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, 7 + 3 * pulse, 0, TAU);
        ctx.stroke();
      }
    }

    // Playhead.
    const beat = entry.beat;
    const frac = Math.max(0, Math.min(1, ((view.now - entry.t) * (entry.rate || 1)) / T.dur[beat]));
    const a1 = ring.rot + this._ang(T, T.beats[beat]);
    const a2 = ring.rot + this._ang(T, T.beats[beat] + T.dur[beat]);
    ctx.strokeStyle = "rgba(255, 248, 236, 0.95)";
    ctx.lineWidth = th + 5;
    ctx.beginPath();
    ctx.arc(ring.x, ring.y, ring.r, a1, a2);
    ctx.stroke();
    const ah = a1 + (a2 - a1) * frac;
    const hx = ring.x + ring.r * Math.cos(ah), hy = ring.y + ring.r * Math.sin(ah);
    const glow = 14 + 10 * this.pulse;
    const g = ctx.createRadialGradient(hx, hy, 0, hx, hy, glow * 2);
    g.addColorStop(0, "rgba(255, 220, 160, 0.9)");
    g.addColorStop(1, "rgba(246, 184, 92, 0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(hx, hy, glow * 2, 0, TAU);
    ctx.fill();
    ctx.fillStyle = "#fff8ec";
    ctx.beginPath();
    ctx.arc(hx, hy, th * 0.42, 0, TAU);
    ctx.fill();
  }

  // During a blend the next song plays too: its own playhead, beat-locked.
  _drawBlendHead(ctx, ring, b, now) {
    let k = 0;
    while (k + 1 < b.times.length && b.times[k + 1] <= now) k++;
    k = Math.min(k, b.L - 1);
    const frac = Math.max(0, Math.min(1, (now - b.times[k]) / (b.times[k + 1] - b.times[k])));
    // tB holds B's audio time at each master beat, whatever the beat ratio.
    const t = b.tB[k] + frac * (b.tB[k + 1] - b.tB[k]);
    const [x, y] = this._point(ring, t, ring.r);
    ctx.fillStyle = `hsla(${trackHue(ring.track.id)}, 90%, 82%, 0.95)`;
    ctx.beginPath();
    ctx.arc(x, y, this._thickness(ring.r) * 0.45, 0, TAU);
    ctx.fill();
  }

  _drawIdle(ctx, now, alpha) {
    // The waiting instrument: the ∞ itself, with a light running along it.
    const a = Math.min(this.w * 0.36, this.h * 0.95);
    const cx = this.w / 2, cy = this.h / 2;
    const pt = (u) => {
      const s = Math.sin(u), c = Math.cos(u);
      const d = 1 + s * s;
      return [cx + (a * c) / d, cy + (a * s * c) / d];
    };
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = "rgba(240, 225, 200, 0.16)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i <= 240; i++) {
      const [x, y] = pt((i / 240) * TAU);
      if (i) ctx.lineTo(x, y);
      else ctx.moveTo(x, y);
    }
    ctx.stroke();
    const u0 = this.reduced ? 0.6 : (now / 7000) * TAU;
    for (let k = 0; k < 28; k++) {
      const [x, y] = pt(u0 - k * 0.025);
      ctx.fillStyle = `rgba(246, 184, 92, ${((1 - k / 28) * 0.55).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(x, y, 2.6 * (1 - k / 40), 0, TAU);
      ctx.fill();
    }
    const [hx, hy] = pt(u0);
    const g = ctx.createRadialGradient(hx, hy, 0, hx, hy, 26);
    g.addColorStop(0, "rgba(255, 220, 160, 0.85)");
    g.addColorStop(1, "rgba(246, 184, 92, 0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(hx, hy, 26, 0, TAU);
    ctx.fill();
    ctx.restore();
    this.idleCaptionY = cy + a * 0.354 + 74;
  }

  // ---------------------------------------------------------------- caption

  _placeCenter(primary) {
    const el = this.center;
    if (!el) return;
    let x, y, w, size, o;
    if (primary && primary.alpha > 0.05) {
      x = primary.x;
      y = primary.y;
      w = primary.r * 1.32;
      size = Math.max(15, Math.min(38, primary.r * 0.125));
      o = Math.min(1, primary.alpha * (primary.fill < 1 ? easeOut(primary.fill) : 1));
    } else {
      x = this.w / 2;
      y = Math.min(this.h - 60, this.idleCaptionY || this.h * 0.78);
      w = Math.min(this.w * 0.8, 520);
      size = Math.max(16, Math.min(28, this.w * 0.03));
      o = 1;
    }
    const key = `${x.toFixed(1)}|${y.toFixed(1)}|${w.toFixed(0)}|${size.toFixed(1)}|${o.toFixed(2)}`;
    if (key === this._centerKey) return;
    this._centerKey = key;
    el.style.setProperty("--rc-x", `${x}px`);
    el.style.setProperty("--rc-y", `${y}px`);
    el.style.setProperty("--rc-w", `${w}px`);
    el.style.setProperty("--rc-size", `${size}px`);
    el.style.setProperty("--rc-o", o.toFixed(2));
    el.dataset.mode = primary ? "ring" : "idle";
    // Small loops (phones, the ∞ layout) keep the title and drop the details.
    el.dataset.size = primary && primary.r < 125 ? "s" : "m";
  }

  // The page's light field follows the loops (atmospheric field, ~10 updates/s).
  _updateField(primary, now) {
    if (now - this.fieldAt < 100) return;
    this.fieldAt = now;
    const root = document.documentElement.style;
    const rect = this.canvas.getBoundingClientRect();
    const vw = window.innerWidth || 1;
    if (primary) root.setProperty("--key-x", `${(((rect.left + primary.x) / vw) * 100).toFixed(1)}%`);
    const second = [...this.rings.values()].find((r) => r.role === "second");
    if (second) {
      root.setProperty("--fill-x", `${(((rect.left + second.x) / vw) * 100).toFixed(1)}%`);
      root.setProperty("--fill", `hsla(${trackHue(second.track.id)}, 60%, 55%, 0.09)`);
    } else {
      root.setProperty("--fill", "oklch(0.6 0.08 40 / 0.04)");
    }
    root.setProperty("--pulse", this.pulse.toFixed(2));
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
      this.pickFeedback = { ok, at: performance.now(), tr: hit.tr, x: hit.x, y: hit.y };
      this.hover = null;
      if (p.type !== "mouse") this.pointer = null;
    });
  }

  _hitTest(px, py) {
    const primary = this.primaryId ? this.rings.get(this.primaryId) : null;
    if (!primary || primary.alpha < 0.5) return null;
    const T = primary.track;
    const rx = this._exitRadius(primary.r);
    let best = null;
    for (const tr of T.transitions) {
      const t = this._exitTime(T, tr);
      if (t === null) continue;
      const [x, y] = this._point(primary, t, rx);
      const d = Math.hypot(px - x, py - y);
      if (d < 12 && (!best || d < best.d)) best = { kind: "exit", tr, x, y, d };
    }
    if (best) return best;
    for (const ring of [primary, ...[...this.rings.values()].filter((r) => r.role === "second")]) {
      const dx = px - ring.x, dy = py - ring.y;
      const d = Math.hypot(dx, dy);
      const th = this._thickness(ring.r);
      if (Math.abs(d - ring.r) > th * 1.5) continue;
      let a = (Math.atan2(dy, dx) - ring.rot) % TAU;
      if (a < 0) a += TAU;
      const t = (a / TAU) * ring.track.end;
      const beats = ring.track.beats;
      let lo = 0, hi = beats.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (beats[mid] <= t) lo = mid;
        else hi = mid - 1;
      }
      return { kind: "beat", ring, beat: lo, t, x: px, y: py };
    }
    return null;
  }

  _drawHover(ctx) {
    if (this.pointer && this.pointer.type === "mouse") this.hover = this._hitTest(this.pointer.x, this.pointer.y);
    const h = this.hover;
    this.canvas.style.cursor = h?.kind === "exit" ? "pointer" : "";
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
    if (h.kind === "beat") {
      const ring = h.ring;
      const T = ring.track;
      ctx.strokeStyle = "rgba(255, 210, 140, 0.95)";
      ctx.lineWidth = 1.6;
      const limit = this.player.maxScore(T);
      const outs = T.jumps[h.beat].filter((e) => e.score <= limit || e.bridge);
      for (const e of outs) {
        this._chordWorld(ctx, ring, h.beat, e.to);
        ctx.stroke();
      }
      const a1 = ring.rot + this._ang(T, T.beats[h.beat]);
      const a2 = ring.rot + this._ang(T, T.beats[h.beat] + T.dur[h.beat]);
      ctx.strokeStyle = "rgba(255, 210, 140, 0.9)";
      ctx.lineWidth = this._thickness(ring.r) + 8;
      ctx.beginPath();
      ctx.arc(ring.x, ring.y, ring.r, a1, a2);
      ctx.stroke();
      const name = esc(short(this.titles.get(T.id) || T.meta.title || "", 34));
      const n = outs.length;
      this._showTip(
        `<span class="mono">${fmt(T.beats[h.beat])}</span> · ${n ? `${n} nhánh nhảy` : "không có nhánh"}<small>${name}</small>`,
        h.x, h.y,
      );
      return;
    }
    // Exit dot.
    ctx.strokeStyle = "rgba(255, 246, 232, 0.95)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(h.x, h.y, 8, 0, TAU);
    ctx.stroke();
    const tr = h.tr;
    const title = esc(short(this.titles.get(tr.to) || tr.to, 36));
    const action = this.armed === tr ? "Chạm lần nữa để chuyển ở điểm này" : "Bấm để chuyển ở điểm này";
    const note = bendNote(tr);
    this._showTip(
      `<b>${KIND_VI[tr.type] || tr.type}</b> → ${title}<br><span class="mono">khớp ${Math.round(tr.q * 100)}%</span>` +
        `${note ? `<small>${esc(note)}</small>` : ""}<small>${action}</small>`,
      h.x, h.y,
    );
  }

  _feedbackHtml() {
    const f = this.pickFeedback;
    return f.ok
      ? `<b>Đã chọn điểm nối này</b><small>Vòng đang xoay về phía bài kế tiếp</small>`
      : `<b>Chưa tới được điểm này</b><small>Thử lại khi đang blend xong, hoặc chọn chấm khác</small>`;
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
