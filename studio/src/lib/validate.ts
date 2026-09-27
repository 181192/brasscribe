// Range and voice-crossing checks on an arranged MusicXML score. Used when
// the engine does not serve its own validator results. Ranges are sounding
// MIDI pitches copied from music/src/brasscribe_music/instruments.py
// (MuseScore instruments.xml: `pro` hard limit, `comfortable` soft limit).
import type { ValidationIssue } from "../api/types";
import type { XmlPart, XmlScore } from "./musicxml";

type Range = { pro: [number, number]; comfortable: [number, number] };

const R = (pro: [number, number], comfortable: [number, number]): Range => ({ pro, comfortable });
const CORNET = R([52, 82], [52, 79]);
export const RANGES: Record<string, Range> = {
  "Soprano Cornet": R([57, 87], [57, 84]),
  "Solo Cornet": CORNET,
  "1st Cornet": CORNET,
  "Repiano Cornet": CORNET,
  "2nd Cornet": CORNET,
  "3rd Cornet": CORNET,
  Flugelhorn: CORNET,
  "Solo Horn": R([45, 75], [45, 72]),
  "Tenor Horn": R([45, 75], [45, 72]),
  "1st Horn": R([45, 75], [45, 72]),
  "2nd Horn": R([45, 75], [45, 72]),
  "1st Baritone": R([40, 70], [40, 67]),
  "2nd Baritone": R([40, 70], [40, 67]),
  "1st Trombone": R([36, 74], [40, 71]),
  "2nd Trombone": R([36, 74], [40, 71]),
  "Bass Trombone": R([21, 77], [32, 65]),
  Euphonium: R([34, 74], [40, 70]),
  "E♭ Bass": R([24, 72], [26, 64]),
  "B♭ Bass": R([22, 72], [28, 58]),
};

/** Adjacent parts of one section, upper part first: the lower must not sound above the upper. */
export const CROSSING_PAIRS: [string, string][] = [
  ["Solo Cornet", "Repiano Cornet"],
  ["Repiano Cornet", "2nd Cornet"],
  ["2nd Cornet", "3rd Cornet"],
  ["Solo Horn", "1st Horn"],
  ["1st Horn", "2nd Horn"],
  ["1st Baritone", "2nd Baritone"],
  ["1st Trombone", "2nd Trombone"],
  ["2nd Trombone", "Bass Trombone"],
  ["E♭ Bass", "B♭ Bass"],
  // Brass quartet
  ["1st Cornet", "2nd Cornet"],
  ["2nd Cornet", "Tenor Horn"],
  ["Tenor Horn", "Euphonium"],
];

const NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
export const pitchName = (p: number): string => `${NAMES[((p % 12) + 12) % 12]}${Math.floor(p / 12) - 1}`;

export function checkRanges(part: XmlPart): ValidationIssue[] {
  const r = RANGES[part.name];
  if (!r || part.percussion) return [];
  const out: ValidationIssue[] = [];
  for (const n of part.notes) {
    const p = n.sounding;
    if (p < r.pro[0] || p > r.pro[1]) {
      out.push({ part: part.name, bar: n.bar, beat: n.beat, kind: "range", severity: "error",
        message: `${pitchName(p)} (sounding) is outside the playable range ${pitchName(r.pro[0])}–${pitchName(r.pro[1])}` });
    } else if (p < r.comfortable[0] || p > r.comfortable[1]) {
      out.push({ part: part.name, bar: n.bar, beat: n.beat, kind: "range", severity: "warning",
        message: `${pitchName(p)} (sounding) is outside the comfortable range ${pitchName(r.comfortable[0])}–${pitchName(r.comfortable[1])}` });
    }
  }
  return out;
}

export function checkCrossing(upper: XmlPart, lower: XmlPart): ValidationIssue[] {
  // Highest note per onset in each part; compare where both parts start a note together.
  const top = (p: XmlPart, pick: (a: number, b: number) => number) => {
    const m = new Map<number, { pitch: number; bar: number; beat: number }>();
    for (const n of p.notes) {
      const k = Math.round(n.onset * 96);
      const cur = m.get(k);
      m.set(k, cur ? { ...cur, pitch: pick(cur.pitch, n.sounding) } : { pitch: n.sounding, bar: n.bar, beat: n.beat });
    }
    return m;
  };
  const u = top(upper, Math.min);
  const l = top(lower, Math.max);
  const out: ValidationIssue[] = [];
  for (const [k, lo] of l) {
    const up = u.get(k);
    if (up && lo.pitch > up.pitch) {
      out.push({ part: lower.name, upper: upper.name, bar: lo.bar, beat: lo.beat, kind: "crossing", severity: "warning",
        message: `${lower.name} ${pitchName(lo.pitch)} sounds above ${upper.name} ${pitchName(up.pitch)}` } as ValidationIssue);
    }
  }
  return out;
}

export function validateScore(score: XmlScore): ValidationIssue[] {
  const byName = new Map(score.parts.map((p) => [p.name, p]));
  const issues = score.parts.flatMap(checkRanges);
  for (const [a, b] of CROSSING_PAIRS) {
    const pa = byName.get(a);
    const pb = byName.get(b);
    if (pa && pb) issues.push(...checkCrossing(pa, pb));
  }
  return issues.sort((x, y) => (x.bar ?? 0) - (y.bar ?? 0) || (x.beat ?? 0) - (y.beat ?? 0));
}
