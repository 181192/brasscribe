// Minimal MusicXML reader for checks and summaries (alphaTab does the rendering).

export interface XmlNote {
  bar: number; // measure number as written
  barIndex: number; // 0-based measure index
  beat: number; // 1-based beat within the bar (quarter-note beats)
  onset: number; // divisions-independent position in quarters from the start
  written: number; // written MIDI pitch
  sounding: number; // concert MIDI pitch
  color?: string;
  parenthesised: boolean;
  /** Uncertainty the engine marked: "u" (a "?" above), "vu" (a boxed "?", confidence below 0.4). */
  level?: "u" | "vu";
}

export interface XmlPart {
  id: string;
  name: string;
  transpose: number; // semitones written -> sounding
  percussion: boolean;
  notes: XmlNote[];
  bars: number;
}

export interface XmlScore {
  title: string;
  parts: XmlPart[];
  bars: number;
  /** Free-time passages as bar-index ranges [from, to], from "ad lib." … "a tempo" words. */
  adlib: [number, number][];
}

// The engine's colour for "very uncertain" notes (design tokens, light theme).
const VERY_UNCERTAIN = "#b04a00";

const STEP: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

function text(el: Element | null | undefined, sel: string): string | null {
  const x = el?.querySelector(sel);
  return x ? (x.textContent ?? "").trim() : null;
}

export function parseMusicXml(xml: string): XmlScore {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.querySelector("parsererror")) throw new Error("not valid MusicXML");
  const root = doc.documentElement;
  if (root.nodeName === "score-timewise") throw new Error("timewise MusicXML is not supported");
  const title = text(root, "work > work-title") ?? text(root, "movement-title") ?? "";
  const names = new Map<string, string>();
  const unpitched = new Set<string>();
  for (const sp of Array.from(root.querySelectorAll("part-list > score-part"))) {
    names.set(sp.getAttribute("id") ?? "", text(sp, "part-name") ?? "");
  }
  const parts: XmlPart[] = [];
  const adlib: [number, number][] = [];
  let maxBars = 0;
  for (const p of Array.from(root.querySelectorAll(":scope > part"))) {
    const id = p.getAttribute("id") ?? "";
    let divisions = 1;
    let transpose = 0;
    let beats = 4;
    let beatType = 4;
    let barStart = 0; // quarters
    let percussion = false;
    const notes: XmlNote[] = [];
    const measures = Array.from(p.children).filter((c) => c.nodeName === "measure");
    measures.forEach((m, barIndex) => {
      const bar = Number(m.getAttribute("number")) || barIndex + 1;
      let pos = 0; // divisions from bar start
      let lastOnset = 0;
      let maxPos = 0;
      // A "?" words direction marks the next note's onset; a rectangle enclosure means very uncertain.
      let qMark: "u" | "vu" | null = null;
      for (const el of Array.from(m.children)) {
        switch (el.nodeName) {
          case "direction": {
            for (const w of Array.from(el.querySelectorAll("direction-type > words"))) {
              const txt = (w.textContent ?? "").trim().toLowerCase();
              if (txt === "?") qMark = w.getAttribute("enclosure") === "rectangle" ? "vu" : "u";
              if (parts.length === 0 && txt.startsWith("ad lib")) adlib.push([barIndex, measures.length - 1]);
              if (parts.length === 0 && txt.startsWith("a tempo") && adlib.length) {
                const last = adlib[adlib.length - 1];
                last[1] = Math.max(last[0], barIndex - 1);
              }
            }
            break;
          }
          case "attributes": {
            const d = text(el, "divisions");
            if (d) divisions = Number(d) || divisions;
            const chrom = text(el, "transpose > chromatic");
            if (chrom !== null) transpose = Number(chrom) + 12 * Number(text(el, "transpose > octave-change") ?? 0);
            const b = text(el, "time > beats");
            const bt = text(el, "time > beat-type");
            if (b) beats = Number(b) || beats;
            if (bt) beatType = Number(bt) || beatType;
            if (text(el, "clef > sign") === "percussion") percussion = true;
            break;
          }
          case "backup":
            pos -= Number(text(el, "duration") ?? 0);
            break;
          case "forward":
            pos += Number(text(el, "duration") ?? 0);
            break;
          case "note": {
            const dur = Number(text(el, "duration") ?? 0);
            const chord = el.querySelector(":scope > chord") !== null;
            const onsetDiv = chord ? lastOnset : pos;
            if (!chord) {
              lastOnset = pos;
              if (!el.querySelector(":scope > grace")) pos += dur;
            }
            maxPos = Math.max(maxPos, pos);
            const pitch = el.querySelector(":scope > pitch");
            if (el.querySelector(":scope > unpitched")) unpitched.add(id);
            if (!pitch) break;
            const written =
              12 * (Number(text(pitch, "octave")) + 1) + STEP[text(pitch, "step") ?? "C"] + Number(text(pitch, "alter") ?? 0);
            const q = onsetDiv / divisions;
            const nh = el.querySelector(":scope > notehead");
            const color = el.getAttribute("color") ?? nh?.getAttribute("color") ?? undefined;
            const level: XmlNote["level"] = color?.toLowerCase() === VERY_UNCERTAIN || (color && qMark === "vu") ? "vu" : color || qMark ? "u" : undefined;
            if (!chord) qMark = null;
            notes.push({
              bar,
              barIndex,
              beat: 1 + (q * beatType) / 4,
              onset: barStart + q,
              written,
              sounding: written + transpose,
              color,
              parenthesised: nh?.getAttribute("parentheses") === "yes",
              level,
            });
            break;
          }
        }
      }
      const nominal = (beats * 4) / beatType;
      barStart += Math.max(nominal, maxPos / divisions);
    });
    maxBars = Math.max(maxBars, measures.length);
    parts.push({ id, name: names.get(id) ?? id, transpose, percussion: percussion || unpitched.has(id), notes, bars: measures.length });
  }
  return { title, parts, bars: maxBars, adlib };
}

/** Count sounding notes per part, the same way the engine's golden comparison does. */
export function noteCounts(score: XmlScore): Record<string, number> {
  return Object.fromEntries(score.parts.map((p) => [p.name, p.notes.length]));
}
