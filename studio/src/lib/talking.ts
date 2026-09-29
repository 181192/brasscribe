// Talking score announcer (docs/accessibility/talking-score-spec.md), checked
// against docs/accessibility/talking-score-vectors.json. It mirrors the core's
// announce() so Studio speaks the same words as the Play apps.

export type Lang = "en" | "nb";
export type Verbosity = "brief" | "standard" | "full";
export type PitchMode = "written" | "concert";

export interface Settings {
  verbosity: Verbosity;
  pitch_mode: PitchMode;
  announce_confident?: boolean;
}

export interface Pitch {
  step: string;
  alter: number;
  octave: number;
}

export interface Pos {
  beat: number;
  num: number;
  den: number;
}

export interface TsEvent {
  kind: "note" | "rest" | "bar-rest" | "chord" | "unpitched" | "held" | "mode-change";
  tick?: number;
  pos?: Pos;
  type?: string;
  dots?: number;
  tuplet?: { actual: number; normal: number; index: number } | null;
  tie?: { start?: boolean; stop?: boolean; next?: { bar: number; type: string; dots: number } | null; chain_beats?: number | null } | null;
  written?: Pitch;
  concert?: Pitch;
  pitches?: { written: Pitch; concert: Pitch }[];
  instruments?: string[];
  instruments_nb?: string[];
  articulations?: string[];
  dynamic?: string | null;
  confidence?: number | null;
  /** Marked uncertain without a confidence value (e.g. a coloured MusicXML note). */
  uncertain?: boolean | "very";
  sources?: string[];
  checked?: boolean;
  time_s?: number | null;
  performed_s?: number | null;
  held_from?: { bar: number } & Pos;
  bars?: number;
}

export interface FreeRegionRef {
  start_bar: number;
  end_bar: number;
  start_s: number;
  end_s: number;
  entering?: boolean;
  notation?: string;
}

export interface TsBar {
  number: number;
  key_fifths?: number;
  /** Concert key when the part transposes (for "natural" in concert pitch). */
  concert_key_fifths?: number;
  /** Key or time change printed at this bar (announced as bar_change). */
  key_change?: boolean;
  time?: { beats: number; beat_type: number } | null;
  time_change?: boolean;
  tempo_bpm?: number | null;
  rehearsal?: string | null;
  a_tempo?: boolean;
  free_region?: FreeRegionRef | null;
}

export interface TsPart {
  name: string;
  name_nb?: string;
  instrument?: string;
  instrument_nb?: string;
}

export interface Context {
  part?: string | null;
  bar?: number | null;
  pitch_mode?: PitchMode;
  /** Force the bar to be spoken (navigation by bar). */
  by_bar?: boolean;
}

export interface Request {
  settings: Settings;
  context: Context;
  bar?: TsBar;
  part?: TsPart;
  event: TsEvent;
  total_bars?: number;
  /** Key used for "natural" when the bar carries none (the vectors' default: 2 sharps). */
  default_key_fifths?: number;
}

const round = (x: number) => Math.floor(x + 0.5);
const num = (x: number, lang: Lang) => (lang === "nb" ? String(x).replace(".", ",") : String(x));

// ---------------------------------------------------------------- pitch

const SHARPS = ["F", "C", "G", "D", "A", "E", "B"];
const FLATS = ["B", "E", "A", "D", "G", "C", "F"];

export function keyAlter(fifths: number, step: string): number {
  if (fifths > 0) return SHARPS.slice(0, fifths).includes(step) ? 1 : 0;
  if (fifths < 0) return FLATS.slice(0, -fifths).includes(step) ? -1 : 0;
  return 0;
}

const NB_NAMES: Record<string, Record<number, string>> = {
  C: { 0: "C", 1: "Ciss", [-1]: "Cess" },
  D: { 0: "D", 1: "Diss", [-1]: "Dess" },
  E: { 0: "E", 1: "Eiss", [-1]: "Ess" },
  F: { 0: "F", 1: "Fiss", [-1]: "Fess" },
  G: { 0: "G", 1: "Giss", [-1]: "Gess" },
  A: { 0: "A", 1: "Aiss", [-1]: "Ass" },
  B: { 0: "H", 1: "Hiss", [-1]: "B" },
};

