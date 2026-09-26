import { describe, expect, it } from "vitest";
import { lang, messages, onLangChange, setLang, t } from "../src/i18n";
import { parseMusicXml } from "../src/lib/musicxml";
import { diffParts } from "../src/lib/xmldiff";

describe("i18n", () => {
  it("has every key in both languages, none empty", () => {
    const en = Object.keys(messages.en);
    const nb = Object.keys(messages.nb);
    expect(nb.sort()).toEqual(en.sort());
    for (const l of ["en", "nb"] as const) {
      for (const [k, v] of Object.entries(messages[l])) expect(v.trim(), `${l} ${k}`).not.toBe("");
    }
  });

  it("keeps the same placeholders in both languages", () => {
    const ph = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
    for (const k of Object.keys(messages.en) as (keyof typeof messages.en)[]) {
      expect(ph(messages.nb[k]), k).toBe(ph(messages.en[k]));
    }
  });

  it("switches language, fills placeholders and notifies listeners", () => {
    const seen: string[] = [];
    const off = onLangChange((l) => seen.push(l));
    setLang("en");
    expect(t("runs.count", { shown: 2, total: 7 })).toBe("2 of 7 runs");
    setLang("nb");
    expect(lang()).toBe("nb");
    expect(t("runs.count", { shown: 2, total: 7 })).toBe("2 av 7 kjøringer");
    expect(t("no.such.key")).toBe("no.such.key");
    setLang("en");
    off();
    expect(seen).toEqual(["nb", "en"]);
  });
});

const part = (notes: string) => `<?xml version="1.0"?><score-partwise><part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>${notes}</measure></part></score-partwise>`;
const note = (step: string, oct: number) => `<note><pitch><step>${step}</step><octave>${oct}</octave></pitch><duration>1</duration></note>`;
const rest = `<note><rest/><duration>1</duration></note>`;

describe("notation diff", () => {
  it("marks removed, added, octave and moved notes on both sides", () => {
    const a = parseMusicXml(part(note("C", 5) + note("D", 5) + note("E", 5) + rest)).parts[0];
    const b = parseMusicXml(part(note("C", 5) + note("D", 6) + rest + note("E", 5))).parts[0];
    const d = diffParts(a, b);
    expect(d.a).toEqual([null, "octave", "moved"]);
    expect(d.b).toEqual([null, "octave", "moved"]);
    expect(d.bars).toEqual([0]);
    const c = parseMusicXml(part(note("C", 5) + note("G", 4) + rest + rest)).parts[0];
    const d2 = diffParts(a, c, 0);
    expect(d2.a).toEqual([null, "removed", "removed"]);
    expect(d2.b).toEqual([null, "added"]);
    expect(d2.perBar.get(0)).toEqual({ a: 2, b: 1 });
  });
});
