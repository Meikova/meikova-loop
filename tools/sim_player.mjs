// Fast simulation of the real Player logic (web/js/player.js) against a fake
// audio engine: hours of playback in seconds.
//   node tools/sim_player.mjs [minutes=180] [mode=chain|single] [seed]
// Checks: no exceptions, every beat starts where the previous ended, gain
// automation never overlaps on a voice, no voice leaks, never falls off the
// end of a song, and (chain mode) how widely the library gets visited.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Track } from "../web/js/graph.js";
import { keyFit, Player, tempoGap } from "../web/js/player.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LIB = path.join(ROOT, "data", "library");
const minutes = +(process.argv[2] || 180);
const mode = process.argv[3] || "chain";
let seed = +(process.argv[4] || 1);
Math.random = () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
};

const read = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const metas = fs.readdirSync(LIB).map((d) => read(path.join(LIB, d, "meta.json"))).filter((m) => m.status === "ready");

// ---------------------------------------------------------------- fake audio
const problems = [];
let now = 0;
class FakeParam {
  constructor(voice, name) {
    this.voice = voice;
    this.name = name;
    this.value = name === "gain" ? 0 : 1;
    this.curves = [];
  }
  setValueAtTime() {}
  linearRampToValueAtTime() {}
  cancelScheduledValues() {
    this.curves = [];
  }
  setValueCurveAtTime(values, when, dur) {
    for (const [a, b] of this.curves) {
      if (when < b - 1e-6 && when + dur > a + 1e-6) {
        problems.push(`overlapping ${this.name} curve on ${this.voice.track.id} at ${when.toFixed(3)}`);
        throw new Error("overlap");
      }
    }
    this.curves.push([when, when + dur]);
  }
}
class FakeVoice {
  constructor(engine, track) {
    this.engine = engine;
    this.track = track;
    this.gain = { gain: new FakeParam(this, "gain") };
    this.low = { gain: new FakeParam(this, "low") };
    this.started = null;
    this.stopTime = Infinity;
  }
  start(when, offset) {
    this.started = when;
    if (offset < -1e-6 || offset > this.track.end + 1e-3) problems.push(`bad offset ${offset} on ${this.track.id}`);
  }
  startSilent(when, offset) {
    this.start(when, offset);
  }
  setRate(when, rate) {
    if (!(rate > 0.8 && rate < 1.2)) problems.push(`rate ${rate}`);
  }
  gainCurve(v, when, dur) {
    try {
      this.gain.gain.setValueCurveAtTime(v, when, dur);
    } catch (_) {
      /* recorded */
    }
  }
  fadeOut(when, dur) {
    this.gainCurve(null, when, dur);
    this.stopAt(when + dur + 0.02);
  }
  stopAt(t) {
    this.stopTime = Math.min(this.stopTime, t);
  }
  bass() {}
  sweep(when, fromHz, toHz, dur) {
    if (!(fromHz > 0 && toHz > 0 && dur > 0)) problems.push(`bad sweep ${fromHz}->${toHz} in ${dur}`);
  }
  brake(t0, t1, from) {
    if (!(from > 0.8 && from < 1.2)) problems.push(`brake from rate ${from}`);
    this.gainCurve(null, t0 + (t1 - t0) * 0.5, (t1 - t0) * 0.5);
    this.stopAt(t1 + 0.02);
  }
  release(t) {
    this.stopTime = t;
  }
}
const fxLog = { echo: 0, roll: 0 };
const engine = {
  ctx: { state: "running", resume: async () => {}, suspend: async () => {} },
  get now() {
    return now;
  },
  audibleTime: () => now,
  voices: new Set(),
  voice(track) {
    const v = new FakeVoice(this, track);
    this.voices.add(v);
    return v;
  },
  stopAll() {
    for (const v of this.voices) v.release(now);
  },
  echoOut(voice, start, end, delay) {
    fxLog.echo++;
    if (!(end > start && delay > 0.05 && delay < 2)) problems.push(`echo window ${start}-${end} delay ${delay}`);
  },
  roll(track, slices) {
    fxLog.roll++;
    let t = slices[0].when;
    for (const s of slices) {
      if (Math.abs(s.when - t) > 1e-6 || !(s.dur > 0.01)) problems.push(`roll slice gap at ${s.when}`);
      t = s.when + s.dur;
    }
  },
};

// ------------------------------------------------------------------- loader
const cache = new Map();
const loader = {
  metas: new Map(metas.map((m) => [m.id, m])),
  readyCount: () => metas.length,
  has: (id) => cache.has(id),
  async get(id) {
    if (!cache.has(id)) {
      const meta = metas.find((m) => m.id === id);
      const t = new Track(meta, read(path.join(LIB, id, "analysis.json")), null);
      const tp = path.join(ROOT, "data", "transitions", `${id}.json`);
      t.transitions = fs.existsSync(tp) ? read(tp).items : [];
      cache.set(id, t);
    }
    return cache.get(id);
  },
  refreshTransitions() {},
};

