import { api, hooks, isMobile, Loader, ready, session } from "./api.js";
import { Engine } from "./engine.js";
import { setupMediaSession } from "./mediasession.js";
import { CRITERIA, DEFAULTS, keyFit, Player, setPhase, shiftCamelot } from "./player.js";
import * as theme from "./theme.js?v=55";
import { bendNote, fmt, KIND_VI, short, splitTitle, Viz } from "./viz.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const reduceMQ = matchMedia("(prefers-reduced-motion: reduce)");

export function showModal({
  title = "Thông báo",
  message = "",
  confirmText = "Đồng ý",
  cancelText = null,
  danger = false,
  prompt = false,
  defaultValue = "",
  placeholder = "",
} = {}) {
  const dlg = $("#app-modal");
  if (!dlg || typeof dlg.showModal !== "function") {
    if (prompt) return Promise.resolve(window.prompt(message || title, defaultValue));
    if (cancelText) return Promise.resolve(window.confirm(message));
    window.alert(message);
    return Promise.resolve(true);
  }
  const titleEl = $("#modal-title");
  const bodyEl = $("#modal-body");
  const iconEl = $("#modal-icon");
  const inputWrap = $("#modal-input-wrap");
  const inputEl = $("#modal-input");
  const cancelBtn = $("#modal-cancel");
  const closeBtn = $("#modal-close");
  const okBtn = $("#modal-ok");

  if (titleEl) titleEl.textContent = title;
  if (iconEl) {
    if (danger) {
      iconEl.innerHTML = '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>';
      iconEl.style.stroke = "var(--danger)";
    } else if (prompt || /playlist|album/i.test(title)) {
      iconEl.innerHTML = '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>';
      iconEl.style.stroke = "var(--accent)";
    } else {
      iconEl.innerHTML = '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>';
      iconEl.style.stroke = "var(--accent)";
    }
  }
  if (bodyEl) {
    bodyEl.textContent = message;
    bodyEl.hidden = !message;
  }
  if (inputWrap && inputEl) {
    inputWrap.hidden = !prompt;
    if (prompt) {
      inputEl.value = defaultValue || "";
      inputEl.placeholder = placeholder || "";
    }
  }
  if (okBtn) {
    okBtn.textContent = confirmText;
    okBtn.classList.toggle("consent__yes--danger", !!danger);
  }

  if (cancelBtn) {
    cancelBtn.hidden = !cancelText && !prompt;
    if (cancelText) cancelBtn.textContent = cancelText;
    else if (prompt) cancelBtn.textContent = "Thôi";
  }

  return new Promise((resolve) => {
    let resolved = false;
    const cleanup = () => {
      cancelBtn?.removeEventListener("click", onCancel);
      closeBtn?.removeEventListener("click", onCancel);
      dlg.removeEventListener("close", onClose);
      form?.removeEventListener("submit", onSubmit);
    };
    const onCancel = (e) => {
      e?.preventDefault();
      if (resolved) return;
      resolved = true;
      cleanup();
      dlg.close("cancel");
      resolve(prompt ? null : false);
    };
    const onSubmit = (e) => {
      e?.preventDefault();
      if (resolved) return;
      resolved = true;
      cleanup();
      const val = prompt ? (inputEl?.value.trim() ?? "") : true;
      dlg.close("ok");
      resolve(val);
    };
    const onClose = () => {
      if (resolved) return;
      resolved = true;
      cleanup();
      if (dlg.returnValue === "ok") {
        resolve(prompt ? (inputEl?.value.trim() ?? "") : true);
      } else {
        resolve(prompt ? null : false);
      }
    };

    const form = $("#modal-form");
    closeBtn?.addEventListener("click", onCancel, { once: true });
    form?.addEventListener("submit", onSubmit);
    cancelBtn?.addEventListener("click", onCancel, { once: true });
    dlg.addEventListener("close", onClose, { once: true });
    dlg.returnValue = "cancel";
    dlg.showModal();
    if (prompt && inputEl) {
      inputEl.focus();
      inputEl.select();
    } else {
      okBtn?.focus();
    }
  });
}

// Global alert override so no native white dialog ever appears
window.alert = (msg) => {
  showModal({ title: "Thông báo", message: String(msg) });
};

const engine = new Engine();
const loader = new Loader(engine);
const player = new Player(engine, loader);
const viz = new Viz($("#viz"), player, {
  center: $("#ring-center"),
  tip: $("#viz-tip"),
  onPick: (tr) => player.planTransition(tr),
  onSeek: (track, beat) => player.seek(beat),
  onCaption: () => renderStage(),
  onCrossClick: () => player.forceTransition(),
});

let metas = [];
let workerState = null;
let serverStale = false;
let lastLinks = null;
// The sample libraries, by theme: songs kept analysed on the server, for a
// visit that does not know what to add. They come in ready and the chain starts.
const samples = { libraries: [], ids: [] };
let moreOpen = false; // the "add a sample library" fold under a library that has songs
// Every song this visit has seen, so the setlist still names one that has left the library.
const known = new Map();

// The sample libraries also play as a chain of their own: the library being
// heard (cur) and the next one (next), taken into this library ahead of time,
// out of sight, so the chain can mix across into it when the way there is good.
// "Kho khác" (or the timer) makes the next exit go there; once a song of it
// plays, the library left behind goes, unless the listener opened it by hand.
const kho = { cur: null, next: null, pinned: new Set(), force: false, forceAt: 0, heard: 0, visits: new Map() };
const libOf = (id) => samples.libraries.find((l) => l.ids.includes(id))?.key || null;
const libByKey = (key) => samples.libraries.find((l) => l.key === key) || null;
const shownLib = (key) => !key || kho.pinned.has(key) || key === kho.cur; // in the list (null: the listener's own song)
// The server forgot this visit's library (it restarted): add the songs back.
hooks.restore = async () => {
  const allIds = [...new Set([
    ...metas.map((m) => m.id),
    ...playlists.flatMap((p) => p.trackIds || []),
  ])].filter(Boolean);
  if (allIds.length) await api.restore(allIds).catch(() => {});
};
const byId = () => new Map(metas.map((m) => [m.id, m]));
// A credited song (the Creative Commons libraries) has its exact title and
// artist already: "Anyway - Produced by J. Glaze" is a title, not "artist - title".
const songOf = (m) => m?.credit
  ? { title: m.title || "", artist: m.channel || m.credit.artist || "" }
  : splitTitle(m?.title || "", m?.channel || "");
const titleOf = (id) => {
  const m = byId().get(id) || known.get(id);
  return m ? songOf(m).title : id;
};

player.enabled = (id) => {
  const m = byId().get(id);
  if (!m || m.status !== "ready" || m.enabled === false) return false;
  if (lockToPlaylist && activePlaylistId !== "all") {
    const pl = getPlaylist(activePlaylistId);
    if (pl && pl.trackIds && !pl.trackIds.includes(id)) return false;
  }
  if (!kho.cur) return true;
  const lib = libOf(id);
  if (kho.force) return lib === kho.next;
  return shownLib(lib) || (lib === kho.next && ui.crossKho);
};
// A little reluctance to leave the library being heard: the chain crosses
// into the next one when the way there is clearly the better transition.
player.bias = (id) => (kho.cur && !kho.force && libOf(id) === kho.next ? -0.12 : 0);
loader.protect = () => [player.cur?.track.id, player.plan?.tr.to, player.blend?.B.id, ...player.prefetchIds].filter(Boolean);
loader.addEventListener("transitions", () => {
  viz.invalidate();
  renderExits();
});

const ICON = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="7 4.5 19 12 7 19.5 7 4.5"/></svg>',
  playlist: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
  out: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
  in: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
  retry: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12a7 7 0 1 0 2.1-5"/><path d="M5 4v4h4"/></svg>',
  del: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17"/></svg>',
  plRemove: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
  up: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>',
  down: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
  move: '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>',
  copy: '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  queueNext: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="6" x2="12" y2="6"/><line x1="4" y1="12" x2="12" y2="12"/><line x1="4" y1="18" x2="10" y2="18"/><polygon points="15 10 15 19 21 14.5 15 10" fill="currentColor"/></svg>',
  download: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  inspect: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  search: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  inf: '<svg viewBox="0 0 48 24" aria-hidden="true"><path d="M24 12 C 30 4, 42 4, 42 12 C 42 20, 30 20, 24 12 C 18 4, 6 4, 6 12 C 6 20, 18 20, 24 12 Z"/></svg>',
  warn: '<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-left:3px;display:inline-block"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
};

setupMediaSession(player, engine, (id) => byId().get(id) || known.get(id));

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
const SETTINGS_VERSION = 2;
const BLEND_STYLES = ["long", "eq", "short", "filter", "swap", "stem", "acapella", "loop", "mashup", "double"];
// Every kind of transition, each with its switch (#s-<kind>).
const KINDS = ["cut", "drop", "blend", "fade", "echo", "wash", "riser", "flanger", "gap", "brake", "roll", "spin", "gate", "tape", "sweeper"];
// 2: the abrupt effects (brake, roll) became opt-in; older saved settings that
// had them on from the first release of effects are switched off once.
const ui = {
  freq: 0.45,
  strict: 0.5,
  volume: 0.85,
  theme: "mood",
  crossKho: true,
  khoMinutes: 0,
  glow: 1.0,
  activePlaylistId: "all",
  lockToPlaylist: false,
  libSortMode: "default",
  activeTab: "library",
};
try {
  const saved = JSON.parse(localStorage.getItem(STORE) || "null");
  if (saved) {
    Object.assign(ui, saved.ui || {});
    Object.assign(player.settings, saved.player || {});
    player.settings.allow = { ...DEFAULTS.allow, ...(saved.player?.allow || {}) };
    player.settings.blendStyles = { ...DEFAULTS.blendStyles, ...(saved.player?.blendStyles || {}) };
    if ((saved.v || 1) < 2) {
      player.settings.allow.brake = false;
      player.settings.allow.roll = false;
    }
  }
} catch (e) {
  console.warn("Could not load local settings:", e);
}

// Fetch server settings and merge if available
fetch("/api/settings")
  .then((r) => (r.ok ? r.json() : null))
  .then((serverData) => {
    if (serverData && (serverData.ui || serverData.player)) {
      const localEmpty = !localStorage.getItem(STORE);
      if (localEmpty) {
        if (serverData.ui) Object.assign(ui, serverData.ui);
        if (serverData.player) {
          Object.assign(player.settings, serverData.player);
          player.settings.allow = { ...DEFAULTS.allow, ...(serverData.player.allow || {}) };
          player.settings.blendStyles = { ...DEFAULTS.blendStyles, ...(serverData.player.blendStyles || {}) };
        }
        applySettings();
      }
    }
  })
  .catch(() => {});

let saveTimer = null;
function save() {
  const data = {
    v: SETTINGS_VERSION,
    ui: {
      ...ui,
      activePlaylistId: typeof activePlaylistId !== "undefined" ? activePlaylistId : ui.activePlaylistId,
      lockToPlaylist: typeof lockToPlaylist !== "undefined" ? lockToPlaylist : ui.lockToPlaylist,
      libSortMode: typeof libSortMode !== "undefined" ? libSortMode : ui.libSortMode,
    },
    player: player.settings,
  };
  try {
    localStorage.setItem(STORE, JSON.stringify(data));
  } catch (err) {
    console.warn("Could not save settings to localStorage:", err);
  }
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).catch(() => {});
  }, 400);
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
  engine.setVolume(window.pywebview ? (isMuted ? 0 : 1.0) : (isMuted ? 0 : ui.volume));
  $("#s-freq").value = ui.freq;
  $("#v-freq").textContent = `~${Math.round(s.jumpEvery)} giây một lần`;
  $("#s-strict").value = ui.strict;
  $("#v-strict").textContent = `giữ ${Math.round(s.keep * 100)}% điểm tốt nhất`;
  $("#s-dmin").value = s.dwellMin;
  $("#v-dmin").textContent = fmt(s.dwellMin);
  $("#s-dmax").value = s.dwellMax;
  $("#v-dmax").textContent = fmt(s.dwellMax);
  if (!CRITERIA[s.criterion]) s.criterion = "balanced";
  for (const r of document.querySelectorAll('input[name="criterion"]')) r.checked = r.value === s.criterion;
  $("#s-variety").value = s.variety;
  $("#v-variety").textContent = `${Math.round(s.variety * 100)}%`;
  for (const k of KINDS) $(`#s-${k}`).checked = s.allow[k] !== false;
  for (const k of BLEND_STYLES) $(`#s-bl-${k}`).checked = s.blendStyles[k] !== false;
  $("#s-keyshift").checked = s.keyShift !== false;
  $("#s-tempo").checked = s.tempoRamp !== false;
  // The ways to blend, and how far a blend may match, while blends are on.
  $("#blend-styles").disabled = !s.allow.blend;
  $("#blend-match").disabled = !s.allow.blend;
  $("#s-vol").value = ui.volume;
  $("#v-vol").textContent = `${Math.round(ui.volume * 100)}`;
  updateVolumeIcon(ui.volume, isMuted);
  $("#s-cross").checked = ui.crossKho;
  $("#s-kmin").value = ui.khoMinutes;
  $("#v-kmin").textContent = ui.khoMinutes ? `${ui.khoMinutes} phút` : "tắt";
  if (!theme.THEMES[ui.theme]) ui.theme = "mood";
  for (const r of document.querySelectorAll('input[name="look"]')) r.checked = r.value === ui.theme;
  if (theme.setTheme(ui.theme)) recolor();
  if (ui.glow === undefined) ui.glow = 1.0;
  if (typeof theme.setGlow === "function") theme.setGlow(ui.glow);
  const glowInput = $("#s-glow");
  if (glowInput) glowInput.value = ui.glow;
  const glowVal = $("#v-glow");
  if (glowVal) glowVal.textContent = `${Math.round(ui.glow * 100)}%`;
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
for (const k of KINDS) {
  $(`#s-${k}`).addEventListener("change", (e) => ((player.settings.allow[k] = e.target.checked), applySettings()));
}
// A blend the chain planned under a switch now off is planned again.
const replanBlend = () => {
  if (player.plan && !player.plan.picked && player.plan.tr.type === "blend") player.cancelPlan();
  player.prefetchedFor = null;
  applySettings();
};
for (const k of BLEND_STYLES) {
  $(`#s-bl-${k}`).addEventListener("change", (e) => ((player.settings.blendStyles[k] = e.target.checked), replanBlend()));
}
$("#s-keyshift").addEventListener("change", (e) => ((player.settings.keyShift = e.target.checked), replanBlend()));
$("#s-tempo")?.addEventListener("change", (e) => ((player.settings.tempoRamp = e.target.checked), replanBlend()));
let isMuted = false;
let prevVol = ui.volume || 0.8;

function updateVolumeIcon(vol, muted) {
  const mb = $("#btn-mute");
  if (!mb) return;
  const isMute = muted || vol <= 0.005;
  mb.dataset.muted = String(isMute);
  let level = "high";
  if (isMute) level = "mute";
  else if (vol <= 0.33) level = "low";
  else if (vol <= 0.66) level = "med";
  else level = "high";
  mb.dataset.level = level;
  mb.title = isMute ? "Bật tiếng (M)" : `Âm lượng ${Math.round(vol * 100)}% (M: Tắt)`;
}

