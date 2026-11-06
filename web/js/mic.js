/**
 * Live Karaoke Microphone Input Engine for Meikova Loop.
 * Streams real-time microphone input into the Web Audio master graph
 * with ultra-low latency monitoring, low-cut filtering, and anti-clipping limiter.
 */

export class KaraokeMic {
  constructor(engine) {
    this.engine = engine;
    this.stream = null;
    this.source = null;
    this.filterNode = null;
    this.gainNode = null;
    this.volume = 1.0;
    this.isActive = false;
    this.onStateChange = null; // callback(isActive)
  }

  async start() {
    if (this.isActive) return true;
    const ctx = this.engine?.ctx;
    if (!ctx) return false;

    if (ctx.state === "suspended") {
      await ctx.resume().catch(() => {});
    }

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("Trình duyệt không hỗ trợ truy cập Micro.");
      }

      try {
        this.stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      } catch (firstErr) {
        // Fallback to basic audio constraint in case audio device rejects DSP options
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }

      this.source = ctx.createMediaStreamSource(this.stream);

      // Low-cut (High-pass 85Hz) filter to strip out air pops and handling thumps
      this.filterNode = ctx.createBiquadFilter();
      this.filterNode.type = "highpass";
      this.filterNode.frequency.value = 85;
      this.filterNode.Q.value = 0.7;

      // Microphone volume gain control
      this.gainNode = ctx.createGain();
      this.gainNode.gain.value = this.volume;

      // Connect source -> filter -> gain -> engine.master
      // engine.master feeds into limiter, equalizer, analyser and ctx.destination (speakers)
      // and simultaneously taps into MixRecorder._destNode!
      this.source.connect(this.filterNode);
      this.filterNode.connect(this.gainNode);
      this.gainNode.connect(this.engine.master);

      this.isActive = true;
      if (this.onStateChange) this.onStateChange(true);
      return true;
    } catch (err) {
      this.stop();
      throw err;
    }
  }

  stop() {
    this.isActive = false;
    if (this.stream) {
      try {
        this.stream.getTracks().forEach((track) => track.stop());
      } catch (_) {}
      this.stream = null;
    }
    if (this.source) {
      try { this.source.disconnect(); } catch (_) {}
      this.source = null;
    }
    if (this.filterNode) {
      try { this.filterNode.disconnect(); } catch (_) {}
      this.filterNode = null;
    }
    if (this.gainNode) {
      try { this.gainNode.disconnect(); } catch (_) {}
      this.gainNode = null;
    }
    if (this.onStateChange) this.onStateChange(false);
  }

  toggle() {
    if (this.isActive) {
      this.stop();
      return Promise.resolve(false);
    }
    return this.start();
  }

  setVolume(vol) {
    this.volume = Math.max(0, Math.min(2.0, vol));
    if (this.gainNode && this.engine?.ctx) {
      this.gainNode.gain.setTargetAtTime(this.volume, this.engine.ctx.currentTime, 0.02);
    }
  }
}
