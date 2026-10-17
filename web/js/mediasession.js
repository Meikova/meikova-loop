/**
 * Media Session API integration for MashLoop.
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
    const title = meta?.title || track.meta?.title || "Mash ∞ Loop";
    const artist = meta?.artist || track.meta?.channel || "MashLoop";
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
      album: "Mash ∞ Loop",
      artwork,
    });
  }

  function updatePlaybackState() {
    navigator.mediaSession.playbackState = (player.cur && !player.userPaused && player.playing) ? "playing" : "paused";
  }

  function updatePositionState() {
    if (!("setPositionState" in navigator.mediaSession)) return;
    try {
      const track = player.cur?.track;
      if (!track || !player.playing) return;
      const duration = track.duration || (track.beats?.length ? track.beats[track.beats.length - 1] : 180);
      const beat = player.cur.beat || 0;
      const pos = Math.min(duration, Math.max(0, track.beats?.[beat] || 0));
      navigator.mediaSession.setPositionState({
        duration: Math.max(1, duration),
        playbackRate: Math.max(0.25, Math.min(4, player.cur.rate || 1)),
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
    await player.play();
  });

  safeSetHandler("pause", async () => {
    navigator.mediaSession.playbackState = "paused";
    await player.pause();
  });

  safeSetHandler("stop", () => {
    navigator.mediaSession.playbackState = "paused";
    player.stop();
  });

  safeSetHandler("nexttrack", () => {
    player.requestNextSong();
  });

  safeSetHandler("previoustrack", () => {
    player.requestJump();
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
      updatePositionState();
    }
  });

  // Keep position synchronized on lock screen periodically while playing
  setInterval(() => {
    if (player.playing) {
      updatePositionState();
    }
  }, 2500);
}
