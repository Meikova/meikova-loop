// The player decides, one beat at a time, what plays next: carry on, jump inside
// the song, or leave for another song through a planned transition. Decisions are
// made LOOKAHEAD seconds before they are heard and scheduled sample-accurately.

const LOOKAHEAD = 0.6;
const TICK_MS = 40;
const SPLICE_XFADE = 0.012;
const RAMP_BEATS = 32;
const JUMP_COOLDOWN = 4;
const LOAD_LEAD = 3; // seconds needed to fetch and decode a song that is not prefetched
const PREFETCH_LEAD = 20; // start loading likely next songs this long before leaving is allowed
// Smooth hand-overs first: beat-matched moves, then long filtered crossfades
// and echoes; the abrupt effects (brake, roll) last and off by default.
const TYPE_BIAS = { cut: 0.08, drop: 0.02, blend: 0.06, fade: 0.0, echo: -0.08, roll: -0.12, brake: -0.15 };
// Utility lost per unit of mood distance between the songs: the chain drifts
// from style to style rather than lurching from a dance track to a ballad.
const MOOD_WEIGHT = 0.35;
// Effect transitions: the old song winds down over a few beats (echo, brake,
// roll) and the new one comes in on its own tempo, no beat matching needed.
const FX = new Set(["echo", "brake", "roll"]);
// Beats over which the playing song bends toward the meeting tempo before a
// tempo-bridged junction.
const BEND_BEATS = 16;
// A drop is a cut that does not require alike music: one switch covers both.
export const allowKey = (type) => (type === "drop" ? "cut" : type);
// Hand-overs that keep the beat running: the next song comes in locked to it.
const BEAT_MATCHED = new Set(["cut", "drop", "blend"]);

// What the chain looks for in the next song (settings.criterion). Every
// criterion is a weighting, never a filter, so the chain cannot get stuck in
// a song with no exit that fits: it waits a little longer for a good one, and
// past dwellMax takes what there is.
//   mood: utility lost per unit of mood distance
//   beat: lost by a hand-over that does not keep the beat (fade, echo, ...)
//   tempo: lost per octave of tempo gap (bending, or the BPMs apart)
//   key: gained per unit of key fit on the Camelot wheel, centred on 0.6
//   explore: weight of the recency penalty; noise: random spread
export const CRITERIA = {
  balanced: { mood: MOOD_WEIGHT, beat: 0, tempo: 0, key: 0, explore: 1, noise: 0.03 },
  mood: { mood: 3.0, beat: 0, tempo: 0, key: 0, explore: 1, noise: 0.03 },
  tempo: { mood: 0.15, beat: 0.45, tempo: 3, key: 0, explore: 1, noise: 0.03 },
  key: { mood: 0.15, beat: 0, tempo: 0, key: 0.9, explore: 1, noise: 0.03 },
  free: { mood: 0, beat: 0, tempo: 0, key: 0, explore: 2, noise: 0.4 },
};

const parseCamelot = (s) => {
  const m = /^(\d{1,2})([AB])$/.exec(s || "");
  return m ? { n: +m[1], l: m[2] } : null;
};

// How well two keys sit together for a DJ (the Camelot wheel): same key 1,
// a step round the wheel 0.85, the relative major or minor 0.8, two steps
// 0.35, anything else 0. B's key moves with the pitch shift of the bridge
// (a semitone up is 7 steps round the wheel).
const wheelStep = (n, semis) => ((((n - 1 + 7 * Math.round(semis)) % 12) + 12) % 12) + 1;

// A Camelot key moved by a pitch shift, as the listener hears it in the mix.
export function shiftCamelot(cam, semis = 0) {
  const k = parseCamelot(cam);
  return k ? `${wheelStep(k.n, semis)}${k.l}` : cam;
}

export function keyFit(camA, camB, semis = 0) {
  const a = parseCamelot(camA), b = parseCamelot(camB);
  if (!a || !b) return 0.6;
  const nb = wheelStep(b.n, semis);
  const d = Math.min((a.n - nb + 12) % 12, (nb - a.n + 12) % 12);
  if (a.l === b.l) return d === 0 ? 1 : d === 1 ? 0.85 : d === 2 ? 0.35 : 0;
  return d === 0 ? 0.8 : 0;
}

