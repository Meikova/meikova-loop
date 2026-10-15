"""Full analysis of one track: audio.flac -> analysis.json + features.npz."""
import time
from typing import Callable

import numpy as np

from .. import audio, library
from ..config import ANALYSIS_SR, ANALYSIS_VERSION, SAMPLE_RATE, TARGET_LUFS
from . import beats as beatmod
from . import features as featmod
from . import jumps as jumpmod
from . import models, similarity, structure
from .beats import HR_HOP


def analyze(tid: str, on_stage: Callable[[str, float], None] = lambda s, p: None) -> dict:
    t0 = time.time()
    path = library.audio_path(tid)
    meta = library.read_meta(tid) or {}

    on_stage("loading", 0.02)
    y = audio.load(path)
    duration = len(y) / SAMPLE_RATE
    lufs = audio.integrated_loudness(path)
    gain_db = float(np.clip(TARGET_LUFS - lufs, -12.0, 6.0))

    on_stage("beats", 0.1)
    raw_beats, downbeats = beatmod.track(y)
    if len(raw_beats) < 32:
        raise RuntimeError("too few beats detected: not a rhythmic track?")
    y22 = featmod.mono22(y)
    env = featmod.onset_hr(y22)
    env_rate = ANALYSIS_SR / HR_HOP
    beats = beatmod.refine(raw_beats, env, env_rate)
    pos, meter = beatmod.bar_positions(beats, downbeats)

    on_stage("stems", 0.35)
    stems, names = models.separate(y)
    order = [names.index(s) for s in featmod.STEMS]
    stems = stems[order]

    on_stage("features", 0.65)
    feat = featmod.compute(y, y22, beats, stems)
    del stems
    scales = similarity.own_scales(feat)

    on_stage("structure", 0.75)
    bpm, local_ibi = structure.tempo(beats)
    key = structure.estimate_key(feat["key_profile"])
    sec = structure.sections(feat, pos, meter)
    phrase = structure.phrase_grid(pos, sec, meter)

    on_stage("jumps", 0.85)
    jr = jumpmod.find(feat, pos, meter, scales, beats, env, env_rate, phrase)

    analysis = {
        "version": ANALYSIS_VERSION,
        "id": tid,
        "title": meta.get("title", tid),
        "duration": round(duration, 4),
        "sr": SAMPLE_RATE,
        "bpm": round(bpm, 2),
        "meter": meter,
        "key": key["name"],
        "camelot": key["camelot"],
        "lufs": round(lufs, 2),
        "gain_db": round(gain_db, 2),
        "beats": [round(float(b), 5) for b in beats],
        "pos": pos.tolist(),
        "phrase": phrase.tolist(),
        "loud": [round(float(v) + gain_db, 1) for v in feat["loud"]],
        "vocal": [round(float(v), 2) for v in feat["vocal"]],
        "color": featmod.timbre_colors(feat["mfcc"]),
        "sections": sec.tolist(),
        "jumps": jr["jumps"],
        "lbp": jr["lbp"],
        "fallback": jr["fallback"],
    }
    library.write_json(library.analysis_path(tid), analysis)
    np.savez_compressed(
        library.features_path(tid),
        **feat,
        beats=beats, pos=pos, phrase=phrase, local_ibi=local_ibi, onset_env=env,
        mfcc_mu=scales[0], mfcc_sd=scales[1], scales=scales[2],
        meter=meter, bpm=bpm, gain_db=gain_db, lbp=jr["lbp"],
        key_tonic=key["tonic"], key_mode=0 if key["mode"] == "major" else 1,
        key_camelot=key["camelot_num"], env_rate=env_rate,
    )
    stats = {
        "duration": round(duration, 1), "bpm": round(bpm, 1), "key": key["name"],
        "camelot": key["camelot"], "meter": meter, "beats": len(beats),
        "jumps": len(jr["jumps"]), "lbp": jr["lbp"], "fallback": jr["fallback"],
        "analysis_version": ANALYSIS_VERSION, "analysis_seconds": round(time.time() - t0, 1),
    }
    on_stage("analyzed", 0.95)
    return stats


def recompute_jumps(tid: str) -> dict:
    """Re-runs only the jump search from the stored features (seconds, no GPU)."""
    with np.load(library.features_path(tid)) as z:
        f = {k: z[k] for k in z.files}
    feat = {k: f[k] for k in ("chroma", "mfcc", "loud", "rhythm", "stems", "vocal", "dur", "vpitch", "vmfcc") if k in f}
    scales = similarity.own_scales(feat)
    f["mfcc_mu"], f["mfcc_sd"], f["scales"] = scales
    jr = jumpmod.find(feat, f["pos"], int(f["meter"]), scales, f["beats"], f["onset_env"], float(f["env_rate"]),
                      f["phrase"])
    analysis = library.read_json(library.analysis_path(tid))
    analysis.update(jumps=jr["jumps"], lbp=jr["lbp"], fallback=jr["fallback"])
    library.write_json(library.analysis_path(tid), analysis)
    f["lbp"] = np.array(jr["lbp"])
    np.savez_compressed(library.features_path(tid), **f)
    library.update(tid, jumps=len(jr["jumps"]), lbp=jr["lbp"], fallback=jr["fallback"])
    return jr
