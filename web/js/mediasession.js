/**
 * Media Session API integration for Meikova Loop.
 * Connects standard OS lock screen, bluetooth controls, Dynamic Island, and hardware media keys to Player.
 */

export function setupMediaSession(player, engine, getSongMeta) {
  if (!("mediaSession" in navigator)) return;

  function updateMetadata() {
    const track = player.cur?.track;
    if (!track) {
      navigator.mediaSession.metadata = null;
      return;
    }
    const meta = getSongMeta ? getSongMeta(track.id) : track.meta;
    const title = meta?.title || track.meta?.title || "Meikova Loop";
    const artist = meta?.artist || track.meta?.channel || "Meikova Loop";
    const artwork = [];

    const thumb = meta?.thumbnail || track.meta?.thumbnail;
    if (thumb) {
      artwork.push({ src: thumb, sizes: "512x512", type: "image/jpeg" });
      artwork.push({ src: thumb, sizes: "256x256", type: "image/jpeg" });
    }
    artwork.push({ src: "/img/icon-512.png", sizes: "512x512", type: "image/png" });
    artwork.push({ src: "/img/icon-192.png", sizes: "192x192", type: "image/png" });
    artwork.push({ src: "/img/apple-touch-icon.png", sizes: "180x180", type: "image/png" });
    artwork.push({ src: "/img/og.png", sizes: "1200x630", type: "image/png" });

    navigator.mediaSession.metadata = new MediaMetadata({
      title,
      artist,
      album: "Meikova Loop",
      artwork,
    });

    const dtNow = document.getElementById("dt-nowplaying");
    if (dtNow) dtNow.textContent = track ? `// ${title}` : "";
  }

  function updatePlaybackState() {
    navigator.mediaSession.playbackState = (player.cur && !player.userPaused && player.playing) ? "playing" : "paused";
  }

  function updatePositionState() {
    if (!("setPositionState" in navigator.mediaSession)) return;
    try {
      const track = player.cur?.track;
      if (!track) return;
      const duration = track.duration || (track.beats?.length ? track.beats[track.beats.length - 1] : 180);
      const beat = player.cur.beat || 0;
      const pos = Math.min(duration, Math.max(0, track.beats?.[beat] || 0));
      navigator.mediaSession.setPositionState({
        duration: Math.max(1, duration),
        playbackRate: Math.max(0.25, Math.min(4, player.cur?.rate || 1)),
        position: Math.min(pos, Math.max(1, duration)),
      });
    } catch (_) {}
  }

  // Hook into Player events
  player.addEventListener("track", () => {
    updateMetadata();
    updatePlaybackState();
    updatePositionState();
  });

  player.addEventListener("state", () => {
    updatePlaybackState();
    updatePositionState();
  });

  player.addEventListener("expired", () => {
    try {
      navigator.mediaSession.playbackState = "none";
      navigator.mediaSession.metadata = null;
    } catch (_) {}
  });

  // Action handlers
  const safeSetHandler = (action, handler) => {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch (_) {
      /* Action not supported in this browser version */
    }
  };

  safeSetHandler("play", async () => {
    navigator.mediaSession.playbackState = "playing";
    if (player.cur) {
      await player.play();
    } else {
      const first = player.loader?.metas ? [...player.loader.metas.values()].find((m) => m.status === "ready" && m.enabled !== false) : null;
      if (first) await player.start(first.id);
    }
    updatePlaybackState();
    updatePositionState();
  });

  safeSetHandler("pause", async () => {
    navigator.mediaSession.playbackState = "paused";
    if (player.cur) {
      await player.pause();
    }
    updatePlaybackState();
    updatePositionState();
  });

  safeSetHandler("stop", () => {
    try {
      navigator.mediaSession.playbackState = "none";
      navigator.mediaSession.metadata = null;
    } catch (_) {}
    player.stop();
  });

  safeSetHandler("nexttrack", async () => {
    if (!player.cur) return;
    if (player.skipToNext) {
      const ok = await player.skipToNext();
      if (!ok && player.forceTransition) {
        player.forceTransition();
      }
    } else if (player.forceTransition) {
      player.forceTransition();
    } else {
      player.requestNextSong();
    }
    updateMetadata();
    updatePlaybackState();
    updatePositionState();
  });

  safeSetHandler("previoustrack", async () => {
    if (!player.cur) return;
    const curBeat = player.cur.beat || 0;
    // If more than 4 bars into track (beat > 16), restart current track from beginning
    if (curBeat > 16) {
      player.seek(0);
      updatePositionState();
      return;
    }
    // If near start and session history has previous songs, return to previous song
    if (player.history && player.history.length >= 2) {
      const prev = player.history[player.history.length - 2];
      if (prev && prev.id && prev.id !== player.cur.track.id) {
        await player.start(prev.id);
        return;
      }
    }
    // Fallback: seek to beginning
    player.seek(0);
    updatePositionState();
  });

  safeSetHandler("seekto", (details) => {
    if (details.seekTime != null && player.cur?.track) {
      const track = player.cur.track;
      let bestBeat = 0;
      let bestDiff = Infinity;
      const beats = track.beats || [];
      for (let i = 0; i < beats.length; i++) {
        const diff = Math.abs(beats[i] - details.seekTime);
        if (diff < bestDiff) {
          bestDiff = diff;
          bestBeat = i;
        }
      }
      player.seek(bestBeat);
      if (player.userPaused && player.cur) player.cur.beat = bestBeat;
      updatePositionState();
    }
  });

  safeSetHandler("seekforward", (details) => {
    const step = details.seekOffset || 10;
    if (player.cur?.track) {
      const track = player.cur.track;
      const curTime = track.beats?.[player.cur.beat] || 0;
      const targetTime = curTime + step;
      let bestBeat = player.cur.beat;
      let bestDiff = Infinity;
      const beats = track.beats || [];
      for (let i = 0; i < beats.length; i++) {
        const diff = Math.abs(beats[i] - targetTime);
        if (diff < bestDiff) {
          bestDiff = diff;
          bestBeat = i;
        }
      }
      player.seek(bestBeat);
      if (player.userPaused && player.cur) player.cur.beat = bestBeat;
      updatePositionState();
    }
  });

  safeSetHandler("seekbackward", (details) => {
    const step = details.seekOffset || 10;
    if (player.cur?.track) {
      const track = player.cur.track;
      const curTime = track.beats?.[player.cur.beat] || 0;
      const targetTime = Math.max(0, curTime - step);
      let bestBeat = 0;
      let bestDiff = Infinity;
      const beats = track.beats || [];
      for (let i = 0; i < beats.length; i++) {
        const diff = Math.abs(beats[i] - targetTime);
        if (diff < bestDiff) {
          bestDiff = diff;
          bestBeat = i;
        }
      }
      player.seek(bestBeat);
      if (player.userPaused && player.cur) player.cur.beat = bestBeat;
      updatePositionState();
    }
  });

  if (player.cur) {
    updateMetadata();
    updatePlaybackState();
    updatePositionState();
  }

  // Keep position synchronized on lock screen periodically while playing
  setInterval(() => {
    if (player.playing) {
      updatePositionState();
    }
  }, 2500);
}
