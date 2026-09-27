// Builds the talking-score structure (spec §6) from MusicXML, so any score
// Studio shows can be navigated and announced. Confidence is not in MusicXML;
// notes the engine coloured are marked `uncertain`.
import type { Pitch, Pos, TsBar, TsEvent, TsPart } from "./talking";

export interface NavEvent extends TsEvent {
  bar: number; // index into part.bars
  tick: number; // alphaTab tick (960 per quarter) from the start of the score
  /** Tie continuation or a bar inside a multi-bar rest: skipped by note navigation. */
  skip?: boolean;
  endTick: number;
}

export interface NavBar extends TsBar {
  index: number;
  startTick: number;
  endTick: number;
  events: NavEvent[];
}

export interface NavPart extends TsPart {
  transpose: { chromatic: number; diatonic: number; octave: number };
  bars: NavBar[];
}

export interface TalkingScore {
  title: string;
  total_bars: number;
  parts: NavPart[];
}

const STEPS = ["C", "D", "E", "F", "G", "A", "B"];
const NAT = [0, 2, 4, 5, 7, 9, 11];
const TPQ = 960;

const NB_PARTS: Record<string, string> = {
  "Soprano Cornet": "Sopran-kornett", "Solo Cornet": "Solokornett", "Repiano Cornet": "Repiano-kornett",
  "1st Cornet": "1. kornett", "Tenor Horn": "Althorn",
  "2nd Cornet": "2. kornett", "3rd Cornet": "3. kornett", Flugelhorn: "Flygelhorn",
  "Solo Horn": "Solo althorn", "1st Horn": "1. althorn", "2nd Horn": "2. althorn",
  "1st Baritone": "1. baryton", "2nd Baritone": "2. baryton", "1st Trombone": "1. trombone", "2nd Trombone": "2. trombone",
  "Bass Trombone": "Basstrombone", Euphonium: "Eufonium", "E♭ Bass": "Ess-bass", "B♭ Bass": "B-bass", Percussion: "Slagverk",
};
const NB_INSTRUMENTS: Record<string, string> = {
  "Bass Drum": "stortromme", "Acoustic Bass Drum": "stortromme", "Snare": "skarptromme", "Snare Drum": "skarptromme", "Acoustic Snare": "skarptromme",
  "Hi-Hat": "hi-hat", "Closed Hi-Hat": "lukket hi-hat", "Open Hi-Hat": "åpen hi-hat", "Pedal Hi-Hat": "pedal-hi-hat",
  "Crash Cymbal": "crash", "Crash Cymbal 1": "crash", "Ride Cymbal": "ride", "Ride Cymbal 1": "ride", "Tom": "tam-tam",
};

export function partNameNb(name: string): string | undefined {
  return NB_PARTS[name];
}

function child(el: Element, name: string): Element | null {
  for (const c of Array.from(el.children)) if (c.nodeName === name) return c;
  return null;
}
function text(el: Element | null | undefined, sel: string): string | null {
  const x = el?.querySelector(sel);
  return x ? (x.textContent ?? "").trim() : null;
}

/** Transpose a spelled pitch by a MusicXML <transpose> (written -> sounding), keeping the diatonic spelling. */
export function transposePitch(p: Pitch, t: { chromatic: number; diatonic: number; octave: number }): Pitch {
  const si = STEPS.indexOf(p.step);
  const midi = 12 * (p.octave + 1) + NAT[si] + p.alter + t.chromatic + 12 * t.octave;
  const idx = si + t.diatonic + 7 * t.octave;
  const step = STEPS[((idx % 7) + 7) % 7];
  const octave = p.octave + Math.floor(idx / 7);
  const natural = 12 * (octave + 1) + NAT[STEPS.indexOf(step)];
  return { step, alter: midi - natural, octave };
}

/** The sounding key of a transposing part: each semitone of transposition moves the key by 7 fifths. */
export function concertFifths(writtenFifths: number, chromatic: number): number {
  let f = writtenFifths + ((((chromatic * 7) % 12) + 12) % 12);
  while (f > 6) f -= 12;
  while (f < -6) f += 12;
  return f;
}