// --------------------------------------------------------------------- run
const player = new Player(engine, loader);
player.settings.mode = mode;
if (process.argv[5]) player.settings.keep = +process.argv[5];
if (process.argv[6]) player.settings.waitCost = +process.argv[6];
// CRITERION=mood|tempo|key|free picks what the chain looks for (default balanced).
if (process.env.CRITERION) player.settings.criterion = process.env.CRITERION;
player.settings.dwellMin = 60;
player.settings.dwellMax = 150;
player.enabled = () => true;
// Plan history per visit, to explain long waits (DEBUG_WAIT=1 prints them).
let planLog = [];
const origSet = player._setPlan.bind(player);
player._setPlan = (T, best, prev, t, picked) => {
  origSet(T, best, prev, t, picked);
  planLog.push(`plan ${best.tr.type}->${best.tr.to.slice(0, 5)} q=${best.tr.q} at ${t.toFixed(1)} eta ${(player.plan.eta - t).toFixed(1)}s`);
};
const origDrop = player._dropPlan.bind(player);
player._dropPlan = () => {
  if (player.plan) planLog.push(`drop ${player.plan.tr.type} at ${now.toFixed(1)} target=${!!player.plan.target}`);
  origDrop();
};
player.addEventListener("track", () => {
  const h = player.history;
  if (process.env.DEBUG_WAIT && h.length > 1) {
    const stay = h[h.length - 1].at - h[h.length - 2].at;
    if (stay > player.settings.dwellMax + 30) console.log(`\nlong stay ${stay.toFixed(0)}s in ${h[h.length - 2].id}:\n  ${planLog.slice(-8).join("\n  ")}`);
  }
  planLog = [];
});
await player.start(metas[0].id);
clearInterval(player.timer);
player.timer = 1;

const end = minutes * 60;
let last = null;
let maxDev = 0;
let steps = 0;
let fellOff = 0;
let rapid = 0;
const jumpGaps = [];
const leaveWaits = [];
const moodsTaken = [];
const changes = []; // per song change: beat kept?, tempo gap (octaves), key fit
let songStart = null;
let lastJumpT = -Infinity;
const counts = {};
const seconds = new Map();
let lastLog = 0;
const step = 0.04;
while (now < end) {
  now += step;
  try {
    player._tick();
  } catch (e) {
    problems.push(`exception at ${now.toFixed(1)}s: ${e.stack}`);
    break;
  }
  await Promise.resolve(); // let loader promises settle like the event loop would
  const tl = player.timeline;
  for (let k = Math.max(0, tl.length - 64); k < tl.length; k++) {
    const e = tl[k];
    if (last && e.t <= last.t) continue;
    if (last && last.kind !== "start") {
      const expected = last.t + last.track.dur[last.beat] / last.rate;
      maxDev = Math.max(maxDev, Math.abs(e.t - expected));
    }
    if (e.kind === "jump" && last && e.beat === 0 && last.beat === last.track.n - 1) fellOff++;
    if (e.kind === "jump") {
      if (e.t - lastJumpT < 1.5) rapid++;
      if (isFinite(lastJumpT)) jumpGaps.push(e.t - lastJumpT);
      lastJumpT = e.t;
    } else if (!["seq", "blend", "fxBeat"].includes(e.kind)) {
      lastJumpT = -Infinity; // a song change restarts the pacing
    }
    // A transition starts (blend start, cut or fade): how long after the
    // minimum stay did it begin? (The song counts as entered when the player
    // enters it: at a cut/fade, or at the end of a blend.)
    if (["blendStart", "fxStart", "cut", "drop", "fade"].includes(e.kind) && songStart !== null) {
      leaveWaits.push(e.t - songStart - player.settings.dwellMin);
      if (e.tr) {
        moodsTaken.push(e.tr.mood ?? 0);
        const from = loader.metas.get(e.fromTrack ?? e.track.id), to = loader.metas.get(e.tr.to);
        changes.push({
          matched: ["cut", "drop", "blend"].includes(e.tr.type),
          gap: tempoGap(from?.bpm, to?.bpm, e.tr),
          key: keyFit(from?.camelot, to?.camelot, e.tr.semis ?? 0),
        });
      }
    }
    if (["start", "promote", "cut", "drop", "fade", "echo", "brake", "roll"].includes(e.kind)) songStart = e.t;
    counts[e.kind] = (counts[e.kind] || 0) + 1;
    seconds.set(e.track.id, (seconds.get(e.track.id) || 0) + e.track.dur[e.beat] / e.rate);
    last = e;
    steps++;
  }
  // Voices still sounding (not yet stopped).
  let live = 0;
  for (const v of engine.voices) if (v.started !== null && v.started <= now && v.stopTime > now) live++;
  if (live > 3) {
    const msg = `${live} live voices at ${now.toFixed(1)}s`;
    if (!problems.some((p) => p.includes("live voices"))) {
      const vs = [...engine.voices].filter((v) => v.stopTime > now).map((v) => `${v.track.id}@${v.started?.toFixed(2)}-${v.stopTime.toFixed(2)}`);
      const ev = player.timeline.slice(-40).filter((e) => e.kind !== "seq" && e.kind !== "blend").map((e) => `${e.kind}@${e.t.toFixed(2)}`);
      problems.push(`${msg}: voices ${vs.join(", ")} | recent ${ev.join(" ")}`);
    } else problems.push(msg);
  }
  for (const v of [...engine.voices]) if (v.stopTime < now - 1) engine.voices.delete(v);
  if (now - lastLog > 1800) {
    lastLog = now;
    process.stdout.write(`  ${Math.round(now / 60)} min, ${player.stats.transitions} transitions\r`);
  }
}

