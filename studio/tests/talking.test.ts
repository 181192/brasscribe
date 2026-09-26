import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { announce, type Lang, type Request } from "../src/lib/talking";

const here = dirname(fileURLToPath(import.meta.url));
const vectors = JSON.parse(readFileSync(join(here, "..", "..", "docs", "accessibility", "talking-score-vectors.json"), "utf8")) as {
  cases: (Omit<Request, "default_key_fifths" | "total_bars"> & { id: string; expected: Record<Lang, string> })[];
};

describe("talking score conformance vectors", () => {
  it("has cases", () => expect(vectors.cases.length).toBeGreaterThan(20));
  for (const c of vectors.cases) {
    for (const lang of ["en", "nb"] as const) {
      it(`${c.id} (${lang})`, () => {
        // The vectors assume the Mikkel golden score: 128 bars, written key 2 sharps unless stated.
        expect(announce({ ...c, default_key_fifths: 2, total_bars: 128 }, lang)).toBe(c.expected[lang]);
      });
    }
  }
});
