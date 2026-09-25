// Beat tracks: the beat tracker's `mix.beats` file and the beat grid a
// Composition carries, plus irregular-tempo (free-time) regions.
import type { Composition } from "../api/types";

export interface Beat {
  time: number; // seconds
  position: number; // 1 = downbeat
}

/** Parse Beat This! output: one "time<TAB>beat-in-bar" per line. */
export function parseBeats(text: string): Beat[] {
  const out: Beat[] = [];
  for (const line of text.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 2) continue;
    const time = Number(parts[0]);
    const position = Number(parts[1]);
    if (Number.isFinite(time) && Number.isFinite(position)) out.push({ time, position });
  }
  return out;
}

/** The beat grid a Composition was quantised to: beat_times with bar positions from its meters. */
export function compositionBeats(c: Composition): Beat[] {
  const times = c.beat_times ?? [];
  const tpb = c.ticks_per_beat ?? 24;
  const first = c.first_downbeat ?? 0; // index into beat_times of tick 0
  const meters = [...(c.meters ?? [])].sort((a, b) => a.tick - b.tick);
  const beatsAt = (beatIndex: number) => {
    const tick = beatIndex * tpb;
    let m = meters[0] ?? { tick: 0, beats: 4 };
    for (const x of meters) if (x.tick <= tick) m = x;
    return m;
  };
  return times.map((time, i) => {
    const rel = i - first; // beats from tick 0
    const m = beatsAt(rel);
    const beatInBar = ((((rel - m.tick / tpb) % m.beats) + m.beats) % m.beats) + 1;
    return { time, position: beatInBar };
  });
}

export interface TempoSummary {
  bpm: number;
  barBeats: number;
  downbeats: number;
  beats: number;
}

export function summarise(beats: Beat[]): TempoSummary {
  const iv = intervals(beats);
  const med = median(iv);
  const barBeats = Math.max(0, ...beats.map((b) => b.position));
  return { bpm: med > 0 ? 60 / med : 0, barBeats, downbeats: beats.filter((b) => b.position === 1).length, beats: beats.length };
}

export interface Region {
  start: number; // seconds
  end: number;
  source: "composition" | "heuristic";
}

/**
 * Passages where consecutive beat intervals vary by more than `tolerance`
 * relative to the local median (a view aid; the engine's free-time detector
 * is authoritative when the Composition carries its regions).
 */
export function irregularRegions(beats: Beat[], tolerance = 0.35, window = 4, minBeats = 3): Region[] {
  const iv = intervals(beats);
  const flags = iv.map((d, i) => {
    const lo = Math.max(0, i - window);
    const local = median(iv.slice(lo, Math.min(iv.length, i + window + 1)));
    return local > 0 && Math.abs(d - local) / local > tolerance;
  });
  const out: Region[] = [];
  let i = 0;
  while (i < flags.length) {
    if (!flags[i]) {
      i++;
      continue;
    }
    let j = i;
    while (j + 1 < flags.length && (flags[j + 1] || (j + 2 < flags.length && flags[j + 2]))) j++;
    if (j - i + 1 >= minBeats) out.push({ start: beats[i].time, end: beats[j + 1].time, source: "heuristic" });
    i = j + 1;
  }
  return out;
}

/** Free-time regions the Composition marks (`free_regions`, seconds as written by the engine). */
export function compositionFreeTime(c: Composition): (Region & { label: string; tempo_bpm?: number; startTick: number; endTick: number })[] {
  return (c.free_regions ?? []).map((r) => ({
    start: r.start_s,
    end: r.end_s,
    startTick: r.start,
    endTick: r.end,
    label: r.label ?? "ad lib.",
    tempo_bpm: r.tempo_bpm,
    source: "composition" as const,
  }));
}

/** Seconds of a tick through the Composition's beat grid (linear between beats). */
export function tickTime(c: Composition, tick: number): number {
  const times = c.beat_times ?? [];
  if (times.length < 2) return 0;
  const b = tick / (c.ticks_per_beat ?? 24) + (c.first_downbeat ?? 0);
  const i = Math.max(0, Math.min(times.length - 2, Math.floor(b)));
  return times[i] + (b - i) * (times[i + 1] - times[i]);
}

function intervals(beats: Beat[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < beats.length; i++) out.push(beats[i].time - beats[i - 1].time);
  return out;
}

export function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
