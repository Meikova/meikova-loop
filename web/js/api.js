import { Track } from "./graph.js";

async function json(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      msg = (await r.json()).detail || msg;
    } catch (_) {
      /* not json */
    }
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  tracks: () => json("/api/tracks"),
  search: (q) => json(`/api/search?q=${encodeURIComponent(q)}`),
  add: (text) => json("/api/tracks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }),
  patch: (id, data) => json(`/api/tracks/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  remove: (id) => json(`/api/tracks/${id}`, { method: "DELETE" }),
  reanalyze: (id) => json(`/api/tracks/${id}/reanalyze`, { method: "POST" }),
  relink: () => json("/api/relink", { method: "POST" }),
  analysis: (id) => json(`/api/tracks/${id}/analysis`),
  transitions: (id) => json(`/api/tracks/${id}/transitions`),
};

// Fetches and decodes tracks, keeping a few decoded buffers in memory
// (a 4-minute song is ~85 MB of float samples).
export class Loader extends EventTarget {
  constructor(engine, keep = 5) {
    super();
    this.engine = engine;
    this.keep = keep;
    this.cache = new Map(); // id -> {promise, track, used}
    this.metas = new Map();
    this.protect = () => [];
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
    return !!this.cache.get(id)?.track;
  }

  get(id) {
    const hit = this.cache.get(id);
    if (hit) {
      hit.used = performance.now();
      return hit.promise;
    }
    const entry = { track: null, used: performance.now() };
    entry.promise = (async () => {
      const meta = this.metas.get(id) || { id, title: id };
      const [analysis, audio, trans] = await Promise.all([
        api.analysis(id),
        fetch(`/api/tracks/${id}/audio`).then((r) => {
          if (!r.ok) throw new Error(`audio ${r.status}`);
          return r.arrayBuffer();
        }),
        api.transitions(id),
      ]);
      const buffer = await this.engine.ctx.decodeAudioData(audio);
      const track = new Track(meta, analysis, buffer);
      track.transitions = trans.items;
      entry.track = track;
      return track;
    })();
    entry.promise.catch(() => this.cache.delete(id));
    this.cache.set(id, entry);
    this._evict();
    return entry.promise;
  }

  async refreshTransitions(track) {
    try {
      const { items } = await api.transitions(track.id);
      track.transitions = items;
      this.dispatchEvent(new CustomEvent("transitions", { detail: track }));
    } catch (_) {
      /* keep the old list */
    }
  }

  drop(id) {
    this.cache.delete(id);
  }

  _evict() {
    if (this.cache.size <= this.keep) return;
    const keep = new Set(this.protect());
    const order = [...this.cache.entries()].filter(([id, e]) => !keep.has(id) && e.track).sort((a, b) => a[1].used - b[1].used);
    while (this.cache.size > this.keep && order.length) this.cache.delete(order.shift()[0]);
  }
}