export function setAppVolume(val, syncSystem = true) {
  if (typeof val !== "number" || isNaN(val)) return;
  const clamped = Math.max(0, Math.min(1, +val.toFixed(3)));
  ui.volume = clamped;
  isMuted = ui.volume === 0;
  updateVolumeIcon(ui.volume, isMuted);
  const sVol = $("#s-vol");
  if (sVol && Math.abs(+sVol.value - ui.volume) >= 0.005) {
    sVol.value = ui.volume;
  }
  applySettings();
  save();
  if (syncSystem) {
    window.pywebview?.api?.set_system_volume?.(ui.volume);
    try {
      window.AndroidAudio?.setVolume?.(ui.volume);
    } catch (_) {}
  }
}

// Global receiver for OS system volume changes (Desktop, Android, iOS)
window.__onSystemVolume = (vol) => {
  if (typeof vol !== "number" || isNaN(vol)) return;
  const clamped = Math.max(0, Math.min(1, +vol.toFixed(3)));
  if (Math.abs(ui.volume - clamped) >= 0.005) {
    setAppVolume(clamped, false);
  }
};

$("#s-vol").addEventListener("input", (e) => {
  setAppVolume(+e.target.value, true);
});
$("#s-cross").addEventListener("change", (e) => {
  ui.crossKho = e.target.checked;
  if (player.plan && !player.plan.picked) player.cancelPlan(); // planned under the old rule
  player.prefetchedFor = null;
  applySettings();
});
$("#s-kmin").addEventListener("input", (e) => ((ui.khoMinutes = +e.target.value), applySettings()));
for (const r of document.querySelectorAll('input[name="look"]')) {
  r.addEventListener("change", () => ((ui.theme = r.value), applySettings()));
}
$("#s-glow")?.addEventListener("input", (e) => {
  ui.glow = +e.target.value;
  if (typeof theme.setGlow === "function") theme.setGlow(ui.glow);
  const glowVal = $("#v-glow");
  if (glowVal) glowVal.textContent = `${Math.round(ui.glow * 100)}%`;
  viz.invalidate();
  recolor();
  applySettings();
});

// The theme tiles preview their colours with three songs of this library.
function renderLooks() {
  const ids = theme.spreadIds();
  for (const tile of document.querySelectorAll(".look")) {
    const cols = theme.preview(tile.querySelector("input").value, ids);
    tile.querySelectorAll(".swatch i").forEach((dot, k) => dot.style.setProperty("--c", theme.css(cols[k])));
  }
}
$("#s-variety").addEventListener("input", (e) => ((player.settings.variety = +e.target.value), applySettings()));
for (const r of document.querySelectorAll('input[name="criterion"]')) {
  r.addEventListener("change", () => {
    player.settings.criterion = r.value;
    // An exit the chain chose under the old criterion is chosen again; one
    // the listener picked on the stage stays.
    if (player.plan && !player.plan.picked) player.cancelPlan();
    player.prefetchedFor = null;
    applySettings();
  });
}
for (const b of document.querySelectorAll(".mode button")) {
  b.addEventListener("click", () => {
    player.settings.mode = b.dataset.mode;
    player.cancelPlan();
    applySettings();
  });
}
for (const b of document.querySelectorAll(".tabs button")) {
  b.addEventListener("click", () => {
    ui.activeTab = b.dataset.tab;
    for (const x of document.querySelectorAll(".tabs button")) {
      x.classList.toggle("on", x === b);
      x.setAttribute("aria-selected", x === b);
    }
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t.id === `tab-${b.dataset.tab}`);
    placeIndicator($(".tabs"));
    save();
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
  engine.unlockAudio();
  engine.ctx.resume();
  try {
    setBusy(true);
    await player.start(id);
  } catch (e) {
    showModal({ title: "Lỗi phát nhạc", message: `Không phát được: ${e.message}` });
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
  if (player.cur) {
    await player.togglePause();
  } else {
    engine.unlockAudio();
    const first = metas.find((m) => m.status === "ready" && m.enabled !== false) || metas.find((m) => m.status === "ready");
    if (first) await play(first.id);
  }
  renderTransport();
});
$("#btn-jump").addEventListener("click", () => player.requestJump());
$("#btn-next").addEventListener("click", () => player.forceTransition());
$("#btn-kho").addEventListener("click", () => switchKho());

// --- Deck controls: Lock, Timer, Night EQ, Quick Mute ---
const lockBtn = $("#btn-lock");
if (lockBtn) {
  lockBtn.addEventListener("click", () => {
    player.toggleLoopLock();
    applySettings();
  });
}

const muteBtn = $("#btn-mute");
function toggleMute() {
  if (!isMuted) {
    prevVol = ui.volume > 0 ? ui.volume : 0.8;
    setAppVolume(0, true);
  } else {
    setAppVolume(prevVol > 0 ? prevVol : 0.8, true);
  }
}
if (muteBtn) muteBtn.addEventListener("click", toggleMute);

const eqBtn = $("#btn-eq");
const eqPopover = $("#eq-popover");
const eqBadge = $("#eq-badge");
const eqLabel = $("#eq-label");
const EQ_NAMES = {
  flat: "Chuẩn",
  night: "Âm đêm",
  bass: "Bass",
  vocal: "Giọng",
  lofi: "Lofi",
};
const EQ_LIST = ["flat", "night", "bass", "vocal", "lofi"];

function setEq(preset) {
  if (!EQ_NAMES[preset]) preset = "flat";
  engine.setEqPreset(preset);
  if (eqBadge) eqBadge.textContent = EQ_NAMES[preset];
  if (eqLabel) eqLabel.textContent = preset === "flat" ? "EQ" : EQ_NAMES[preset];
  if (eqBtn) {
    eqBtn.setAttribute("data-active", preset !== "flat");
    eqBtn.setAttribute("aria-pressed", preset !== "flat");
  }
  const nb = $("#btn-night");
  const isNight = preset === "night";
  if (isNightMode !== isNight) {
    isNightMode = isNight;
    document.body.classList.toggle("is-night", isNightMode);
    if (typeof theme?.reapply === "function") theme.reapply();
  }
  if (nb) nb.setAttribute("aria-pressed", String(isNight));
  document.querySelectorAll(".eq-opt").forEach((b) => b.classList.toggle("on", b.dataset.eq === preset));
}

// Chế độ đêm theo múi giờ Việt Nam (UTC+7, xuất hiện sau 9h tối - từ 21h đến 6h sáng)
function getVietnamHour() {
  try {
    const vnStr = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Ho_Chi_Minh",
      hour12: false,
      hour: "numeric",
    }).format(new Date());
    const h = parseInt(vnStr, 10);
    if (!isNaN(h)) return h;
  } catch (_) {}
  const utc = Date.now() + new Date().getTimezoneOffset() * 60000;
  return new Date(utc + 7 * 3600000).getHours();
}

let isNightMode = false;
function setNightMode(active) {
  isNightMode = Boolean(active);
  document.body.classList.toggle("is-night", isNightMode);
  const nb = $("#btn-night");
  if (nb) {
    nb.setAttribute("aria-pressed", String(isNightMode));
    nb.title = isNightMode ? "Chế độ đêm: Đang bật (bấm để tắt)" : "Chế độ đêm / Âm dịu mắt & tai";
  }
  setEq(isNightMode ? "night" : "flat");
  if (typeof theme?.reapply === "function") theme.reapply();
  checkNightButtonVisibility();
}

function checkNightButtonVisibility() {
  const nb = $("#btn-night");
  if (!nb) return;
  const h = getVietnamHour();
  // Sau 9h tối (>= 21h) đến 6h sáng theo giờ VN (UTC+7)
  const isNightTime = h >= 21 || h < 6;
  nb.hidden = !isNightTime && !isNightMode;
}

const nightBtn = $("#btn-night");
if (nightBtn) {
  nightBtn.addEventListener("click", () => setNightMode(!isNightMode));
  checkNightButtonVisibility();
  setInterval(checkNightButtonVisibility, 30000);
}

if (eqBtn && eqPopover) {
  eqBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const isHidden = eqPopover.hidden;
    eqPopover.hidden = !isHidden;
    eqBtn.setAttribute("aria-expanded", !isHidden);
  });

  document.addEventListener("click", (e) => {
    if (!eqPopover.hidden && !e.target.closest("#eq-popover, #btn-eq")) {
      eqPopover.hidden = true;
      eqBtn.setAttribute("aria-expanded", "false");
    }
  });

  document.querySelectorAll(".eq-opt").forEach((btn) => {
    btn.addEventListener("click", () => {
      setEq(btn.dataset.eq);
      eqPopover.hidden = true;
      eqBtn.setAttribute("aria-expanded", "false");
    });
  });
}

const timerBtn = $("#btn-timer");
const timerPopover = $("#timer-popover");
if (timerBtn && timerPopover) {
  timerBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const isHidden = timerPopover.hidden;
    timerPopover.hidden = !isHidden;
    timerBtn.setAttribute("aria-expanded", !isHidden);
  });

  document.addEventListener("click", (e) => {
    if (!timerPopover.hidden && !e.target.closest("#timer-popover, #btn-timer")) {
      timerPopover.hidden = true;
      timerBtn.setAttribute("aria-expanded", "false");
    }
  });

  document.querySelectorAll(".timer-opt").forEach((btn) => {
    btn.addEventListener("click", () => {
      const val = btn.dataset.timer;
      document.querySelectorAll(".timer-opt").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      if (val === "0") {
        player.clearSleepTimer();
      } else if (val === "song") {
        player.setSleepTimer(0, "song");
      } else {
        player.setSleepTimer(parseFloat(val), "time");
      }
      timerPopover.hidden = true;
      timerBtn.setAttribute("aria-expanded", "false");
    });
  });

  player.addEventListener("sleep-timer-tick", (e) => {
    const detail = e.detail;
    const label = $("#timer-label");
    const badge = $("#timer-badge");
    if (!detail) {
      timerBtn.removeAttribute("data-active");
      if (label) label.textContent = "Hẹn giờ";
      if (badge) badge.textContent = "Tắt";
      document.querySelectorAll(".timer-opt").forEach((b) => b.classList.toggle("on", b.dataset.timer === "0"));
      return;
    }
    timerBtn.setAttribute("data-active", "true");
    if (detail.mode === "song") {
      if (label) label.textContent = "Hết bài";
      if (badge) badge.textContent = "Hết bài";
      document.querySelectorAll(".timer-opt").forEach((b) => b.classList.toggle("on", b.dataset.timer === "song"));
    } else {
      const m = Math.floor(detail.remaining / 60);
      const s = detail.remaining % 60;
      const text = `${m}:${s < 10 ? "0" : ""}${s}`;
      if (label) label.textContent = text;
      if (badge) badge.textContent = text;
    }
  });
}

document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, select")) return;
  if (e.code === "Space") {
    if (e.target.closest("button")) return; // a focused button handles Space itself
    e.preventDefault();
    $("#btn-play").click();
  } else if (e.key === "j" || e.key === "J") player.requestJump();
  else if (e.key === "n" || e.key === "N") player.forceTransition();
  else if (e.key === "k" || e.key === "K") switchKho();
  else if (e.key === "l" || e.key === "L") { player.toggleLoopLock(); applySettings(); }
  else if (e.key === "t" || e.key === "T") { if (timerBtn) timerBtn.click(); }
  else if (e.key === "m" || e.key === "M") { toggleMute(); }
  else if (e.key === "]") {
    e.preventDefault();
    setAppVolume(Math.min(1, +(ui.volume + 0.02).toFixed(2)), true);
  } else if (e.key === "[") {
    e.preventDefault();
    setAppVolume(Math.max(0, +(ui.volume - 0.02).toFixed(2)), true);
  } else if (e.key === "e" || e.key === "E") {
    const nextIdx = (EQ_LIST.indexOf(engine.eqMode || "flat") + 1) % EQ_LIST.length;
    setEq(EQ_LIST[nextIdx]);
  } else if (e.key === "f" || e.key === "F") {
    toggleZen();
  } else if (e.key === "Escape" && document.body.classList.contains("is-zen")) {
    toggleZen();
  }
  else if (e.key === "?") { $("#btn-shortcuts-modal")?.click(); }
});
player.addEventListener("state", renderTransport);
player.addEventListener("track", () => {
  enteredSong();
  renderLibrary();
  renderExits();
});

// ------------------------------------------------------- sample library chain

// Takes the next sample library into this one, out of sight: the one heard
// least recently (never heard first), in the shelf's order.
let preparing = null;
function prepareNext() {
  if (!kho.cur || kho.next || preparing) return preparing;
  const lib = samples.libraries
    .filter((l) => l.key !== kho.cur && !kho.pinned.has(l.key))
    .sort((a, b) => (kho.visits.get(a.key) || 0) - (kho.visits.get(b.key) || 0))[0];
  if (!lib) return null;
  preparing = (async () => {
    await api.restore(lib.ids);
    kho.next = lib.key;
    await refresh();
    loader.refreshAll(); // the song playing now learns its ways into the next library
    viz.invalidate(); // which exits the stage shows depends on the libraries in play
    renderExits();
    renderTransport();
  })().catch(() => {}).finally(() => (preparing = null));
  return preparing;
}

// A song of another sample library has started: that library is the one
// heard now, and the next comes in. The one left behind goes, unless the chain
// wandered out of a library opened by hand; "Kho khác" (or the timer) swaps
// the whole library, so then it goes too.
function enteredSong() {
  const id = player.cur?.track.id;
  const lib = id ? libOf(id) : null;
  if (!lib || lib === kho.cur || (!kho.cur && !kho.pinned.has(lib))) return;
  const left = kho.cur;
  const swapped = kho.force;
  kho.cur = lib;
  if (kho.next === lib) kho.next = null;
  kho.force = false;
  kho.heard = 0;
  kho.visits.set(lib, Date.now());
  if (left && (swapped || !kho.pinned.has(left))) {
    kho.pinned.delete(left);
    dropLib(left);
  }
  prepareNext();
  viz.invalidate();
  renderTransport();
}

function dropLib(key) {
  const keep = new Set(loader.protect());
  for (const id of libByKey(key)?.ids || []) {
    if (keep.has(id)) continue;
    loader.drop(id);
    api.remove(id).catch(() => {});
  }
  refresh();
}

// "Kho khác": the next exit goes into the next library, at the nearest good
// point, the way "Bài khác" finds one for any song.
async function switchKho() {
  if (!kho.cur || !player.cur || player.settings.mode !== "chain" || kho.force) return;
  await prepareNext();
  if (!kho.next) return;
  kho.force = true;
  kho.forceAt = performance.now();
  player.requestNextSong();
  viz.invalidate();
  renderExits();
  renderTransport();
}