export function pitchWords(p: Pitch, lang: Lang, keyFifths: number): string {
  if (lang === "nb") {
    let name: string;
    if (p.alter === 2) name = `${NB_NAMES[p.step][0]} dobbeltkryss`;
    else if (p.alter === -2) name = `${NB_NAMES[p.step][0]} dobbelt-b`;
    else name = NB_NAMES[p.step]?.[p.alter] ?? p.step;
    return `${name} ${p.octave}`;
  }
  const acc: Record<number, string> = { 1: "-sharp", [-1]: "-flat", 2: "-double-sharp", [-2]: "-double-flat" };
  let a = acc[p.alter] ?? "";
  if (p.alter === 0 && keyAlter(keyFifths, p.step) !== 0) a = "-natural";
  return `${p.step}${a} ${p.octave}`;
}

// ---------------------------------------------------------------- durations

const TYPES: Record<string, { en: string; enBrief: string; nb: string; nbBrief: string }> = {
  breve: { en: "double whole note", enBrief: "double whole", nb: "brevis", nbBrief: "brevis" },
  whole: { en: "whole note", enBrief: "whole", nb: "helnote", nbBrief: "hel" },
  half: { en: "half note", enBrief: "half", nb: "halvnote", nbBrief: "halv" },
  quarter: { en: "quarter note", enBrief: "quarter", nb: "fjerdedelsnote", nbBrief: "fjerdedel" },
  eighth: { en: "eighth note", enBrief: "eighth", nb: "åttendedelsnote", nbBrief: "åttendedel" },
  "16th": { en: "sixteenth note", enBrief: "sixteenth", nb: "sekstendedelsnote", nbBrief: "sekstendedel" },
  "32nd": { en: "thirty-second note", enBrief: "thirty-second", nb: "trettitodelsnote", nbBrief: "trettitodel" },
  "64th": { en: "sixty-fourth note", enBrief: "sixty-fourth", nb: "sekstifiredelsnote", nbBrief: "sekstifiredel" },
};

function dotsWord(dots: number, lang: Lang): string {
  if (!dots) return "";
  if (lang === "nb") return dots === 1 ? "punktert " : "dobbeltpunktert ";
  return dots === 1 ? "dotted " : "double-dotted ";
}

export function duration(type: string, dots: number, lang: Lang, brief = false): string {
  const t = TYPES[type] ?? { en: type, enBrief: type, nb: type, nbBrief: type };
  const word = lang === "nb" ? (brief ? t.nbBrief : t.nb) : brief ? t.enBrief : t.en;
  return `${dotsWord(dots, lang)}${word}`;
}

function restWord(type: string, dots: number, lang: Lang): string {
  const t = TYPES[type] ?? { en: type, enBrief: type, nb: type, nbBrief: type };
  if (lang === "nb") return `${dotsWord(dots, lang)}${t.nbBrief}${t.nbBrief.endsWith("del") ? "spause" : "pause"}`;
  return `${dotsWord(dots, lang)}${t.enBrief} rest`;
}

// ---------------------------------------------------------------- positions

/** "beat 2 and" / "slag 2-og"; `word` false gives the short form ("2 and"). */
export function position(p: Pos, lang: Lang, word = true): string {
  const w = word ? (lang === "nb" ? "slag " : "beat ") : "";
  const b = `${w}${p.beat}`;
  const f = p.num === 0 ? 0 : p.num / p.den;
  const is = (n: number, d: number) => p.num * d === n * p.den;
  if (f === 0) return b;
  if (is(1, 2)) return lang === "nb" ? `${b}-og` : `${b} and`;
  if (is(1, 4)) return lang === "nb" ? `${b}, 2. av 4` : `${b} e`;
  if (is(3, 4)) return lang === "nb" ? `${b}, 4. av 4` : `${b} a`;
  if (is(1, 3)) return lang === "nb" ? `${b}, triol 2` : `${b}, triplet 2`;
  if (is(2, 3)) return lang === "nb" ? `${b}, triol 3` : `${b}, triplet 3`;
  return lang === "nb" ? `${b} pluss ${p.num}/${p.den}` : `${b} plus ${p.num}/${p.den}`;
}

