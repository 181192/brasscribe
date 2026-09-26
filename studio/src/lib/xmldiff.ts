// Note diff between the same part in two MusicXML scores, bar by bar, for
// marking the notation. Kinds match lib/diff.ts: a note only in A is
// "removed", only in B "added"; "octave" and "moved" mark both sides.
import type { XmlPart } from "./musicxml";

export type MarkKind = "added" | "removed" | "moved" | "octave";

export interface PartDiff {
  a: (MarkKind | null)[]; // per note of part A
  b: (MarkKind | null)[]; // per note of part B
  bars: number[]; // bar indexes with any difference, ascending
  perBar: Map<number, { a: number; b: number }>;
}

const key = (onset: number) => Math.round(onset * 96);

export function diffParts(pa: XmlPart | undefined, pb: XmlPart | undefined, toleranceQuarters = 1): PartDiff {
  const A = pa?.notes ?? [];
  const B = pb?.notes ?? [];
  const a: (MarkKind | null)[] = A.map(() => null);
  const b: (MarkKind | null)[] = B.map(() => null);
  const usedB = new Set<number>();
  const restA: number[] = [];
  const idx = new Map<string, number[]>();
  B.forEach((n, j) => {
    const k = `${n.barIndex}:${key(n.onset)}:${n.sounding}`;
    (idx.get(k) ?? idx.set(k, []).get(k)!).push(j);
  });
  A.forEach((n, i) => {
    const list = idx.get(`${n.barIndex}:${key(n.onset)}:${n.sounding}`);
    const j = list?.find((x) => !usedB.has(x));
    if (j !== undefined) usedB.add(j);
    else restA.push(i);
  });
  const pass = (kind: MarkKind, ok: (i: number, j: number) => boolean, cost: (i: number, j: number) => number) => {
    for (let r = restA.length - 1; r >= 0; r--) {
      const i = restA[r];
      let best = -1;
      let bestCost = Infinity;
      for (let j = 0; j < B.length; j++) {
        if (usedB.has(j) || !ok(i, j)) continue;
        const c = cost(i, j);
        if (c < bestCost) {
          bestCost = c;
          best = j;
        }
      }
      if (best >= 0) {
        usedB.add(best);
        a[i] = kind;
        b[best] = kind;
        restA.splice(r, 1);
      }
    }
  };
  pass("octave",
    (i, j) => A[i].barIndex === B[j].barIndex && key(A[i].onset) === key(B[j].onset) && A[i].sounding !== B[j].sounding && Math.abs(A[i].sounding - B[j].sounding) % 12 === 0,
    (i, j) => Math.abs(A[i].sounding - B[j].sounding));
  pass("moved",
    (i, j) => A[i].sounding === B[j].sounding && Math.abs(A[i].onset - B[j].onset) <= toleranceQuarters,
    (i, j) => Math.abs(A[i].onset - B[j].onset));
  for (const i of restA) a[i] = "removed";
  B.forEach((_, j) => {
    if (!usedB.has(j)) b[j] = "added";
  });
  const perBar = new Map<number, { a: number; b: number }>();
  const bump = (bar: number, side: "a" | "b") => {
    const v = perBar.get(bar) ?? { a: 0, b: 0 };
    v[side]++;
    perBar.set(bar, v);
  };
  a.forEach((k, i) => k && bump(A[i].barIndex, "a"));
  b.forEach((k, j) => k && bump(B[j].barIndex, "b"));
  return { a, b, perBar, bars: [...perBar.keys()].sort((x, y) => x - y) };
}
