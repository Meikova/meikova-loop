"""Song-level structure: section boundaries, phrase grid, key and tempo."""
import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter
from scipy.signal import find_peaks

# Albrecht & Shanahan (2013) key profiles, derived from popular music. On the
# test library they beat Krumhansl-Kessler, Temperley and EDMA profiles.
_MAJOR = np.array([0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081])
_MINOR = np.array([0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052])
_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
# Camelot number for each tonic (index = pitch class).
_CAMELOT_MAJOR = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1]
_CAMELOT_MINOR = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10]

PHRASE_NONE, PHRASE_BAR, PHRASE_4BAR, PHRASE_SECTION = 0, 1, 2, 3


def estimate_key(prof: np.ndarray) -> dict:
    best = (-2.0, 0, "major")
    scores = []
    for tonic in range(12):
        for mode, tmpl in (("major", _MAJOR), ("minor", _MINOR)):
            r = np.corrcoef(prof, np.roll(tmpl, tonic))[0, 1]
            scores.append(r)
            if r > best[0]:
                best = (r, tonic, mode)
    r, tonic, mode = best
    second = sorted(scores)[-2]
    num = (_CAMELOT_MAJOR if mode == "major" else _CAMELOT_MINOR)[tonic]
    return {
        "name": f"{_NAMES[tonic]} {mode}",
        "tonic": tonic,
        "mode": mode,
        "camelot": f"{num}{'B' if mode == 'major' else 'A'}",
        "camelot_num": num,
        "confidence": float(r - second),
    }


def camelot_distance(a: dict, b: dict) -> int:
    """0 = same key, 1 = adjacent or relative major/minor, larger = further apart."""
    d = abs(a["camelot_num"] - b["camelot_num"]) % 12
    d = min(d, 12 - d)
    if a["mode"] != b["mode"]:
        d += 1
    return d


def tempo(beats: np.ndarray) -> tuple[float, np.ndarray]:
    ibi = np.diff(beats)
    if len(ibi) == 0:
        return 120.0, np.array([0.5])
    local = median_filter(ibi, size=9, mode="nearest")
    local = np.append(local, local[-1])
    return float(60.0 / np.median(ibi)), local


def sections(feat: dict, pos: np.ndarray, meter: int) -> np.ndarray:
    """Section boundaries from a checkerboard novelty curve over the beat
    self-similarity matrix, snapped to downbeats."""
    n = len(pos)
    x = np.concatenate([
        feat["chroma"].mean(1),
        (feat["mfcc"].mean(1) - feat["mfcc"].mean((0, 1))) / (feat["mfcc"].std((0, 1)) + 1e-9) * 0.5,
        ((feat["loud"] - feat["loud"].mean()) / (feat["loud"].std() + 1e-9))[:, None],
        (feat["stems"] - feat["stems"].mean(0)) / (feat["stems"].std(0) + 1e-9) * 0.5,
    ], 1)
    x = x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)
    ssm = x @ x.T
    half = 4 * meter
    g = np.exp(-0.5 * (np.linspace(-2, 2, 2 * half)) ** 2)
    kernel = np.outer(g, g) * np.outer(np.r_[-np.ones(half), np.ones(half)], np.r_[-np.ones(half), np.ones(half)])
    pad = np.pad(ssm, half, mode="edge")
    nov = np.array([np.sum(pad[i:i + 2 * half, i:i + 2 * half] * kernel) for i in range(n)])
    nov = gaussian_filter1d(np.maximum(nov, 0), 1.0)
    if nov.max() > 0:
        nov /= nov.max()
    peaks, _ = find_peaks(nov, distance=4 * meter, height=0.15, prominence=0.08)
    downbeats = np.where(pos == 0)[0]
    out = {int(downbeats[0])} if len(downbeats) else {0}
    for p in peaks:
        if len(downbeats):
            d = downbeats[np.argmin(np.abs(downbeats - p))]
            if abs(d - p) <= meter:
                out.add(int(d))
    return np.array(sorted(out), dtype=np.int64)


def phrase_grid(pos: np.ndarray, section_starts: np.ndarray, meter: int) -> np.ndarray:
    n = len(pos)
    ph = np.where(pos == 0, PHRASE_BAR, PHRASE_NONE).astype(np.int64)
    bounds = list(section_starts) + [n]
    for s, e in zip(bounds[:-1], bounds[1:]):
        bar = 0
        for b in range(s, e):
            if pos[b] == 0:
                if bar % 4 == 0:
                    ph[b] = PHRASE_4BAR
                bar += 1
        ph[s] = PHRASE_SECTION
    return ph