// The tempo gap a transition has to cover, in octaves: the bending of a
// beat-matched hand-over, or how far apart the two songs' tempos are
// (double and half time count as the same tempo).
export function tempoGap(bpmA, bpmB, tr) {
  if (BEAT_MATCHED.has(tr.type)) {
    return Math.abs(Math.log2(tr.rate || 1)) + Math.abs(Math.log2(tr.pre || 1)) + ((tr.m || 1) !== 1 ? 0.04 : 0);
  }
  if (!bpmA || !bpmB) return 0.15;
  const r = Math.log2(bpmB / bpmA);
  return Math.abs(r - Math.round(r));
}

function sampleCurve(fn, n = 256) {
  const c = new Float32Array(n);
  for (let i = 0; i < n; i++) c[i] = Math.max(0, Math.min(1, fn(i / (n - 1))));
  return c;
}
const clamp01 = (x) => Math.max(0, Math.min(1, x));
// DJ-style crossfade: the incoming song is up by 60 %, the outgoing one leaves from 40 %.
const BLEND_IN = sampleCurve((x) => Math.sin((Math.PI / 2) * clamp01(x / 0.6)));
const BLEND_OUT = sampleCurve((x) => Math.cos((Math.PI / 2) * clamp01((x - 0.4) / 0.6)));
const FADE_A = sampleCurve((x) => Math.cos((Math.PI / 2) * x));

export const DEFAULTS = {
  mode: "chain",
  jumpEvery: 20, // mean seconds between in-song jumps, whatever the tempo
  keep: 0.6, // fraction of each song's best jumps the walk may use
  dwellMin: 90, // a song may be left from here on, at the nearest good exit
  dwellMax: 200, // past this, the nearest exit is taken whatever its quality
  // Utility lost per second of waiting for an exit. 0.05: an exit 10 s later
  // must be 0.5 better in quality to be preferred (simulated: transitions start
  // a median 13 s after dwellMin, the wait mostly being the next phrase start).
  waitCost: 0.05,
  variety: 0.5,
  criterion: "balanced", // see CRITERIA
  allow: { cut: true, blend: true, fade: true, echo: true, brake: false, roll: false },
};

export class Player extends EventTarget {
  constructor(engine, loader) {
    super();
    this.engine = engine;
    this.loader = loader;
    this.settings = structuredClone(DEFAULTS);
    this.enabled = () => true;
    this.timer = null;
    this.reset();
  }

  reset() {
    this.cur = null;
    this.nextTime = 0;
    this.lastJumpAt = -Infinity;
    this.lastChanceAt = -Infinity;
    this.prefetchIds = [];
    this.prefetchedFor = null;
    this.cooldown = 0;
    this.ramp = null;
    this.hold = 1;
    this.blend = null;
    this.fx = null;
    this.plan = null;
    this.jumpNow = false;
    this.urgent = false;
    this.history = [];
    this.timeline = [];
    this.visits = new Map();
    this.stats = { jumps: 0, transitions: 0, startedAt: 0 };
  }

  get playing() {
    return this.timer !== null && this.engine.ctx.state === "running";
  }

  async start(trackId) {
    const track = await this.loader.get(trackId);
    this.engine.stopAll();
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.reset();
    await this.engine.ctx.resume();
    const t = this.engine.now + 0.15;
    this.stats.startedAt = t;
    const voice = this.engine.voice(track);
    voice.start(t, track.beats[0], 1, 0.01);
    this.cur = { track, beat: 0, rate: 1, voice };
    this._enterTrack(track, t, "start");
    this._log(t, "start");
    this.nextTime = t + track.dur[0];
    this.timer = setInterval(() => this._tick(), TICK_MS);
    this._tick();
    this.dispatchEvent(new Event("state"));
  }

  async togglePause() {
    if (!this.cur) return;
    const ctx = this.engine.ctx;
    if (ctx.state === "running") await ctx.suspend();
    else await ctx.resume();
    this.dispatchEvent(new Event("state"));
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.engine.stopAll();
    this.reset();
    this.dispatchEvent(new Event("state"));
  }

  requestJump() {
    this.jumpNow = true;
  }

  // Forget the planned exit (settings changed); a bent tempo bends back.
  cancelPlan() {
    if (this.plan) this._dropPlan();
  }

  // Score limit for this song's jumps under the current strictness setting.
  maxScore(T) {
    return T.scoreCut(this.settings.keep);
  }

  requestNextSong() {
    if (!this.cur || this.blend || this.fx) return;
    this.plan = null;
    this.urgent = true;
    this._prefetch(true);
  }

