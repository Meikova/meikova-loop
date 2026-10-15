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

// A band at or below this many dB is killed outright (gain 0).
export const KILL_DB = -60;
const toGain = (db) => (db <= KILL_DB ? 0 : dbToGain(db));
// Crossover points of the isolator EQ, like a DJ mixer's three-band isolator.
const LOW_X = 200;
const HIGH_X = 2500;

function butter(ctx, type, freq) {
  const f = ctx.createBiquadFilter();
  f.type = type;
  f.frequency.value = freq;
  f.Q.value = Math.SQRT1_2;
  return f;
}

// Linkwitz-Riley (two Butterworth sections): a low and a high band of one
// crossover sum back flat, so the open EQ leaves the sound untouched.
function lr4(ctx, input, type, freq) {
  const a = butter(ctx, type, freq);
  const b = butter(ctx, type, freq);
  input.connect(a).connect(b);
  return b;
}

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

  // Key lock needs AudioWorklet (Signalsmith Stretch runs in one).
  get canStretch() {
    return typeof AudioWorkletNode === "function" && !!this.ctx.audioWorklet;
  }

  // A voice reading [from, to] s of the track through Signalsmith Stretch, so
  // its tempo can change with its pitch kept; with `vocals` (the stem's
  // AudioBuffer) both go through one stretcher, four channels, so they stay
  // sample-aligned and the voice can be taken out of the mix. Resolves once
  // the audio is loaded into the worklet (prepared ahead of the transition).
  async stretchVoice(track, from, to, vocals = null) {
    const { default: SignalsmithStretch } = await import("../vendor/signalsmith-stretch-1.3.2.mjs");
    const channels = vocals ? 4 : 2;
    const node = await SignalsmithStretch(this.ctx, { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [channels] });
    const sr = track.buffer.sampleRate;
    const a = Math.max(0, Math.floor(from * sr));
    const b = Math.min(track.buffer.length, Math.ceil(to * sr));
    const take = (buf, c) => buf.getChannelData(Math.min(c, buf.numberOfChannels - 1)).slice(a, b);
    const chans = [take(track.buffer, 0), take(track.buffer, 1)];
    if (vocals) chans.push(take(vocals, 0), take(vocals, 1));
    await node.addBuffers(chans, chans.map((c) => c.buffer));
    const v = new Voice(this, track, { node, from: a / sr, to: b / sr, channels, latency: await node.latency() });
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

  // Echo out: the voice's signal (before its fader) feeds a feedback delay for
  // the last beat only; the repeats are band-limited inside the loop (high-pass
  // 350 Hz, low-pass 4 kHz), so each one is thinner and the tail never muddies
  // the next song's bass. The tail rings on after the dry song is cut.
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
    fb.gain.value = 0.5;
    lp.type = "lowpass";
    lp.frequency.value = 4000;
    hp.type = "highpass";
    hp.frequency.value = 350;
    wet.gain.value = 0.85;
    voice.trim.connect(send);
    send.connect(dl).connect(lp).connect(hp);
    hp.connect(fb).connect(dl);
    hp.connect(wet).connect(this.master);
    send.gain.setValueAtTime(0, start);
    send.gain.linearRampToValueAtTime(1, start + 0.01);
    send.gain.setValueAtTime(1, Math.max(start + 0.01, end - 0.01));
    send.gain.linearRampToValueAtTime(0, end + 0.01);
    this._keep([send, dl, fb, lp, hp, wet], end + delay * 14 + 1);
  }

  // Reverb wash: the voice swells into a long, high-passed reverb over
  // [start, end] and is cut there; the tail (about 4 s) blurs whatever differs
  // between the songs while the next one comes in under it.
  wash(voice, start, end) {
    const ctx = this.ctx;
    const send = ctx.createGain();
    const hp = ctx.createBiquadFilter();
    const verb = ctx.createConvolver();
    const ret = ctx.createGain();
    hp.type = "highpass";
    hp.frequency.value = 300;
    verb.buffer = this._impulse();
    send.gain.setValueAtTime(0, start);
    send.gain.linearRampToValueAtTime(1, end);
    send.gain.linearRampToValueAtTime(0, end + 0.02);
    ret.gain.setValueAtTime(0.9, start);
    ret.gain.setValueAtTime(0.9, end);
    ret.gain.linearRampToValueAtTime(0.5, end + 0.6); // -6 dB once the next song is in
    voice.trim.connect(send);
    send.connect(hp).connect(verb).connect(ret).connect(this.master);
    this._keep([send, hp, verb, ret], end + 5);
  }

  // A synthetic hall: stereo noise decaying 60 dB over 4 s, made once.
  _impulse() {
    if (this.ir) return this.ir;
    const sr = this.ctx.sampleRate;
    const n = Math.round(sr * 4.5);
    const buf = this.ctx.createBuffer(2, n, sr);
    for (let c = 0; c < 2; c++) {
      const d = buf.getChannelData(c);
      for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.exp((-6.9 * i) / (4 * sr)) * 0.35;
    }
    this.ir = buf;
    return buf;
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
    hp.frequency.setValueAtTime(40, t0);
    hp.frequency.exponentialRampToValueAtTime(1500, t1);
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

// The vocal stem against the full track: kept out (the instrumental: the
// full mix minus the sample-aligned stem), alone (the acapella), or neither.
const VOCAL_MODES = { full: [1, 0], instrumental: [1, -1], acapella: [0, 1] };

export class Voice {
  // `stretch`: { node, from, channels } for a key-locked voice (Engine.stretchVoice):
  // the track read through Signalsmith Stretch, tempo changed with pitch kept.
  constructor(engine, track, stretch = null) {
    const ctx = engine.ctx;
    this.engine = engine;
    this.track = track;
    this.stretch = stretch;
    this.stretched = !!stretch;
    this.shift = 0; // read position minus the beat time it plays (set by the player)
    // Before the EQ: the track (mainGain) and, when attached, its vocal stem
    // (vocGain), summed, so the stem can take the voice out or leave it alone.
    this.pre = ctx.createGain();
    this.mainGain = ctx.createGain();
    this.vocGain = ctx.createGain();
    this.vocGain.gain.value = 0;
    this.mix = { main: 1, voc: 0 };
    this.hasVocals = false;
    this.voc = null;
    this.mainGain.connect(this.pre);
    this.vocGain.connect(this.pre);
    if (stretch) {
      const split = ctx.createChannelSplitter(stretch.channels);
      const main = ctx.createChannelMerger(2);
      stretch.node.connect(split);
      split.connect(main, 0, 0);
      split.connect(main, 1, 1);
      main.connect(this.mainGain);
      if (stretch.channels === 4) {
        const voc = ctx.createChannelMerger(2);
        split.connect(voc, 2, 0);
        split.connect(voc, 3, 1);
        voc.connect(this.vocGain);
        this.hasVocals = true;
      }
      this.src = null;
    } else {
      this.src = ctx.createBufferSource();
      this.src.buffer = track.buffer;
      this.src.connect(this.mainGain);
    }
    // Three-band isolator: low (< 200 Hz), mid, high (> 2.5 kHz), one gain each,
    // so a band can be dipped or killed (the bass swap of a DJ mix).
    this.sum = ctx.createGain();
    this.bands = { low: ctx.createGain(), mid: ctx.createGain(), high: ctx.createGain() };
    this.level = { low: 1, mid: 1, high: 1 }; // last scheduled gain per band
    lr4(ctx, this.pre, "lowpass", LOW_X).connect(this.bands.low).connect(this.sum);
    lr4(ctx, lr4(ctx, this.pre, "highpass", LOW_X), "lowpass", HIGH_X).connect(this.bands.mid).connect(this.sum);
    lr4(ctx, this.pre, "highpass", HIGH_X).connect(this.bands.high).connect(this.sum);
    // Open low-pass, swept down to darken a song leaving and up to open one
    // arriving; open high-pass, swept up to thin a song out of a filter hand-over.
    this.lp = ctx.createBiquadFilter();
    this.lp.type = "lowpass";
    this.lp.frequency.value = 20000;
    this.lp.Q.value = 0.5;
    this.hp = ctx.createBiquadFilter();
    this.hp.type = "highpass";
    this.hp.frequency.value = 10;
    this.hp.Q.value = Math.SQRT1_2;
    this.trim = ctx.createGain();
    this.trim.gain.value = dbToGain(track.analysis.gain_db);
    this.gain = ctx.createGain();
    this.gain.gain.value = 0;
    this.sum.connect(this.lp).connect(this.hp).connect(this.trim).connect(this.gain).connect(engine.master);
    if (this.src) {
      this.src.onended = () => {
        engine.voices.delete(this);
        this.gain.disconnect();
      };
    }
    this.stopped = false;
  }

  start(when, offset, rate, fadeIn) {
    this._read(when, offset, rate);
    if (fadeIn > 0) {
      this.gain.gain.setValueAtTime(0, when);
      this._curve(FADE_IN, when, fadeIn);
    } else {
      this.gain.gain.setValueAtTime(1, when);
    }
  }

  // Starts reading without touching the gain: the caller automates it.
  startSilent(when, offset, rate) {
    this._read(when, offset, rate);
  }

  _read(when, offset, rate) {
    if (this.stretch) {
      this.stretch.node.schedule({ active: true, input: offset - this.stretch.from, output: when, outputTime: when, rate, semitones: 0 });
      return;
    }
    this.src.playbackRate.setValueAtTime(rate, when);
    this.src.start(when, Math.max(0, offset));
  }

  // `pos`: the read position at `when` (a key-locked voice resyncs to it on
  // every beat; a plain voice just follows its rate).
  setRate(when, rate, pos = null) {
    if (this.stretch) {
      const change = { output: when, outputTime: when, rate };
      if (pos != null) change.input = pos - this.stretch.from;
      this.stretch.node.schedule(change);
      return;
    }
    this.src.playbackRate.setValueAtTime(rate, when);
    if (this.voc) this.voc.playbackRate.setValueAtTime(rate, when);
  }

  // The vocal stem, read alongside from `offset` at `rate` from `when` on
  // (a plain voice; a key-locked one gets it from Engine.stretchVoice).
  attachVocals(buffer, when, offset, rate) {
    if (!buffer || this.stretch || this.voc) return;
    const s = this.engine.ctx.createBufferSource();
    s.buffer = buffer;
    s.playbackRate.setValueAtTime(rate, when);
    s.connect(this.vocGain);
    s.start(when, Math.max(0, offset));
    if (this.stopWhen != null) s.stop(this.stopWhen);
    this.voc = s;
    this.hasVocals = true;
  }

  // full | instrumental (voice out) | acapella (voice alone), over `ramp` s.
  vocals(when, mode, ramp = 0) {
    if (!this.hasVocals) return;
    const [main, voc] = VOCAL_MODES[mode];
    const end = when + Math.max(0.005, ramp);
    for (const [k, node, to] of [["main", this.mainGain, main], ["voc", this.vocGain, voc]]) {
      node.gain.setValueAtTime(this.mix[k], when);
      node.gain.linearRampToValueAtTime(to, end);
      this.mix[k] = to;
    }
  }

  // Turntable brake: the platter slows to a near stop over [t0, t1] while the
  // sound fades through the last part of it.
  brake(t0, t1, from) {
    if (this.stretch) {
      for (let k = 0; k < 8; k++) this.setRate(t0 + ((t1 - t0) * k) / 8, from * (1 - (0.95 * k) / 8));
    } else {
      const p = this.src.playbackRate;
      p.setValueAtTime(from, t0);
      p.linearRampToValueAtTime(0.05, t1);
    }
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
    this.stopWhen = when;
    if (this.stretch) {
      this.stretch.node.schedule({ active: false, output: when, outputTime: when });
      const ms = Math.max(0, (when - this.engine.ctx.currentTime) * 1000) + 500;
      setTimeout(() => this.dispose(), ms);
      return;
    }
    try {
      this.src.stop(when);
      if (this.voc) this.voc.stop(when);
    } catch (_) {
      /* already stopped */
    }
  }

  // A key-locked voice frees its worklet and buffers once it has stopped.
  dispose() {
    this.engine.voices.delete(this);
    this.gain.disconnect();
    if (this.stretch) {
      this.stretch.node.disconnect();
      this.stretch.node.dropBuffers?.();
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

  // A band set at `when` (dB; KILL_DB and below: off).
  setBand(name, when, db) {
    const v = toGain(db);
    this.bands[name].gain.setValueAtTime(v, when);
    this.level[name] = v;
  }

  // A band moved from its last scheduled level to `db` over [when, when+dur].
  // Long moves go evenly in dB (exponentially), as a DJ turns an EQ knob;
  // a kill or a short swap goes straight.
  rampBand(name, when, db, dur) {
    const p = this.bands[name].gain;
    const from = this.level[name];
    const to = toGain(db);
    const end = when + Math.max(0.005, dur);
    p.setValueAtTime(from, when);
    if (from > 0 && to > 0 && dur > 0.25) p.exponentialRampToValueAtTime(to, end);
    else p.linearRampToValueAtTime(to, end);
    this.level[name] = to;
  }

  bass(when, db, ramp = 0.06) {
    this.rampBand("low", when, db, ramp);
  }

  // Low-pass sweep (exponential, so it sounds even across octaves).
  sweep(when, fromHz, toHz, dur) {
    const f = this.lp.frequency;
    f.setValueAtTime(fromHz, when);
    f.exponentialRampToValueAtTime(toHz, when + Math.max(0.05, dur));
  }

  // High-pass sweep with a resonance that rises as it climbs.
  hpSweep(when, fromHz, toHz, dur, qFrom = 0.7, qTo = 1.2) {
    const f = this.hp.frequency;
    const q = this.hp.Q;
    const end = when + Math.max(0.05, dur);
    f.setValueAtTime(fromHz, when);
    f.exponentialRampToValueAtTime(toHz, end);
    q.setValueAtTime(qFrom, when);
    q.linearRampToValueAtTime(qTo, end);
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