// The timer counts listening time in the library being heard; a switch that
// finds no way in after half a minute starts the next library outright.
setInterval(() => {
  if (!kho.cur || !player.cur || !player.playing || player.settings.mode !== "chain") return;
  kho.heard += 2;
  if (!kho.force && ui.khoMinutes && kho.heard >= ui.khoMinutes * 60) switchKho();
  if (kho.force && performance.now() - kho.forceAt > 30000 && libOf(player.plan?.tr.to) !== kho.next) {
    const first = metas.find((m) => m.status === "ready" && libOf(m.id) === kho.next);
    if (first) play(first.id);
  }
}, 2000);
player.addEventListener("plan", renderExits);

function renderTransport() {
  const btn = $("#btn-play");
  const state = busy ? "load" : player.cur && player.playing ? "pause" : "play";
  btn.dataset.state = state;
  btn.setAttribute("aria-label", state === "load" ? "Đang tải bài" : state === "pause" ? "Tạm dừng" : player.cur ? "Tiếp tục" : "Phát");
  btn.disabled = busy || (!player.cur && !metas.some((m) => m.status === "ready"));
  $("#btn-jump").disabled = !player.cur;
  $("#btn-next").disabled = !player.cur || player.settings.mode !== "chain";
  const k = $("#btn-kho");
  k.hidden = !kho.cur;
  k.disabled = !player.cur || player.settings.mode !== "chain" || kho.force;
  k.setAttribute("aria-pressed", kho.force);
  const next = libByKey(kho.next);
  k.title = kho.force ? `Đang tìm điểm nối sang ${next?.name || "kho khác"}`
    : `Sang kho khác${next ? ` (${next.name})` : ""} ở điểm nối gần nhất (K)`;

  const isLocked = player.settings.mode === "single";
  const lb = $("#btn-lock");
  if (lb) {
    lb.setAttribute("aria-pressed", isLocked);
    lb.disabled = !player.cur;
    lb.title = isLocked ? "Đang khoá bài này lặp mãi (L)" : "Khoá lặp bài này mãi (L)";
  }
}

// ------------------------------------------------------------------ library

const STAGES = {
  queued: "đang chờ", downloading: "đang tải về", converting: "chuyển định dạng", analyzing: "đang phân tích",
  loading: "đọc audio", beats: "dò beat", stems: "tách giọng và nhạc cụ", features: "đo đặc trưng", structure: "tìm cấu trúc",
  jumps: "tìm điểm nhảy", analyzed: "xong phân tích", linking: "nối với thư viện", ready: "sẵn sàng", error: "lỗi",
};

// Mini loops: each ready track drawn as a small beat ring from its analysis,
// in its own colours, so the library reads as a palette of moods.
const analysisCache = new Map(); // id -> Promise<analysis|null>
const miniCache = new Map(); // `${id}|${palette}` -> Promise<HTMLCanvasElement|null>

function analysisOf(id) {
  if (!analysisCache.has(id)) {
    analysisCache.set(id, api.analysis(id).catch(() => {
      analysisCache.delete(id);
      return null;
    }));
  }
  return analysisCache.get(id);
}

function miniRing(id) {
  const key = `${id}|${theme.paletteVersion()}`;
  if (!miniCache.has(key)) {
    miniCache.set(key, analysisOf(id).then((a) => {
      if (!a) {
        miniCache.delete(key);
        return null;
      }
      const size = 72;
      const c = document.createElement("canvas");
      c.width = size;
      c.height = size;
      const ctx = c.getContext("2d");
      const r = size / 2 - 6;
      const end = a.duration;
      const lmax = Math.max(...a.loud), lmin = Math.min(...a.loud);
      const colors = theme.beatColors(id, a.color);
      ctx.lineWidth = 6;
      for (let b = 0; b < a.beats.length; b++) {
        const t0 = a.beats[b], t1 = b + 1 < a.beats.length ? a.beats[b + 1] : end;
        ctx.globalAlpha = 0.35 + 0.65 * ((a.loud[b] - lmin) / Math.max(1, lmax - lmin));
        ctx.strokeStyle = colors[b];
        ctx.beginPath();
        ctx.arc(size / 2, size / 2, r, -Math.PI / 2 + (Math.PI * 2 * t0) / end, -Math.PI / 2 + (Math.PI * 2 * t1) / end + 0.01);
        ctx.stroke();
      }
      return c;
    }));
  }
  return miniCache.get(key);
}

function forget(id) {
  analysisCache.delete(id);
  for (const k of [...miniCache.keys()]) if (k.startsWith(`${id}|`)) miniCache.delete(k);
}

// Colours changed (another theme, or the library's moods moved): repaint.
function recolor() {
  miniCache.clear();
  for (const c of document.querySelectorAll("canvas.mini[data-id]")) delete c.dataset.painted;
  paintMinis();
  viz.invalidate();
  renderLooks();
  if (setlistEl) setlistEl.dataset.html = "";
}

function paintMinis() {
  const palette = theme.paletteVersion();
  for (const c of document.querySelectorAll("canvas.mini[data-id]")) {
    if (c.dataset.painted === palette) continue;
    c.dataset.painted = palette;
    miniRing(c.dataset.id).then((img) => {
      if (!img) return;
      const ctx = c.getContext("2d");
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
    });
  }
}

// A Creative Commons song carries its licence and a link back to where it lives.
function creditLine(c) {
  if (!c?.license) return "";
  const link = (href, text) => href
    ? `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(text)}</a>`
    : esc(text);
  return `<div class="s cc">${link(c.license_url, c.license)}${c.via ? ` · ${link(c.page, c.via)}` : ""}</div>`;
}

function libCards(libs) {
  return `<div class="libs">${libs.map((l) => `<button type="button" class="lib" data-act="samples" data-key="${esc(l.key)}">
      <b>${esc(l.name)}</b><span>${l.ids.length} bài${l.blurb ? ` · ${esc(l.blurb)}` : ""}</span>
    </button>`).join("")}</div>`;
}

// ------------------------------------------------------------- playlists & albums
const PL_STORE_KEY = "mashloop.playlists.v1";
let playlists = [];
let activePlaylistId = ui.activePlaylistId || "all";
let lockToPlaylist = Boolean(ui.lockToPlaylist);
let modalTrackIds = [];
let plModalMode = "copy"; // "copy" or "move"
let batchMode = false;
const selectedTrackIds = new Set();
let libSearchQuery = "";
let libSortMode = ui.libSortMode || "default";

function cleanVi(s) {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .trim();
}

function loadPlaylists() {
  try {
    const raw = localStorage.getItem(PL_STORE_KEY);
    playlists = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(playlists)) playlists = [];
  } catch (_) {
    playlists = [];
  }
}

function savePlaylists() {
  try {
    localStorage.setItem(PL_STORE_KEY, JSON.stringify(playlists));
  } catch (_) {}
  renderPlaylistChips();
  renderActivePlaylistHeader();
}

function getPlaylist(id) {
  return playlists.find((p) => p.id === id) || null;
}

function createPlaylist(name, trackIds = []) {
  const cleanName = (name || "").trim() || "Playlist mới";
  const pl = {
    id: "pl_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 6),
    name: cleanName,
    trackIds: Array.from(new Set(trackIds)),
    createdAt: Date.now(),
  };
  playlists.push(pl);
  savePlaylists();
  return pl;
}

function deletePlaylist(id) {
  playlists = playlists.filter((p) => p.id !== id);
  if (activePlaylistId === id) {
    activePlaylistId = "all";
    lockToPlaylist = false;
    save();
  }
  savePlaylists();
  renderLibrary();
}

function renamePlaylist(id, newName) {
  const pl = getPlaylist(id);
  if (pl && newName.trim()) {
    pl.name = newName.trim();
    savePlaylists();
    renderLibrary();
  }
}

function addTracksToActivePlaylist(trackIds) {
  if (activePlaylistId === "all" || !trackIds || !trackIds.length) return;
  const pl = getPlaylist(activePlaylistId);
  if (!pl) return;
  let changed = false;
  for (const tid of trackIds) {
    if (!pl.trackIds.includes(tid)) {
      pl.trackIds.push(tid);
      changed = true;
    }
  }
  if (changed) savePlaylists();
}

function updatePlNavArrows() {
  const container = $("#pl-chips");
  const leftBtn = $("#pl-scroll-left");
  const rightBtn = $("#pl-scroll-right");
  if (!container || !leftBtn || !rightBtn) return;
  const maxScroll = container.scrollWidth - container.clientWidth;
  if (maxScroll <= 6) {
    leftBtn.hidden = true;
    rightBtn.hidden = true;
    return;
  }
  leftBtn.hidden = container.scrollLeft <= 4;
  rightBtn.hidden = container.scrollLeft >= maxScroll - 4;
}

function scrollChipIntoView(container, chip) {
  if (!container || !chip) return;
  const cRect = container.getBoundingClientRect();
  const chipRect = chip.getBoundingClientRect();
  if (chipRect.left < cRect.left) {
    container.scrollLeft -= (cRect.left - chipRect.left) + 8;
  } else if (chipRect.right > cRect.right) {
    container.scrollLeft += (chipRect.right - cRect.right) + 8;
  }
}

let lastChipsHtml = "";
function renderPlaylistChips() {
  const nav = $("#pl-nav");
  const container = $("#pl-chips");
  if (!container || !nav) return;
  if (!playlists.length) {
    nav.hidden = true;
    container.innerHTML = "";
    lastChipsHtml = "";
    return;
  }
  nav.hidden = false;
  let html = `<button type="button" class="pl-chip ${activePlaylistId === "all" ? "on" : ""}" data-pl-id="all" title="Tất cả bài hát"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/></svg><span>Tất cả</span></button>`;
  for (const pl of playlists) {
    const count = pl.trackIds.filter((tid) => metas.some((m) => m.id === tid)).length;
    html += `<button type="button" class="pl-chip ${activePlaylistId === pl.id ? "on" : ""}" data-pl-id="${esc(pl.id)}" title="${esc(pl.name)} (${count} bài)"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg><span>${esc(pl.name)}</span> (${count})</button>`;
  }
  if (html !== lastChipsHtml) {
    lastChipsHtml = html;
    container.innerHTML = html;
    updatePlNavArrows();
  }
}

function renderActivePlaylistHeader() {
  const header = $("#pl-header");
  if (!header) return;
  if (activePlaylistId === "all") {
    header.hidden = true;
    return;
  }
  const pl = getPlaylist(activePlaylistId);
  if (!pl) {
    header.hidden = true;
    return;
  }
  header.hidden = false;
  $("#pl-active-title").textContent = pl.name;
  const lockCb = $("#pl-lock-toggle");
  if (lockCb) lockCb.checked = lockToPlaylist;
}

function filterMetas(list) {
  let res = list.filter((m) => shownLib(libOf(m.id)));
  if (activePlaylistId !== "all") {
    const pl = getPlaylist(activePlaylistId);
    if (pl) {
      const idMap = new Map(res.map((m) => [m.id, m]));
      res = (pl.trackIds || []).map((id) => idMap.get(id)).filter(Boolean);
    }
  }

  // Filter by search query (Title, Artist, BPM, Camelot Key)
  if (libSearchQuery) {
    const q = cleanVi(libSearchQuery);
    const isNum = /^\d+(\.\d+)?$/.test(libSearchQuery);
    const numVal = isNum ? parseFloat(libSearchQuery) : null;
    res = res.filter((m) => {
      const s = songOf(m);
      const title = cleanVi(s.title);
      const artist = cleanVi(s.artist);
      if (title.includes(q) || artist.includes(q)) return true;
      if (m.camelot && m.camelot.toLowerCase().includes(q)) return true;
      if (numVal != null && m.bpm && Math.abs(m.bpm - numVal) <= 3) return true;
      return false;
    });
  }

  // Sort by chosen mode
  if (libSortMode !== "default") {
    if (libSortMode === "bpm-asc") {
      res = res.slice().sort((a, b) => (a.bpm || 0) - (b.bpm || 0));
    } else if (libSortMode === "bpm-desc") {
      res = res.slice().sort((a, b) => (b.bpm || 0) - (a.bpm || 0));
    } else if (libSortMode === "key") {
      const parseCam = (s) => {
        const m = /^(\d{1,2})([AB])$/i.exec(s || "");
        return m ? +m[1] * 2 + (m[2].toUpperCase() === "B" ? 1 : 0) : 999;
      };
      res = res.slice().sort((a, b) => parseCam(a.camelot) - parseCam(b.camelot));
    } else if (libSortMode === "title") {
      res = res.slice().sort((a, b) => (songOf(a).title || "").localeCompare(songOf(b).title || "", "vi"));
    } else if (libSortMode === "duration") {
      res = res.slice().sort((a, b) => (b.duration || 0) - (a.duration || 0));
    }
  }

  return res;
}

function updatePlaylistModalModeUI() {
  const copyBtn = $("#pl-mode-copy");
  const moveBtn = $("#pl-mode-move");
  if (copyBtn) copyBtn.classList.toggle("on", plModalMode === "copy");
  if (moveBtn) moveBtn.classList.toggle("on", plModalMode === "move");
  const hint = $("#pl-modal-hint");
  if (hint) {
    if (plModalMode === "copy") {
      hint.textContent = "Thêm bản sao vào playlist được chọn (vẫn giữ ở danh sách hiện tại).";
    } else {
      hint.textContent = activePlaylistId !== "all"
        ? "Chuyển bài sang playlist mới và rút khỏi playlist hiện tại."
        : "Chuyển bài vào playlist đích.";
    }
  }
}

function openPlaylistModal(tids) {
  modalTrackIds = Array.isArray(tids) ? tids : [tids];
  const dlg = $("#pl-modal");
  if (!dlg) return;
  if (modalTrackIds.length === 1) {
    const m = byId().get(modalTrackIds[0]);
    const title = songOf(m).title || modalTrackIds[0];
    $("#pl-modal-song").textContent = title;
  } else {
    $("#pl-modal-song").textContent = `${modalTrackIds.length} bài đã chọn`;
  }
  updatePlaylistModalModeUI();
  renderPlaylistModalList();
  dlg.showModal();
}

function renderPlaylistModalList() {
  const listEl = $("#pl-modal-list");
  if (!listEl) return;
  if (!playlists.length) {
    listEl.innerHTML = `<div style="text-align:center;padding:12px;color:var(--text-faint);font-size:var(--step--1)">Chưa có playlist nào. Nhập tên ở ô bên dưới để tạo!</div>`;
    return;
  }
  listEl.innerHTML = playlists.map((pl) => {
    const isCurrent = activePlaylistId === pl.id;
    const count = (pl.trackIds || []).length;
    const hasAll = modalTrackIds.length > 0 && modalTrackIds.every((id) => (pl.trackIds || []).includes(id));

    let actHtml = "";
    if (plModalMode === "move") {
      if (isCurrent) {
        actHtml = `<span class="pl-badge-cur">Playlist này</span><button type="button" class="pl-btn-apply" disabled title="Bài hát đã ở trong playlist này">Ở đây</button>`;
      } else {
        actHtml = `<button type="button" class="pl-btn-apply" data-action="apply-move" data-pl-id="${esc(pl.id)}" title="Di chuyển ${modalTrackIds.length} bài sang ${esc(pl.name)}">${ICON.move} <span>Chuyển</span></button>`;
      }
    } else {
      actHtml = `${isCurrent ? `<span class="pl-badge-cur">Hiện tại</span>` : ""}<button type="button" class="pl-btn-apply" data-action="apply-copy" data-pl-id="${esc(pl.id)}" title="Sao chép ${modalTrackIds.length} bài vào ${esc(pl.name)}">${hasAll ? "Đã có (+)" : `${ICON.copy} <span>Sao chép</span>`}</button>`;
    }

    return `<div class="pl-modal__item">
      <div class="pl-modal__item-info">
        <span class="pl-modal__item-title"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg> ${esc(pl.name)}</span>
        <span class="pl-modal__item-count">${count} bài</span>
      </div>
      <div class="pl-modal__item-acts">
        ${actHtml}
      </div>
    </div>`;
  }).join("");
}