  // ---------------------------------------------------------------- scheduling

  _tick() {
    if (!this.cur || this.engine.ctx.state !== "running") return;
    const horizon = this.engine.now + LOOKAHEAD;
    let guard = 0;
    while (this.nextTime < horizon && guard++ < 64) this._advance();
  }

  _advance() {
    const t = this.nextTime;
    const step = this._decide(t);
    this._execute(step, t);
    this.nextTime = t + step.track.dur[step.beat] / step.rate;
  }

  // Playback rate for the next beat: follows the current ramp, then holds its
  // end value (1 after a song settles, the meeting tempo while bending).
  _rate() {
    const r = this.ramp;
    if (!r) return this.hold;
    r.k++;
    const v = r.from + (r.to - r.from) * Math.min(1, r.k / r.n);
    if (r.k >= r.n) {
      this.ramp = null;
      this.hold = r.to;
    }
    return v;
  }

  _rampTo(to, beats, from = this.cur ? this.cur.rate : 1) {
    if (Math.abs(from - to) < 1e-4) {
      this.ramp = null;
      this.hold = to;
    } else {
      this.ramp = { from, to, k: 0, n: Math.max(1, Math.round(beats)) };
    }
  }

  // Where a transition is triggered on the walk: blends and effects begin when
  // the walk arrives at a beat; cuts, drops and fades happen after a beat ends.
  _triggerOf(tr) {
    if (tr.type === "blend") return { node: tr.a, arrive: true };
    if (FX.has(tr.type)) return { node: tr.i - (tr.beats || 1) + 1, arrive: true };
    return { node: tr.i, arrive: false };
  }

  // Abandon the planned exit; a song bent toward a meeting tempo bends back.
  _dropPlan() {
    this.plan = null;
    if (this.cur && Math.abs(this.cur.rate - 1) > 1e-3 && !this.blend && !this.fx) this._rampTo(1, BEND_BEATS);
  }

  _decide(t) {
    const { track: T, beat: i } = this.cur;

    if (this.blend) {
      const b = this.blend;
      const k = b.k + 1;
      if (k < b.L) return { kind: "blend", track: T, beat: b.a + k, rate: b.rateA, k };
      return { kind: "promote", track: b.B, beat: b.b + Math.round(b.m * b.L), rate: b.ratesB[b.L - 1] };
    }

    if (this.fx) {
      // The old song is winding down (its audio is already scheduled): keep
      // the clock on its beats, then the new song comes in.
      const f = this.fx;
      if (i < f.end && i + 1 < T.n) return { kind: "fxBeat", track: T, beat: i + 1, rate: this.cur.rate };
      return { kind: "fxDrop", track: f.B, beat: f.tr.j, rate: 1, tr: f.tr };
    }

    if (this.cooldown > 0) this.cooldown--;

    if (this.settings.mode === "chain" && !this.plan) {
      const elapsed = t - this.dwellStart;
      if (elapsed >= this.settings.dwellMin - PREFETCH_LEAD) this._prefetch();
      // From the minimum time on, look for an exit on every beat until one is
      // planned: the nearest good one wins, not a fixed countdown.
      if (elapsed >= this.settings.dwellMin || this.urgent) this._planExit(t);
    }

    const plan = this.plan;
    if (plan) {
      const tr = plan.tr;
      // Tempo bridge: in the bars before the junction the playing song eases
      // toward the meeting tempo, so the next one can come in at it.
      const pre = tr.pre || 1;
      if (!plan.bent && Math.abs(pre - 1) > 1e-4) {
        const beatsLeft = (plan.eta - t) / (T.dur[i] / this.cur.rate);
        if (beatsLeft <= BEND_BEATS + 1) {
          plan.bent = true;
          this._rampTo(pre, Math.max(2, Math.floor(beatsLeft) - 1));
        }
      }
      const routeJump = plan.jumps.get(i);
      const next = routeJump !== undefined ? routeJump : i + 1;
      const trg = this._triggerOf(tr);
      const atTrigger = trg.arrive ? next === trg.node : i === trg.node;
      if (atTrigger) {
        if (!plan.target) {
          // Next song not decoded in time: drop this exit; the next beat plans
          // again and only considers songs that are ready or far enough away.
          this._dropPlan();
        } else if (tr.type === "blend") {
          return { kind: "blendStart", track: T, beat: tr.a, rate: this._rate(), splice: routeJump !== undefined, shift: 0, tr };
        } else if (FX.has(tr.type)) {
          return { kind: "fxStart", track: T, beat: next, rate: this._rate(), splice: routeJump !== undefined, tr };
        } else {
          // B starts at the tempo A has actually reached (normally `pre`).
          const rate = tr.type === "fade" ? 1 : (tr.rate / pre) * this.cur.rate;
          return {
            kind: tr.type === "drop" ? "cut" : tr.type, track: plan.target, beat: tr.j, rate,
            shift: tr.shift_ms / 1000, xf: (tr.xf_ms || 12) / 1000, tr,
          };
        }
      } else if (routeJump !== undefined) {
        const e = T.jumps[i].find((x) => x.to === routeJump);
        return { kind: "jump", track: T, beat: routeJump, rate: this._rate(), shift: e ? e.shift : 0, xf: e ? e.xf : SPLICE_XFADE };
      } else if (i + 1 < T.n) {
        return { kind: "seq", track: T, beat: i + 1, rate: this._rate() };
      }
      if (this.plan) this._dropPlan();
    }

    const jump = this._walk(T, i, t);
    if (jump) return { kind: "jump", track: T, beat: jump.to, rate: this._rate(), shift: jump.shift, xf: jump.xf };
    if (i + 1 < T.n) return { kind: "seq", track: T, beat: i + 1, rate: this._rate() };
    // Fell off the end (no backward jump available): loop to the first beat.
    return { kind: "jump", track: T, beat: 0, rate: this._rate(), shift: 0, xf: 0.04 };
  }

