import { api, Loader } from "./api.js";
import { Engine } from "./engine.js";
import { DEFAULTS, Player } from "./player.js";
import { bendNote, fmt, KIND_VI, short, splitTitle, trackHue, Viz } from "./viz.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const reduceMQ = matchMedia("(prefers-reduced-motion: reduce)");

const engine = new Engine();
const loader = new Loader(engine);
const player = new Player(engine, loader);
const viz = new Viz($("#viz"), player, {
  center: $("#ring-center"),
  tip: $("#viz-tip"),
  onPick: (tr) => player.planTransition(tr),
});

let metas = [];
let workerState = null;
let serverStale = false;
const byId = () => new Map(metas.map((m) => [m.id, m]));
const songOf = (m) => splitTitle(m?.title || "", m?.channel || "");
const titleOf = (id) => {
  const m = byId().get(id);
  return m ? songOf(m).title : id;
};

player.enabled = (id) => {
  const m = byId().get(id);
  return !!m && m.status === "ready" && m.enabled !== false;
};
loader.protect = () => [player.cur?.track.id, player.plan?.tr.to, player.blend?.B.id, ...player.prefetchIds].filter(Boolean);
loader.addEventListener("transitions", () => {
  viz.invalidate();
  renderExits();
});

const ICON = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>',
  out: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"/><path d="M9 12h6"/></svg>',
  in: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"/><path d="M9 12h6M12 9v6"/></svg>',
  retry: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12a7 7 0 1 0 2.1-5"/><path d="M5 4v4h4"/></svg>',
  del: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17"/></svg>',
  inf: '<svg viewBox="0 0 48 24" aria-hidden="true"><path d="M24 12 C 30 4, 42 4, 42 12 C 42 20, 30 20, 24 12 C 18 4, 6 4, 6 12 C 6 20, 18 20, 24 12 Z"/></svg>',
};

// ------------------------------------------------------------- segmented

// The amber pill slides to whichever option is on (mode switch, panel tabs).
function placeIndicator(seg) {
  const on = seg.querySelector("button.on");
  const ind = seg.querySelector(".seg__ind");
  if (!on || !ind) return;
  ind.style.setProperty("--ind-x", `${on.offsetLeft}px`);
  ind.style.setProperty("--ind-w", `${on.offsetWidth}px`);
}
const placeIndicators = () => document.querySelectorAll(".seg").forEach(placeIndicator);
window.addEventListener("resize", placeIndicators);
document.fonts?.ready.then(placeIndicators);

// ------------------------------------------------------------------ settings

const STORE = "loopbox.settings.v1";
// 2: the abrupt effects (brake, roll) became opt-in; older saved settings that
// had them on from the first release of effects are switched off once.
const SETTINGS_VERSION = 2;
const ui = { freq: 0.45, strict: 0.5, volume: 0.85 };
try {
  const saved = JSON.parse(localStorage.getItem(STORE) || "null");
  if (saved) {
    Object.assign(ui, saved.ui || {});
    Object.assign(player.settings, saved.player || {});
    player.settings.allow = { ...DEFAULTS.allow, ...(saved.player?.allow || {}) };
    if ((saved.v || 1) < 2) {
      player.settings.allow.brake = false;
      player.settings.allow.roll = false;
    }
  }
} catch (_) {
  /* storage unavailable */
}

function save() {
  try {
    localStorage.setItem(STORE, JSON.stringify({ v: SETTINGS_VERSION, ui, player: player.settings }));
  } catch (_) {
    /* storage unavailable */
  }
}

// Range fill: the amber part of the track follows the value.
function syncRange(input) {
  const min = +input.min || 0, max = +input.max || 1;
  input.style.setProperty("--v", `${((+input.value - min) / (max - min)) * 100}%`);
}