const title = (id) => (metas.find((m) => m.id === id)?.title || id).slice(0, 38);
console.log(`\nsimulated ${minutes} min in ${mode} mode over ${metas.length} tracks`);
console.log(`steps ${steps}, max schedule deviation ${(maxDev * 1000).toFixed(4)} ms, fell off the end ${fellOff}x`);
console.log(`events`, counts);
console.log(`jumps ${player.stats.jumps} (${(player.stats.jumps / minutes).toFixed(1)}/min), back-to-back (<1.5 s apart) ${rapid}, transitions ${player.stats.transitions}`);
const via = {};
for (const h of player.history) via[h.via] = (via[h.via] || 0) + 1;
console.log(`last ${player.history.length} song changes by kind`, via);
// How long each song was kept, against the minimum: with "nearest good exit"
// most visits should end shortly after dwellMin.
const stays = [];
for (let k = 1; k < player.history.length; k++) stays.push(player.history[k].at - player.history[k - 1].at);
if (stays.length) {
  stays.sort((a, b) => a - b);
  const q = (p) => stays[Math.min(stays.length - 1, Math.floor(p * stays.length))].toFixed(0);
  const wait = stays.map((s) => s - player.settings.dwellMin).sort((a, b) => a - b);
  const w = (p) => wait[Math.min(wait.length - 1, Math.floor(p * wait.length))].toFixed(0);
  console.log(`time per visit (dwellMin ${player.settings.dwellMin}s, dwellMax ${player.settings.dwellMax}s): p10 ${q(0.1)}s p50 ${q(0.5)}s p90 ${q(0.9)}s max ${q(1)}s`);
  console.log(`  wait after the minimum: p50 ${w(0.5)}s p90 ${w(0.9)}s`);
}
if (moodsTaken.length) {
  // Compare with what a mood-blind chain would take: the mean over all pairs.
  const all = [];
  for (const m of metas) {
    const tp = path.join(ROOT, "data", "transitions", `${m.id}.json`);
    if (!fs.existsSync(tp)) continue;
    const seen = new Set();
    for (const t of read(tp).items) if (!seen.has(t.to)) (seen.add(t.to), all.push(t.mood ?? 0));
  }
  const mean = (a) => a.reduce((s, x) => s + x, 0) / Math.max(1, a.length);
  console.log(`mood distance per song change: ${mean(moodsTaken).toFixed(2)} (all pairs: ${mean(all).toFixed(2)})`);
  const pct = (f) => `${Math.round((100 * changes.filter(f).length) / Math.max(1, changes.length))}%`;
  console.log(`criterion ${player.settings.criterion}: beat kept ${pct((c) => c.matched)}, ` +
    `tempo gap ${(100 * (2 ** mean(changes.map((c) => c.gap)) - 1)).toFixed(1)}% mean, ` +
    `keys compatible ${pct((c) => c.key >= 0.8)}, songs played ${seconds.size}/${metas.length}`);
}
if (leaveWaits.length) {
  leaveWaits.sort((a, b) => a - b);
  const g = (p) => leaveWaits[Math.min(leaveWaits.length - 1, Math.floor(p * leaveWaits.length))].toFixed(1);
  console.log(`transition starts after the minimum stay: p10 ${g(0.1)}s p50 ${g(0.5)}s p90 ${g(0.9)}s max ${g(1)}s`);
}
// Pacing of in-song jumps (seconds between consecutive jumps).
if (jumpGaps.length) {
  jumpGaps.sort((a, b) => a - b);
  const g = (p) => jumpGaps[Math.min(jumpGaps.length - 1, Math.floor(p * jumpGaps.length))].toFixed(1);
  console.log(`seconds between jumps (target ~${player.settings.jumpEvery}s): p10 ${g(0.1)} p50 ${g(0.5)} p90 ${g(0.9)}`);
}
console.log("time per song:");
for (const [id, s] of [...seconds.entries()].sort((a, b) => b[1] - a[1])) {
  console.log(`  ${(s / 60).toFixed(1).padStart(6)} min  ${title(id)}`);
}
const unvisited = metas.filter((m) => !seconds.has(m.id)).map((m) => title(m.id));
console.log(`never visited: ${unvisited.length ? unvisited.join(", ") : "none"}`);
const uniq = [...new Set(problems)];
console.log(`problems: ${uniq.length}`);
for (const p of uniq.slice(0, 15)) console.log("  ", p);
process.exit(uniq.length ? 1 : 0);
