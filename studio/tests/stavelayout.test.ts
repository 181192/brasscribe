import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseMusicXml } from "../src/lib/musicxml";
import { frettedProgram, makeDrawable, playsGeneral, readable, showsTab, staveLayout, STAVE_PROFILE, type StaffLike } from "../src/lib/stavelayout";
import type { Job, Manifest, ProfileInfo } from "../src/api/types";
import { isTabRun } from "../src/views/run";

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

  it("keeps the instrument a fretted part's file names", () => {
    // <midi-program> 27 in the file (a jazz guitar), whatever the part is called.
    expect(frettedProgram("Bass", GUITAR, 26, 26)).toBe(26);
    // The file has no <midi-instrument> for the part: alphaTab's default is not the file's choice.
    expect(frettedProgram("Guitar", GUITAR, null, 0)).toBe(25);
    // Compressed MusicXML is not read for it: a loaded program other than the default is the file's.
    expect(frettedProgram("Guitar", GUITAR, undefined, 30)).toBe(30);
    expect(frettedProgram("Guitar", GUITAR, undefined, 0)).toBe(25);
  });

  it("plays a tab with a drum part with the General MIDI set, and a band score with the band's", () => {
    const part = (percussion: boolean, band: boolean) => ({ percussion, band });
    // Guitar (no band sound) and drums (the band has a kit for any drum part).
    expect(playsGeneral([part(false, false), part(true, true)])).toBe(true);
    expect(playsGeneral([part(false, false)])).toBe(true);
    // Any pitched band part keeps the band's sounds, also beside a part the band does not have.
    expect(playsGeneral([part(false, true), part(false, false), part(true, true)])).toBe(false);
    // Percussion alone goes by whether the band has it.
    expect(playsGeneral([part(true, true)])).toBe(false);
    expect(playsGeneral([part(true, false)])).toBe(true);
  });

  it("reads a notation part aloud beside a tab part, and not a part with tablature", () => {
    expect(readable({ staves: [notation()] })).toBe(true);
    expect(readable({ staves: [tabOnly()] })).toBe(false);
    expect(readable({ staves: [notation(), tabOnly()] })).toBe(false);
  });
});

describe("a tab in the MusicXML reader", () => {
  // Each probe is one tab written three ways. With tablature under notation every note is written
  // twice and the "?" of an uncertain note once, over the tablature.
  const probes = readdirSync(join(fixtures, "tab-probes"), { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name);
  it.each(probes)("reads the same notes and uncertain marks from %s as notation, as tablature and as both", (probe) => {
    const notes = (file: string) => parseMusicXml(read(`tab-probes/${probe}/${file}`)).parts[0].notes.map((n) => [n.barIndex, n.onset, n.written, n.color, n.level]);
    const alone = notes("notation.musicxml");
    expect(alone.length).toBeGreaterThan(0);
    expect(notes("tab-and-notation.musicxml")).toEqual(alone);
    // The tablature alone leaves out a note that has no place on the fretboard (no-place-in-a-chord).
    const tab = notes("tab.musicxml");
    expect(alone).toEqual(expect.arrayContaining(tab));
    if (probe !== "no-place-in-a-chord") expect(tab).toHaveLength(alone.length);
  });

  it("reads a band score's uncertain marks as before", () => {
    const levels = (file: string) => parseMusicXml(read(file)).parts.flatMap((p) => p.notes.map((n) => n.level)).filter(Boolean);
    // Old Hundredth as the core arranges it: four notes marked.
    expect(levels("old-hundredth/brass-band.musicxml").sort()).toEqual(["u", "u", "u", "u"]);
  });

  it("has uncertain notes in the probes, so the comparison above checks their marks", () => {
    const levels = probes.flatMap((probe) => parseMusicXml(read(`tab-probes/${probe}/tab-and-notation.musicxml`)).parts[0].notes.map((n) => n.level));
    expect(levels.filter(Boolean).length).toBeGreaterThan(0);
  });
});

describe("which runs are tab runs", () => {
  const job = (profile: string, outputs: string[]) => ({ id: "x", profile, outputs }) as unknown as Job;
  const profiles = [{ name: "tab", pipeline: "tab" }, { name: "bass-tab", pipeline: "tab" }, { name: "solo", pipeline: "layered-solo" }] as unknown as ProfileInfo[];

  it("goes by the profile's pipeline, so a tab run that has written nothing yet is one", () => {
    expect(isTabRun(job("bass-tab", []), null, profiles)).toBe(true);
    expect(isTabRun(job("solo", []), null, profiles)).toBe(false);
    expect(isTabRun(job("renamed", []), { pipeline: "tab" } as unknown as Manifest, profiles)).toBe(true);
    expect(isTabRun(job("renamed", ["tab.musicxml"]), { pipeline: "A" } as unknown as Manifest, profiles)).toBe(false);
  });

  it("goes by what the run wrote when neither the manifest nor the profiles say", () => {
    expect(isTabRun(job("gone", ["tab.musicxml"]))).toBe(true);
    expect(isTabRun(job("gone", ["brass-band.musicxml"]))).toBe(false);
  });
});
