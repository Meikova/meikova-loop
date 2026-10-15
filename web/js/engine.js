// Web Audio plumbing. A Voice is one running read head into a track's buffer;
// the player creates a new voice at every splice and lets the old one fade out.

const CURVE_POINTS = 128;

export function dbToGain(db) {
  return Math.pow(10, db / 20);
}

function curve(fn) {
  const c = new Float32Array(CURVE_POINTS);
  for (let i = 0; i < CURVE_POINTS; i++) c[i] = fn(i / (CURVE_POINTS - 1));
  return c;
}

export const FADE_IN = curve((x) => Math.sin((Math.PI / 2) * x));
export const FADE_OUT = curve((x) => Math.cos((Math.PI / 2) * x));

export class Engine {
  constructor() {
    // Same rate as the stored audio: beat times map to samples with no resampling.
    this.ctx = new AudioContext({ sampleRate: 44100, latencyHint: "playback" });
    this.master = this.ctx.createGain();
    this.master.gain.value = dbToGain(-3);
    this.limiter = this.ctx.createDynamicsCompressor();
    this.limiter.threshold.value = -2;
    this.limiter.knee.value = 3;
    this.limiter.ratio.value = 12;
    this.limiter.attack.value = 0.002;
    this.limiter.release.value = 0.15;
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.master.connect(this.limiter).connect(this.analyser).connect(this.ctx.destination);
    this.voices = new Set();
  }

  get now() {
    return this.ctx.currentTime;
  }

  // Time the listener is hearing right now, on the context clock.
  audibleTime() {
    const lat = (this.ctx.outputLatency || 0) + (this.ctx.baseLatency || 0);
    return this.ctx.currentTime - lat;
  }

  setVolume(v) {
    this.master.gain.setTargetAtTime(v, this.ctx.currentTime, 0.05);
  }

  voice(track) {
    const v = new Voice(this, track);
    this.voices.add(v);
    return v;
  }

  stopAll(fade = 0.08) {
    const t = this.ctx.currentTime;
    for (const v of this.voices) v.release(t, fade);
    this.voices.clear();
    for (const n of this.fxNodes || []) n.disconnect();
    this.fxNodes = [];
  }

  _keep(nodes, until) {
    this.fxNodes = (this.fxNodes || []).concat(nodes);
    const ms = Math.max(0, (until - this.ctx.currentTime) * 1000);
    setTimeout(() => {
      for (const n of nodes) n.disconnect();
      this.fxNodes = this.fxNodes.filter((n) => !nodes.includes(n));
    }, ms + 200);
  }

  // Echo out: the voice's signal (before its fader) feeds a feedback delay
  // whose repeats get darker and quieter. The feed opens over [start, end],
  // then closes; the tail rings on under the next song.
  echoOut(voice, start, end, delay) {
    const ctx = this.ctx;
    const send = ctx.createGain();
    const dl = ctx.createDelay(4);
    const fb = ctx.createGain();
    const lp = ctx.createBiquadFilter();
    const hp = ctx.createBiquadFilter();
    const wet = ctx.createGain();
    send.gain.value = 0;
    dl.delayTime.value = Math.min(3.9, delay);
    fb.gain.value = 0.55;
    lp.type = "lowpass";
    lp.frequency.value = 2300;
    hp.type = "highpass";
    hp.frequency.value = 180;
    wet.gain.value = 0.9;
    voice.trim.connect(send);
    send.connect(dl).connect(lp).connect(hp);
    hp.connect(fb).connect(dl);
    hp.connect(wet).connect(this.master);
    send.gain.setValueAtTime(0, start);
    send.gain.linearRampToValueAtTime(1, end);
    send.gain.linearRampToValueAtTime(0, end + 0.03);
    this._keep([send, dl, fb, lp, hp, wet], end + delay * 12 + 1);
  }

  // Loop roll: slices of one beat replayed back to back in a shrinking pattern
  // under a rising high-pass, so the old song winds up into the new one.
  roll(track, slices, gainDb) {
    const ctx = this.ctx;
    const t0 = slices[0].when;
    const last = slices[slices.length - 1];
    const t1 = last.when + last.dur;
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.setValueAtTime(90, t0);
    hp.frequency.exponentialRampToValueAtTime(1600, t1);
    const out = ctx.createGain();
    out.gain.value = dbToGain(gainDb);
    hp.connect(out).connect(this.master);
    const nodes = [hp, out];
    for (const s of slices) {
      const src = ctx.createBufferSource();
      src.buffer = track.buffer;
      src.playbackRate.value = s.rate;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, s.when);
      g.gain.linearRampToValueAtTime(s.level, s.when + 0.003);
      g.gain.setValueAtTime(s.level, Math.max(s.when + 0.003, s.when + s.dur - 0.004));
      g.gain.linearRampToValueAtTime(0, s.when + s.dur);
      src.connect(g).connect(hp);
      src.start(s.when, Math.max(0, s.offset));
      src.stop(s.when + s.dur + 0.01);
      nodes.push(src, g);
    }
    this._keep(nodes, t1 + 0.5);
  }
}

