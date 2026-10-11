import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseMusicXml } from "../src/lib/musicxml";
import { frettedProgram, makeDrawable, showsTab, staveLayout, STAVE_PROFILE, type StaffLike } from "../src/lib/stavelayout";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "apps", "fixtures");
const read = (path: string) => readFileSync(join(fixtures, path), "utf8");

const GUITAR = [64, 59, 55, 50, 45, 40];
const staff = (s: Partial<StaffLike>): StaffLike => ({ showTablature: false, showStandardNotation: true, isPercussion: false, tuning: [], ...s });
/** The staves as alphaTab reads them from MusicXML: a staff with `staff-tuning` shows tablature only. */
const tabOnly = () => staff({ showTablature: true, showStandardNotation: false, tuning: GUITAR });
const notation = () => staff({});

describe("what a score's staves show", () => {
  it("is tablature for a tab-only part, notation for a band score, and both for the two together", () => {
    expect(staveLayout([{ staves: [tabOnly()] }])).toBe("tab");
    expect(staveLayout([{ staves: [notation()] }, { staves: [notation()] }])).toBe("notation");
    expect(staveLayout([{ staves: [notation(), tabOnly()] }])).toBe("tab-and-notation");
    // A band part and a tab part in one file: each is drawn as it is written.
    expect(staveLayout([{ staves: [notation()] }, { staves: [tabOnly()] }])).toBe("tab-and-notation");
  });

  it("names the stave profile that draws it: a tab under the notation profile has no staff to draw", () => {
    expect(STAVE_PROFILE).toEqual({ notation: "Score", tab: "Tab", "tab-and-notation": "ScoreTab" });
  });

  it("does not count tablature without a tuning, or on a percussion staff, which alphaTab cannot draw", () => {
    expect(showsTab(staff({ showTablature: true }))).toBe(false);
    expect(showsTab(staff({ showTablature: true, tuning: GUITAR, isPercussion: true }))).toBe(false);
    expect(staveLayout([{ staves: [staff({ showTablature: true })] }])).toBe("notation");
  });

  it("draws a staff that asks for nothing as notation, so no track is left without a staff", () => {
    const tracks = [{ staves: [staff({ showTablature: true, showStandardNotation: false })] }, { staves: [tabOnly()] }];
    makeDrawable(tracks);
    expect(tracks[0].staves[0].showStandardNotation).toBe(true);
    expect(tracks[1].staves[0].showStandardNotation).toBe(false);
    expect(staveLayout(tracks)).toBe("tab-and-notation");
  });

  it("plays a fretted part with no instrument in its file as a guitar, or as a bass", () => {
    expect(frettedProgram("Guitar", GUITAR)).toBe(25);
    expect(frettedProgram("Bass", [43, 38, 33, 28])).toBe(33);
    expect(frettedProgram("", [43, 38, 33, 28])).toBe(33);
    expect(frettedProgram("Ukulele", [69, 64, 60, 67])).toBe(25);
  });
});

describe("a tab in the MusicXML reader", () => {
  it("marks a part with a tablature staff", () => {
    const tab = parseMusicXml(read("guitar-line/tab.musicxml"));
    expect(tab.parts.map((p) => [p.name, p.tab])).toEqual([["Guitar", true]]);
    expect(parseMusicXml(read("old-hundredth/brass-band.musicxml")).parts.every((p) => !p.tab)).toBe(true);
  });

  it("counts each note once when the tablature sits under a notation staff", () => {
    const probe = "tab-probes/chords";
    const notes = (file: string) => parseMusicXml(read(`${probe}/${file}`)).parts[0].notes;
    const alone = notes("notation.musicxml");
    const both = notes("tab-and-notation.musicxml");
    expect(alone.length).toBeGreaterThan(0);
    expect(both.map((n) => [n.barIndex, n.onset, n.written, n.color])).toEqual(alone.map((n) => [n.barIndex, n.onset, n.written, n.color]));
    // The uncertain notes keep their mark (the colour is on both staves; the "?" word is over the tablature).
    expect(both.filter((n) => n.level).length).toBe(both.filter((n) => n.color).length);
    expect(notes("tab.musicxml")).toHaveLength(alone.length);
  });
});
