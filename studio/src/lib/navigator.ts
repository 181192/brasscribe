// Talking-score navigation (spec §5): note, beat, bar, part and uncertain-note
// moves over a TalkingScore, each returning the announcement for the new stop.
import { announce, type Context, type Lang, type Settings, type TsEvent } from "./talking";
import type { NavBar, NavEvent, NavPart, TalkingScore } from "./talkingxml";

export interface Cursor {
  part: number;
  bar: number;
  event: number; // index into bar.events, or -1 for the bar itself
  tick: number;
}

export interface Stop {
  cursor: Cursor;
  text: string;
}

export class Navigator {
  cursor: Cursor = { part: 0, bar: 0, event: 0, tick: 0 };
  context: Context = { part: null, bar: null, pitch_mode: "written" };

  constructor(
    public ts: TalkingScore,
    public settings: Settings = { verbosity: "standard", pitch_mode: "written" },
    public lang: Lang = "en",
  ) {}

  private get part(): NavPart {
    return this.ts.parts[this.cursor.part];
  }

  private say(part: NavPart, bar: NavBar, e: TsEvent, opts: { byBar?: boolean; verbosity?: Settings["verbosity"] } = {}): string {
    const settings = { ...this.settings, verbosity: opts.verbosity ?? this.settings.verbosity };
    const text = announce({
      settings, context: { ...this.context, by_bar: opts.byBar }, bar, part, event: e, total_bars: this.ts.total_bars,
    }, this.lang);
    this.context = { part: part.name, bar: bar.number, pitch_mode: this.settings.pitch_mode };
    return text;
  }

  private stop(partIdx: number, barIdx: number, evIdx: number, opts: { byBar?: boolean; verbosity?: Settings["verbosity"] } = {}): Stop {
    const part = this.ts.parts[partIdx];
    const bar = part.bars[barIdx];
    const e = bar.events[evIdx];
    this.cursor = { part: partIdx, bar: barIdx, event: evIdx, tick: e ? e.tick : bar.startTick };
    const ev: TsEvent = e ?? { kind: "bar-rest", bars: 1 };
    return { cursor: { ...this.cursor }, text: this.say(part, bar, ev, opts) };
  }

  /** Every note-navigable event of the current part, in order. */
  private stops(part = this.part): [number, number][] {
    const out: [number, number][] = [];
    part.bars.forEach((b, bi) => b.events.forEach((e, ei) => {
      if (!e.skip) out.push([bi, ei]);
    }));
    return out;
  }

  current(): NavEvent | undefined {
    return this.part.bars[this.cursor.bar]?.events[this.cursor.event];
  }

  /** Announce a given event (used to render the text form in reading order). */
  goBarEvent(barIdx: number, evIdx: number): string {
    return this.stop(this.cursor.part, barIdx, evIdx).text;
  }

  goBar(barIdx: number): Stop {
    const b = Math.max(0, Math.min(this.part.bars.length - 1, barIdx));
    return this.stop(this.cursor.part, b, this.part.bars[b].events.length ? 0 : -1, { byBar: true });
  }

  nextBar(dir: 1 | -1 = 1): Stop {
    return this.goBar(this.cursor.bar + dir);
  }

  nextNote(dir: 1 | -1 = 1): Stop | null {
    const list = this.stops();
    const i = list.findIndex(([b, e]) => b === this.cursor.bar && e === this.cursor.event);
    let j: number;
    if (i >= 0) j = i + dir;
    else {
      // Cursor sits on a skipped event or a bar: next stop after (or before) its tick.
      const at = this.cursor.tick;
      const ev = (bi: number, ei: number) => this.part.bars[bi].events[ei];
      j = dir > 0 ? list.findIndex(([b, e]) => ev(b, e).tick > at) : findLast(list, ([b, e]) => ev(b, e).tick < at);
    }
    if (j < 0 || j >= list.length) return null;
    return this.stop(this.cursor.part, list[j][0], list[j][1]);
  }