function checkUrlPlaylistImport() {
  const params = new URLSearchParams(window.location.search);
  const name = params.get("pl_name");
  const tracksParam = params.get("pl_tracks");
  if (name && tracksParam) {
    const tids = tracksParam.split(",").map((s) => s.trim()).filter(Boolean);
    if (tids.length) {
      let existing = playlists.find((p) => p.name === name);
      if (!existing) {
        existing = createPlaylist(name, tids);
      } else {
        for (const tid of tids) {
          if (!existing.trackIds.includes(tid)) existing.trackIds.push(tid);
        }
        savePlaylists();
      }
      activePlaylistId = existing.id;
      if (session.multiuser) {
        api.restore(tids).catch(() => {});
      }
    }
  }
}

function trackRow(m, idx = 0, total = 0) {
  const playing = player.audible()?.entry.track.id === m.id;
  const isSelected = selectedTrackIds.has(m.id);
  const isQueued = player.targetNextId === m.id;
  const inPl = activePlaylistId !== "all";
  let lead, status;
  if (m.status === "ready") {
    lead = `<canvas class="mini" data-id="${esc(m.id)}" width="72" height="72" aria-hidden="true"></canvas>`;
    const artist = songOf(m).artist;
    status = `<div class="s">${artist ? `<span class="a">${esc(artist)}</span> · ` : ""}${m.bpm ? m.bpm.toFixed(0) : "?"} BPM · ${esc(m.camelot || "")}</div>${creditLine(m.credit)}`;
  } else if (m.status === "error") {
    lead = `<span class="pending" style="--p:0;opacity:.5" aria-hidden="true"></span>`;
    const errText = cleanUiError(m.error || "Lỗi xử lý");
    status = `<div class="s err" title="${esc(m.error || '')}">${esc(errText)}</div>`;
  } else {
    lead = `<span class="pending" style="--p:${(m.progress || 0).toFixed(3)}" aria-hidden="true"></span>`;
    status = `<div class="s">${STAGES[m.stage] || m.stage || "đang chờ"} · ${Math.round(100 * (m.progress || 0))}%</div><div class="progress"><i style="width:${Math.round(100 * (m.progress || 0))}%"></i></div>`;
  }
  const title = esc(songOf(m).title);
  const full = esc(`${m.title}${m.status === "ready" ? ` · ${m.jumps ?? 0} nhánh nhảy · ${fmt(m.duration || 0)}` : ""}`);
  const reorderBtns = inPl
    ? `<button type="button" data-act="move-up" ${idx === 0 ? "disabled" : ""} aria-label="Đưa lên trên" title="Đưa lên trên">${ICON.up}</button>
       <button type="button" data-act="move-down" ${idx === total - 1 ? "disabled" : ""} aria-label="Đưa xuống dưới" title="Đưa xuống dưới">${ICON.down}</button>`
    : "";
  const queueNextBtn = m.status === "ready"
    ? `<button type="button" data-act="queue-next" data-active="${isQueued}" aria-label="Chuyển sang bài này tiếp theo" title="${isQueued ? "Đang chờ chuyển (bấm để hủy)" : "Chuyển sang bài này tiếp theo"}">${ICON.queueNext}</button>`
    : "";
  const inspectBtn = m.status === "ready"
    ? `<button type="button" data-act="inspect" aria-label="Chi tiết & tùy chọn" title="Chi tiết & tùy chọn (tải MP3, playlist...)">${ICON.inspect}</button>`
    : "";
  const acts = m.status === "ready"
    ? `${reorderBtns}
       ${queueNextBtn}
       <button type="button" data-act="play" aria-label="Phát ${title}" title="Phát từ bài này">${ICON.play}</button>
       <button type="button" data-act="toggle" aria-label="${m.enabled === false ? "Đưa vào chuỗi" : "Bỏ khỏi chuỗi"}" title="${m.enabled === false ? "Đưa vào chuỗi" : "Bỏ khỏi chuỗi"}">${m.enabled === false ? ICON.in : ICON.out}</button>
       ${inspectBtn}`
    : m.status === "error" ? `<button type="button" data-act="retry" aria-label="Thử lại" title="Thử lại">${ICON.retry}</button>` : "";
  const removeBtn = inPl
    ? `<button type="button" data-act="pl-remove" aria-label="Bỏ khỏi playlist này" title="Bỏ khỏi playlist này">${ICON.plRemove}</button>`
    : (m.status === "error" ? `<button type="button" data-act="delete" aria-label="Xoá lỗi" title="Xoá">${ICON.del}</button>` : "");
  const cb = batchMode
    ? `<input type="checkbox" class="track-cb" data-id="${esc(m.id)}" ${isSelected ? "checked" : ""} aria-label="Chọn bài ${title}" />`
    : "";
  const isTooLong = m.status === "ready" && loader.isOversized(m);
  const warnTitle = isMobile
    ? `Bài dài ${Math.round((m.duration || 0) / 60)} phút - có thể quá tải RAM trên thiết bị di động`
    : `Bài dài ${Math.round((m.duration || 0) / 60)} phút - vượt giới hạn trình phát`;
  const durHtml = (m.status === "ready" && m.duration)
    ? `<span class="track__dur" ${isTooLong ? `style="color:var(--c-warn,#f59e0b)" title="${warnTitle}"` : ""}>${fmt(m.duration)}${isTooLong ? ` ${ICON.warn}` : ""}</span>`
    : "";
  return `<li class="track ${playing ? "playing" : ""} ${m.enabled === false ? "off" : ""} ${isSelected ? "selected" : ""} ${isQueued ? "queued-next" : ""}" data-id="${esc(m.id)}">
    ${cb}${lead}
    <div class="track__body">
      <div class="track__top">
        <div class="t" data-act="inspect" title="Bấm để xem chi tiết & phân tích">${title}${isQueued ? `<span class="badge-queued">Kế tiếp</span>` : ""}</div>
        ${durHtml}
      </div>
      <div class="track__bottom">
        ${status}
        <div class="acts">${acts}${removeBtn}</div>
      </div>
    </div>
  </li>`;
}

function updateBatchBar() {
  const bar = $("#batch-bar");
  if (!bar || bar.hidden) return;
  const countEl = $("#batch-count");
  if (countEl) countEl.textContent = `${selectedTrackIds.size} đã chọn`;
  const selectAllCb = $("#batch-select-all");
  const shown = filterMetas(metas);
  if (selectAllCb) {
    const allSelected = shown.length > 0 && shown.every((m) => selectedTrackIds.has(m.id));
    selectAllCb.checked = allSelected;
    selectAllCb.indeterminate = selectedTrackIds.size > 0 && !allSelected;
  }
  const hasSelection = selectedTrackIds.size > 0;
  for (const id of ["batch-btn-in", "batch-btn-out", "batch-btn-pl", "batch-btn-del"]) {
    const btn = $(`#${id}`);
    if (btn) btn.disabled = !hasSelection;
  }
  const plRemoveBtn = $("#batch-btn-pl-remove");
  if (plRemoveBtn) {
    plRemoveBtn.hidden = activePlaylistId === "all";
    plRemoveBtn.disabled = !hasSelection;
  }
}

let lastListHtml = "";
let lastListKey = "";
function renderLibrary() {
  renderPlaylistChips();
  renderActivePlaylistHeader();

  const trackListEl = $("#track-list");
  if (trackListEl) trackListEl.classList.toggle("batch-mode", batchMode);

  const batchToggleBtn = $("#btn-batch-toggle");
  if (batchToggleBtn) {
    batchToggleBtn.classList.toggle("on", batchMode);
    const span = batchToggleBtn.querySelector("span");
    if (span) span.textContent = batchMode ? "Xong" : "Chọn";
  }

  const batchBar = $("#batch-bar");
  if (batchBar) batchBar.hidden = !batchMode;
  updateBatchBar();

  const errors = metas.filter((m) => m.status === "error");
  const errorBar = $("#lib-error-bar");
  if (errorBar) {
    if (errors.length > 0) {
      errorBar.hidden = false;
      const msg = $("#lib-error-msg");
      if (msg) msg.innerHTML = `<b>${errors.length}</b> bài lỗi`;
    } else {
      errorBar.hidden = true;
    }
  }

  const shown = filterMetas(metas);
  const listToRender = (libSortMode === "default" && activePlaylistId === "all") ? shown.slice().reverse() : shown;
  const have = new Set(shown.map((m) => m.id));
  const offer = samples.libraries.filter((l) => l.ids.some((id) => !have.has(id)));
  let html;
  if (shown.length) {
    html = listToRender.map((m, idx) => trackRow(m, idx, listToRender.length)).join("");
    if (activePlaylistId === "all" && offer.length) {
      html += `<li class="more"><details${moreOpen ? " open" : ""}><summary>Thêm một kho có sẵn · ${offer.length} kho</summary>${libCards(offer)}</details></li>`;
    }
  } else {
    let intro = "";
    if (libSearchQuery) {
      intro = `Không tìm thấy bài hát nào khớp với "<b>${esc(libSearchQuery)}</b>".<br><button type="button" class="batch-btn" id="btn-clear-search-empty" style="margin-top:8px">Xoá bộ lọc tìm kiếm</button>`;
    } else if (activePlaylistId !== "all") {
      const pl = getPlaylist(activePlaylistId);
      intro = `Playlist "${esc(pl?.name || "")}" đang trống.<br>Bấm biểu tượng <b>${ICON.playlist}</b> ở bất kỳ bài hát nào để đưa vào playlist này.`;
    } else {
      intro = session.multiuser
        ? "Thư viện của bạn đang trống.<br>Dán link YouTube, SoundCloud, Zing MP3, Jamendo, gõ tên bài, hoặc thả file nhạc (cả file zip) vào đây."
        : "Thư viện còn trống.<br>Gõ tên một bài ở ô phía trên để thêm vòng đầu tiên.";
    }
    html = `<li class="empty">${ICON.inf}${intro}${activePlaylistId === "all" && !libSearchQuery && offer.length ? `<br>Chưa biết thêm gì? Nghe thử một kho có sẵn:${libCards(offer)}` : ""}</li>`;
  }
  const currentKey = `${batchMode ? "b:" : ""}${libSortMode}:${libSearchQuery}:${player.targetNextId}:${shown.map((m) => `${m.id}:${m.status}:${m.enabled}:${selectedTrackIds.has(m.id)}`).join(",")}`;
  if (html !== lastListHtml || currentKey !== lastListKey) {
    lastListHtml = html;
    lastListKey = currentKey;
    if (trackListEl) trackListEl.innerHTML = html;
    paintMinis();
  }
  const readyMetas = shown.filter((m) => m.status === "ready");
  const inChainCount = readyMetas.filter((m) => m.enabled !== false).length;
  const totalCount = readyMetas.length;
  const own = metas.filter((m) => !samples.ids.includes(m.id)).length;
  $("#lib-count").textContent = session.limits.tracks
    ? `${own}/${session.limits.tracks}`
    : shown.length ? `${inChainCount}/${totalCount}` : "";
  const w = workerState || {};
  const busy = metas.filter((m) => m.status !== "ready" && m.status !== "error");
  const active = busy.filter((m) => m.status !== "queued");
  let line = "";
  if (serverStale) line = "Server đang chạy phiên bản cũ: tắt nó (Ctrl+C) rồi chạy lại run.ps1";
  else if (w.relink) line = "Đang tính lại điểm nối giữa các bài…";
  else if (busy.length) {
    line = active.length === 1
      ? `Đang xử lý ${short(songOf(active[0]).title, 30)} · ${STAGES[active[0].stage] || active[0].stage}`
      : active.length > 1 ? `Đang xử lý ${active.length} bài cùng lúc` : "Đang chờ tới lượt xử lý";
    if (busy.length > active.length) line += ` · ${busy.length - active.length} bài chờ`;
  } else if (w.linking) line = `Đang nối các bài với nhau · còn ${w.linking} cặp`;
  $("#worker").textContent = line;
  viz.setTitles(new Map(metas.map((m) => [m.id, songOf(m).title])));
  renderTransport();
}

// The sample library the empty stage offers: one drawn at random per visit.
let stageSampleKey = null;
function stageSample() {
  const libs = samples.libraries;
  if (!libs.length) return null;
  if (!libs.some((l) => l.key === stageSampleKey)) stageSampleKey = libs[Math.floor(Math.random() * libs.length)].key;
  return libs.find((l) => l.key === stageSampleKey);
}

$("#rc-cta").addEventListener("click", (e) => loadSamples(e.currentTarget));

async function loadSamples(btn) {
  const lib = samples.libraries.find((l) => l.key === btn.dataset.key);
  if (!lib) return;
  const note = btn.querySelector("span");
  btn.disabled = true;
  note.textContent = "Đang mở…";
  engine.ctx.resume(); // inside the click: lets the chain start playing below
  try {
    await api.restore(lib.ids);
    // Opened by hand: it stays in the library while the chain wanders.
    kho.pinned.add(lib.key);
    if (kho.next === lib.key) kho.next = null;
    if (!kho.cur) {
      kho.cur = lib.key;
      kho.heard = 0;
      kho.visits.set(lib.key, Date.now());
    }
    moreOpen = false;
    await refresh();
    const first = metas.find((m) => m.status === "ready" && lib.ids.includes(m.id));
    if (first && !player.cur) await play(first.id);
    prepareNext();
    renderTransport();
  } catch (err) {
    btn.disabled = false;
    note.textContent = `Không mở được: ${err.message}`;
  }
}

$("#track-list").addEventListener("toggle", (e) => {
  if (e.target.matches(".more details")) moreOpen = e.target.open;
}, true);

