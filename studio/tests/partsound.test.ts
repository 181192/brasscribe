import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DRUM_CHANNEL, METRONOME_CHANNEL, PartSoundResolver, playbackChannels, type Mapping } from "../src/lib/partsound";

const sounds = join(__dirname, "..", "..", "sounds");
const mapping = JSON.parse(readFileSync(join(sounds, "mapping.json"), "utf8")) as Mapping & { lineups: Record<string, unknown> };
const vectors = JSON.parse(readFileSync(join(sounds, "partsound-vectors.json"), "utf8")).vectors as {
  name: string;
  instrument: string | null;
  program: number | null;
  expect: { part: string; step: string; program: number; bank: number; channel_gain_db: number; percussion: boolean } | null;
}[];

describe("part sound resolver (sounds/partsound-vectors.json)", () => {
  const resolver = new PartSoundResolver(mapping);

  it.each(vectors.map((v) => [`${v.name} / ${v.instrument} / ${v.program}`, v] as const))("%s", (_, v) => {
    const got = resolver.resolve(v.name, v.instrument, v.program);
    if (v.expect === null) {
      expect(got).toBeNull();
      return;
    }
    expect(got).not.toBeNull();
    expect({ part: got!.part, step: got!.step, program: got!.sound.program, bank: got!.sound.bank,
      channel_gain_db: got!.sound.gainDb, percussion: got!.sound.percussion }).toEqual(v.expect);
  });

  it("resolves every lineup part by its own name", () => {
    for (const [name, parts] of Object.entries(mapping.lineups)) {
      if (!Array.isArray(parts)) continue;
      for (const p of parts) expect(resolver.resolve(p)?.step, `${name}: ${p}`).toBe("exact");
    }
  });
});

describe("playback channels", () => {
  it("gives every part its own channel and the drums channel 10", () => {
    const perc = [...Array(17).fill(false), true];
    const ch = playbackChannels(perc);
    expect(ch[17]).toBe(DRUM_CHANNEL);
    expect(new Set(ch.slice(0, 17)).size).toBe(17);
    expect(ch.slice(0, 17)).not.toContain(DRUM_CHANNEL);
    expect(ch).not.toContain(METRONOME_CHANNEL);
  });
});