  /** Next beat: the event starting there, or the note still sounding ("held"). */
  nextBeat(dir: 1 | -1 = 1): Stop | null {
    const part = this.part;
    let bi = this.cursor.bar;
    const bar = part.bars[bi];
    const beatTicks = 960 * (4 / (bar.time?.beat_type ?? 4)) * (bar.time && bar.time.beat_type === 8 && bar.time.beats % 3 === 0 && bar.time.beats > 3 ? 3 : 1);
    const rel = this.cursor.tick - bar.startTick;
    let target = dir > 0 ? bar.startTick + (Math.floor(rel / beatTicks) + 1) * beatTicks : bar.startTick + (Math.ceil(rel / beatTicks) - 1) * beatTicks;
    if (target >= bar.endTick) {
      if (bi + 1 >= part.bars.length) return null;
      bi++;
      target = part.bars[bi].startTick;
    } else if (target < bar.startTick) {
      if (bi === 0) return null;
      bi--;
      const pb = part.bars[bi];
      target = pb.startTick + Math.floor((pb.endTick - pb.startTick - 1) / beatTicks) * beatTicks;
    }
    const b = part.bars[bi];
    const at = b.events.findIndex((e) => e.tick === target && !(e.tie?.stop));
    if (at >= 0) return this.stop(this.cursor.part, bi, at);
    // Something sounding across the beat?
    const all = part.bars.flatMap((x) => x.events);
    const sounding = all.find((e) => (e.kind === "note" || e.kind === "chord") && e.tick < target && e.endTick > target && !e.tie?.stop)
      ?? findTieStart(part, target);
    if (sounding) {
      const from = part.bars[sounding.bar];
      const beat = beatOf(b, target, beatTicks);
      const held: TsEvent = {
        kind: "held", pos: beat, written: sounding.written, concert: sounding.concert,
        held_from: { bar: from.number, ...(sounding.pos ?? { beat: 1, num: 0, den: 1 }) },
      };
      this.cursor = { part: this.cursor.part, bar: bi, event: -1, tick: target };
      return { cursor: { ...this.cursor }, text: this.say(part, b, held) };
    }
    // Nothing there (e.g. inside a bar rest): announce the bar.
    this.cursor = { part: this.cursor.part, bar: bi, event: b.events.length ? 0 : -1, tick: target };
    return this.stop(this.cursor.part, bi, b.events.length ? 0 : -1);
  }

  /** Same time position in the next part (spec §4.9: the part name and its key come first). */
  nextPart(dir: 1 | -1 = 1): Stop | null {
    const n = this.ts.parts.length;
    const p = (this.cursor.part + dir + n) % n;
    const part = this.ts.parts[p];
    const tick = this.cursor.tick;
    const bi = Math.max(0, part.bars.findIndex((b) => b.startTick <= tick && tick < b.endTick));
    const bar = part.bars[bi];
    let ei = bar.events.findIndex((e) => !e.skip && e.tick <= tick && tick < e.endTick);
    if (ei < 0) ei = bar.events.findIndex((e) => !e.skip && e.tick >= tick);
    if (ei < 0) ei = bar.events.length ? 0 : -1;
    return this.stop(p, bi, ei);
  }

  nextUncertain(dir: 1 | -1 = 1): Stop | null {
    const list = this.stops();
    const ev = (bi: number, ei: number) => this.part.bars[bi].events[ei];
    const isU = (e: NavEvent) => !e.checked && (!!e.uncertain || (e.confidence != null && e.confidence < 0.7));
    const at = this.cursor.tick;
    const j = dir > 0
      ? list.findIndex(([b, e]) => ev(b, e).tick > at && isU(ev(b, e)))
      : findLast(list, ([b, e]) => ev(b, e).tick < at && isU(ev(b, e)));
    if (j < 0) return null;
    return this.stop(this.cursor.part, list[j][0], list[j][1]);
  }

  /** Every event of the current bar in brief form (spec §5 "Read bar"). */
  readBar(): string {
    const part = this.part;
    const bar = part.bars[this.cursor.bar];
    const saved = { ...this.context };
    const parts = bar.events.filter((e) => !(e.tie?.stop) || e.kind === "bar-rest").map((e, i) => {
      this.context = i === 0 ? { ...saved, bar: null } : { part: part.name, bar: bar.number };
      return announce({ settings: { ...this.settings, verbosity: "brief" }, context: this.context, bar, part, event: e, total_bars: this.ts.total_bars }, this.lang);
    });
    this.context = { part: part.name, bar: bar.number, pitch_mode: this.settings.pitch_mode };
    return parts.join(", ") || announce({ settings: this.settings, context: { bar: null }, bar, event: { kind: "bar-rest", bars: 1 } }, this.lang);
  }