  // Random in-song jumps are paced in seconds, not beats: at least 35 % of the
  // mean interval apart, then an even chance per second of playing time, so a
  // 70 BPM ballad and a 170 BPM track move around at the same pace.
  _walk(T, i, t) {
    const s = this.settings;
    if (i >= T.lbp && T.lbp >= 0) {
      const back = T.jumps[i].filter((e) => e.to <= i).sort((a, b) => a.score - b.score);
      if (back.length) return back[0];
    }
    if (this.cooldown > 0) return null;
    const limit = this.maxScore(T);
    const cands = T.eligible(i, this.jumpNow ? Math.max(limit, T.scoreCut(1)) : limit);
    if (!cands.length) return null;
    if (!this.jumpNow) {
      const minGap = 0.35 * s.jumpEvery;
      if (t - this.lastJumpAt < minGap) return null;
      const since = Math.max(this.lastChanceAt, this.lastJumpAt + minGap);
      this.lastChanceAt = t;
      const p = 1 - Math.exp(-Math.max(0, t - since) / (0.65 * s.jumpEvery));
      if (Math.random() >= p) return null;
    }
    // Prefer good matches, and places we have not landed on much, so the walk
    // keeps exploring the whole song.
    const visits = this._visits(T);
    const w = cands.map((e) => Math.exp(-e.score / 0.08) / (1 + 0.6 * visits[e.to]));
    let r = Math.random() * w.reduce((a, b) => a + b, 0);
    let pick = cands[cands.length - 1];
    for (let k = 0; k < cands.length; k++) {
      r -= w[k];
      if (r <= 0) {
        pick = cands[k];
        break;
      }
    }
    this.jumpNow = false;
    return pick;
  }

  _visits(T) {
    let v = this.visits.get(T.id);
    if (!v) {
      v = new Float32Array(T.n);
      this.visits.set(T.id, v);
    }
    return v;
  }

