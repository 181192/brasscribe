import { describe, expect, it } from "vitest";
import type { Composition, Job, Note } from "../src/api/types";
import { compositionBeats, compositionFreeTime, irregularRegions, parseBeats, summarise, tickTime } from "../src/lib/beats";
import { diffCompositions, diffNotes } from "../src/lib/diff";
import { energy, fft, peaks, spectrogram } from "../src/lib/dsp";
import { fromJob, reduce, totals } from "../src/lib/events";
import { parseMidi } from "../src/lib/midi";
import { parseMusicXml } from "../src/lib/musicxml";
import { checkCrossing, checkRanges, pitchName, validateScore } from "../src/lib/validate";

const n = (pitch: number, start: number, dur = 24): Note => ({ pitch, start, dur });

describe("beats", () => {
  it("parses Beat This! output", () => {
    const b = parseBeats("2.94\t1\n8.92\t2\n\n10.3 1\nbad line\n");
    expect(b).toEqual([
      { time: 2.94, position: 1 },
      { time: 8.92, position: 2 },
      { time: 10.3, position: 1 },
    ]);
  });

  it("derives bar positions from a composition's beat grid", () => {
    const c: Composition = {
      title: "t", voices: [], keys: [], meters: [{ tick: 0, beats: 3 }],
      beat_times: [0, 0.5, 1, 1.5, 2, 2.5], first_downbeat: 1, ticks_per_beat: 24,
    };
    // beat_times[1] is tick 0, so it is the downbeat; beat 0 is the last beat of the pickup bar.
    expect(compositionBeats(c).map((b) => b.position)).toEqual([3, 1, 2, 3, 1, 2]);
    expect(tickTime(c, 24)).toBeCloseTo(1);
    expect(tickTime(c, 36)).toBeCloseTo(1.25);
  });

  it("summarises tempo", () => {
    const beats = Array.from({ length: 9 }, (_, i) => ({ time: i * 0.5, position: (i % 4) + 1 }));
    const s = summarise(beats);
    expect(s.bpm).toBeCloseTo(120);
    expect(s.barBeats).toBe(4);
    expect(s.downbeats).toBe(3);
  });

  it("finds irregular passages and ignores steady ones", () => {
    const times = [0, 0.5, 1, 1.5, 2, 2.5, 3.6, 4.0, 5.5, 5.8, 7.2, 7.7, 8.2, 8.7, 9.2, 9.7, 10.2];
    const regions = irregularRegions(times.map((time) => ({ time, position: 1 })));
    expect(regions.length).toBe(1);
    expect(regions[0].start).toBeGreaterThanOrEqual(2.5);
    expect(regions[0].end).toBeLessThanOrEqual(7.7);
    const steady = Array.from({ length: 20 }, (_, i) => ({ time: i * 0.5, position: 1 }));
    expect(irregularRegions(steady)).toEqual([]);
  });

  it("reads free regions from the composition", () => {
    const c: Composition = {
      title: "t", voices: [], keys: [], meters: [],
      free_regions: [{ start: 0, end: 96, start_s: 0, end_s: 7.5, tempo_bpm: 40, label: "ad lib." }],
    };
    expect(compositionFreeTime(c)[0]).toMatchObject({ start: 0, end: 7.5, label: "ad lib.", source: "composition" });
  });
});

describe("note diff", () => {
  it("classifies same, octave, moved, added and removed", () => {
    const a = [n(60, 0), n(62, 24), n(64, 48), n(65, 72), n(67, 96)];
    const b = [n(60, 0), n(74, 24), n(64, 54), n(67, 96), n(69, 120)];
    const d = diffNotes("v", a, b, 24);
    expect(d.counts).toEqual({ same: 2, octave: 1, moved: 1, removed: 1, added: 1 });
    expect(d.changes.find((c) => c.kind === "removed")?.a?.pitch).toBe(65);
    expect(d.changes.find((c) => c.kind === "added")?.b?.pitch).toBe(69);
  });

  it("does not call a far-away note moved", () => {
    const d = diffNotes("v", [n(60, 0)], [n(60, 200)], 24);
    expect(d.counts.moved).toBe(0);
    expect(d.counts.added + d.counts.removed).toBe(2);
  });

  it("diffs whole compositions per voice and totals them", () => {
    const base: Composition = { title: "a", keys: [], meters: [], voices: [{ id: "solo", role: "melody", notes: [n(60, 0)] }] };
    const other: Composition = {
      ...base,
      voices: [
        { id: "solo", role: "melody", notes: [n(60, 0), n(62, 24)] },
        { id: "bass", role: "bass", notes: [n(36, 0)] },
      ],
    };
    const d = diffCompositions(base, other);
    expect(d.voices.map((v) => v.voice)).toEqual(["solo", "bass"]);
    expect(d.totals).toMatchObject({ same: 1, added: 2, removed: 0 });
  });
});

