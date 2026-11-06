/**
 * Live Mix Audio Recorder for Meikova Loop.
 * Records the master audio output in real-time, tracking track transitions,
 * generating formatted chapter markers, and exporting high-quality audio files.
 */

export class MixRecorder {
  constructor(engine, player = null) {
    this.engine = engine;
    this.player = player;
    this.mediaRecorder = null;
    this.chunks = [];
    this.startTime = 0;
    this.chapters = [];
    this.timerInterval = null;
    this.onTick = null; // callback(elapsedSeconds)
    this.state = "inactive"; // "inactive" | "recording" | "paused"
    this._destNode = null;
    this._onTrackChange = null;
  }

  get isRecording() {
    return this.state === "recording";
  }

  get elapsedSeconds() {
    if (!this.startTime) return 0;
    return Math.max(0, Math.floor((Date.now() - this.startTime) / 1000));
  }

  getDuration() {
    return this.elapsedSeconds;
  }

  static formatTime(s) {
    const sec = Math.floor(s % 60);
    const m = Math.floor((s / 60) % 60);
    const h = Math.floor(s / 3600);
    if (h > 0) {
      return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    }
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }

  /**
   * Start recording the audio stream from engine.master / analyser.
   */
  start() {
    if (this.isRecording) return true;
    const ctx = this.engine?.ctx;
    if (!ctx) return false;

    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }

    try {
      if (!this._destNode) {
        this._destNode = ctx.createMediaStreamDestination();
        // Tap directly from analyser to capture full EQ, master gain, and limiter processing
        if (this.engine.analyser) {
          this.engine.analyser.connect(this._destNode);
        } else if (this.engine.master) {
          this.engine.master.connect(this._destNode);
        }
      }

      const stream = this._destNode.stream;
      const mimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/mp4",
        "",
      ];

      let selectedMime = "";
      for (const mime of mimeTypes) {
        if (!mime || (window.MediaRecorder && MediaRecorder.isTypeSupported(mime))) {
          selectedMime = mime;
          break;
        }
      }