  _execute(step, t) {
    const prev = this.cur;
    const T = step.track;
    switch (step.kind) {
      case "seq":
        if (step.rate !== prev.rate) prev.voice.setRate(t, step.rate);
        this.cur = { ...prev, beat: step.beat, rate: step.rate };
        break;

      case "jump":
      case "cut": {
        const x = step.xf || SPLICE_XFADE;
        const v = this.engine.voice(T);
        v.start(t - x / 2, T.beats[step.beat] + step.shift - (x / 2) * step.rate, step.rate, x);
        prev.voice.fadeOut(t - x / 2, x);
        this.cur = { track: T, beat: step.beat, rate: step.rate, voice: v };
        this.cooldown = JUMP_COOLDOWN;
        this.lastJumpAt = t;
        if (step.kind === "jump") {
          this.stats.jumps++;
          this._visits(T)[step.beat] += 1;
          this._log(t, "jump", { from: prev.beat });
        } else {
          // B glides from the meeting tempo back to its own.
          this._rampTo(1, RAMP_BEATS, step.rate);
          const via = step.tr?.type === "drop" ? "drop" : "cut";
          this._log(t, via, { from: prev.beat, fromTrack: prev.track.id, tr: step.tr });
          this._enterTrack(T, t, via);
        }
        break;
      }

      case "fxStart":
        this._startFx(step, prev, t);
        break;

      case "fxBeat":
        this.cur = { ...prev, beat: step.beat, rate: step.rate };
        break;

      case "fxDrop": {
        const tr = step.tr;
        const v = this.engine.voice(T);
        if (tr.type === "echo") {
          // Under the ringing echo the new song rises in, filtered, and opens.
          v.low.gain.value = -12;
          v.start(t, T.beats[step.beat], 1, 1.6);
          v.sweep(t, 600, 18000, 2.4);
          v.bass(t + 0.8, 0, 1.4);
        } else {
          // After a brake or a roll it lands on the beat.
          v.start(t, T.beats[step.beat], 1, 0.006);
        }
        this.cur = { track: T, beat: step.beat, rate: 1, voice: v };
        this.fx = null;
        this.ramp = null;
        this.hold = 1;
        this._log(t, tr.type, { fromTrack: prev.track.id, tr });
        this._enterTrack(T, t, tr.type);
        if (tr.type === "echo") this.cooldown = Math.max(this.cooldown, 12);
        break;
      }

      case "fade": {
        const secs = step.tr.seconds || 4;
        const v = this.engine.voice(T);
        // B arrives filtered and without bass and opens up as A recedes; A
        // gives up its bass first, then darkens and sinks under B. The two
        // never fight in the same register, so even far-apart moods blur.
        v.low.gain.value = -14;
        v.start(t, T.beats[step.beat], 1, secs * 0.7);
        v.sweep(t, 420, 18000, secs * 0.75);
        v.bass(t + secs * 0.45, 0, secs * 0.3);
        prev.voice.bass(t, -16, secs * 0.35);
        prev.voice.sweep(t + secs * 0.2, 16000, 700, secs * 0.8);
        prev.voice.gainCurve(FADE_A, t, secs);
        prev.voice.stopAt(t + secs + 0.05);
        this.cur = { track: T, beat: step.beat, rate: 1, voice: v };
        this.ramp = null;
        this.hold = 1;
        // No jumps while the old song is still fading out underneath.
        this.cooldown = Math.max(this.cooldown, Math.ceil(secs / T.dur[step.beat]) + 2);
        this._log(t, "fade", { from: prev.beat, fromTrack: prev.track.id, tr: step.tr });
        this._enterTrack(T, t, "fade");
        break;
      }

      case "blendStart":
        this._startBlend(step, prev, t);
        break;

      case "blend":
        this.blend.k = step.k;
        this.cur = { ...prev, beat: step.beat, rate: step.rate };
        break;

      case "promote": {
        const b = this.blend;
        this.blend = null;
        b.voiceB.setRate(t, step.rate);
        this.cur = { track: b.B, beat: step.beat, rate: step.rate, voice: b.voiceB };
        this._rampTo(1, RAMP_BEATS, step.rate);
        this._enterTrack(b.B, t, "blend");
        this._log(t, "promote");
        break;
      }
    }
    if (step.kind === "seq" || step.kind === "blend" || step.kind === "fxBeat") this._log(t, step.kind);
  }