function applySettings() {
  const s = player.settings;
  // Log scale: 60 s between jumps at the far left, 6 s at the far right.
  s.jumpEvery = 60 * Math.pow(0.1, ui.freq);
  s.keep = 0.15 + 0.85 * ui.strict;
  if (s.dwellMax < s.dwellMin) s.dwellMax = s.dwellMin;
  engine.setVolume(ui.volume);
  $("#s-freq").value = ui.freq;
  $("#v-freq").textContent = `~${Math.round(s.jumpEvery)} giây một lần`;
  $("#s-strict").value = ui.strict;
  $("#v-strict").textContent = `giữ ${Math.round(s.keep * 100)}% điểm tốt nhất`;
  $("#s-dmin").value = s.dwellMin;
  $("#v-dmin").textContent = fmt(s.dwellMin);
  $("#s-dmax").value = s.dwellMax;
  $("#v-dmax").textContent = fmt(s.dwellMax);
  $("#s-variety").value = s.variety;
  $("#v-variety").textContent = `${Math.round(s.variety * 100)}%`;
  $("#s-cut").checked = s.allow.cut;
  $("#s-blend").checked = s.allow.blend;
  $("#s-fade").checked = s.allow.fade;
  $("#s-echo").checked = s.allow.echo !== false;
  $("#s-brake").checked = s.allow.brake !== false;
  $("#s-roll").checked = s.allow.roll !== false;
  $("#s-vol").value = ui.volume;
  $("#v-vol").textContent = `${Math.round(ui.volume * 100)}`;
  document.querySelectorAll('input[type="range"]').forEach(syncRange);
  for (const b of document.querySelectorAll(".mode button")) {
    const on = b.dataset.mode === s.mode;
    b.classList.toggle("on", on);
    b.setAttribute("aria-checked", on);
  }
  placeIndicator($(".mode"));
  viz.invalidate();
  renderTransport();
  save();
}

$("#s-freq").addEventListener("input", (e) => ((ui.freq = +e.target.value), applySettings()));
$("#s-strict").addEventListener("input", (e) => ((ui.strict = +e.target.value), applySettings()));
$("#s-dmin").addEventListener("input", (e) => {
  player.settings.dwellMin = +e.target.value;
  if (player.settings.dwellMax < player.settings.dwellMin) player.settings.dwellMax = player.settings.dwellMin;
  applySettings();
});
$("#s-dmax").addEventListener("input", (e) => {
  player.settings.dwellMax = +e.target.value;
  if (player.settings.dwellMin > player.settings.dwellMax) player.settings.dwellMin = player.settings.dwellMax;
  applySettings();
});
for (const k of ["cut", "blend", "fade", "echo", "brake", "roll"]) {
  $(`#s-${k}`).addEventListener("change", (e) => ((player.settings.allow[k] = e.target.checked), applySettings()));
}
$("#s-vol").addEventListener("input", (e) => ((ui.volume = +e.target.value), applySettings()));
$("#s-variety").addEventListener("input", (e) => ((player.settings.variety = +e.target.value), applySettings()));
for (const b of document.querySelectorAll(".mode button")) {
  b.addEventListener("click", () => {
    player.settings.mode = b.dataset.mode;
    player.cancelPlan();
    applySettings();
  });
}
for (const b of document.querySelectorAll(".tabs button")) {
  b.addEventListener("click", () => {
    for (const x of document.querySelectorAll(".tabs button")) {
      x.classList.toggle("on", x === b);
      x.setAttribute("aria-selected", x === b);
    }
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t.id === `tab-${b.dataset.tab}`);
    placeIndicator($(".tabs"));
  });
}
$("#btn-relink").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = "Đang tính lại…";
  await api.relink().catch(() => {});
  setTimeout(() => {
    btn.disabled = false;
    btn.textContent = "Tính lại điểm nối giữa các bài";
  }, 2500);
  refresh();
});

// ----------------------------------------------------------------- transport

let busy = false;

async function play(id) {
  // Resume inside the click itself: browsers only unlock audio on a user gesture.
  engine.ctx.resume();
  try {
    setBusy(true);
    await player.start(id);
  } catch (e) {
    alert(`Không phát được: ${e.message}`);
  } finally {
    setBusy(false);
  }
}

function setBusy(b) {
  busy = b;
  renderTransport();
}

$("#btn-play").addEventListener("click", async () => {
  if (busy) return;
  if (player.cur) await player.togglePause();
  else {
    const first = metas.find((m) => m.status === "ready" && m.enabled !== false) || metas.find((m) => m.status === "ready");
    if (first) await play(first.id);
  }
  renderTransport();
});
$("#btn-jump").addEventListener("click", () => player.requestJump());
$("#btn-next").addEventListener("click", () => player.requestNextSong());
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, select")) return;
  if (e.code === "Space") {
    if (e.target.closest("button")) return; // a focused button handles Space itself
    e.preventDefault();
    $("#btn-play").click();
  } else if (e.key === "j" || e.key === "J") player.requestJump();
  else if (e.key === "n" || e.key === "N") player.requestNextSong();
});
player.addEventListener("state", renderTransport);
player.addEventListener("track", () => {
  renderLibrary();
  renderExits();
});
player.addEventListener("plan", renderExits);