describe("events", () => {
  const job: Job = {
    id: "r1", profile: "p", status: "queued", created: 0, progress: 0, outputs: [],
    stages: [
      { name: "beats", kind: "beats", status: "pending" },
      { name: "stems", kind: "stems", status: "pending" },
    ],
  };

  it("folds stage events into timings, devices and cache hits", () => {
    let v = fromJob(job);
    v = reduce(v, { id: 0, run: "r1", type: "job", status: "running" });
    v = reduce(v, { id: 1, run: "r1", type: "stage", stage: "beats", status: "started", time: 10 });
    v = reduce(v, { id: 2, run: "r1", type: "stage", stage: "beats", status: "cached", seconds: 0.01, device: "mps" });
    v = reduce(v, { id: 3, run: "r1", type: "stage", stage: "stems", status: "ran", seconds: 12.5, device: "cuda" });
    expect(v.status).toBe("running");
    expect(v.stages[0]).toMatchObject({ status: "cached", cacheHit: true, device: "mps", startedAt: 10 });
    expect(v.stages[1]).toMatchObject({ status: "ran", cacheHit: false, seconds: 12.5 });
    expect(totals(v)).toEqual({ done: 2, total: 2, cached: 1, seconds: 12.51 });
  });

  it("ignores replayed events after a reconnect", () => {
    let v = reduce(fromJob(job), { id: 5, run: "r1", type: "job", status: "running" });
    v = reduce(v, { id: 5, run: "r1", type: "job", status: "failed" });
    expect(v.status).toBe("running");
  });

  it("records failures and log lines", () => {
    let v = reduce(fromJob(job), { id: 0, run: "r1", type: "stage", stage: "stems", status: "failed", error: "boom" });
    v = reduce(v, { id: 1, run: "r1", type: "log", message: "hello" });
    v = reduce(v, { id: 2, run: "r1", type: "job", status: "failed", error: "stems failed" });
    expect(v.log).toEqual(["stems: boom", "hello"]);
    expect(v.error).toBe("stems failed");
  });
});

describe("midi", () => {
  // Format 0, 96 ticks per quarter, tempo 120 bpm: C4 for one quarter, then E4 (running status) for two.
  const bytes = [
    ...[0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 0, 0, 1, 0, 96],
    ...[0x4d, 0x54, 0x72, 0x6b, 0, 0, 0, 27],
    ...[0x00, 0xff, 0x51, 0x03, 0x07, 0xa1, 0x20], // tempo 500000 us
    ...[0x00, 0x90, 60, 100],
    ...[0x60, 0x80, 60, 0],
    ...[0x00, 0x90, 64, 90],
    ...[0x81, 0x40, 64, 0], // running status note-on velocity 0 = off, delta 192
    ...[0x00, 0xff, 0x2f, 0x00],
  ];
  it("reads notes in seconds", () => {
    const m = parseMidi(new Uint8Array(bytes).buffer);
    expect(m.ticksPerQuarter).toBe(96);
    expect(m.notes).toHaveLength(2);
    expect(m.notes[0]).toMatchObject({ pitch: 60, velocity: 100, start: 0, end: 0.5 });
    expect(m.notes[1].pitch).toBe(64);
    expect(m.notes[1].start).toBeCloseTo(0.5);
    expect(m.notes[1].end).toBeCloseTo(1.5);
  });
  it("rejects other files", () => {
    expect(() => parseMidi(new Uint8Array([1, 2, 3, 4, 0, 0, 0, 0]).buffer)).toThrow();
  });
});

const XML = `<?xml version="1.0"?>
<score-partwise version="4.0">
  <work><work-title>Test</work-title></work>
  <part-list>
    <score-part id="P1"><part-name>Solo Cornet</part-name></score-part>
    <score-part id="P2"><part-name>Repiano Cornet</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>2</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
        <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
      <note color="#D0021B"><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration></note>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration></note>
    </measure>
    <measure number="2">
      <note><pitch><step>D</step><octave>7</octave></pitch><duration>8</duration></note>
    </measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes><divisions>1</divisions>
        <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
      <note><pitch><step>E</step><octave>5</octave></pitch><duration>2</duration></note>
      <note><rest/><duration>2</duration></note>
    </measure>
    <measure number="2">
      <note><rest/><duration>4</duration></note>
    </measure>
  </part>
</score-partwise>`;

