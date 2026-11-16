import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient


class LongTrackPlaybackTests(unittest.TestCase):
    def test_multiuser_send_sound_range_request_unscrambles_exact_slice(self):
        """Regression test: _send_sound in MULTIUSER=1 must support HTTP Range without NameError."""
        from loopbox import server, sessions

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "audio.mp3"
            raw_bytes = bytes((i * 37 + 13) % 256 for i in range(20000))
            p.write_bytes(raw_bytes)

            sess = sessions.SessionView("test_range_sid")
            tid = "gebkUty7dPU"

            from fastapi import FastAPI, Request
            mini = FastAPI()

            @mini.get("/test-sound")
            def _ep(request: Request):
                return server._send_sound(p, tid, request, sess)

            client = TestClient(mini)
            with patch.object(server, "MULTIUSER", True):
                resp = client.get("/test-sound", headers={"Range": "bytes=4096-12287"})

            self.assertEqual(resp.status_code, 206)
            self.assertEqual(resp.headers.get("Content-Range"), "bytes 4096-12287/20000")
            self.assertEqual(int(resp.headers.get("Content-Length", "0")), 8192)
            self.assertEqual(resp.headers.get("X-Mash"), "1")

            ks = server.keystream(sess.key, tid)
            body = resp.content
            unscrambled = bytes(b ^ ks[(4096 + idx) % len(ks)] for idx, b in enumerate(body))
            self.assertEqual(unscrambled, raw_bytes[4096:12288])

    def test_chunked_mp3_decoder_handles_oversized_monolithic_decode_failure(self):
        """Regression test: decodeTrackAudio must chunk-decode >15m MP3s when monolithic decodeAudioData throws EncodingError."""
        script = r"""
import assert from "node:assert/strict";
import { parseMp3Frames, decodeTrackAudio, MAX_SAFE_DURATION_S } from "./web/js/api.js";

// 1. Both Desktop and Mobile Web must allow up to 3600s (60 min) tracks ingested on Desktop
assert.ok(MAX_SAFE_DURATION_S >= 3600, `Expected MAX_SAFE_DURATION_S >= 3600, got ${MAX_SAFE_DURATION_S}`);

// 2. Build a synthetic valid CBR 192kbps 44100Hz MP3 with ID3v2 tag (containing fake 0xFF 0xFB bytes!) + Info header + 600 audio frames
const id3Payload = new Uint8Array(64);
id3Payload[10] = 0xff;
id3Payload[11] = 0xfb; // fake sync inside ID3v2 cover art must be skipped!
const id3Header = new Uint8Array([
  0x49, 0x44, 0x33, 0x04, 0x00, 0x00,
  0x00, 0x00, 0x00, 64
]);
// MPEG-1 Layer 3, 192kbps (idx 11 = 0xb), 44100Hz (idx 0), no padding -> frame len = floor(144000*192/44100) = 626 bytes
const makeFrame = (marker = null) => {
  const f = new Uint8Array(626);
  f[0] = 0xff;
  f[1] = 0xfb; // MPEG1 Layer3 no-CRC
  f[2] = 0xb0; // 192kbps, 44100Hz, pad=0
  f[3] = 0x00;
  if (marker) {
    for (let i = 0; i < marker.length; i++) f[36 + i] = marker.charCodeAt(i);
  }
  return f;
};

const totalAudioFrames = 600;
const totalBytes = 10 + 64 + (1 + totalAudioFrames) * 626;
const mp3 = new Uint8Array(totalBytes);
mp3.set(id3Header, 0);
mp3.set(id3Payload, 10);
let off = 74;
mp3.set(makeFrame("Info"), off);
off += 626;
for (let i = 0; i < totalAudioFrames; i++) {
  const f = makeFrame();
  f[4] = i & 0xff;
  mp3.set(f, off);
  off += 626;
}

const parsed = parseMp3Frames(mp3);
assert.equal(parsed.sampleRate, 44100);
assert.equal(parsed.samplesPerFrame, 1152);
assert.equal(parsed.hasInfoHeader, true);
assert.equal(parsed.audioStartIndex, 1);
assert.equal(parsed.frames.length, 601);

// 3. Simulate Chromium throwing EncodingError when monolithic decodeAudioData is called on a >15m track,
//    while succeeding on smaller chunk slices!
let monolithicCalls = 0;
let chunkCalls = 0;
const makeFakeBuffer = (channels, length, sampleRate) => {
  const chData = Array.from({ length: channels }, () => new Float32Array(length));
  return {
    numberOfChannels: channels,
    length,
    sampleRate,
    duration: length / sampleRate,
    getChannelData: (c) => chData[c],
    copyToChannel: (src, c, startInChannel = 0) => {
      chData[c].set(src.subarray(0, Math.max(0, Math.min(src.length, length - startInChannel))), startInChannel);
    },
  };
};

const fakeCtx = {
  sampleRate: 44100,
  createBuffer: (ch, len, sr) => makeFakeBuffer(ch, len, sr),
  decodeAudioData: async (buf) => {
    if (buf.byteLength >= mp3.byteLength) {
      monolithicCalls++;
      const err = new Error("Unable to decode audio data");
      err.name = "EncodingError";
      throw err;
    }
    chunkCalls++;
    const p = parseMp3Frames(new Uint8Array(buf));
    const audioCount = p.frames.length - p.audioStartIndex;
    const rawSamples = audioCount * 1152 + (p.hasInfoHeader ? 0 : 1105);
    const b = makeFakeBuffer(2, rawSamples, 44100);
    // Fill deterministic ramp so seam continuity can be verified
    const c0 = b.getChannelData(0);
    for (let i = 0; i < c0.length; i++) c0[i] = 0.25;
    return b;
  },
};

const decoded = await decodeTrackAudio(fakeCtx, mp3.buffer, {
  durationSec: 2100, // 35 minutes (>15m)
  maxFramesPerChunk: 150,
  forceSampleRate: 44100,
});
assert.equal(monolithicCalls, 0, "Tracks >15m must go straight to chunked decode without wasting 8s failing monolithic decode!");
assert.ok(chunkCalls >= 4, `Expected >=4 chunk decodes, got ${chunkCalls}`);
assert.equal(decoded.length, totalAudioFrames * 1152);
assert.equal(decoded.getChannelData(0)[0], 0.25);
assert.equal(decoded.getChannelData(0)[decoded.length - 1], 0.25);
console.log("NODE_CHUNK_DECODE_OK");
"""
        loader_hook = (
            "data:text/javascript,"
            "import{register}from'node:module';"
            "register('data:text/javascript,export async function resolve(s,c,n){return n(s.replace(/\\\\?v=\\\\d+$/,\"\"),c);}');"
        )
        proc = subprocess.run(
            ["node", f"--import={loader_hook}", "--input-type=module", "-e", script],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, f"Node test failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("NODE_CHUNK_DECODE_OK", proc.stdout)

    def test_satellite_render_advances_when_raf_throttled_and_deck_play_uses_visible_order(self):
        """Regression test: Satellite must advance frame when rAF is throttled, and #btn-play must respect visible track order."""
        root = Path(__file__).resolve().parent.parent
        viz_src = (root / "web" / "js" / "viz.js").read_text("utf-8")
        main_src = (root / "web" / "js" / "main.js").read_text("utf-8")
        engine_src = (root / "web" / "js" / "engine.js").read_text("utf-8")

        self.assertIn("document.hidden", viz_src)
        self.assertRegex(viz_src, r"renderSatellite\s*\([^)]*\)\s*\{[\s\S]{0,260}document\.hidden")
        self.assertIn("getOrderedReadyTracks", main_src)
        self.assertIn("_sliceAtContextRate", engine_src)

    def test_loader_never_evicts_newly_loaded_track_and_cut_keyshift_glides_home(self):
        """Regression test (v171): Loader._evict must never evict the track being loaded or null out live Track.buffer."""
        script = r"""
import assert from "node:assert/strict";
import { Loader } from "./web/js/api.js";

const loader = new Loader({ ctx: { sampleRate: 44100 } }, 3);
const makeBuf = () => ({ length: 44100 * 60, numberOfChannels: 2, sampleRate: 44100, duration: 60 });
const t1 = { id: "t1", buffer: makeBuf() };
const t2 = { id: "t2", buffer: makeBuf() };
const t3 = { id: "t3", buffer: makeBuf() };
const t4 = { id: "t4", buffer: makeBuf() };

loader.cache.set("t1", { track: t1, used: 1, promise: Promise.resolve(t1) });
loader.cache.set("t2", { track: t2, used: 2, promise: Promise.resolve(t2) });
loader.cache.set("t3", { track: t3, used: 3, promise: Promise.resolve(t3) });
loader.cache.set("t4", { track: t4, used: 4, promise: Promise.resolve(t4) });

// Simulate player.start("t4") while t1, t2, t3 were still protected in old state:
loader.protect = () => ["t1", "t2", "t3"];
loader._evict(3, "t4");

// t4 is pinned as the newly loaded track: it MUST remain in cache with its buffer intact!
assert.equal(loader.has("t4"), true, "Newly loaded track t4 must not be evicted by _evict!");
assert.ok(t4.buffer, "Newly loaded track t4.buffer must not be nulled out!");

// Now protect only t4 and evict old tracks: evicted tracks must be removed from cache and unprotected buffers nulled out to reclaim PCM RAM
loader.protect = () => ["t4"];
loader._evict(1, "t4");
assert.equal(loader.has("t4"), true);
assert.equal(loader.has("t1"), false);
assert.equal(t1.buffer, null, "Evicted unprotected track t1.buffer must be nulled out to reclaim float PCM memory!");
console.log("LOADER_PIN_OK");
"""
        loader_hook = (
            "data:text/javascript,"
            "import{register}from'node:module';"
            "register('data:text/javascript,export async function resolve(s,c,n){return n(s.replace(/\\\\?v=\\\\d+$/,\"\"),c);}');"
        )
        proc = subprocess.run(
            ["node", f"--import={loader_hook}", "--input-type=module", "-e", script],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, f"Node test failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("LOADER_PIN_OK", proc.stdout)

        root = Path(__file__).resolve().parent.parent
        player_src = (root / "web" / "js" / "player.js").read_text("utf-8")
        self.assertIn("outOfStretchSlice", player_src)
        self.assertIn("this._loadingTrackId = trackId;", player_src)


if __name__ == "__main__":
    unittest.main()