function renderTransport() {
  const btn = $("#btn-play");
  const state = busy ? "load" : player.cur && player.playing ? "pause" : "play";
  btn.dataset.state = state;
  btn.setAttribute("aria-label", state === "load" ? "Đang tải bài" : state === "pause" ? "Tạm dừng" : player.cur ? "Tiếp tục" : "Phát");
  btn.disabled = busy || (!player.cur && !metas.some((m) => m.status === "ready"));
  $("#btn-jump").disabled = !player.cur;
  $("#btn-next").disabled = !player.cur || player.settings.mode !== "chain";
}

// ------------------------------------------------------------------ library

const STAGES = {
  queued: "đang chờ", downloading: "đang tải về", converting: "chuyển định dạng", analyzing: "đang phân tích",
  loading: "đọc audio", beats: "dò beat", stems: "tách giọng và nhạc cụ", features: "đo đặc trưng", structure: "tìm cấu trúc",
  jumps: "tìm điểm nhảy", analyzed: "xong phân tích", linking: "nối với thư viện", ready: "sẵn sàng", error: "lỗi",
};

// Mini loops: each ready track drawn as a small beat ring from its analysis.
const miniCache = new Map(); // id -> Promise<ImageBitmap|HTMLCanvasElement>

function miniRing(id) {
  if (!miniCache.has(id)) {
    miniCache.set(id, api.analysis(id).then((a) => {
      const size = 76;
      const c = document.createElement("canvas");
      c.width = size;
      c.height = size;
      const ctx = c.getContext("2d");
      const r = size / 2 - 7;
      const end = a.duration;
      const lmax = Math.max(...a.loud), lmin = Math.min(...a.loud);
      ctx.lineWidth = 6;
      for (let b = 0; b < a.beats.length; b++) {
        const t0 = a.beats[b], t1 = b + 1 < a.beats.length ? a.beats[b + 1] : end;
        ctx.globalAlpha = 0.35 + 0.65 * ((a.loud[b] - lmin) / Math.max(1, lmax - lmin));
        ctx.strokeStyle = a.color[b];
        ctx.beginPath();
        ctx.arc(size / 2, size / 2, r, -Math.PI / 2 + (Math.PI * 2 * t0) / end, -Math.PI / 2 + (Math.PI * 2 * t1) / end + 0.01);
        ctx.stroke();
      }
      return c;
    }).catch(() => {
      miniCache.delete(id);
      return null;
    }));
  }
  return miniCache.get(id);
}

function paintMinis() {
  for (const c of document.querySelectorAll("canvas.mini[data-id]")) {
    if (c.dataset.painted) continue;
    c.dataset.painted = "1";
    miniRing(c.dataset.id).then((img) => {
      if (!img) return;
      const ctx = c.getContext("2d");
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
    });
  }
}

function trackRow(m) {
  const playing = player.audible()?.entry.track.id === m.id;
  let lead, status;
  if (m.status === "ready") {
    lead = `<canvas class="mini" data-id="${esc(m.id)}" width="76" height="76" aria-hidden="true"></canvas>`;
    const artist = songOf(m).artist;
    status = `<div class="s">${artist ? `<span class="a">${esc(artist)}</span> · ` : ""}${m.bpm ? m.bpm.toFixed(0) : "?"} BPM · ${esc(m.camelot || "")}</div>`;
  } else if (m.status === "error") {
    lead = `<span class="pending" style="--p:0;opacity:.5" aria-hidden="true"></span>`;
    status = `<div class="s err">${esc(m.error || "lỗi")}</div>`;
  } else {
    lead = `<span class="pending" style="--p:${(m.progress || 0).toFixed(3)}" aria-hidden="true"></span>`;
    status = `<div class="s">${STAGES[m.stage] || m.stage || "đang chờ"} · ${Math.round(100 * (m.progress || 0))}%</div><div class="progress"><i style="width:${Math.round(100 * (m.progress || 0))}%"></i></div>`;
  }
  const title = esc(songOf(m).title);
  const full = esc(`${m.title}${m.status === "ready" ? ` · ${m.jumps ?? 0} nhánh nhảy · ${fmt(m.duration || 0)}` : ""}`);
  const acts = m.status === "ready"
    ? `<button type="button" data-act="play" aria-label="Phát ${title}" title="Phát từ bài này">${ICON.play}</button>
       <button type="button" data-act="toggle" aria-label="${m.enabled === false ? "Đưa vào chuỗi" : "Bỏ khỏi chuỗi"}" title="${m.enabled === false ? "Đưa vào chuỗi" : "Bỏ khỏi chuỗi"}">${m.enabled === false ? ICON.in : ICON.out}</button>`
    : m.status === "error" ? `<button type="button" data-act="retry" aria-label="Thử lại" title="Thử lại">${ICON.retry}</button>` : "";
  return `<li class="track ${playing ? "playing" : ""} ${m.enabled === false ? "off" : ""}" data-id="${esc(m.id)}">
    ${lead}
    <div><div class="t" title="${full}">${title}</div>${status}</div>
    <div class="acts">${acts}<button type="button" data-act="delete" aria-label="Xoá ${title}" title="Xoá">${ICON.del}</button></div>
  </li>`;
}