function gcd(a: number, b: number): number {
  return b ? gcd(b, a % b) : Math.abs(a);
}

const ARTICS = ["staccato", "accent", "tenuto", "strong-accent", "staccatissimo"];

export function buildTalkingScore(xml: string): TalkingScore {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.querySelector("parsererror")) throw new Error("not valid MusicXML");
  const root = doc.documentElement;
  const title = text(root, "work > work-title") ?? text(root, "movement-title") ?? "";
  const names = new Map<string, { name: string; instruments: Map<string, string> }>();
  for (const sp of Array.from(root.querySelectorAll("part-list > score-part"))) {
    const inst = new Map<string, string>();
    for (const si of Array.from(sp.querySelectorAll("score-instrument"))) inst.set(si.getAttribute("id") ?? "", text(si, "instrument-name") ?? "");
    names.set(sp.getAttribute("id") ?? "", { name: text(sp, "part-name") ?? "", instruments: inst });
  }
  const parts: NavPart[] = [];
  let total = 0;
  for (const p of Array.from(root.querySelectorAll(":scope > part"))) {
    const meta = names.get(p.getAttribute("id") ?? "") ?? { name: "", instruments: new Map() };
    const part: NavPart = { name: meta.name, name_nb: partNameNb(meta.name), transpose: { chromatic: 0, diatonic: 0, octave: 0 }, bars: [] };
    let divisions = 1;
    let fifths = 0;
    let beats = 4;
    let beatType = 4;
    let barStart = 0; // ticks
    let pendingDynamic: string | null = null;
    let pendingQ: "u" | "vu" | null = null; // a "?" words direction before the note
    let tupletIndex = 0;
    const measures = Array.from(p.children).filter((c) => c.nodeName === "measure");
    measures.forEach((m, index) => {
      const number = Number(m.getAttribute("number")) || index + 1;
      const bar: NavBar = { index, number, events: [], startTick: barStart, endTick: barStart };
      let pos = 0;
      let lastOnset = 0;
      let maxPos = 0;
      let lastEvent: NavEvent | null = null;
      for (const el of Array.from(m.children)) {
        if (el.nodeName === "attributes") {
          const d = text(el, "divisions");
          if (d) divisions = Number(d) || divisions;
          const k = text(el, "key > fifths");
          if (k !== null) {
            if (Number(k) !== fifths || index === 0) bar.key_change = index > 0;
            fifths = Number(k);
          }
          const b = text(el, "time > beats");
          const bt = text(el, "time > beat-type");
          if (b && bt) {
            if (index > 0 && (Number(b) !== beats || Number(bt) !== beatType)) bar.time_change = true;
            beats = Number(b);
            beatType = Number(bt);
          }
          const chrom = text(el, "transpose > chromatic");
          if (chrom !== null) {
            part.transpose = { chromatic: Number(chrom), diatonic: Number(text(el, "transpose > diatonic") ?? 0), octave: Number(text(el, "transpose > octave-change") ?? 0) };
          }
        } else if (el.nodeName === "direction") {
          const dyn = el.querySelector("direction-type > dynamics > *");
          if (dyn) pendingDynamic = dyn.nodeName === "other-dynamics" ? dyn.textContent ?? null : dyn.nodeName;
          for (const w of Array.from(el.querySelectorAll("direction-type > words"))) {
            if ((w.textContent ?? "").trim() === "?") pendingQ = w.getAttribute("enclosure") === "rectangle" ? "vu" : "u";
          }
          const reh = text(el, "direction-type > rehearsal");
          if (reh) bar.rehearsal = reh;
          const tempo = el.querySelector("sound[tempo]")?.getAttribute("tempo");
          if (tempo) bar.tempo_bpm = Math.round(Number(tempo));
        } else if (el.nodeName === "sound" && el.getAttribute("tempo")) {
          bar.tempo_bpm = Math.round(Number(el.getAttribute("tempo")));
        } else if (el.nodeName === "backup") {
          pos -= Number(text(el, "duration") ?? 0);
        } else if (el.nodeName === "forward") {
          pos += Number(text(el, "duration") ?? 0);
        } else if (el.nodeName === "note") {
          if (child(el, "grace")) continue;
          const dur = Number(text(el, "duration") ?? 0);
          const isChord = !!child(el, "chord");
          const onset = isChord ? lastOnset : pos;
          if (!isChord) {
            lastOnset = pos;
            pos += dur;
          }
          maxPos = Math.max(maxPos, pos);
          const pitchEl = child(el, "pitch");
          const written: Pitch | undefined = pitchEl
            ? { step: text(pitchEl, "step") ?? "C", alter: Number(text(pitchEl, "alter") ?? 0), octave: Number(text(pitchEl, "octave") ?? 4) }
            : undefined;
          if (isChord && lastEvent && written) {
            // Add to the previous event, turning it into a chord.
            const prev = lastEvent;
            const pitches = prev.pitches ?? (prev.written ? [{ written: prev.written, concert: prev.concert! }] : []);
            pitches.push({ written, concert: transposePitch(written, part.transpose) });
            pitches.sort((a, b) => midiOf(a.written) - midiOf(b.written));
            prev.kind = "chord";
            prev.pitches = pitches;
            continue;
          }
          if (isChord && lastEvent && child(el, "unpitched")) {
            const inst = child(el, "instrument")?.getAttribute("id");
            const nm = (inst && meta.instruments.get(inst)) || "drum";
            lastEvent.instruments = [...(lastEvent.instruments ?? []), nm];
            lastEvent.instruments_nb = [...(lastEvent.instruments_nb ?? []), NB_INSTRUMENTS[nm] ?? nm];
            continue;
          }
          const beatDiv = (divisions * 4) / beatType * (beatType === 8 && beats % 3 === 0 && beats > 3 ? 3 : 1);
          const beatIdx = Math.floor(onset / beatDiv) + 1;
          const off = onset - (beatIdx - 1) * beatDiv;
          const g = gcd(Math.round(off * 1000), Math.round(beatDiv * 1000)) || 1;
          const pos_: Pos = off === 0 ? { beat: beatIdx, num: 0, den: 1 } : { beat: beatIdx, num: Math.round(off * 1000) / g, den: Math.round(beatDiv * 1000) / g };
          const type = text(el, "type") ?? "quarter";
          const dots = el.querySelectorAll(":scope > dot").length;
          const tm = child(el, "time-modification");
          const tupStart = el.querySelector("notations > tuplet[type=start]");
          if (tupStart || !tm) tupletIndex = 0;
          const tuplet = tm ? { actual: Number(text(tm, "actual-notes") ?? 3), normal: Number(text(tm, "normal-notes") ?? 2), index: ++tupletIndex } : null;
          const ties = Array.from(el.querySelectorAll(":scope > tie")).map((t) => t.getAttribute("type"));
          const colour = el.getAttribute("color") ?? child(el, "notehead")?.getAttribute("color");
          const tick = barStart + Math.round((onset / divisions) * TPQ);
          const ev: NavEvent = {
            kind: child(el, "rest") ? "rest" : child(el, "unpitched") ? "unpitched" : "note",
            bar: index, tick, endTick: tick + Math.round((dur / divisions) * TPQ),
            pos: pos_, type, dots, tuplet,
            tie: ties.length ? { start: ties.includes("start"), stop: ties.includes("stop"), next: null, chain_beats: null } : null,
            articulations: [
              ...ARTICS.filter((a) => el.querySelector(`notations > articulations > ${a}`)),
              ...(el.querySelector("notations > fermata") ? ["fermata"] : []),
            ],
            dynamic: pendingDynamic,
            uncertain: colour?.toLowerCase() === "#b04a00" || (colour && pendingQ === "vu") ? "very" : !!(colour || pendingQ),
          };
          pendingDynamic = null;
          pendingQ = null;
          if (written) {
            ev.written = written;
            ev.concert = transposePitch(written, part.transpose);
          }
          if (ev.kind === "unpitched") {
            const inst = child(el, "instrument")?.getAttribute("id");
            const nm = (inst && meta.instruments.get(inst)) || "drum";
            ev.instruments = [nm];
            ev.instruments_nb = [NB_INSTRUMENTS[nm] ?? nm];
          }
          if (ev.kind === "rest") {
            const measureRest = child(el, "rest")?.getAttribute("measure") === "yes";
            if (measureRest || dur >= (beats * 4 * divisions) / beatType) {
              ev.kind = "bar-rest";
              ev.bars = 1;
            }
          }
          if (ev.tie?.stop) ev.skip = true;
          bar.events.push(ev);
          lastEvent = ev;
        }
      }
      bar.events.sort((a, b) => a.tick - b.tick);
      bar.key_fifths = fifths;
      if (part.transpose.chromatic) bar.concert_key_fifths = concertFifths(fifths, part.transpose.chromatic);
      bar.time = { beats, beat_type: beatType };
      const nominal = Math.round(((beats * 4) / beatType) * TPQ);
      const len = Math.max(nominal, Math.round((maxPos / divisions) * TPQ));
      bar.endTick = barStart + len;
      barStart += len;
      // A bar of only rests, in the voice we read, counts as a bar rest.
      if (bar.events.length && bar.events.every((e) => e.kind === "rest" || e.kind === "bar-rest") && bar.events.some((e) => e.kind === "bar-rest")) {
        bar.events = [bar.events.find((e) => e.kind === "bar-rest")!];
      }
      part.bars.push(bar);
    });
    linkTies(part);
    collapseRests(part);
    total = Math.max(total, part.bars.length);
    parts.push(part);
  }
  return { title, total_bars: total, parts };
}

