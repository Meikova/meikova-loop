/**
 * Media Session API integration for MashLoop
 * Connects standard OS lock screen, bluetooth controls, and hardware media keys to Player
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
    artwork.push({ src: "/img/og.png", sizes: "1200x630", type: "image/png" });

    navigator.mediaSession.metadata = new MediaMetadata({
      title,
      artist,
      album: "Mash ∞ Loop",
      artwork,
    });
  }

  function updatePlaybackState() {
    navigator.mediaSession.playbackState = player.playing ? "playing" : "paused";
  }

  // Hook into Player events
  player.addEventListener("track", () => {
    updateMetadata();
    updatePlaybackState();
  });

  player.addEventListener("state", () => {
    updatePlaybackState();
  });

  // Action handlers
  const safeSetHandler = (action, handler) => {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch (_) {
      /* Action not supported in this browser version */
    }
  };

  safeSetHandler("play", () => {
    if (!player.playing) player.play();
  });

  safeSetHandler("pause", () => {
    if (player.playing) player.pause();
  });

  safeSetHandler("nexttrack", () => {
    player.requestNextSong();
  });

  safeSetHandler("previoustrack", () => {
    player.requestJump();
  });
}