$("#track-list").addEventListener("click", async (e) => {
  const clearSearchBtn = e.target.closest("#btn-clear-search-empty");
  if (clearSearchBtn) {
    libSearchQuery = "";
    const searchInput = $("#lib-search-input");
    if (searchInput) searchInput.value = "";
    const clearBtn = $("#lib-search-clear");
    if (clearBtn) clearBtn.hidden = true;
    renderLibrary();
    return;
  }

  const actEl = e.target.closest("[data-act]");
  if (actEl) {
    if (actEl.dataset.act === "samples") return loadSamples(actEl);
    const id = actEl.closest(".track")?.dataset.id;
    if (!id) return;
    const m = byId().get(id);
    switch (actEl.dataset.act) {
      case "play":
        await play(id);
        break;
      case "playlist":
        openPlaylistModal(id);
        return;
      case "queue-next":
        player.setTargetNext(player.targetNextId === id ? null : id);
        renderLibrary();
        renderTransport();
        return;
      case "download":
        await downloadTrack(id, actEl.tagName === "BUTTON" ? actEl : null);
        return;
      case "inspect":
        actEl?.blur();
        openInspectModal(id);
        return;
      case "toggle":
        await api.patch(id, { enabled: m.enabled === false });
        break;
      case "retry":
        await api.reanalyze(id);
        break;
      case "move-up": {
        if (activePlaylistId !== "all") {
          const pl = getPlaylist(activePlaylistId);
          if (pl && pl.trackIds) {
            const curIdx = pl.trackIds.indexOf(id);
            if (curIdx > 0) {
              const temp = pl.trackIds[curIdx - 1];
              pl.trackIds[curIdx - 1] = pl.trackIds[curIdx];
              pl.trackIds[curIdx] = temp;
              savePlaylists();
              renderLibrary();
            }
          }
        }
        return;
      }
      case "move-down": {
        if (activePlaylistId !== "all") {
          const pl = getPlaylist(activePlaylistId);
          if (pl && pl.trackIds) {
            const curIdx = pl.trackIds.indexOf(id);
            if (curIdx >= 0 && curIdx < pl.trackIds.length - 1) {
              const temp = pl.trackIds[curIdx + 1];
              pl.trackIds[curIdx + 1] = pl.trackIds[curIdx];
              pl.trackIds[curIdx] = temp;
              savePlaylists();
              renderLibrary();
            }
          }
        }
        return;
      }
      case "pl-remove": {
        if (activePlaylistId !== "all") {
          const pl = getPlaylist(activePlaylistId);
          if (pl && pl.trackIds) {
            pl.trackIds = pl.trackIds.filter((t) => t !== id);
            savePlaylists();
            renderLibrary();
          }
        }
        return;
      }
      case "delete":
        if (!session.multiuser) {
          const ok = await showModal({
            title: "Xác nhận xoá",
            message: `Xoá "${m.title}" khỏi thư viện?`,
            confirmText: "Xoá",
            cancelText: "Thôi",
            danger: true,
          });
          if (!ok) return;
        }
        if (player.cur?.track.id === id) player.stop();
        loader.drop(id);
        forget(id);
        await api.remove(id);
        break;
    }
    refresh();
    return;
  }

  if (batchMode) {
    const row = e.target.closest(".track");
    if (!row) return;
    const id = row.dataset.id;
    if (!id) return;
    if (selectedTrackIds.has(id)) {
      selectedTrackIds.delete(id);
    } else {
      selectedTrackIds.add(id);
    }
    const cb = row.querySelector(".track-cb");
    if (cb) cb.checked = selectedTrackIds.has(id);
    row.classList.toggle("selected", selectedTrackIds.has(id));
    updateBatchBar();
  }
});

// --------------------------------------------------- batch management listeners
$("#btn-batch-toggle")?.addEventListener("click", () => {
  batchMode = !batchMode;
  if (!batchMode) selectedTrackIds.clear();
  renderLibrary();
});

$("#batch-btn-close")?.addEventListener("click", () => {
  batchMode = false;
  selectedTrackIds.clear();
  renderLibrary();
});

$("#batch-select-all")?.addEventListener("change", (e) => {
  const shown = filterMetas(metas);
  if (e.target.checked) {
    for (const m of shown) selectedTrackIds.add(m.id);
  } else {
    for (const m of shown) selectedTrackIds.delete(m.id);
  }
  renderLibrary();
});

$("#batch-btn-in")?.addEventListener("click", async () => {
  if (!selectedTrackIds.size) return;
  const ids = Array.from(selectedTrackIds);
  try {
    await api.batch(ids, "enable");
    for (const m of metas) {
      if (selectedTrackIds.has(m.id)) m.enabled = true;
    }
    renderLibrary();
    renderStage();
  } catch (err) {
    await showModal({ title: "Lỗi thao tác", message: `Không thể đưa các bài đã chọn vào chuỗi: ${err.message}`, confirmText: "Đóng" });
  }
});

$("#batch-btn-out")?.addEventListener("click", async () => {
  if (!selectedTrackIds.size) return;
  const ids = Array.from(selectedTrackIds);
  try {
    await api.batch(ids, "disable");
    for (const m of metas) {
      if (selectedTrackIds.has(m.id)) m.enabled = false;
    }
    renderLibrary();
    renderStage();
  } catch (err) {
    await showModal({ title: "Lỗi thao tác", message: `Không thể bỏ các bài đã chọn khỏi chuỗi: ${err.message}`, confirmText: "Đóng" });
  }
});

$("#batch-btn-pl")?.addEventListener("click", () => {
  if (!selectedTrackIds.size) return;
  openPlaylistModal(Array.from(selectedTrackIds));
});

$("#batch-btn-pl-remove")?.addEventListener("click", () => {
  if (activePlaylistId === "all" || !selectedTrackIds.size) return;
  const pl = getPlaylist(activePlaylistId);
  if (!pl || !pl.trackIds) return;
  pl.trackIds = pl.trackIds.filter((t) => !selectedTrackIds.has(t));
  selectedTrackIds.clear();
  savePlaylists();
  renderLibrary();
});

$("#batch-btn-del")?.addEventListener("click", async () => {
  if (!selectedTrackIds.size) return;
  const ids = Array.from(selectedTrackIds);
  const ok = await showModal({
    title: "Xác nhận xoá theo lô",
    message: `Xoá ${ids.length} bài đã chọn khỏi thư viện?`,
    confirmText: `Xoá ${ids.length} bài`,
    cancelText: "Thôi",
    danger: true,
  });
  if (!ok) return;

  for (const id of ids) {
    if (player.cur?.track.id === id) player.stop();
    loader.drop(id);
    forget(id);
  }
  try {
    await api.batch(ids, "delete");
  } catch (_) {
    for (const id of ids) await api.remove(id).catch(() => {});
  }
  metas = metas.filter((m) => !selectedTrackIds.has(m.id));
  for (const pl of playlists) {
    pl.trackIds = (pl.trackIds || []).filter((t) => !selectedTrackIds.has(t));
  }
  savePlaylists();
  selectedTrackIds.clear();
  renderLibrary();
  refresh();
});

$("#btn-retry-all-errors")?.addEventListener("click", async () => {
  const errIds = metas.filter((m) => m.status === "error").map((m) => m.id);
  if (!errIds.length) return;
  const btn = $("#btn-retry-all-errors");
  if (btn) btn.disabled = true;
  try {
    await api.batch(errIds, "reanalyze");
  } catch (_) {
    for (const id of errIds) await api.reanalyze(id).catch(() => {});
  }
  refresh();
  if (btn) btn.disabled = false;
});

$("#btn-clean-all-errors")?.addEventListener("click", async () => {
  const errIds = metas.filter((m) => m.status === "error").map((m) => m.id);
  if (!errIds.length) return;
  const ok = await showModal({
    title: "Xác nhận xoá tất cả lỗi",
    message: `Xoá toàn bộ ${errIds.length} bài hát bị lỗi khỏi danh sách?`,
    confirmText: `Xoá ${errIds.length} bài lỗi`,
    cancelText: "Thôi",
    danger: true,
  });
  if (!ok) return;

  const btn = $("#btn-clean-all-errors");
  if (btn) btn.disabled = true;
  for (const id of errIds) {
    if (player.cur?.track.id === id) player.stop();
    loader.drop(id);
    forget(id);
  }
  try {
    await api.batch(errIds, "delete");
  } catch (_) {
    for (const id of errIds) await api.remove(id).catch(() => {});
  }
  const errSet = new Set(errIds);
  metas = metas.filter((m) => !errSet.has(m.id));
  for (const pl of playlists) {
    pl.trackIds = (pl.trackIds || []).filter((t) => !errSet.has(t));
  }
  savePlaylists();
  renderLibrary();
  refresh();
  if (btn) btn.disabled = false;
});

// --------------------------------------------------- playlist event listeners
async function promptCreatePlaylist() {
  const name = await showModal({
    title: "Tạo playlist / album mới",
    message: "Nhập tên danh sách phát:",
    prompt: true,
    placeholder: "Ví dụ: Nhạc Chill, Quán Cafe, Vinahey...",
    confirmText: "Tạo playlist",
    cancelText: "Thôi",
  });
  if (name && name.trim()) {
    const pl = createPlaylist(name.trim());
    activePlaylistId = pl.id;
    renderLibrary();
  }
}

$("#btn-create-pl")?.addEventListener("click", promptCreatePlaylist);

const plChipsEl = $("#pl-chips");
if (plChipsEl) {
  plChipsEl.addEventListener("scroll", updatePlNavArrows, { passive: true });
  plChipsEl.addEventListener("wheel", (e) => {
    if (e.deltaY && plChipsEl.scrollWidth > plChipsEl.clientWidth) {
      e.preventDefault();
      plChipsEl.scrollLeft += e.deltaY;
    }
  }, { passive: false });
}
$("#pl-scroll-left")?.addEventListener("click", () => {
  $("#pl-chips")?.scrollBy({ left: -160, behavior: "smooth" });
});
$("#pl-scroll-right")?.addEventListener("click", () => {
  $("#pl-chips")?.scrollBy({ left: 160, behavior: "smooth" });
});
window.addEventListener("resize", updatePlNavArrows, { passive: true });

$("#pl-chips")?.addEventListener("click", (e) => {
  const chip = e.target.closest(".pl-chip[data-pl-id]");
  if (!chip) return;
  activePlaylistId = chip.dataset.plId;
  ui.activePlaylistId = activePlaylistId;
  save();
  const container = $("#pl-chips");
  if (container) scrollChipIntoView(container, chip);
  renderLibrary();
});

$("#pl-play-btn")?.addEventListener("click", async () => {
  if (activePlaylistId === "all") return;
  const pl = getPlaylist(activePlaylistId);
  if (!pl || !pl.trackIds.length) return;
  const readyInPl = metas.find((m) => m.status === "ready" && pl.trackIds.includes(m.id));
  if (!readyInPl) {
    await showModal({
      title: "Chưa có bài sẵn sàng",
      message: "Chưa có bài hát nào đã hoàn tất phân tích trong playlist này.",
      confirmText: "Đã hiểu",
    });
    return;
  }
  lockToPlaylist = true;
  ui.lockToPlaylist = true;
  save();
  const lockCb = $("#pl-lock-toggle");
  if (lockCb) lockCb.checked = true;
  engine.ctx.resume();
  await play(readyInPl.id);
});

$("#pl-lock-toggle")?.addEventListener("change", (e) => {
  lockToPlaylist = e.target.checked;
  ui.lockToPlaylist = lockToPlaylist;
  save();
  prepareNext();
});

$("#pl-rename-btn")?.addEventListener("click", async () => {
  if (activePlaylistId === "all") return;
  const pl = getPlaylist(activePlaylistId);
  if (!pl) return;
  const newName = await showModal({
    title: "Đổi tên playlist / album",
    prompt: true,
    defaultValue: pl.name,
    confirmText: "Lưu thay đổi",
    cancelText: "Thôi",
  });
  if (newName && newName.trim() && newName.trim() !== pl.name) {
    renamePlaylist(pl.id, newName.trim());
  }
});

$("#pl-share-btn")?.addEventListener("click", async () => {
  if (activePlaylistId === "all") return;
  const pl = getPlaylist(activePlaylistId);
  if (!pl || !pl.trackIds.length) return;
  const url = new URL(window.location.origin + window.location.pathname);
  url.searchParams.set("pl_name", pl.name);
  url.searchParams.set("pl_tracks", pl.trackIds.join(","));
  try {
    await navigator.clipboard.writeText(url.toString());
    await showModal({
      title: "Đã sao chép link",
      message: `Đã sao chép link chia sẻ playlist "${pl.name}" vào clipboard!\nGửi link này cho bạn bè để cùng nghe playlist này.`,
      confirmText: "Đã hiểu",
    });
  } catch (_) {
    await showModal({
      title: "Link chia sẻ playlist",
      message: "Sao chép link dưới đây để gửi cho bạn bè:",
      prompt: true,
      defaultValue: url.toString(),
      confirmText: "Xong",
      cancelText: "Đóng",
    });
  }
});

$("#pl-delete-btn")?.addEventListener("click", async () => {
  if (activePlaylistId === "all") return;
  const pl = getPlaylist(activePlaylistId);
  if (!pl) return;
  const ok = await showModal({
    title: "Xoá playlist",
    message: `Xoá playlist "${pl.name}"? Các bài hát vẫn được giữ nguyên trong thư viện.`,
    confirmText: "Xoá",
    cancelText: "Thôi",
    danger: true,
  });
  if (ok) {
    deletePlaylist(pl.id);
  }
});

$("#pl-modal-close")?.addEventListener("click", () => {
  $("#pl-modal")?.close();
});

$("#pl-modal-mode")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".pl-mode-btn[data-mode]");
  if (!btn) return;
  plModalMode = btn.dataset.mode;
  updatePlaylistModalModeUI();
  renderPlaylistModalList();
});

$("#pl-modal-list")?.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn || !modalTrackIds.length) return;
  const plId = btn.dataset.plId;
  const targetPl = getPlaylist(plId);
  if (!targetPl) return;
  const act = btn.dataset.action;

  if (act === "apply-copy") {
    for (const tid of modalTrackIds) {
      if (!targetPl.trackIds.includes(tid)) targetPl.trackIds.push(tid);
    }
    savePlaylists();
    renderPlaylistModalList();
    renderLibrary();
  } else if (act === "apply-move") {
    for (const tid of modalTrackIds) {
      if (!targetPl.trackIds.includes(tid)) targetPl.trackIds.push(tid);
    }
    if (activePlaylistId !== "all" && activePlaylistId !== plId) {
      const curPl = getPlaylist(activePlaylistId);
      if (curPl) {
        curPl.trackIds = curPl.trackIds.filter((t) => !modalTrackIds.includes(t));
      }
    }
    savePlaylists();
    renderLibrary();
    $("#pl-modal")?.close();
  }
});

function handleModalCreatePlaylist() {
  const input = $("#pl-modal-new-name");
  const name = input?.value.trim();
  if (!name) return;
  const targetPl = createPlaylist(name, [...modalTrackIds]);
  if (plModalMode === "move" && activePlaylistId !== "all" && activePlaylistId !== targetPl.id) {
    const curPl = getPlaylist(activePlaylistId);
    if (curPl) {
      curPl.trackIds = curPl.trackIds.filter((t) => !modalTrackIds.includes(t));
    }
    $("#pl-modal")?.close();
  }
  input.value = "";
  savePlaylists();
  renderPlaylistModalList();
  renderLibrary();
}