  _startBlend(step, prev, t) {
    const tr = step.tr;
    const A = step.track;
    const B = this.plan.target;
    const L = tr.len;
    let voiceA = prev.voice;
    let outStart = t;
    if (step.splice) {
      const e = A.jumps[prev.beat].find((x) => x.to === step.beat);
      const x = e ? e.xf : SPLICE_XFADE;
      voiceA = this.engine.voice(A);
      voiceA.start(t - x / 2, A.beats[step.beat] + (e ? e.shift : 0) - (x / 2) * step.rate, step.rate, x);
      prev.voice.fadeOut(t - x / 2, x);
      outStart = t + x / 2; // let the splice fade-in finish before the blend curve
      this.stats.jumps++;
      this.lastJumpAt = t;
    } else if (step.rate !== prev.rate) {
      voiceA.setRate(t, step.rate);
    }
    // Master clock: A's beats at A's rate. B's rate per beat makes the stretch
    // of B laid over each A beat last exactly as long: one B beat, two (B in
    // double time, m = 2) or half of one (B in half time, m = 0.5).
    const m = tr.m || 1;
    const times = [t];
    const ratesB = [];
    const tB = [B.beats[tr.b] + tr.shift_ms / 1000];
    for (let k = 0; k < L; k++) {
      const dM = A.dur[tr.a + k] / step.rate;
      times.push(times[k] + dM);
      let span = 0;
      if (m >= 1) for (let q = 0; q < m; q++) span += B.dur[Math.min(B.n - 1, tr.b + m * k + q)];
      else span = B.dur[Math.min(B.n - 1, tr.b + Math.floor(k * m))] * m;
      ratesB.push(Math.max(0.8, Math.min(1.25, span / dM)));
      tB.push(tB[k] + span);
    }
    const total = times[L] - t;
    const voiceB = this.engine.voice(B);
    voiceB.low.gain.value = -26;
    voiceB.startSilent(t, tB[0], ratesB[0]);
    voiceB.gainCurve(BLEND_IN, t, total);
    for (let k = 1; k < L; k++) voiceB.setRate(times[k], ratesB[k]);
    voiceA.gainCurve(BLEND_OUT, outStart, times[L] - outStart);
    const mid = times[L >> 1];
    voiceA.bass(mid, -26, 0.08);
    voiceB.bass(mid, 0, 0.08);
    voiceA.stopAt(times[L] + 0.05);
    this.blend = { A, B, a: tr.a, b: tr.b, L, m, k: 0, rateA: step.rate, ratesB, voiceB, times, tB, tr };
    this.ramp = null;
    this.hold = step.rate;
    this.plan = null;
    this.cur = { track: A, beat: step.beat, rate: step.rate, voice: voiceA };
    this._log(t, "blendStart", { tr, to: B.id, end: times[L] });
  }

  // Effect transitions. The window is the last `beats` beats of A: an echo
  // feeds a dark delay that rings on, a brake slows the platter to a stop, a
  // roll replays the window's first beat in shrinking slices. Then B comes in
  // on its own tempo at the end of the window.
  _startFx(step, prev, t) {
    const tr = step.tr;
    const A = step.track;
    const B = this.plan.target;
    const w = tr.beats || 1;
    const rate = step.rate;
    let voiceA = prev.voice;
    if (step.splice) {
      const e = A.jumps[prev.beat].find((x) => x.to === step.beat);
      const x = e ? e.xf : SPLICE_XFADE;
      voiceA = this.engine.voice(A);
      voiceA.start(t - x / 2, A.beats[step.beat] + (e ? e.shift : 0) - (x / 2) * rate, rate, x);
      prev.voice.fadeOut(t - x / 2, x);
      this.stats.jumps++;
    } else if (rate !== prev.rate) {
      voiceA.setRate(t, rate);
    }
    const times = [t];
    for (let k = 0; k < w; k++) times.push(times[k] + A.dur[Math.min(A.n - 1, step.beat + k)] / rate);
    const end = times[w];
    const beat = A.dur[step.beat] / rate;
    if (tr.type === "echo") {
      // The dry song sinks across the whole window while the echo it feeds
      // grows, so nothing stops: the song turns into its own echo.
      this.engine.echoOut(voiceA, t, end, beat * 0.75);
      voiceA.fadeOut(t, end - t);
    } else if (tr.type === "brake") {
      voiceA.brake(t, end, rate);
    } else {
      // Roll: halves then quarters of the window's first beat, getting louder.
      const pattern = w >= 2 ? [0.5, 0.5, 0.25, 0.25, 0.25, 0.25] : [0.25, 0.25, 0.25, 0.25];
      const unit = (end - t) / pattern.reduce((s, u) => s + u, 0);
      const slices = [];
      let when = t;
      pattern.forEach((u, n) => {
        slices.push({ when, offset: A.beats[step.beat], dur: u * unit, rate, level: 0.7 + (0.3 * n) / (pattern.length - 1) });
        when += u * unit;
      });
      this.engine.roll(A, slices, A.analysis.gain_db);
      voiceA.fadeOut(t - 0.004, 0.008);
    }
    this.fx = { A, B, tr, end: tr.i, times };
    this.plan = null;
    this.cur = { track: A, beat: step.beat, rate, voice: voiceA };
    this._log(t, "fxStart", { tr, to: B.id, end });
  }