function timePosition(seconds: number, lang: Lang): string {
  const s = round(seconds);
  if (s < 60) return lang === "nb" ? `ved ${s} sekunder` : `at ${s} seconds`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (lang === "nb") return `ved ${m} ${m === 1 ? "minutt" : "minutter"} ${r} sekunder`;
  return `at ${m} ${m === 1 ? "minute" : "minutes"} ${r} seconds`;
}

// ---------------------------------------------------------------- bar and part

function keyWords(fifths: number, lang: Lang): string {
  if (fifths === 0) return lang === "nb" ? "ingen faste fortegn" : "no sharps or flats";
  const n = Math.abs(fifths);
  if (lang === "nb") return `${n} ${fifths > 0 ? "kryss" : "b"}`;
  return `key ${n} ${fifths > 0 ? (n === 1 ? "sharp" : "sharps") : n === 1 ? "flat" : "flats"}`;
}

function timeWords(t: { beats: number; beat_type: number }, lang: Lang): string {
  if (lang === "en") return `${t.beats} ${t.beat_type} time`;
  const nb: Record<number, string> = { 1: "hel", 2: "halv", 4: "fjerdedels", 8: "åttendedels", 16: "sekstendedels" };
  return `${t.beats} ${nb[t.beat_type] ?? `${t.beat_type}-dels`} takt`;
}

function barPart(bar: TsBar, lang: Lang, full: boolean, total: number | undefined, partChanged: boolean, skipTempo: boolean): string {
  let s = `${lang === "nb" ? "takt" : "bar"} ${bar.number}`;
  if (full && total) s += ` ${lang === "nb" ? "av" : "of"} ${total}`;
  const changes: string[] = [];
  if ((bar.key_change || partChanged) && bar.key_fifths !== undefined) changes.push(keyWords(bar.key_fifths, lang));
  if (bar.time_change && bar.time) changes.push(timeWords(bar.time, lang));
  if (bar.tempo_bpm && !skipTempo && !bar.a_tempo) changes.push(`tempo ${bar.tempo_bpm}`);
  if (bar.rehearsal) changes.push(`${lang === "nb" ? "øvingsbokstav" : "rehearsal"} ${bar.rehearsal}`);
  return [s, ...changes].join(", ");
}

// ---------------------------------------------------------------- modifiers

const ARTIC: Record<string, { en: string; nb: string }> = {
  staccato: { en: "staccato", nb: "staccato" },
  accent: { en: "accent", nb: "aksent" },
  tenuto: { en: "tenuto", nb: "tenuto" },
  marcato: { en: "marcato", nb: "marcato" },
  "strong-accent": { en: "marcato", nb: "marcato" },
  fermata: { en: "fermata", nb: "fermat" },
  trill: { en: "trill", nb: "trille" },
  "trill-sharp": { en: "trill with sharp", nb: "trille med kryss" },
  "trill-flat": { en: "trill with flat", nb: "trille med b" },
  "trill-natural": { en: "trill with natural", nb: "trille med oppløsningstegn" },
  "trill-double-sharp": { en: "trill with double sharp", nb: "trille med dobbeltkryss" },
  "trill-flat-flat": { en: "trill with double flat", nb: "trille med dobbelt-b" },
};

const DYN: Record<string, string> = {
  ppp: "pianississimo", pp: "pianissimo", p: "piano", mp: "mezzo-piano", mf: "mezzo-forte", f: "forte", ff: "fortissimo", fff: "fortississimo",
  sf: "sforzando", sfz: "sforzando", fp: "fortepiano",
};

const SOURCES: Record<string, string> = {
  swiftf0: "SwiftF0", "swift-f0": "SwiftF0", muscriptor: "MuScriptor", "basic-pitch": "Basic Pitch", mega53: "Mega-53", "beat-this": "Beat This",
};

function halves(beats: number, lang: Lang): string {
  const whole = Math.floor(beats);
  const half = Math.abs(beats - whole - 0.5) < 1e-9;
  if (!half) return num(round(beats * 100) / 100, lang);
  return lang === "nb" ? `${whole} og et halvt` : `${whole} and a half`;
}