let lastListHtml = "";
function renderLibrary() {
  const html = metas.length
    ? metas.slice().reverse().map(trackRow).join("")
    : `<li class="empty">${ICON.inf}Thư viện còn trống.<br>Gõ tên một bài ở ô phía trên để thêm vòng đầu tiên.</li>`;
  if (html !== lastListHtml) {
    lastListHtml = html;
    $("#track-list").innerHTML = html;
    paintMinis();
  }
  const ready = metas.filter((m) => m.status === "ready").length;
  $("#lib-count").textContent = metas.length ? `${ready}/${metas.length}` : "";
  const w = workerState;
  const cur = w?.current?.id ? byId().get(w.current.id) : null;
  $("#worker").textContent = serverStale
    ? "Server đang chạy phiên bản cũ: tắt nó (Ctrl+C) rồi chạy lại run.ps1"
    : w?.relink
      ? `Đang tính lại điểm nối ${w.relink.done}/${w.relink.total}`
      : cur
        ? `Đang xử lý ${short(cur.title, 34)} · ${STAGES[cur.stage] || cur.stage}${w.queued > 1 ? ` · còn ${w.queued - 1} bài chờ` : ""}`
        : "";
  viz.setTitles(new Map(metas.map((m) => [m.id, songOf(m).title])));
  renderTransport();
}

$("#track-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.closest(".track").dataset.id;
  const m = byId().get(id);
  switch (btn.dataset.act) {
    case "play":
      await play(id);
      break;
    case "toggle":
      await api.patch(id, { enabled: m.enabled === false });
      break;
    case "retry":
      await api.reanalyze(id);
      break;
    case "delete":
      if (!confirm(`Xoá "${m.title}" khỏi thư viện?`)) return;
      if (player.cur?.track.id === id) player.stop();
      loader.drop(id);
      miniCache.delete(id);
      await api.remove(id);
      break;
  }
  refresh();
});

async function refresh() {
  try {
    const r = await api.tracks();
    metas = r.tracks;
    workerState = r.worker;
    loader.setMetas(metas);
    // An old server process (started before an update) is still serving: its
    // results would not match the files on disk. Servers older than this check
    // do not send the flag at all.
    serverStale = !("stale_server" in r) || r.stale_server;
    renderLibrary();
  } catch (_) {
    $("#worker").textContent = "Mất kết nối tới server";
  }
}

let pollTimer = null;
function schedulePoll() {
  clearTimeout(pollTimer);
  const working = metas.some((m) => m.status !== "ready" && m.status !== "error") || workerState?.current;
  pollTimer = setTimeout(async () => {
    await refresh();
    schedulePoll();
  }, working ? 1200 : 5000);
}

// --------------------------------------------------------------- add / search