  // ------------------------------------------------------------ chain planning

  _enterTrack(track, t, via) {
    this.dwellStart = t;
    this.plan = null;
    this.urgent = false;
    this.prefetchedFor = null;
    this.prefetchIds = [];
    // Let the new song settle before the first random jump.
    this.lastJumpAt = t;
    this.cooldown = Math.max(this.cooldown, JUMP_COOLDOWN * 2);
    if (via !== "start") this.stats.transitions++;
    this.history.push({ id: track.id, at: t, via });
    if (this.history.length > 50) this.history.shift();
    this.loader.refreshTransitions(track);
    this.dispatchEvent(new CustomEvent("track", { detail: { track, via, at: t } }));
  }

  // Penalty for going back to a song heard recently or often; negative (a
  // bonus) for songs not heard yet this session. Scaled by the variety setting.
  _recency(id) {
    const recent = this.history.map((h) => h.id).reverse();
    const idx = recent.indexOf(id);
    const scale = 0.4 + 1.2 * this.settings.variety;
    if (idx < 0) return -0.3 * scale;
    const window = Math.max(1, Math.min(6, this.loader.readyCount() - 1));
    const plays = recent.filter((x) => x === id).length;
    return scale * (0.8 * Math.max(0, 1 - idx / window) + 0.06 * plays);
  }

  // How much the chain wants this transition, apart from its quality and the
  // wait for it: the kind of hand-over, the chosen criterion, and whether the
  // song was heard lately.
  _appeal(T, tr) {
    const c = CRITERIA[this.settings.criterion] || CRITERIA.balanced;
    let u = (TYPE_BIAS[tr.type] ?? 0) - c.mood * (tr.mood ?? 0) - c.explore * this._recency(tr.to);
    if (c.beat || c.tempo || c.key) {
      const meta = this.loader.metas?.get(tr.to);
      if (c.beat && !BEAT_MATCHED.has(tr.type)) u -= c.beat;
      if (c.tempo) u -= c.tempo * tempoGap(T.analysis.bpm, meta?.bpm, tr);
      if (c.key) u += c.key * (keyFit(T.analysis.camelot, meta?.camelot, tr.semis ?? 0) - 0.6);
    }
    return u;
  }