describe("musicxml and validation", () => {
  it("reads parts, bars, beats and sounding pitch", () => {
    const s = parseMusicXml(XML);
    expect(s.title).toBe("Test");
    expect(s.bars).toBe(2);
    const solo = s.parts[0];
    expect(solo.name).toBe("Solo Cornet");
    expect(solo.transpose).toBe(-2);
    expect(solo.notes.map((x) => [x.bar, x.beat, x.written, x.sounding])).toEqual([
      [1, 1, 74, 72],
      [1, 3, 72, 70],
      [2, 1, 98, 96],
    ]);
    expect(solo.notes[0].color).toBe("#D0021B");
    expect(solo.notes[2].onset).toBe(4);
  });

  it("flags range and crossing problems", () => {
    const s = parseMusicXml(XML);
    const range = checkRanges(s.parts[0]);
    expect(range).toHaveLength(1);
    expect(range[0]).toMatchObject({ bar: 2, severity: "error", kind: "range" });
    const cross = checkCrossing(s.parts[0], s.parts[1]);
    expect(cross).toHaveLength(1);
    expect(cross[0]).toMatchObject({ part: "Repiano Cornet", bar: 1, kind: "crossing" });
    expect(validateScore(s)).toHaveLength(2);
    expect(pitchName(70)).toBe("B♭4");
  });

  it("checks the soloist lead against the cornet's solo range, the section against 82", () => {
    // Sounding C6 (84): written D6 on a B♭ part.
    const part = (name: string) => `<score-part id="P1"><part-name>${name}</part-name></score-part></part-list>
      <part id="P1"><measure number="1"><attributes><divisions>1</divisions>
        <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
        <note><pitch><step>D</step><octave>6</octave></pitch><duration>4</duration></note></measure></part>`;
    const score = (name: string) => parseMusicXml(`<?xml version="1.0"?><score-partwise version="4.0"><part-list>${part(name)}</score-partwise>`);
    expect(checkRanges(score("Solo Cornet").parts[0])).toMatchObject([{ severity: "warning", kind: "range" }]);
    expect(checkRanges(score("Repiano Cornet").parts[0])).toMatchObject([{ severity: "error", kind: "range" }]);
  });
});

describe("dsp", () => {
  it("computes peaks", () => {
    const p = peaks(new Float32Array([0, 1, -1, 0.5, -0.25, 0]), 2);
    expect(Array.from(p)).toEqual([-1, 1, -0.25, 0.5]);
  });

  it("finds a sine's frequency bin", () => {
    const size = 1024;
    const re = new Float64Array(size);
    const im = new Float64Array(size);
    for (let i = 0; i < size; i++) re[i] = Math.sin((2 * Math.PI * 64 * i) / size);
    fft(re, im);
    let best = 0;
    for (let k = 1; k < size / 2; k++) if (Math.hypot(re[k], im[k]) > Math.hypot(re[best], im[best])) best = k;
    expect(best).toBe(64);
  });

  it("builds a spectrogram and an energy curve", () => {
    const x = new Float32Array(8192).map((_, i) => Math.sin((2 * Math.PI * 440 * i) / 44100));
    const s = spectrogram(x, 4, 1024);
    expect(s.frames).toBe(4);
    expect(s.bins).toBe(512);
    const bin = Math.round((440 / 44100) * 1024);
    const col = Array.from(s.data.slice(0, 512));
    expect(col.indexOf(Math.max(...col))).toBe(bin);
    const e = energy(new Float32Array(1000).fill(0.5), 2);
    expect(e[0]).toBeCloseTo(20 * Math.log10(0.5), 3);
  });
});

describe("quartet part names", () => {
  it("has ranges, crossing pairs and nb names for every quartet part", async () => {
    const { RANGES, CROSSING_PAIRS } = await import("../src/lib/validate");
    const { partNameNb } = await import("../src/lib/talkingxml");
    const quartet = ["1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium"];
    for (const name of quartet) {
      expect(RANGES[name], name).toBeDefined();
      expect(partNameNb(name), name).toBeDefined();
    }
    expect(partNameNb("1st Cornet")).toBe("1. kornett");
    expect(partNameNb("Tenor Horn")).toBe("Althorn");
    for (let i = 0; i < 3; i++) {
      expect(CROSSING_PAIRS).toContainEqual([quartet[i], quartet[i + 1]]);
    }
  });
});