const isUrl = (s) => /^https?:\/\//i.test(s.trim());

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#add-input").value.trim();
  if (!text) return;
  const box = $("#search-results");
  const submit = $("#add-form button[type=submit]");
  submit.disabled = true;
  if (isUrl(text)) {
    box.innerHTML = `<div class="msg">Đang thêm…</div>`;
    try {
      const r = await api.add(text);
      box.innerHTML = `<div class="msg">Đã thêm ${r.added.length} bài vào hàng đợi phân tích.</div>`;
      $("#add-input").value = "";
      setTimeout(() => (box.innerHTML = ""), 3000);
    } catch (err) {
      box.innerHTML = `<div class="msg">Không thêm được: ${esc(err.message)}</div>`;
    }
    submit.disabled = false;
    refresh();
    schedulePoll();
    return;
  }
  box.innerHTML = `<div class="msg">Đang tìm trên YouTube…</div>`;
  try {
    const { results } = await api.search(text);
    const have = byId();
    box.innerHTML = results.length
      ? results.map((r) => `<div class="result">
          <img src="${esc(r.thumbnail)}" alt="" loading="lazy" width="64" height="36">
          <div><div class="t" title="${esc(r.title)}">${esc(r.title)}</div><div class="s">${esc(r.channel)}${r.duration ? ` · ${fmt(r.duration)}` : ""}</div></div>
          <button type="button" data-url="${esc(r.url)}" ${have.has(r.id) ? "disabled" : ""}>${have.has(r.id) ? "Đã có" : "Thêm"}</button>
        </div>`).join("")
      : `<div class="msg">Không tìm thấy bài nào. Thử tên khác, hoặc dán link YouTube.</div>`;
  } catch (err) {
    box.innerHTML = `<div class="msg">Tìm không được: ${esc(err.message)}</div>`;
  }
  submit.disabled = false;
});

$("#search-results").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-url]");
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = "…";
  try {
    await api.add(btn.dataset.url);
    btn.textContent = "Đã thêm";
  } catch (err) {
    btn.textContent = "Lỗi";
    btn.title = err.message;
  }
  refresh();
  schedulePoll();
});

// ------------------------------------------------------------- stage text

const KIND = { cut: "nối thẳng", drop: "drop", blend: "blend khớp nhịp", fade: "crossfade", echo: "echo vang", brake: "phanh đĩa", roll: "cuộn nhịp" };
const KIND_CAP = KIND_VI;

function setHTML(el, html) {
  if (el.innerHTML !== html) el.innerHTML = html;
}

function renderStage() {
  const view = player.audible();
  const p = player;
  const T = view?.entry.track;
  if (!T) {
    const empty = !metas.some((m) => m.status === "ready");
    setHTML($("#rc-kicker"), "HAI VÒNG ĐANG CHỜ");
    setHTML($("#rc-title"), empty ? "Thêm một bài để có vòng đầu tiên" : "Chọn một bài để bắt đầu vòng lặp");
    setHTML($("#rc-meta"), empty ? "Gõ tên bài ở ô Thêm bài trong thư viện" : "Bấm phát, hoặc nút ▶ ở một bài trong thư viện");
    setHTML($("#ro-tl"), `<b>MASH ∞ LOOP</b> // ${p.settings.mode === "chain" ? "chuỗi" : "một bài"} · chưa phát`);
    setHTML($("#ro-tr"), `<span class="mono">∞ 0:00</span><span class="ro-stats"> · chưa có vòng nào</span>`);
    setHTML($("#next-info"), "");
    return;
  }
  const a = T.analysis;
  const b = p.blend;
  const blending = b && view.now >= b.times[0];
  setHTML($("#rc-kicker"), blending ? "ĐANG BLEND" : p.settings.mode === "chain" ? "ĐANG PHÁT · CHUỖI" : "ĐANG PHÁT · LẶP MÃI");
  const song = songOf(T.meta);
  setHTML($("#rc-title"), esc(song.title || T.id));
  setHTML($("#rc-meta"), `${song.artist ? `<span class="rc-artist">${esc(song.artist)}</span>` : ""}<span class="mono">${a.bpm.toFixed(0)} BPM · ${esc(a.camelot)} · ${esc(a.key)}</span>`);
  setHTML($("#ro-tl"), `<b>${p.settings.mode === "chain" ? "CHUỖI" : "LẶP"}</b> // ${esc(short(T.meta.channel || T.meta.title || "", 34))}`);
  const listened = Math.max(0, view.now - p.stats.startedAt);
  setHTML($("#ro-tr"), `<span class="mono">∞ ${fmt(listened)}</span><span class="ro-stats"> · ${p.stats.jumps} nhảy · ${p.stats.transitions} chuyển</span>`);

  const now = view.now;
  const name = (id) => esc(short(titleOf(id), 46));
  let next;
  if (blending) {
    const k = Math.min(1, (now - b.times[0]) / (b.times[b.L] - b.times[0]));
    const note = bendNote(b.tr);
    next = `Đang blend sang <strong>${name(b.B.id)}</strong> · <span class="eta">${Math.round(k * 100)}%</span>${note ? ` · ${note}` : ""}`;
  } else if (p.fx) {
    next = `Đang ${KIND[p.fx.tr.type]} sang <strong>${name(p.fx.B.id)}</strong>`;
  } else if (p.plan) {
    const eta = Math.max(0, p.plan.eta - now);
    const note = bendNote(p.plan.tr);
    next = `${p.plan.picked ? "Bạn đã chọn: " : "Sắp "}${KIND[p.plan.tr.type] || p.plan.tr.type} sang <strong>${name(p.plan.tr.to)}</strong> · <span class="eta">${fmt(eta)}</span>` +
      ` · khớp ${Math.round(p.plan.tr.q * 100)}%${note ? ` · ${note}` : ""}${p.plan.target ? "" : " · đang tải"}`;
  } else if (p.settings.mode === "chain") {
    const left = p.dwellStart + p.settings.dwellMin - now;
    next = left > 0
      ? `Có thể chuyển bài sau <span class="eta">${fmt(left)}</span>, ở điểm nối tốt gần nhất`
      : `Đang chờ điểm nối tốt gần nhất…`;
  } else {
    next = "Lặp mãi bài này. Chạm một chấm ngoài vòng để tự chọn điểm chuyển bài.";
  }
  setHTML($("#next-info"), next);
}

