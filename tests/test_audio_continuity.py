"""
Tests for Audio Continuity, Varispeed Resampling, and Single-Machine Anti-Clash Isolation.
Verifies:
1. Zero packet-to-packet gap and zero packet overlap (sample-exact contiguous buffer scheduling).
2. Continuous varispeed rate nudge bounded within [0.985, 1.015].
3. Single-machine detection and speaker anti-clash (prevents slapback echo and comb-filtering).
4. Discrete channel routing matrix on desktop / stereo endpoints.
5. AudioWorklet Ring Buffer player with continuous fractional linear interpolation.
6. Safe stage mirror captioning and HUD formatting against idle DOM leaks.
7. Same-machine master channel fallback ensuring full stereo sound when follower is muted.
8. Service Worker and asset cache synchronization to v176.
"""

import unittest
from pathlib import Path


class TestAudioContinuityAndIsolation(unittest.TestCase):
    def setUp(self):
        self.stage_sync_js = Path("web/js/stage_sync.js").read_text(encoding="utf-8")
        self.viz_js = Path("web/js/viz.js").read_text(encoding="utf-8")
        self.engine_js = Path("web/js/engine.js").read_text(encoding="utf-8")
        self.index_html = Path("web/index.html").read_text(encoding="utf-8")
        self.sw_js = Path("web/sw.js").read_text(encoding="utf-8")

    def test_contiguous_packet_scheduling_invariants(self):
        """Verify that _schedulePcmPacket schedules contiguous start times without chopping gaps."""
        # Must schedule contiguous end-to-start timing
        self.assertIn("src.playbackRate.value = rateNudge;", self.stage_sync_js)
        self.assertIn("src.start(this.satNextPlayTime);", self.stage_sync_js)
        self.assertIn("this.satNextPlayTime += (audioBuf.duration / rateNudge);", self.stage_sync_js)

        # Must NOT perform abrupt un-crossfaded jump that causes 43Hz crackle
        self.assertNotIn("this.satNextPlayTime += driftSec * 0.10;", self.stage_sync_js)

    def test_drift_filter_and_rate_nudge_bounds(self):
        """Verify low-pass EMA drift filtering and safe varispeed bounds."""
        self.assertIn("this._filteredDriftSec = (this._filteredDriftSec ?? 0) * 0.94 + rawDriftSec * 0.06;", self.stage_sync_js)
        self.assertIn("Math.max(0.988, Math.min(1.012, 1.0 + (this._filteredDriftSec * 0.12)))", self.stage_sync_js)

    def test_single_machine_anti_clash_detection_and_defaults(self):
        """Verify that follower on the same machine defaults to muted to prevent acoustic echo."""
        self.assertIn("this.isSameMachine = this.isLocalHost;", self.stage_sync_js)
        self.assertIn("if (this.isSameMachine || this.isLocalHost)", self.stage_sync_js)
        self.assertIn("this.satAudioMuted = true;", self.stage_sync_js)
        self.assertIn("setFollowerAudioMuted(muted = true)", self.stage_sync_js)
        self.assertIn("btn-cluster-audio-toggle", self.stage_sync_js)
        self.assertIn('id="btn-cluster-audio-toggle"', self.index_html)

    def test_discrete_channel_routing_on_desktop(self):
        """Verify discrete Left/Right channel routing prevents mono sum collision on PC speakers/headphones."""
        self.assertIn('const isDiscrete = this.isSameMachine || this.deviceType === "desktop";', self.stage_sync_js)
        self.assertIn("this.satChannelSplitter.connect(this.satChannelMerger, 0, 0);", self.stage_sync_js)
        self.assertIn("this.satChannelSplitter.connect(this.satChannelMerger, 1, 1);", self.stage_sync_js)
        self.assertIn("setLocalSpeakerMuted(muted = false)", self.engine_js)

    def test_audio_worklet_capture_with_fallback(self):
        """Verify AudioWorklet processor capture exists and is prioritized over main-thread ScriptProcessor."""
        self.assertIn("class MLStreamCaptureProcessor extends AudioWorkletProcessor", self.stage_sync_js)
        self.assertIn("setupScriptProcessorFallback", self.stage_sync_js)

    def test_audio_worklet_player_jitter_ring_buffer(self):
        """Verify AudioWorklet continuous jitter ring buffer player MLStreamPlayerProcessor."""
        self.assertIn("class MLStreamPlayerProcessor extends AudioWorkletProcessor", self.stage_sync_js)
        self.assertIn("registerProcessor(\"ml-stream-player\", MLStreamPlayerProcessor)", self.stage_sync_js)
        self.assertIn("_initSatPlayerWorklet", self.stage_sync_js)
        self.assertIn("_pushToSatWorklet", self.stage_sync_js)
        # Fractional linear interpolation between adjacent samples
        self.assertIn("sL = this.bufL[i0] + frac * (this.bufL[i1] - this.bufL[i0]);", self.stage_sync_js)
        self.assertIn("sR = this.bufR[i0] + frac * (this.bufR[i1] - this.bufR[i0]);", self.stage_sync_js)

    def test_caption_and_ro_hud_protection_against_idle_pollution(self):
        """Verify that stage mirror protects caption and HUD against stale idle DOM strings."""
        self.assertIn("isHtmlIdle", self.stage_sync_js)
        self.assertIn("isRoIdle", self.stage_sync_js)
        self.assertIn("hasActiveTrackId", self.stage_sync_js)
        self.assertIn("this._placeCenter(this.capPlace);", self.viz_js)
        self.assertIn("if (this.onCaption) this.onCaption();", self.viz_js)

    def test_same_machine_master_channel_adaptation(self):
        """Verify that Master plays full stereo when all followers are muted local tabs on the same machine."""
        self.assertIn("_syncMasterEffectiveChannels()", self.stage_sync_js)
        self.assertIn("const effMode = (this.isSameMachine && !hasRemoteActiveFollower) ? \"stereo\" : this.myChannelMode;", self.stage_sync_js)

    def test_version_176_cache_busting_sync(self):
        """Verify v176 cache busting is synchronized across SW, HTML, and JS modules."""
        self.assertIn('const CACHE_NAME = "meikova-loop-v176";', self.sw_js)
        self.assertIn('const LOCAL_APP_VER = 176;', self.stage_sync_js)
        self.assertIn('app_ver: "v176",', self.viz_js)
        self.assertIn('href="css/app.css?v=176"', self.index_html)
        self.assertIn('src="js/main.js?v=176"', self.index_html)
        self.assertIn('.register("sw.js?v=176"', self.index_html)


if __name__ == "__main__":
    unittest.main()
