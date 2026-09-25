// Note-level diff between two Compositions, voice by voice.
import type { Composition, Note } from "../api/types";

export type ChangeKind = "same" | "added" | "removed" | "moved" | "octave";

export interface Change {
  kind: ChangeKind;
  voice: string;
  a?: Note; // note in the base run
  b?: Note; // note in the other run
}

export interface VoiceDiff {
  voice: string;
  counts: Record<ChangeKind, number>;
  changes: Change[];
}

export interface CompositionDiff {
  voices: VoiceDiff[];
  totals: Record<ChangeKind, number>;
}

const zero = (): Record<ChangeKind, number> => ({ same: 0, added: 0, removed: 0, moved: 0, octave: 0 });

/**
 * Match notes in three passes: identical (pitch, start, dur); octave (same
 * start, pitch a whole number of octaves apart); moved (same pitch, start
 * within `tolerance` ticks, or same start with a different length). What is
 * left is removed (only in `a`) or added (only in `b`).
 */
export function diffNotes(voice: string, a: Note[], b: Note[], tolerance: number): VoiceDiff {
  const changes: Change[] = [];
  const usedB = new Set<number>();
  const restA: number[] = [];
  const index = new Map<string, number[]>();
  b.forEach((n, i) => {
    const k = `${n.pitch}:${n.start}:${n.dur}`;
    (index.get(k) ?? index.set(k, []).get(k)!).push(i);
  });
  a.forEach((n, i) => {
    const list = index.get(`${n.pitch}:${n.start}:${n.dur}`);
    const j = list?.find((x) => !usedB.has(x));
    if (j !== undefined) {
      usedB.add(j);
      changes.push({ kind: "same", voice, a: n, b: b[j] });
    } else restA.push(i);
  });

  const pass = (kind: ChangeKind, ok: (x: Note, y: Note) => boolean, cost: (x: Note, y: Note) => number) => {
    for (let k = restA.length - 1; k >= 0; k--) {
      const x = a[restA[k]];
      let best = -1;
      let bestCost = Infinity;
      for (let j = 0; j < b.length; j++) {
        if (usedB.has(j) || !ok(x, b[j])) continue;
        const c = cost(x, b[j]);
        if (c < bestCost) {
          bestCost = c;
          best = j;
        }
      }
      if (best >= 0) {
        usedB.add(best);
        changes.push({ kind, voice, a: x, b: b[best] });
        restA.splice(k, 1);
      }
    }
  };
  pass(
    "octave",
    (x, y) => x.start === y.start && x.pitch !== y.pitch && Math.abs(x.pitch - y.pitch) % 12 === 0,
    (x, y) => Math.abs(x.pitch - y.pitch) + Math.abs(x.dur - y.dur) / 1000,
  );
  pass(
    "moved",
    (x, y) => x.pitch === y.pitch && Math.abs(x.start - y.start) <= tolerance,
    (x, y) => Math.abs(x.start - y.start) + Math.abs(x.dur - y.dur) / 1000,
  );
  for (const i of restA) changes.push({ kind: "removed", voice, a: a[i] });
  b.forEach((n, j) => {
    if (!usedB.has(j)) changes.push({ kind: "added", voice, b: n });
  });
  changes.sort((x, y) => ((x.a ?? x.b)!.start - (y.a ?? y.b)!.start) || ((x.a ?? x.b)!.pitch - (y.a ?? y.b)!.pitch));
  const counts = zero();
  for (const c of changes) counts[c.kind]++;
  return { voice, counts, changes };
}

export function diffCompositions(a: Composition, b: Composition, toleranceBeats = 1): CompositionDiff {
  const tol = toleranceBeats * (a.ticks_per_beat ?? 24);
  const ids = [...new Set([...a.voices.map((v) => v.id), ...b.voices.map((v) => v.id)])];
  const voices = ids.map((id) =>
    diffNotes(id, a.voices.find((v) => v.id === id)?.notes ?? [], b.voices.find((v) => v.id === id)?.notes ?? [], tol),
  );
  const totals = zero();
  for (const v of voices) for (const k of Object.keys(totals) as ChangeKind[]) totals[k] += v.counts[k];
  return { voices, totals };
}