function midiOf(p: Pitch): number {
  return 12 * (p.octave + 1) + NAT[STEPS.indexOf(p.step)] + p.alter;
}

/** Fill `tie.next` and `tie.chain_beats` on notes that start a tie. */
function linkTies(part: NavPart): void {
  const notes = part.bars.flatMap((b) => b.events).filter((e) => e.kind === "note");
  notes.forEach((e, i) => {
    if (!e.tie?.start || e.tie.stop || !e.written) return;
    const chain: NavEvent[] = [e];
    let cur = e;
    for (let j = i + 1; j < notes.length && cur.tie?.start; j++) {
      const n = notes[j];
      if (n.written && midiOf(n.written) === midiOf(cur.written!) && n.tie?.stop && n.tick >= cur.endTick - 1) {
        chain.push(n);
        cur = n;
      }
    }
    if (chain.length < 2) return;
    const next = chain[1];
    e.tie.next = { bar: part.bars[next.bar].number, type: next.type ?? "quarter", dots: next.dots ?? 0 };
    if (chain.length > 2) {
      const beatTicks = TPQ * (4 / (part.bars[e.bar].time?.beat_type ?? 4));
      e.tie.chain_beats = Math.round(((chain[chain.length - 1].endTick - e.tick) / beatTicks) * 2) / 2;
    }
  });
}

/** Runs of whole-bar rests become one event with `bars` = run length; the rest of the run is skipped by note navigation. */
function collapseRests(part: NavPart): void {
  let i = 0;
  while (i < part.bars.length) {
    const isRest = (b: NavBar) => b.events.length === 1 && b.events[0].kind === "bar-rest";
    if (!isRest(part.bars[i])) {
      i++;
      continue;
    }
    let j = i;
    while (j + 1 < part.bars.length && isRest(part.bars[j + 1]) && !part.bars[j + 1].key_change && !part.bars[j + 1].time_change) j++;
    part.bars[i].events[0].bars = j - i + 1;
    for (let k = i + 1; k <= j; k++) part.bars[k].events[0].skip = true;
    i = j + 1;
  }
}