$("#pl-modal-new-btn")?.addEventListener("click", handleModalCreatePlaylist);
$("#pl-modal-new-name")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    handleModalCreatePlaylist();
  }
});

// --------------------------------------------------- download & track inspector
async function downloadTrack(id, btn) {
  const m = byId().get(id);
  const title = songOf(m).title || id;
  const origHtml = btn ? btn.innerHTML : null;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" class="spin"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"/></svg>`;
  }
  try {
    const rawBuf = await api.audio(id);
    const blob = new Blob([rawBuf], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title} - MashLoop.mp3`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (err) {
    await showModal({
      title: "Không thể tải file",
      message: `Đã xảy ra lỗi khi tải file âm thanh: ${err.message}`,
      confirmText: "Đóng",
    });
  } finally {
    if (btn && origHtml) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

async function openInspectModal(id) {
  const m = byId().get(id);
  if (!m) return;
  const song = songOf(m);
  const dlg = $("#inspect-modal");
  const content = $("#inspect-content");
  if (!dlg || !content) return;

  const isQueued = player.targetNextId === id;
  const bpmStr = m.bpm ? `${Math.round(m.bpm)} BPM` : "--";
  const camStr = m.camelot || "--";
  const durStr = m.duration ? fmt(m.duration) : "--";
  const jumpsStr = `${m.jumps ?? 0} nhánh`;

  content.innerHTML = `
    <div class="inspect-hero">
      <h3 class="inspect-song-title">${esc(song.title)}</h3>
      <p class="inspect-song-artist">${esc(song.artist || "Nghệ sĩ chưa rõ")}</p>
    </div>
    <div class="inspect-grid">
      <div class="inspect-card">
        <span class="inspect-card__val">${esc(bpmStr)}</span>
        <span class="inspect-card__lbl">Nhịp điệu</span>
      </div>
      <div class="inspect-card">
        <span class="inspect-card__val">${esc(camStr)}</span>
        <span class="inspect-card__lbl">Tone Camelot</span>
      </div>
      <div class="inspect-card">
        <span class="inspect-card__val">${esc(durStr)}</span>
        <span class="inspect-card__lbl">Thời lượng</span>
      </div>
      <div class="inspect-card">
        <span class="inspect-card__val">${esc(jumpsStr)}</span>
        <span class="inspect-card__lbl">Điểm nhảy</span>
      </div>
    </div>
    <div class="inspect-section">
      <h4 class="inspect-section__title">Điểm nối hòa âm</h4>
      <div class="inspect-links" id="inspect-links-box">
        <div style="text-align:center;padding:12px;color:var(--text-faint);font-size:var(--step--2)">
          Đang tải dữ liệu điểm nối...
        </div>
      </div>
    </div>
    <div class="inspect-acts">
      <button type="button" class="inspect-btn inspect-btn--play" id="inspect-act-play">
        ${ICON.play} <span>Phát ngay</span>
      </button>
      <div class="inspect-acts__sub">
        <button type="button" class="inspect-btn inspect-btn--queue" id="inspect-act-queue" data-act="queue-next" title="${isQueued ? "Hủy chờ phát tiếp" : "Phát tiếp theo"}">
          ${ICON.queueNext} <span>${isQueued ? "Hủy chờ" : "Kế tiếp"}</span>
        </button>
        <button type="button" class="inspect-btn" id="inspect-act-dl" data-act="download" title="Tải file MP3">
          ${ICON.download} <span>Tải MP3</span>
        </button>
        <button type="button" class="inspect-btn" id="inspect-act-pl" data-act="playlist" title="Thêm vào playlist">
          ${ICON.playlist} <span>Playlist</span>
        </button>
        <button type="button" class="inspect-btn inspect-btn--del" id="inspect-act-del" data-act="delete" title="Xoá bài khỏi thư viện">
          ${ICON.del} <span>Xoá</span>
        </button>
      </div>
    </div>
  `;

  dlg.showModal();

  $("#inspect-act-play")?.addEventListener("click", () => {
    dlg.close();
    play(id);
  });
  $("#inspect-act-queue")?.addEventListener("click", () => {
    player.setTargetNext(player.targetNextId === id ? null : id);
    renderLibrary();
    renderTransport();
    dlg.close();
  });
  $("#inspect-act-dl")?.addEventListener("click", (e) => {
    downloadTrack(id, e.currentTarget);
  });
  $("#inspect-act-pl")?.addEventListener("click", () => {
    dlg.close();
    openPlaylistModal(id);
  });
  $("#inspect-act-del")?.addEventListener("click", async () => {
    dlg.close();
    if (!session.multiuser) {
      const ok = await showModal({
        title: "Xác nhận xoá",
        message: `Xoá "${song.title}" khỏi thư viện?`,
        confirmText: "Xoá",
        cancelText: "Thôi",
        danger: true,
      });
      if (!ok) return;
    }
    if (player.cur?.track.id === id) player.stop();
    loader.drop(id);
    forget(id);
    await api.remove(id);
    refresh();
  });

  try {
    const res = await api.transitions(id);
    const box = $("#inspect-links-box");
    if (!box) return;
    const items = res?.items || [];
    if (!items.length) {
      box.innerHTML = `<div style="text-align:center;padding:10px;color:var(--text-faint);font-size:var(--step--2)">Chưa có điểm nối sang bài khác trong thư viện hiện tại.</div>`;
      return;
    }
    const bestByDest = new Map();
    for (const tr of items) {
      const curBest = bestByDest.get(tr.to);
      if (!curBest || (tr.q || 0) > (curBest.q || 0)) {
        bestByDest.set(tr.to, tr);
      }
    }
    const sorted = Array.from(bestByDest.values()).sort((a, b) => (b.q || 0) - (a.q || 0));
    box.innerHTML = sorted.map((tr) => {
      const destMeta = byId().get(tr.to);
      const destTitle = destMeta ? songOf(destMeta).title : tr.to;
      const pct = Math.round((tr.q || 0.8) * 100);
      const typeLabel = KIND_VI[tr.type] || tr.type || "chuyển bài";
      return `
        <div class="inspect-link-item">
          <div class="inspect-link-info">
            <span class="inspect-link-target">${esc(destTitle)}</span>
            <span class="inspect-link-meta">${esc(typeLabel)} · ${pct}%</span>
          </div>
          <button type="button" class="pl-btn-apply" data-goto="${esc(tr.to)}" title="Xem bài này" aria-label="Xem bài này"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg></button>
        </div>
      `;
    }).join("");

    box.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-goto]");
      if (b) {
        const destId = b.dataset.goto;
        if (destId) openInspectModal(destId);
      }
    });
  } catch (_) {
    const box = $("#inspect-links-box");
    if (box) box.innerHTML = `<div style="text-align:center;padding:10px;color:var(--text-faint);font-size:var(--step--2)">Không tải được danh sách điểm nối.</div>`;
  }
}

// --------------------------------------------------- library search & sort listeners
$("#lib-search-input")?.addEventListener("input", (e) => {
  libSearchQuery = e.target.value.trim();
  const clearBtn = $("#lib-search-clear");
  if (clearBtn) clearBtn.hidden = !libSearchQuery;
  renderLibrary();
});

$("#lib-search-clear")?.addEventListener("click", () => {
  libSearchQuery = "";
  const input = $("#lib-search-input");
  if (input) input.value = "";
  const clearBtn = $("#lib-search-clear");
  if (clearBtn) clearBtn.hidden = true;
  renderLibrary();
  input?.focus();
});

const sortBtn = $("#lib-sort-btn");
const sortPopover = $("#lib-sort-popover");
const sortLabel = $("#lib-sort-label");
const sortSelect = $("#lib-sort-select");

function closeSortPopover() {
  if (sortPopover && !sortPopover.hidden) {
    sortPopover.hidden = true;
    sortBtn?.setAttribute("aria-expanded", "false");
  }
}

sortBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  const willOpen = sortPopover ? sortPopover.hidden : false;
  if (sortPopover) sortPopover.hidden = !willOpen;
  sortBtn.setAttribute("aria-expanded", willOpen ? "true" : "false");
});

document.addEventListener("click", (e) => {
  if (!e.target.closest("#lib-sort-wrap")) {
    closeSortPopover();
  }
});

sortPopover?.addEventListener("click", (e) => {
  const opt = e.target.closest(".lib-sort-opt");
  if (!opt) return;
  const val = opt.getAttribute("data-val") || "default";
  libSortMode = val;
  ui.libSortMode = libSortMode;
  save();
  if (sortSelect) sortSelect.value = val;
  if (sortLabel) sortLabel.textContent = opt.querySelector("span")?.textContent || "Mới nhất";
  sortPopover.querySelectorAll(".lib-sort-opt").forEach((el) => {
    el.classList.toggle("on", el === opt);
  });
  closeSortPopover();
  renderLibrary();
});

sortSelect?.addEventListener("change", (e) => {
  libSortMode = e.target.value;
  ui.libSortMode = libSortMode;
  save();
  const matchingOpt = sortPopover?.querySelector(`[data-val="${libSortMode}"]`);
  if (matchingOpt && sortLabel) {
    sortLabel.textContent = matchingOpt.querySelector("span")?.textContent || "Mới nhất";
    sortPopover?.querySelectorAll(".lib-sort-opt").forEach((el) => {
      el.classList.toggle("on", el === matchingOpt);
    });
  }
  renderLibrary();
});

function syncSortUI() {
  if (sortSelect) sortSelect.value = libSortMode;
  const matchingOpt = sortPopover?.querySelector(`[data-val="${libSortMode}"]`);
  if (matchingOpt && sortLabel) {
    sortLabel.textContent = matchingOpt.querySelector("span")?.textContent || "Mới nhất";
    sortPopover?.querySelectorAll(".lib-sort-opt").forEach((el) => {
      el.classList.toggle("on", el === matchingOpt);
    });
  }
}
syncSortUI();

$("#inspect-close")?.addEventListener("click", () => {
  $("#inspect-modal")?.close();
  document.activeElement?.blur();
});

$("#inspect-modal")?.addEventListener("close", () => {
  document.activeElement?.blur();
});

player.addEventListener("target-next", () => {
  renderLibrary();
  renderTransport();
});

player.addEventListener("plan-failed", (e) => {
  showModal({
    title: "Không thể chuyển bài",
    message: e.detail?.error || "Không thể tải bài hát tiếp theo.",
  });
});

async function refresh() {
  try {
    const r = await api.tracks();
    metas = r.tracks;
    for (const m of metas) known.set(m.id, m);
    workerState = r.worker;
    loader.setMetas(metas);
    // New pairs were linked in this library: loaded songs pick up their new exits.
    if (lastLinks !== null && r.links !== lastLinks) {
      loader.refreshAll();
      viz.invalidate();
    }
    lastLinks = r.links;
    if (theme.setMoods(metas.filter((m) => m.status === "ready"))) recolor();
    // An old server process (started before an update) is still serving: its
    // results would not match the files on disk. Servers older than this check
    // do not send the flag at all.
    serverStale = !("stale_server" in r) || r.stale_server;
    renderLibrary();
    return true;
  } catch (err) {
    console.error("Refresh error:", err);
    if (err instanceof ReferenceError || err instanceof TypeError) {
      $("#worker").textContent = `Lỗi script: ${err.message}`;
      return false;
    }
    const msg = err?.message || "";
    if (msg.includes("quá nhiều") || msg.includes("429")) {
      $("#worker").textContent = msg;
    } else if (msg.includes("502") || msg.includes("503") || msg.includes("504") || msg.includes("Failed to fetch") || msg.includes("session expired") || msg.includes("410")) {
      $("#worker").textContent = "Đang kết nối lại server…";
      if (msg.includes("session expired") || msg.includes("410")) {
        session.id = null;
      }
    } else {
      $("#worker").textContent = "Mất kết nối tới server";
    }
    return false;
  }
}

let pollTimer = null;
let pollInterval = 5000;
function schedulePoll() {
  clearTimeout(pollTimer);
  const working = metas.some((m) => m.status !== "ready" && m.status !== "error") || workerState?.current;
  const delay = working ? 1200 : pollInterval;
  pollTimer = setTimeout(async () => {
    const ok = await refresh();
    pollInterval = ok ? 5000 : 2500;
    schedulePoll();
  }, delay);
}

// --------------------------------------------------------------- add / search

const isUrl = (s) => /^https?:\/\//i.test(s.trim());

// Hosted: before the first song a visitor brings in (a link, a search result,
// a file), they confirm they may use it. Asked once per visit, kept nowhere.
let consented = false;
async function consent() {
  await ready();
  if (!session.multiuser || consented) return true;
  const dlg = $("#consent");
  dlg.returnValue = "";
  dlg.showModal();
  await new Promise((resolve) => dlg.addEventListener("close", resolve, { once: true }));
  consented = dlg.returnValue === "yes";
  return consented;
}