export class Voice {
  constructor(engine, track) {
    const ctx = engine.ctx;
    this.engine = engine;
    this.track = track;
    this.src = ctx.createBufferSource();
    this.src.buffer = track.buffer;
    this.low = ctx.createBiquadFilter();
    this.low.type = "lowshelf";
    this.low.frequency.value = 180;
    this.low.gain.value = 0;
    // Open low-pass, swept down to darken a song leaving and up to open one arriving.
    this.lp = ctx.createBiquadFilter();
    this.lp.type = "lowpass";
    this.lp.frequency.value = 20000;
    this.lp.Q.value = 0.5;
    this.trim = ctx.createGain();
    this.trim.gain.value = dbToGain(track.analysis.gain_db);
    this.gain = ctx.createGain();
    this.gain.gain.value = 0;
    this.src.connect(this.low).connect(this.lp).connect(this.trim).connect(this.gain).connect(engine.master);
    this.src.onended = () => {
      engine.voices.delete(this);
      this.gain.disconnect();
    };
    this.stopped = false;
  }

  start(when, offset, rate, fadeIn) {
    this.src.playbackRate.setValueAtTime(rate, when);
    if (fadeIn > 0) {
      this.gain.gain.setValueAtTime(0, when);
      this._curve(FADE_IN, when, fadeIn);
    } else {
      this.gain.gain.setValueAtTime(1, when);
    }
    this.src.start(when, Math.max(0, offset));
  }

  // Starts reading without touching the gain: the caller automates it.
  startSilent(when, offset, rate) {
    this.src.playbackRate.setValueAtTime(rate, when);
    this.src.start(when, Math.max(0, offset));
  }

  setRate(when, rate) {
    this.src.playbackRate.setValueAtTime(rate, when);
  }

  // Turntable brake: the platter slows to a near stop over [t0, t1] while the
  // sound fades through the last part of it.
  brake(t0, t1, from) {
    const p = this.src.playbackRate;
    p.setValueAtTime(from, t0);
    p.linearRampToValueAtTime(0.05, t1);
    const tf = t0 + (t1 - t0) * 0.5;
    this._curve(FADE_OUT, tf, t1 - tf);
    this.stopAt(t1 + 0.02);
  }

  gainCurve(values, when, dur) {
    this._curve(values, when, dur);
  }

  fadeOut(when, dur) {
    this._curve(FADE_OUT, when, dur);
    this.stopAt(when + dur + 0.02);
  }

  stopAt(when) {
    if (this.stopped) return;
    this.stopped = true;
    try {
      this.src.stop(when);
    } catch (_) {
      /* already stopped */
    }
  }

  // Immediate release used when the whole transport stops.
  release(t, fade) {
    const g = this.gain.gain;
    g.cancelScheduledValues(t);
    g.setValueAtTime(g.value, t);
    g.linearRampToValueAtTime(0, t + fade);
    this.stopped = false;
    this.stopAt(t + fade + 0.02);
  }

  bass(when, db, ramp = 0.06) {
    const p = this.low.gain;
    p.setValueAtTime(p.value, when);
    p.linearRampToValueAtTime(db, when + ramp);
  }

  // Low-pass sweep (exponential, so it sounds even across octaves).
  sweep(when, fromHz, toHz, dur) {
    const f = this.lp.frequency;
    f.setValueAtTime(fromHz, when);
    f.exponentialRampToValueAtTime(toHz, when + Math.max(0.05, dur));
  }

  _curve(values, when, dur) {
    const g = this.gain.gain;
    try {
      g.setValueCurveAtTime(values, when, Math.max(0.005, dur));
    } catch (_) {
      // Overlapping automation: fall back to a ramp toward the curve's end value.
      g.cancelScheduledValues(when);
      g.setValueAtTime(g.value, when);
      g.linearRampToValueAtTime(values[values.length - 1], when + Math.max(0.005, dur));
    }
  }
}