      this.mediaRecorder = selectedMime
        ? new MediaRecorder(stream, { mimeType: selectedMime, audioBitsPerSecond: 256000 })
        : new MediaRecorder(stream);
    } catch (e) {
      console.warn("MediaRecorder creation error:", e);
      try {
        this.mediaRecorder = new MediaRecorder(this._destNode.stream);
      } catch (err) {
        console.error("MediaRecorder unsupported:", err);
        return false;
      }
    }

    this.chunks = [];
    this.chapters = [];
    this.startTime = Date.now();
    this.state = "recording";

    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        this.chunks.push(e.data);
      }
    };

    // Record initial track if playing
    this._recordCurrentTrack("Bắt đầu");

    // Listen to track changes if player is available
    if (this.player) {
      this._onTrackChange = () => {
        if (this.isRecording) {
          this._recordCurrentTrack("Chuyển bài");
        }
      };
      this.player.addEventListener("track", this._onTrackChange);
    }

    // Timer tick callback
    if (this.timerInterval) clearInterval(this.timerInterval);
    this.timerInterval = setInterval(() => {
      if (this.isRecording && this.onTick) {
        this.onTick(this.elapsedSeconds);
      }
    }, 1000);

    this.mediaRecorder.start(1000);
    return true;
  }

  addTrackMarker(title = "Bài hát", bpm = null, camelot = null, artist = null) {
    if (!this.isRecording) return;
    const elapsed = this.elapsedSeconds;
    const last = this.chapters[this.chapters.length - 1];
    if (last && last.title === title && elapsed - last.seconds < 4) return;

    this.chapters.push({
      title: title || "Bài hát",
      artist: artist || "",
      bpm: bpm ? Math.round(bpm) : null,
      camelot: camelot || "",
      seconds: elapsed,
      timestamp: MixRecorder.formatTime(elapsed),
      via: "Marker",
    });
  }

  _recordCurrentTrack(via = "Bắt đầu") {
    if (!this.player) return;
    const cur = this.player.cur?.track;
    if (!cur) return;
    const meta = cur.meta || {};
    const title = meta.title || cur.id || "Bài hát";
    const artist = meta.artist || meta.channel || "Nhiều nghệ sĩ";
    const bpm = Math.round(cur.bpm || meta.bpm || 0);
    const camelot = cur.camelot || meta.camelot || "";
    const elapsed = this.elapsedSeconds;

    // Check if this track is already the most recent chapter
    const last = this.chapters[this.chapters.length - 1];
    if (last && last.id === cur.id && elapsed - last.seconds < 5) return;

    this.chapters.push({
      id: cur.id,
      title,
      artist,
      bpm,
      camelot,
      seconds: elapsed,
      timestamp: MixRecorder.formatTime(elapsed),
      via,
    });
  }

  /**
   * Stop recording and return result object with audio blob and tracklist.
   */
  async stop() {
    if (!this.isRecording || !this.mediaRecorder) {
      return null;
    }

    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }

    if (this._onTrackChange && this.player) {
      this.player.removeEventListener("track", this._onTrackChange);
      this._onTrackChange = null;
    }

    return new Promise((resolve) => {
      this.mediaRecorder.onstop = () => {
        const mime = this.mediaRecorder.mimeType || "audio/webm";
        const blob = new Blob(this.chunks, { type: mime });
        const ext = mime.includes("mp4") ? "mp4" : mime.includes("ogg") ? "ogg" : "webm";
        const url = URL.createObjectURL(blob);
        const durationSec = this.elapsedSeconds;
        const durationStr = MixRecorder.formatTime(durationSec);
        const now = new Date();
        const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}`;
        const baseName = `MeikovaLoop_Mix_${dateStr}`;

        // Build Tracklist text
        const tracklist = this.generateTracklist(durationStr);

        this.state = "inactive";
        this.chunks = [];

        resolve({
          blob,
          url,
          audioUrl: url,
          mime,
          extension: ext,
          size: blob.size,
          fileName: `${baseName}.${ext}`,
          tracklistFileName: `${baseName}_tracklist.txt`,
          duration: durationSec,
          durationSeconds: durationSec,
          durationFormatted: durationStr,
          trackCount: this.chapters.length,
          chapters: [...this.chapters],
          tracklist,
          tracklistText: tracklist,
        });
      };

      this.mediaRecorder.stop();
    });
  }

  /**
   * Generate human-readable tracklist text.
   */
  generateTracklist(totalDuration) {
    const lines = [
      "===========================================================",
      "  MEIKOVA LOOP // LIVE DJ SET TRACKLIST",
      "===========================================================",
      `Ngày thu: ${new Date().toLocaleString("vi-VN")}`,
      `Tổng thời lượng: ${totalDuration}`,
      `Số bài mix: ${this.chapters.length}`,
      "",
      "DANH SÁCH BÀI HÁT THEO MỐC THỜI GIAN (CHAPTER TIMESTAMPS):",
      "-----------------------------------------------------------",
    ];

    this.chapters.forEach((ch, idx) => {
      const num = String(idx + 1).padStart(2, "0");
      const keyInfo = ch.camelot ? ` · ${ch.camelot}` : "";
      const bpmInfo = ch.bpm ? ` (${ch.bpm} BPM${keyInfo})` : "";
      const viaInfo = idx > 0 && ch.via ? ` // [${ch.via}]` : "";
      const artistInfo = ch.artist ? ` — ${ch.artist}` : "";
      lines.push(`${num}. [${ch.timestamp}] ${ch.title}${artistInfo}${bpmInfo}${viaInfo}`);
    });

    lines.push("");
    lines.push("-----------------------------------------------------------");
    lines.push("Thu âm trực tiếp bởi Meikova Loop — Infinite Soundscape");
    lines.push("https://meikova.dev/loop/");
    return lines.join("\n");
  }

  downloadTracklist(durationStr = null) {
    const text = this.generateTracklist(durationStr || MixRecorder.formatTime(this.elapsedSeconds));
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const dateStr = new Date().toISOString().slice(0, 10);
    a.href = url;
    a.download = `MeikovaLoop-LiveMix-Tracklist-${dateStr}.txt`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 1000);
  }
}