  /** Full-verbosity description of the current stop (spec §5 "Where am I"). */
  whereAmI(): string {
    const part = this.part;
    const bar = part.bars[this.cursor.bar];
    const e = this.current() ?? ({ kind: "bar-rest", bars: 1 } as TsEvent);
    this.context = { ...this.context, part: null, bar: null };
    return this.say(part, bar, e, { verbosity: "full" });
  }

  setPitchMode(mode: Settings["pitch_mode"]): string {
    const prev = this.settings.pitch_mode;
    this.settings = { ...this.settings, pitch_mode: mode };
    if (prev === mode) return "";
    const part = this.part;
    return announce({ settings: this.settings, context: { ...this.context, pitch_mode: prev }, part: { ...part, instrument: instrumentOf(part), instrument_nb: instrumentNbOf(part) }, event: { kind: "mode-change" } }, this.lang);
  }

  /** Move the cursor to the stop at or before a tick without announcing (follows playback or the score). */
  syncToTick(tick: number): void {
    const part = this.part;
    const bi = part.bars.findIndex((b) => b.startTick <= tick && tick < b.endTick);
    if (bi < 0) return;
    const bar = part.bars[bi];
    let ei = -1;
    bar.events.forEach((e, i) => {
      if (e.tick <= tick && !e.skip) ei = i;
    });
    this.cursor = { part: this.cursor.part, bar: bi, event: ei, tick };
  }

  setPart(p: number): void {
    this.cursor = { ...this.cursor, part: Math.max(0, Math.min(this.ts.parts.length - 1, p)) };
  }
}

function findLast<T>(xs: T[], pred: (x: T) => boolean): number {
  for (let i = xs.length - 1; i >= 0; i--) if (pred(xs[i])) return i;
  return -1;
}

function findTieStart(part: NavPart, target: number): NavEvent | undefined {
  // A tie continuation starting on the beat: report the note that started the tie.
  const all = part.bars.flatMap((x) => x.events);
  const cont = all.find((e) => e.tie?.stop && e.tick <= target && e.endTick > target);
  if (!cont?.written) return undefined;
  const key = (p: { step: string; alter: number; octave: number }) => `${p.step}${p.alter}${p.octave}`;
  return [...all].reverse().find((e) => e.tick < cont.tick && e.tie?.start && !e.tie.stop && e.written && key(e.written) === key(cont.written!));
}

function beatOf(bar: NavBar, tick: number, beatTicks: number) {
  const rel = tick - bar.startTick;
  return { beat: Math.floor(rel / beatTicks) + 1, num: 0, den: 1 };
}

const INSTRUMENTS: Record<number, [string, string]> = {
  [-2]: ["Cornet in B♭", "kornett i B"],
  3: ["Cornet in E♭", "kornett i Ess"],
  [-9]: ["Horn in E♭", "althorn i Ess"],
  [-14]: ["Baritone in B♭", "baryton i B"],
  [-21]: ["Bass in E♭", "Ess-bass"],
  [-26]: ["Bass in B♭", "B-bass"],
};
/** Parts named for an instrument the transposition alone doesn't tell apart (a trumpet is in B♭ like a cornet). */
const BY_NAME: [RegExp, [string, string]][] = [[/trumpet/i, ["Trumpet in B♭", "trompet i B"]]];
function instrumentPair(p: NavPart): [string, string] | undefined {
  return BY_NAME.find(([re]) => re.test(p.name))?.[1] ?? INSTRUMENTS[p.transpose.chromatic + 12 * p.transpose.octave];
}
function instrumentOf(p: NavPart): string | undefined {
  return instrumentPair(p)?.[0];
}
function instrumentNbOf(p: NavPart): string | undefined {
  return instrumentPair(p)?.[1];
}