function modifiers(e: TsEvent, bar: TsBar | undefined, s: Settings, lang: Lang, freeTime: boolean): string[] {
  const out: string[] = [];
  const t = e.tie;
  if (t?.start) {
    if (t.chain_beats != null) out.push(lang === "nb" ? `bundet, ${halves(t.chain_beats, lang)} slag i alt` : `tied, ${halves(t.chain_beats, lang)} beats in all`);
    else if (t.next) {
      const where = bar && t.next.bar !== bar.number ? (lang === "nb" ? ` i takt ${t.next.bar}` : ` in bar ${t.next.bar}`) : "";
      out.push(`${lang === "nb" ? "bundet til" : "tied to"} ${duration(t.next.type, t.next.dots, lang)}${where}`);
    }
  }
  const tu = e.tuplet;
  if (tu) {
    if (tu.actual === 3 && tu.normal === 2) out.push(lang === "nb" ? `triol, ${tu.index} av 3` : `triplet, ${tu.index} of 3`);
    else out.push(lang === "nb" ? `${tu.actual} på ${tu.normal}, ${tu.index} av ${tu.actual}` : `${tu.actual} in the time of ${tu.normal}, ${tu.index} of ${tu.actual}`);
  }
  for (const a of e.articulations ?? []) out.push(ARTIC[a]?.[lang] ?? a);
  if (e.dynamic) out.push(DYN[e.dynamic] ?? e.dynamic);
  if (freeTime && e.performed_s != null && e.performed_s >= 1.0) {
    const x = round(e.performed_s * 2) / 2;
    out.push(lang === "nb" ? `holdes omtrent ${num(x, lang)} sekunder` : `held about ${num(x, lang)} seconds`);
  }
  if (!e.checked) {
    const c = e.confidence;
    if (c != null) {
      if (c < 0.4) out.push(lang === "nb" ? "svært usikker" : "very uncertain");
      else if (c < 0.7) out.push(lang === "nb" ? "usikker" : "uncertain");
      else if (s.verbosity === "full" && s.announce_confident) out.push(lang === "nb" ? "sikker" : "confident");
      if (s.verbosity === "full") {
        const srcs = (e.sources ?? []).map((x) => SOURCES[x] ?? x);
        const pct = `${lang === "nb" ? "sikkerhet" : "confidence"} ${round(c * 100)} ${lang === "nb" ? "prosent" : "percent"}`;
        out.push(srcs.length
          ? `${pct}, ${lang === "nb" ? (srcs.length > 1 ? "kilder" : "kilde") : srcs.length > 1 ? "sources" : "source"} ${srcs.join(lang === "nb" ? " og " : " and ")}`
          : pct);
      }
    } else if (e.uncertain === "very") out.push(lang === "nb" ? "svært usikker" : "very uncertain");
    else if (e.uncertain) out.push(lang === "nb" ? "usikker" : "uncertain");
  }
  return out;
}

// ---------------------------------------------------------------- announce

function instrumentWords(name: string, lang: Lang): string {
  if (lang === "nb") return name;
  return name.replace(/([A-G])♭/g, "$1-flat").replace(/([A-G])♯/g, "$1-sharp");
}

