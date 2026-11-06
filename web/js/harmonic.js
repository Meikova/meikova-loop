/**
 * Harmonic DJ Sequence Sorter for Meikova Loop.
 * Sorts any list of tracks into an optimal DJ set based on Camelot Wheel harmonic mixing
 * and BPM compatibility.
 */

const CAMELOT_RE = /^([0-9]{1,2})\s*([abAB])$/i;

export function parseCamelot(cam) {
  if (!cam) return null;
  const m = String(cam).trim().match(CAMELOT_RE);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  if (n < 1 || n > 12) return null;
  return { n, l: m[2].toUpperCase() };
}

/**
 * Calculate Camelot harmonic distance between two keys (0 = identical, 1 = adjacent/relative, etc.)
 */
export function camelotDistance(camA, camB) {
  const a = parseCamelot(camA);
  const b = parseCamelot(camB);
  if (!a || !b) return 3; // neutral penalty for unknown keys

  const diff = Math.min((a.n - b.n + 12) % 12, (b.n - a.n + 12) % 12);
  if (a.l === b.l) {
    // Same mode (both Minor A or both Major B)
    if (diff === 0) return 0; // Same key
    if (diff === 1) return 1; // Adjacent key on wheel (+1 or -1 hour)
    if (diff === 2) return 3; // Energy boost / drop (+2 or -2)
    return 4 + diff;
  } else {
    // Relative Major <-> Minor (e.g. 8A <-> 8B)
    if (diff === 0) return 1; // Relative Major/Minor
    if (diff === 1) return 2.2; // Diagonal harmonic step (e.g. 8A -> 9B)
    return 4 + diff;
  }
}

/**
 * Calculate tempo gap between two BPMs, considering half-time / double-time matching.
 */
export function tempoDifference(bpmA, bpmB) {
  let a = Number(bpmA) || 120;
  let b = Number(bpmB) || 120;
  if (a <= 0) a = 120;
  if (b <= 0) b = 120;

  // Direct ratio
  let diff = Math.abs(a - b) / Math.max(a, b);

  // Check half time (e.g. 70 BPM vs 140 BPM)
  const diffHalf = Math.abs(a * 2 - b) / Math.max(a * 2, b);
  const diffDouble = Math.abs(a - b * 2) / Math.max(a, b * 2);

  return Math.min(diff, diffHalf, diffDouble);
}

/**
 * Combined transition penalty between two songs (lower is smoother).
 */
export function transitionCost(trackA, trackB) {
  const camA = trackA.camelot || trackA.meta?.camelot || "";
  const camB = trackB.camelot || trackB.meta?.camelot || "";
  const bpmA = trackA.bpm || trackA.meta?.bpm || 120;
  const bpmB = trackB.bpm || trackB.meta?.bpm || 120;

  const keyDist = camelotDistance(camA, camB);
  const tempoDiff = tempoDifference(bpmA, bpmB);

  // Key harmony is weighted at 2.5x, tempo gap at 12x
  return keyDist * 2.5 + tempoDiff * 12.0;
}

/**
 * Sort a list of tracks into an optimal DJ harmonic sequence using Nearest Neighbor + 2-Opt.
 */
export function sortHarmonicSequence(tracks) {
  if (!tracks || tracks.length <= 2) {
    return tracks ? [...tracks] : [];
  }

  const pool = [...tracks];
  const n = pool.length;

  // Find a solid starting track (prefer tracks with known Camelot key and medium energy BPM)
  let bestStartIdx = 0;
  let minStartPenalty = Infinity;
  for (let i = 0; i < n; i++) {
    const cam = pool[i].camelot || pool[i].meta?.camelot;
    const bpm = pool[i].bpm || pool[i].meta?.bpm || 120;
    const penalty = (!cam ? 10 : 0) + Math.abs(bpm - 128) * 0.05;
    if (penalty < minStartPenalty) {
      minStartPenalty = penalty;
      bestStartIdx = i;
    }
  }

  // 1. Greedy Nearest Neighbor Chain Construction
  const result = [];
  const visited = new Set();

  result.push(pool[bestStartIdx]);
  visited.add(bestStartIdx);

  while (result.length < n) {
    const current = result[result.length - 1];
    let bestNextIdx = -1;
    let lowestCost = Infinity;

    for (let i = 0; i < n; i++) {
      if (visited.has(i)) continue;
      const candidate = pool[i];
      const cost = transitionCost(current, candidate);
      if (cost < lowestCost) {
        lowestCost = cost;
        bestNextIdx = i;
      }
    }

    if (bestNextIdx !== -1) {
      result.push(pool[bestNextIdx]);
      visited.add(bestNextIdx);
    } else {
      break;
    }
  }

  // 2. 2-Opt Local Optimization refinement
  let improved = true;
  let passes = 0;
  while (improved && passes < 20) {
    improved = false;
    passes++;
    for (let i = 0; i < result.length - 2; i++) {
      for (let k = i + 1; k < result.length - 1; k++) {
        const curCost = transitionCost(result[i], result[i + 1]) + transitionCost(result[k], result[k + 1]);
        const newCost = transitionCost(result[i], result[k]) + transitionCost(result[i + 1], result[k + 1]);
        if (newCost < curCost - 0.05) {
          // Reverse segment between i+1 and k
          const reversed = result.slice(i + 1, k + 1).reverse();
          result.splice(i + 1, reversed.length, ...reversed);
          improved = true;
        }
      }
    }
  }

  return result;
}