  // Loads the songs this one is most likely to hand over to, so that an exit
  // only a beat or two away can still be taken.
  _prefetch(force = false) {
    const T = this.cur?.track;
    if (!T) return;
    const key = `${T.id}|${this.history.length}`;
    if (!force && this.prefetchedFor === key) return;
    this.prefetchedFor = key;
    const best = new Map();
    for (const tr of T.transitions) {
      if (!this.settings.allow[allowKey(tr.type)] || tr.to === T.id || !this.enabled(tr.to)) continue;
      const u = tr.q + this._appeal(T, tr);
      if (!best.has(tr.to) || u > best.get(tr.to)) best.set(tr.to, u);
    }
    this.prefetchIds = [...best.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map((e) => e[0]);
    for (const id of this.prefetchIds) this.loader.get(id).catch(() => {});
  }

  // Runs on every beat once the song may be left, until an exit is planned.
  // Waiting costs utility per second, so the nearest good exit wins; after
  // dwellMax (or on request) waiting costs far more and any exit will do.
  _planExit(t) {
    const T = this.cur.track;
    const s = this.settings;
    const items = T.transitions.filter((tr) => s.allow[allowKey(tr.type)] && tr.to !== T.id && this.enabled(tr.to));
    if (!items.length) return;
    const late = this.urgent || t - this.dwellStart >= s.dwellMax;
    const { dist, prev } = T.distances(this.cur.beat, this.maxScore(T));
    const lambda = late ? Math.max(0.15, s.waitCost) : s.waitCost;
    const floor = late ? 0 : 0.3;
    let best = null;
    for (const tr of items) {
      if (tr.q < floor) continue;
      const { node: trigger, arrive } = this._triggerOf(tr);
      if (trigger < 0 || trigger >= T.n) continue;
      let arrival = dist[trigger];
      if (arrive && trigger === this.cur.beat) arrival = Infinity;
      if (!isFinite(arrival)) continue;
      if (arrival < LOAD_LEAD && !this.loader.has(tr.to)) continue;
      const noise = (CRITERIA[s.criterion] || CRITERIA.balanced).noise;
      const u = tr.q - lambda * arrival + this._appeal(T, tr) + Math.random() * noise;
      if (!best || u > best.u) best = { tr, u, trigger, arrival };
    }
    if (!best && late) best = this._emergencyExit(T, items);
    if (!best) return;
    this._setPlan(T, best, prev, t);
  }

  // The listener picked an exit on the stage. Plan it now if the walk can
  // reach it; returns false when it cannot (or while a blend is running).
  planTransition(tr) {
    if (!this.cur || this.blend || this.fx) return false;
    const T = this.cur.track;
    if (!T.transitions.includes(tr) || !this.enabled(tr.to)) return false;
    const { dist, prev } = T.distances(this.cur.beat, this.maxScore(T));
    const { node: trigger, arrive } = this._triggerOf(tr);
    if (trigger < 0 || trigger >= T.n) return false;
    let arrival = dist[trigger];
    if (arrive && trigger === this.cur.beat) arrival = Infinity;
    if (!isFinite(arrival)) return false;
    if (this.plan) this._dropPlan();
    this._setPlan(T, { tr, trigger, arrival }, prev, this.nextTime, true);
    return true;
  }

  _setPlan(T, best, prev, t, picked = false) {
    const jumps = best.tr.synthetic ? new Map() : T.route(prev, this.cur.beat, best.trigger);
    // dist[] counts from the start of the beat just scheduled; a cut, drop or
    // fade happens at the end of its trigger beat, a blend or effect at its start.
    const curStart = t - T.dur[this.cur.beat] / this.cur.rate;
    const arrive = this._triggerOf(best.tr).arrive;
    const eta = curStart + best.arrival + (arrive ? 0 : T.dur[best.trigger]);
    const plan = { tr: best.tr, jumps, target: null, eta, from: T.id, picked };
    this.plan = plan;
    this.loader.get(best.tr.to).then(
      (track) => {
        if (this.plan !== plan) return;
        if (plan.tr.j == null) plan.tr.j = track.entryBeat();
        plan.target = track;
      },
      () => {
        if (this.plan === plan) this._dropPlan();
      },
    );
    this.dispatchEvent(new Event("plan"));
  }

  // No analysed exit is reachable from here (strict settings can isolate a
  // stretch of the song): crossfade out at the next phrase start ahead, into
  // the song that the analysed transitions would have favoured.
  _emergencyExit(T, items) {
    const ph = T.analysis.phrase;
    let k = this.cur.beat + 2;
    while (k < T.n - 1 && ph[k] < 2) k++;
    k = Math.min(k, T.n - 1);
    let arrival = 0;
    for (let b = this.cur.beat; b < k; b++) arrival += T.dur[b];
    if (arrival < LOAD_LEAD) {
      k = Math.min(T.n - 1, k + 4 * (T.analysis.meter || 4));
      arrival = 0;
      for (let b = this.cur.beat; b < k; b++) arrival += T.dur[b];
    }
    let pick = null;
    for (const tr of items) {
      const u = tr.q + this._appeal(T, tr) - (TYPE_BIAS[tr.type] ?? 0);
      if (!pick || u > pick.u) pick = { to: tr.to, u };
    }
    if (!pick) return null;
    const tr = { type: "fade", to: pick.to, i: k - 1, j: null, seconds: 4, rate: 1, shift_ms: 0, q: 0.2, synthetic: true };
    return { tr, u: pick.u, trigger: k - 1, arrival };
  }

  // ------------------------------------------------------------------ UI view

  _log(t, kind, extra = {}) {
    const c = this.cur;
    this.timeline.push({ t, kind, track: c.track, beat: c.beat, rate: c.rate, ...extra });
    if (this.timeline.length > 400) this.timeline.splice(0, 100);
  }

  // The step being heard right now (the scheduler runs ahead of the speakers).
  audible() {
    const now = this.engine.audibleTime();
    const tl = this.timeline;
    for (let k = tl.length - 1; k >= 0; k--) if (tl[k].t <= now) return { entry: tl[k], now, index: k };
    return tl.length ? { entry: tl[0], now, index: 0 } : null;
  }

  recentEvents(since) {
    return this.timeline.filter((e) => e.t > since && e.t <= this.engine.audibleTime() && !["seq", "blend", "fxBeat"].includes(e.kind));
  }
}