export function announce(r: Request, lang: Lang): string {
  const { settings: s, context: ctx, bar, event: e } = r;
  const brief = s.verbosity === "brief";
  const full = s.verbosity === "full";

  if (e.kind === "mode-change") {
    if (s.pitch_mode === "concert") return lang === "nb" ? "Klingende tone" : "Concert pitch";
    const inst = lang === "nb" ? r.part?.instrument_nb ?? r.part?.instrument : r.part?.instrument;
    const head = lang === "nb" ? "Skrevet tone" : "Written pitch";
    return inst ? `${head}, ${instrumentWords(inst, lang)}` : head;
  }

  const partName = r.part ? (lang === "nb" ? r.part.name_nb ?? r.part.name : r.part.name) : null;
  const partChanged = !!r.part && ctx.part != null && r.part.name !== ctx.part;
  const region = bar?.free_region && bar.free_region.notation !== "tempo" ? bar.free_region : null;
  const sentences: string[] = [];
  if (bar?.free_region?.entering) {
    const fr = bar.free_region;
    const secs = round(fr.end_s - fr.start_s);
    sentences.push(lang === "nb"
      ? `Ad lib, fritt tempo, takt ${fr.start_bar} til ${fr.end_bar}, omtrent ${secs} sekunder.`
      : `Ad lib, free time, bars ${fr.start_bar} to ${fr.end_bar}, about ${secs} seconds.`);
  }
  if (bar?.a_tempo && bar.tempo_bpm) {
    sentences.push(lang === "nb" ? `A tempo, ${bar.tempo_bpm} slag per minutt.` : `A tempo, ${bar.tempo_bpm} beats per minute.`);
  }
  if (partChanged && partName) sentences.push(`${partName}.`);

  const showBar = !!bar && (ctx.bar !== bar.number || partChanged || !!ctx.by_bar || !!bar.free_region?.entering);
  const keyFifths = bar?.key_fifths ?? r.default_key_fifths ?? 0;
  const barText = bar ? barPart(bar, lang, full, r.total_bars, partChanged, !!bar.a_tempo) : "";

  let location: string;
  let body: string;
  if (e.kind === "bar-rest") {
    const n = e.bars ?? 1;
    if (n > 1 && bar) {
      location = lang === "nb" ? `takt ${bar.number} til ${bar.number + n - 1}` : `bars ${bar.number} to ${bar.number + n - 1}`;
      body = lang === "nb" ? `pause, ${n} takter` : `rest, ${n} bars`;
    } else {
      location = barText;
      body = lang === "nb" ? "pause hele takten" : "rest, whole bar";
    }
    return [...sentences, `${location}: ${body}`].join(" ");
  }

  const pos = e.pos ?? { beat: 1, num: 0, den: 1 };
  const where = region && e.time_s != null ? timePosition(e.time_s, lang) : brief ? position(pos, lang, false) : position(pos, lang);
  location = showBar ? `${barText}, ${where}` : where;

  const pitchOf = (w?: Pitch, c?: Pitch): string => {
    if (!w && !c) return "";
    if (full && w && c) {
      return lang === "nb"
        ? `skrevet ${pitchWords(w, lang, keyFifths)}, klinger ${pitchWords(c, lang, bar?.concert_key_fifths ?? keyFifths)}`
        : `written ${pitchWords(w, lang, keyFifths)}, sounds ${pitchWords(c, lang, bar?.concert_key_fifths ?? keyFifths)}`;
    }
    if (s.pitch_mode === "concert" && c) return pitchWords(c, lang, bar?.concert_key_fifths ?? keyFifths);
    return pitchWords(w ?? c!, lang, keyFifths);
  };
  const dur = (sep: string) => (e.type ? `${sep}${duration(e.type, e.dots ?? 0, lang, brief)}` : "");

  switch (e.kind) {
    case "note":
      body = `${pitchOf(e.written, e.concert)}${dur(brief ? " " : ", ")}`;
      break;
    case "held": {
      const hf = e.held_from;
      const from = hf
        ? `${lang === "nb" ? "fra" : "from"} ${hf.bar !== bar?.number ? `${lang === "nb" ? "takt" : "bar"} ${hf.bar} ` : ""}${position(hf, lang)}`
        : "";
      body = `${pitchOf(e.written, e.concert)} ${lang === "nb" ? "holdes" : "held"}${from ? `, ${from}` : ""}`;
      break;
    }
    case "rest":
      body = restWord(e.type ?? "quarter", e.dots ?? 0, lang);
      break;
    case "chord": {
      const ps = (e.pitches ?? []).map((x) => pitchOf(x.written, x.concert));
      body = `${lang === "nb" ? "akkord" : "chord"}, ${ps.length} ${lang === "nb" ? "toner" : "notes"}: ${ps.join(", ")}${dur(", ")}`;
      break;
    }
    case "unpitched": {
      const names = lang === "nb" ? e.instruments_nb ?? e.instruments ?? [] : e.instruments ?? [];
      body = `${names.join(lang === "nb" ? " og " : " and ")}${dur(", ")}`;
      break;
    }
    default:
      body = "";
  }
  const mods = e.kind === "rest" || e.kind === "held" ? [] : modifiers(e, bar, s, lang, !!region);
  return [...sentences, `${location}: ${[body, ...mods].join(", ")}`].join(" ");
}