// Setlist: the session as a chain of linked loops.
function renderSetlist() {
  const hist = player.history.filter((h) => h.at <= engine.audibleTime()).slice(-10);
  const html = hist.map((h) => `<li data-via="${h.via}" style="--hue:hsl(${trackHue(h.id)} 72% 62%)"><span class="loop" aria-hidden="true"></span><span>${esc(short(titleOf(h.id), 30))}</span><span class="sr">, vào bằng ${h.via === "start" ? "bắt đầu" : KIND[h.via] || h.via}</span></li>`).join("");
  const ol = $("#history");
  if (ol.dataset.html !== html) {
    ol.dataset.html = html;
    ol.innerHTML = html;
    ol.scrollLeft = ol.scrollWidth;
  }
}

// Keyboard and screen-reader access to the exits that the stage draws as dots.
const exits = document.createElement("div");
exits.className = "exits";
exits.innerHTML = `<p class="label">Điểm nối sang bài khác</p><ul></ul>`;
$("#canvas-wrap").append(exits);

function renderExits() {
  const T = player.cur?.track;
  const list = T ? T.transitions.filter((tr) => player.enabled(tr.to)).sort((x, y) => y.q - x.q).slice(0, 8) : [];
  exits.querySelector("ul").innerHTML = list.map((tr, k) =>
    `<li><button type="button" data-k="${k}">${KIND_CAP[tr.type]} → ${esc(short(titleOf(tr.to), 32))} <span class="mono">${Math.round(tr.q * 100)}%</span></button></li>`).join("");
  exits.hidden = !list.length;
  exits._list = list;
}
exits.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-k]");
  if (!btn) return;
  const ok = player.planTransition(exits._list[+btn.dataset.k]);
  btn.classList.toggle("is-bad", !ok);
});

setInterval(() => {
  renderStage();
  renderSetlist();
}, 250);

let lastPlaying = null;
setInterval(() => {
  const id = player.audible()?.entry.track.id || null;
  if (id !== lastPlaying) {
    lastPlaying = id;
    renderLibrary();
  }
}, 500);

// Mark: the dot runs along the ∞. One fast lap when the mark is hovered.
(function traceMark() {
  const path = document.querySelector(".brand__path");
  const dot = document.querySelector(".brand__dot");
  if (!path || !dot) return;
  const len = path.getTotalLength();
  let u = 0.25, last = performance.now(), boost = 0;
  document.querySelector(".brand").addEventListener("pointerenter", () => (boost = 1));
  const step = (now) => {
    const dt = (now - last) / 1000;
    last = now;
    if (!reduceMQ.matches) {
      u = (u + dt * (1 / 6 + boost * 1.2)) % 1;
      boost = Math.max(0, boost - dt * 0.9);
    }
    const pt = path.getPointAtLength(u * len);
    dot.setAttribute("cx", pt.x.toFixed(2));
    dot.setAttribute("cy", pt.y.toFixed(2));
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
})();

applySettings();
renderTransport();
renderStage();
placeIndicators();
refresh().then(schedulePoll);

// Handle for the browser console and the end-to-end test.
window.loopbox = { player, engine, loader, play, refresh, applySettings, ui, viz };