function cleanUiError(msg) {
  let s = String(msg || "").trim();
  s = s.replace(/^(?:could not resolve|error|[A-Za-z_]+Error):\s*/i, "");
  s = s.replace(/^\[[^\]]+\]\s*/i, "");
  const low = s.toLowerCase();
  if (low.includes("unviewable") || low.includes("playlist type is unviewable")) {
    return "YouTube Mix này cần mở kèm bài hát gốc (đã tự động nắn link).";
  }
  if (low.includes("confirm you're not a bot") || (low.includes("bot") && (low.includes("sign in") || low.includes("protect")))) {
    return "YouTube yêu cầu xác minh bot hoặc video bị giới hạn vùng/độ tuổi.";
  }
  if (low.includes("this video is unavailable") || low.includes("unavailable")) {
    return "Video này không khả dụng hoặc đã bị tác giả xóa.";
  }
  if (low.includes("private video")) {
    return "Video này được đặt ở chế độ riêng tư.";
  }
  if (low.includes("unsupported url")) {
    return "Đường link không thuộc nguồn được hỗ trợ hoặc sai định dạng.";
  }
  if (low.includes("vip")) {
    return "Bài này yêu cầu tài khoản VIP của nền tảng nguồn.";
  }
  if (low.includes("timed out") || low.includes("timeout")) {
    return "Hết thời gian kết nối tới máy chủ nguồn (timeout).";
  }
  s = s.replace(/https?:\/\/\S+/g, "");
  s = s.replace(/--cookies[^\s.]*/g, "");
  s = s.replace(/\s+/g, " ").trim();
  if (s.length > 90) s = s.slice(0, 90) + "…";
  return s || "Không thể tải bài từ đường link này.";
}

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#add-input").value.trim();
  if (!text) return;
  const box = $("#search-results");
  const submit = $("#add-form button[type=submit]");

  // Check if user pasted a MashLoop share URL
  if (text.includes("pl_tracks=") || text.includes("tracks=")) {
    try {
      const u = new URL(text);
      const name = u.searchParams.get("pl_name") || "Playlist đã chia sẻ";
      const tracksParam = u.searchParams.get("pl_tracks") || u.searchParams.get("tracks");
      if (tracksParam) {
        const tids = tracksParam.split(",").map((s) => s.trim()).filter(Boolean);
        if (tids.length) {
          let existing = playlists.find((p) => p.name === name);
          if (!existing) {
            existing = createPlaylist(name, tids);
          } else {
            for (const tid of tids) {
              if (!existing.trackIds.includes(tid)) existing.trackIds.push(tid);
            }
            savePlaylists();
          }
          activePlaylistId = existing.id;
          if (session.multiuser) {
            api.restore(tids).catch(() => {});
          }
          box.innerHTML = `<div class="msg">Đã nạp playlist <b>"${esc(name)}"</b> (${tids.length} bài) thành công.</div>`;
          $("#add-input").value = "";
          refresh();
          renderPlaylists();
          setTimeout(() => (box.innerHTML = ""), 4500);
          return;
        }
      }
    } catch (_) {}
  }

  if (isUrl(text) && !(await consent())) return;
  submit.disabled = true;
  if (isUrl(text)) {
    box.innerHTML = `<div class="msg">Đang quét link và nạp danh sách bài…</div>`;
    try {
      const r = await api.add(text);
      const total = r.added.length;
      const have = r.added.filter((m) => m.status === "ready").length;
      const todo = total - have;
      let msg = "";
      if (activePlaylistId !== "all") {
        addTracksToActivePlaylist(r.added.map((m) => m.id));
        const curPl = getPlaylist(activePlaylistId);
        msg = `Đã nạp ${total} bài vào playlist "${esc(curPl?.name || "")}"`;
      } else if (total > 1) {
        const albumName = `Album (${total} bài)`;
        const newPl = createPlaylist(albumName, r.added.map((m) => m.id));
        activePlaylistId = newPl.id;
        msg = `Đã nạp thành công <b>${total} bài</b> và gom vào <b>"${esc(newPl.name)}"</b> (${todo} bài mới vào hàng đợi)`;
      } else {
        msg = [have && `Đã thêm ${have} bài có sẵn`, todo && `${have ? "" : "Đã thêm "}${todo} bài vào hàng đợi phân tích`].filter(Boolean).join(", ") || "Không thêm được bài nào";
      }
      box.innerHTML = `<div class="msg">${msg}.${r.note ? ` ${esc(r.note)}.` : ""}</div>`;
      $("#add-input").value = "";
      setTimeout(() => (box.innerHTML = ""), 4500);
    } catch (err) {
      box.innerHTML = `<div class="msg msg--err">${cleanUiError(err.message)}</div>`;
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
    box.innerHTML = `<div class="msg msg--err">${cleanUiError(err.message)}</div>`;
  }
  submit.disabled = false;
});

$("#search-results").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-url]");
  if (!btn || !(await consent())) return;
  btn.disabled = true;
  btn.textContent = "…";
  try {
    const r = await api.add(btn.dataset.url);
    if (r?.added) addTracksToActivePlaylist(r.added.map((m) => m.id));
    btn.textContent = "Đã thêm";
  } catch (err) {
    btn.textContent = "Lỗi";
    btn.title = err.message;
  }
  refresh();
  schedulePoll();
});

// ------------------------------------------------------------------ upload

// Files go up one after another (the server analyses several at once anyway);
// each gets a line with its progress in the results box.
const uploads = [];
let uploading = false;

function renderUploads() {
  const box = $("#search-results");
  if (!uploads.length) return;
  box.innerHTML = uploads.map((u) => `<div class="upload-row ${u.error ? "err" : ""}">
      <div class="t">${esc(u.name)}</div>
      ${u.error ? `<small>${esc(u.error)}</small>`
        : u.done ? `<small>${u.count > 1 ? `Đã thêm ${u.count} bài` : "Đã thêm"}, đang phân tích${u.note ? `. ${esc(u.note)}` : ""}</small>`
        : `<div class="progress"><i style="width:${Math.round(100 * u.p)}%"></i></div>`}
    </div>`).join("");
}

async function uploadFiles(files) {
  if (!files.length || !(await consent())) return;
  const maxMb = session.limits.upload_mb || 500;
  for (const f of files) {
    const u = { name: f.name, p: 0, done: false, error: null, file: f };
    if (f.size > maxMb * 1024 * 1024) u.error = `Lớn hơn ${maxMb} MB`;
    else if (f.type && !/^(audio|video)\/|zip/.test(f.type) && !/\.zip$/i.test(f.name)) u.error = "Không phải file âm thanh";
    uploads.push(u);
  }
  renderUploads();
  if (uploading) return;
  uploading = true;
  for (const u of uploads) {
    if (u.done || u.error) continue;
    try {
      const r = await api.upload(u.file, (p) => ((u.p = p), renderUploads()));
      u.done = true;
      u.count = r?.added?.length || 0;
      u.note = r?.note || "";
      if (r?.added?.length) {
        if (activePlaylistId !== "all") {
          addTracksToActivePlaylist(r.added.map((m) => m.id));
        } else if (r.added.length > 1) {
          const albumName = (u.file?.name || "Album").replace(/\.[^/.]+$/, "");
          const newPl = createPlaylist(albumName, r.added.map((m) => m.id));
          activePlaylistId = newPl.id;
        }
      }
    } catch (err) {
      u.error = `Không tải lên được: ${err.message}`;
    }
    u.file = null;
    renderUploads();
    refresh();
    schedulePoll();
  }
  uploading = false;
  setTimeout(() => {
    if (uploading) return;
    uploads.length = 0;
    $("#search-results").innerHTML = "";
  }, 6000);
}

$("#file-input").addEventListener("change", (e) => {
  uploadFiles([...e.target.files]);
  e.target.value = "";
});

// Desktop native integration (pywebview)
function setupDesktopBridge() {
  const row = $("#desktop-row");
  if (!window.pywebview) return;
  if (row) row.hidden = false;

  if (window.pywebview?.api?.get_system_volume) {
    window.pywebview.api.get_system_volume().then((vol) => {
      if (typeof vol === "number" && !isNaN(vol)) setAppVolume(vol, false);
    }).catch(() => {});
  }

  $("#btn-desktop-files")?.addEventListener("click", async () => {
    try {
      const files = await window.pywebview.api.select_files();
      if (!files || !files.length) return;
      $("#search-results").innerHTML = `<div class="msg">Đang chuẩn bị ${files.length} file...</div>`;
      const r = await api.ingestLocal(files);
      const added = r?.added?.length || 0;
      $("#search-results").innerHTML = `<div class="msg">Đã thêm ${added} bài từ máy tính. Đang phân tích...</div>`;
      refresh();
      schedulePoll();
    } catch (err) {
      $("#search-results").innerHTML = `<div class="msg err">Lỗi thêm file: ${esc(err.message)}</div>`;
    }
  });

  $("#btn-desktop-folder")?.addEventListener("click", async () => {
    try {
      const files = await window.pywebview.api.select_folder();
      if (!files || !files.length) return;
      $("#search-results").innerHTML = `<div class="msg">Tìm thấy ${files.length} bài trong thư mục...</div>`;
      const r = await api.ingestLocal(files);
      const added = r?.added?.length || 0;
      $("#search-results").innerHTML = `<div class="msg">Đã thêm ${added} bài từ thư mục. Đang phân tích...</div>`;
      refresh();
      schedulePoll();
    } catch (err) {
      $("#search-results").innerHTML = `<div class="msg err">Lỗi chọn thư mục: ${esc(err.message)}</div>`;
    }
  });
}

window.addEventListener("pywebviewready", setupDesktopBridge);
if (window.pywebview) setupDesktopBridge();

// Sync initial mobile system volume if Android bridge is present
if (window.AndroidAudio?.getVolume) {
  try {
    const mVol = window.AndroidAudio.getVolume();
    if (typeof mVol === "number" && !isNaN(mVol)) setAppVolume(mVol, false);
  } catch (_) {}
}

// Mobile Install Modal
const mobileModal = $("#mobile-modal");

function updateMobileModal() {
  const currentOrigin = window.location.origin;
  const isTailscale = window.location.hostname.startsWith("100.");
  const isHfSpace =
    window.location.hostname.includes("hf.space") ||
    window.location.hostname.includes("huggingface.co");
  const isLocal =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";

  const ipSpan = $("#mobile-modal-ip");
  const subText = $("#mobile-modal-sub");
  const qrImg = $("#mobile-modal-qr");
  const modalLink = $("#mobile-modal-link");
  const scanDesc = $("#mobile-modal-scan-desc");

  const displayUrl = currentOrigin;

  if (ipSpan) ipSpan.textContent = displayUrl;
  if (modalLink) {
    modalLink.href = displayUrl;
    modalLink.textContent = `${displayUrl} ↗`;
  }
  if (subText) {
    if (isHfSpace) {
      subText.innerHTML = `Đang chạy trên Hugging Face Spaces: <span class="mono mobile-modal__ip">${displayUrl}</span>`;
    } else if (isTailscale) {
      subText.innerHTML = `Đã kết nối máy chủ Tailscale: <span class="mono mobile-modal__ip">${displayUrl}</span>`;
    } else if (isLocal) {
      subText.innerHTML = `Máy chủ cục bộ: <span class="mono mobile-modal__ip">${displayUrl}</span>`;
    } else {
      subText.innerHTML = `Địa chỉ máy chủ: <span class="mono mobile-modal__ip">${displayUrl}</span>`;
    }
  }
  if (scanDesc) {
    scanDesc.textContent = isHfSpace
      ? " để mở trực tiếp qua Hugging Face Space."
      : " để mở ứng dụng tức thì trên điện thoại.";
  }
  if (qrImg) {
    qrImg.src = `/api/qr?data=${encodeURIComponent(displayUrl)}`;
    qrImg.onerror = () => {
      qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(displayUrl)}`;
    };
  }
}

$("#btn-mobile-modal")?.addEventListener("click", () => {
  updateMobileModal();
  mobileModal?.showModal();
});
$("#mobile-modal-close")?.addEventListener("click", () => {
  mobileModal?.close();
});

mobileModal?.addEventListener("click", (e) => {
  const rect = mobileModal.getBoundingClientRect();
  const inside =
    rect.top <= e.clientY &&
    e.clientY <= rect.top + rect.height &&
    rect.left <= e.clientX &&
    e.clientX <= rect.left + rect.width;
  if (!inside) mobileModal.close();
});

// Shortcuts & Help Modal
const shortcutsModal = $("#shortcuts-modal");
export const openShortcuts = () => shortcutsModal?.showModal();
export const closeShortcuts = () => shortcutsModal?.close();
$("#btn-shortcuts-modal")?.addEventListener("click", openShortcuts);
$("#shortcuts-modal-close")?.addEventListener("click", closeShortcuts);
shortcutsModal?.addEventListener("click", (e) => {
  if (e.target === shortcutsModal) {
    shortcutsModal.close();
    return;
  }
  const rect = shortcutsModal.getBoundingClientRect();
  const inside =
    rect.top <= e.clientY &&
    e.clientY <= rect.top + rect.height &&
    rect.left <= e.clientX &&
    e.clientX <= rect.left + rect.width;
  if (!inside) shortcutsModal.close();
});

// ------------------------------------------------------------- Zen Fullscreen Mode
let zenIdleTimer = null;
function resetZenIdle() {
  document.body.classList.remove("zen-idle");
  clearTimeout(zenIdleTimer);
  if (document.body.classList.contains("is-zen")) {
    zenIdleTimer = setTimeout(() => {
      document.body.classList.add("zen-idle");
    }, 3500);
  }
}

window.addEventListener("pointermove", resetZenIdle, { passive: true });
window.addEventListener("pointerdown", resetZenIdle, { passive: true });
window.addEventListener("keydown", resetZenIdle, { passive: true });

function updateZenUI(isZen) {
  const zenBtn = $("#btn-zen");
  if (zenBtn) {
    const label = zenBtn.querySelector(".zen-label");
    if (label) label.textContent = isZen ? "Thu nhỏ" : "Toàn màn hình";
    zenBtn.setAttribute("aria-label", isZen ? "Thu nhỏ visualizer (F)" : "Toàn màn hình visualizer (F)");
    zenBtn.title = isZen ? "Thu nhỏ visualizer (F)" : "Toàn màn hình visualizer (F)";
  }
  resetZenIdle();
  setTimeout(() => viz && typeof viz._resize === "function" && viz._resize(), 50);
}

export function toggleZen() {
  const isZen = document.body.classList.toggle("is-zen");
  if (isZen) {
    if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  } else {
    if (document.exitFullscreen && document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  }
  updateZenUI(isZen);
}

$("#btn-zen")?.addEventListener("click", toggleZen);
$("#btn-zen-exit")?.addEventListener("click", toggleZen);

document.addEventListener("fullscreenchange", () => {
  const isFull = !!document.fullscreenElement;
  if (!isFull && document.body.classList.contains("is-zen")) {
    document.body.classList.remove("is-zen");
    updateZenUI(false);
  }
});

// Zen HUD tools: Tape stop, Filter sweep, Neon glow booster
$("#zen-fx-tape")?.addEventListener("click", () => {
  if (player.cur && player.playing) {
    player.forceTransition("tape");
  } else if (player.cur) {
    player.requestJump();
  }
});

$("#zen-fx-sweep")?.addEventListener("click", () => {
  if (player.cur && player.playing) {
    player.forceTransition("sweeper");
  } else if (player.cur) {
    player.requestJump();
  }
});

const GLOW_STEPS = [0.5, 1.0, 1.5, 2.0];
$("#zen-glow-toggle")?.addEventListener("click", () => {
  const currentGlow = ui.glow ?? 1.0;
  let nextIdx = 0;
  for (let i = 0; i < GLOW_STEPS.length; i++) {
    if (Math.abs(GLOW_STEPS[i] - currentGlow) < 0.15) {
      nextIdx = (i + 1) % GLOW_STEPS.length;
      break;
    }
  }
  const nextGlow = GLOW_STEPS[nextIdx];
  ui.glow = nextGlow;
  if (typeof theme.setGlow === "function") theme.setGlow(nextGlow);
  const glowInput = $("#s-glow");
  if (glowInput) glowInput.value = nextGlow;
  const glowVal = $("#v-glow");
  if (glowVal) glowVal.textContent = `${Math.round(nextGlow * 100)}%`;
  const zenGlowLabel = $("#zen-glow-val");
  if (zenGlowLabel) zenGlowLabel.textContent = `${Math.round(nextGlow * 100)}%`;
  viz.invalidate();
  recolor();
  applySettings();
});

// Drop files anywhere on the page.
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
document.addEventListener("dragenter", (e) => {
  if (!hasFiles(e)) return;
  dragDepth++;
  document.body.classList.add("dragging");
});
document.addEventListener("dragleave", (e) => {
  if (!hasFiles(e)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) document.body.classList.remove("dragging");
});
document.addEventListener("dragover", (e) => {
  if (hasFiles(e)) e.preventDefault();
});
document.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("dragging");
  uploadFiles([...e.dataTransfer.files]);
});

// ------------------------------------------------------------- stage text

const KIND = {
  cut: "nối thẳng", drop: "drop", blend: "blend khớp nhịp", fade: "crossfade", echo: "echo vang", wash: "reverb wash",
  riser: "build-up", flanger: "flanger", gap: "ngắt lặng", brake: "phanh đĩa", roll: "cuộn nhịp", spin: "spinback",
  gate: "gate",
};
const KIND_CAP = KIND_VI;
// A blend named by how the two songs are mixed.
const BLEND_STYLE = { long: "blend dài", eq: "blend EQ", short: "blend ngắn", filter: "blend lọc", swap: "drop swap",
  stem: "trao giọng", acapella: "acapella", loop: "blend vòng lặp", mashup: "mashup", double: "double drop" };
const kindOf = (tr) => (tr.type === "blend" && BLEND_STYLE[tr.style]) || KIND[tr.type] || tr.type;
const kindCap = (tr) => {
  const s = tr.type === "blend" && BLEND_STYLE[tr.style];
  return s ? s[0].toUpperCase() + s.slice(1) : KIND_CAP[tr.type] || tr.type;
};
const CRIT_TAG = { mood: "CÙNG MOOD", tempo: "CÙNG NHỊP", key: "HỢP TÔNG", set: "SET DJ", free: "TỰ DO" };
// Where a set stands, for the hand-over about to happen.
const SET_PHASE = { warmup: "khởi động", cruise: "giữ nhịp", build: "đẩy lên", peak: "lên đỉnh", breather: "khoảng nghỉ",
  lift: "bùng lại" };

// Why the chain picked this exit, in the terms of the chosen criterion.
function criterionNote(T, tr) {
  const m = byId().get(tr.to);
  switch (player.settings.criterion) {
    case "mood": {
      const d = tr.mood ?? 0;
      return ` · ${d < 0.25 ? "mood rất gần" : d < 0.5 ? "mood gần" : "mood hơi khác"}`;
    }
    case "tempo":
      return m?.bpm ? ` · ${Math.round(T.analysis.bpm)} → ${Math.round(m.bpm)} BPM` : "";
    case "key": {
      if (!m?.camelot) return "";
      const fit = keyFit(T.analysis.camelot, m.camelot, tr.semis ?? 0);
      return ` · tông ${esc(T.analysis.camelot)} → ${esc(shiftCamelot(m.camelot, tr.semis ?? 0))}${fit >= 0.8 ? ", hợp" : fit > 0.3 ? ", gần hợp" : ""}`;
    }
    case "set":
      return ` · set: ${SET_PHASE[setPhase(player.stats.transitions).phase]}`;
    default:
      return "";
  }
}

function setHTML(el, html) {
  if (el.innerHTML !== html) el.innerHTML = html;
}

function renderStage() {
  const view = player.audible();
  const p = player;
  const T = view?.entry.track;
  const cta = $("#rc-cta");
  if (!T) {
    const empty = !metas.some((m) => m.status === "ready");
    // An empty library: one sample library offered right on the stage.
    const lib = empty ? stageSample() : null;
    setHTML($("#rc-kicker"), "HAI VÒNG ĐANG CHỜ");
    setHTML($("#rc-title"), empty ? "Thêm một bài để có vòng đầu tiên" : "Chọn một bài để bắt đầu vòng lặp");
    setHTML($("#rc-meta"), !empty ? "Bấm phát, hoặc nút ▶ ở một bài trong thư viện"
      : lib ? "Gõ tên bài ở ô Thêm bài trong thư viện, hoặc nghe thử ngay" : "Gõ tên bài ở ô Thêm bài trong thư viện");
    cta.hidden = !lib;
    if (lib && !cta.disabled) {
      cta.dataset.key = lib.key;
      cta.querySelector("span").textContent = `Nghe thử kho ${lib.name}`;
    }
    setHTML($("#ro-tl"), `<b>MASH ∞ LOOP</b> // ${p.settings.mode === "chain" ? "chuỗi" : "một bài"} · chưa phát`);
    setHTML($("#ro-tr"), `<span class="mono">∞ 0:00</span><span class="ro-stats"> · chưa có vòng nào</span>`);
    setHTML($("#next-info"), "");
    return;
  }
  cta.hidden = true;
  cta.disabled = false;
  // The mix as heard (the stage holds it until its end reaches the speakers).
  const held = viz.mixNow;
  const b = held?.blend ? held.m : null;
  const fx = held && !held.blend ? held.m : null;
  const blending = b && view.now >= b.times[0];
  setHTML($("#rc-kicker"), blending ? "ĐANG BLEND" : p.settings.mode === "chain" ? "ĐANG PHÁT · CHUỖI" : "ĐANG PHÁT · LẶP MÃI");
  // Past the middle of a blend the caption has moved into the next loop.
  const shown = viz.captionTrack?.analysis ? viz.captionTrack : T;
  const sa = shown.analysis;
  const song = songOf(shown.meta);
  setHTML($("#rc-title"), esc(song.title || shown.id));
  setHTML($("#rc-meta"), `${song.artist ? `<span class="rc-artist">${esc(song.artist)}</span>` : ""}<span class="mono">${sa.bpm.toFixed(0)} BPM · ${esc(sa.camelot)} · ${esc(sa.key)}</span>`);
  const crit = p.settings.mode === "chain" && CRIT_TAG[p.settings.criterion] ? ` · ${CRIT_TAG[p.settings.criterion]}` : "";
  const inLib = libByKey(libOf(shown.id));
  setHTML($("#ro-tl"), `<b>${p.settings.mode === "chain" ? "CHUỖI" : "LẶP"}${crit}</b> // ${inLib ? `${esc(inLib.name)} · ` : ""}${esc(short(song.artist || shown.meta.title || "", 34))}`);
  const listened = Math.max(0, view.now - p.stats.startedAt);
  const camelotBadge = sa.camelot ? `<span class="badge-camelot" title="Tông ${esc(sa.key)}">${esc(sa.camelot)}</span> · ` : "";
  const bpmText = sa.bpm ? `${sa.bpm.toFixed(0)} BPM · ` : "";
  setHTML($("#ro-tr"), `<span class="mono">∞ ${fmt(listened)}</span><span class="ro-stats"> · ${camelotBadge}${bpmText}${p.stats.jumps} nhảy · ${p.stats.transitions} chuyển</span>`);

  const now = view.now;
  const name = (id) => esc(short(titleOf(id), 46));
  let next;
  if (blending) {
    const k = Math.min(1, (now - b.times[0]) / (b.times[b.L] - b.times[0]));
    const note = bendNote(b.tr);
    next = `Đang ${kindOf(b.tr)} sang <strong>${name(b.B.id)}</strong> · <span class="eta">${Math.round(k * 100)}%</span>${note ? ` · ${note}` : ""}`;
  } else if (fx) {
    next = `Đang ${KIND[fx.tr.type]} sang <strong>${name(fx.B.id)}</strong>`;
  } else if (p.plan) {
    const eta = Math.max(0, p.plan.eta - now);
    const note = bendNote(p.plan.tr);
    next = `${p.plan.picked ? "Bạn đã chọn: " : "Sắp "}${kindOf(p.plan.tr)} sang <strong>${name(p.plan.tr.to)}</strong> · <span class="eta">${fmt(eta)}</span>` +
      ` · khớp ${Math.round(p.plan.tr.q * 100)}%${criterionNote(T, p.plan.tr)}${note ? ` · ${note}` : ""}${p.plan.target ? "" : " · đang tải"}`;
  } else if (p.settings.mode === "chain") {
    const left = p.dwellStart + p.settings.dwellMin - now;
    next = left > 0
      ? `Có thể chuyển bài sau <span class="eta">${fmt(left)}</span>, ở điểm nối tốt gần nhất`
      : `Đang chờ điểm nối tốt gần nhất…`;
  } else {
    next = "Lặp mãi bài này. Chạm lên vòng để phát từ đoạn đó, chạm một chấm ngoài vòng để chuyển bài.";
  }
  setHTML($("#next-info"), next);
}

// Setlist: the session as a chain of linked loops, each in its song's colour.
const setlistEl = $("#history");
function renderSetlist() {
  const hist = player.history.filter((h) => h.at <= engine.audibleTime()).slice(-11);
  const col = (id) => theme.css(theme.songColor(id));
  const html = hist.slice(-10).map((h, k, list) => {
    const prev = k ? list[k - 1] : hist.length > list.length ? hist[0] : null;
    return `<li data-via="${h.via}" style="--hue:${col(h.id)}${prev ? `;--from:${col(prev.id)}` : ""}"><span class="loop" aria-hidden="true"></span><span>${esc(short(titleOf(h.id), 30))}</span><span class="sr">, vào bằng ${h.via === "start" ? "bắt đầu" : KIND[h.via] || h.via}</span></li>`;
  }).join("");
  const ol = setlistEl;
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
  const list = T ? T.transitions.filter((tr) => player.canTake(T, tr)).sort((x, y) => y.q - x.q).slice(0, 8) : [];
  exits.querySelector("ul").innerHTML = list.map((tr, k) =>
    `<li><button type="button" data-k="${k}">${kindCap(tr)} → ${esc(short(titleOf(tr.to), 32))} <span class="mono">${Math.round(tr.q * 100)}%</span></button></li>`).join("");
  exits.hidden = !list.length;
  exits._list = list;
}
exits.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-k]");
  if (!btn) return;
  const ok = player.planTransition(exits._list[+btn.dataset.k]);
  btn.classList.toggle("is-bad", !ok);
  btn.title = ok ? "" : PICK_ERROR[player.pickError] || PICK_ERROR.gone;
});
const PICK_ERROR = {
  busy: "Đang chuyển sang bài khác: chọn lại khi bài sau đã vào hẳn",
  unreachable: "Từ chỗ đang phát không có đường tới điểm này",
  soon: "Điểm này tới quá sát: chọn điểm xa hơn một chút",
  gone: "Điểm này không còn dùng được",
};

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

// Cookie management
async function refreshCookieStatus() {
  const badge = $("#cookie-badge");
  const statusText = $("#cookie-status-text");
  const desc = $("#cookie-desc");
  const delBtn = $("#btn-del-cookie");
  if (!badge || !statusText) return;
  try {
    const res = await api.cookieStatus();
    if (res.has_cookies) {
      badge.classList.add("active");
      const doms = (res.domains || []).join(", ");
      statusText.textContent = `Sẵn sàng (${res.count})`;
      if (desc) desc.textContent = doms || "Đã nạp";
      if (delBtn) delBtn.hidden = false;
    } else {
      badge.classList.remove("active");
      statusText.textContent = "Chưa có";
      if (desc) desc.textContent = "Bypass bot check";
      if (delBtn) delBtn.hidden = true;
    }
  } catch (_) {
    statusText.textContent = "Chưa có";
  }
}

function initCookieManagement() {
  const fileInput = $("#cookie-file-input");
  const uploadBtn = $("#btn-upload-cookie");
  const pasteBtn = $("#btn-paste-cookie");
  const delBtn = $("#btn-del-cookie");
  const modal = $("#cookie-modal");
  const modalClose = $("#cookie-modal-close");
  const cancelBtn = $("#btn-cancel-cookie");
  const saveBtn = $("#btn-save-cookie");
  const textarea = $("#cookie-paste-textarea");

  uploadBtn?.addEventListener("click", () => fileInput?.click());

  fileInput?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const res = await api.uploadCookies(text);
      await refreshCookieStatus();
      await showModal({
        title: "Đã nạp cookie",
        message: res.message || "Đã lưu cookie thành công!",
        confirmText: "Đã hiểu",
      });
    } catch (err) {
      await showModal({
        title: "Lỗi nạp cookie",
        message: err.message || "File cookie không đúng định dạng Netscape hoặc JSON.",
        confirmText: "Đã hiểu",
      });
    } finally {
      fileInput.value = "";
    }
  });

  pasteBtn?.addEventListener("click", () => {
    if (!modal) return;
    if (textarea) textarea.value = "";
    modal.showModal();
  });

  modalClose?.addEventListener("click", () => modal?.close());
  cancelBtn?.addEventListener("click", () => modal?.close());

  saveBtn?.addEventListener("click", async () => {
    const text = textarea?.value?.trim();
    if (!text) {
      modal?.close();
      return;
    }
    saveBtn.disabled = true;
    try {
      const res = await api.uploadCookies(text);
      modal?.close();
      await refreshCookieStatus();
      await showModal({
        title: "Đã lưu cookie",
        message: res.message || "Đã lưu cookie thành công!",
        confirmText: "Đã hiểu",
      });
    } catch (err) {
      await showModal({
        title: "Lỗi lưu cookie",
        message: err.message || "Nội dung cookie không hợp lệ.",
        confirmText: "Đã hiểu",
      });
    } finally {
      saveBtn.disabled = false;
    }
  });

  delBtn?.addEventListener("click", async () => {
    const ok = await showModal({
      title: "Xóa cookie",
      message: "Bạn có chắc chắn muốn xóa toàn bộ cookies đã lưu?",
      confirmText: "Xóa",
      cancelText: "Thôi",
      danger: true,
    });
    if (ok) {
      await api.deleteCookies().catch(() => {});
      await refreshCookieStatus();
    }
  });

  refreshCookieStatus();
}

loadPlaylists();
checkUrlPlaylistImport();
applySettings();
if (ui.activeTab && ui.activeTab !== "library") {
  for (const x of document.querySelectorAll(".tabs button")) {
    const isTarget = x.dataset.tab === ui.activeTab;
    x.classList.toggle("on", isTarget);
    x.setAttribute("aria-selected", isTarget);
  }
  for (const t of document.querySelectorAll(".tab")) {
    t.classList.toggle("on", t.id === `tab-${ui.activeTab}`);
  }
}
initCookieManagement();
renderLooks();
renderTransport();
renderStage();
placeIndicators();
ready().then(async () => {
  if (session.multiuser) {
    // Hosted: a library per visit; pairs are linked automatically and shared.
    $("#add-hint").textContent = "Mỗi lần mở trang là một thư viện mới. Bài ai đó đã thêm trước sẽ vào ngay, không phải chờ phân tích.";
    const groupRelink = $("#group-relink") || $("#btn-relink")?.closest(".group");
    if (groupRelink) groupRelink.hidden = true;
    $("#fine").hidden = false;
    for (const el of document.querySelectorAll("[data-ttl]")) el.textContent = session.limits.audio_ttl_h || 12;

    const plIds = [...new Set(playlists.flatMap((p) => p.trackIds || []))].filter(Boolean);
    if (plIds.length && !metas.length) {
      await api.restore(plIds).catch(() => {});
      await refresh();
    }
  }
  if (session.limits.upload_mb) $("#upload-limit").textContent = `, tối đa ${session.limits.upload_mb} MB`;
  renderLibrary();
  api.samples().then((s) => {
    samples.libraries = s.libraries || [];
    samples.ids = [...new Set(samples.libraries.flatMap((l) => l.ids))];
    lastListHtml = "";
    renderLibrary();
    renderStage(); // the empty stage can offer one of them now
  }, () => {});
}).catch(() => {});
refresh().then(schedulePoll);

// Handle for the browser console and the end-to-end test.
window.loopbox = { player, engine, loader, play, refresh, applySettings, ui, viz, session };
