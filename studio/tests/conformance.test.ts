import { afterEach, describe, expect, it } from "vitest";
import type { ConformanceReport } from "../src/api/types";
import { setLang } from "../src/i18n";
import { comparePair } from "../src/views/conformance";

afterEach(() => setLang("en"));

const comp = (pitches: number[], extra: Record<string, unknown> = {}) =>
  ({ voices: [{ id: "v1", role: "melody", notes: pitches.map((pitch, i) => ({ pitch, start: i * 24, dur: 24 })) }], ...extra }) as unknown as ConformanceReport;

describe("a Python and Rust conformance pair", () => {
  it("says in words what differs, in English and Norwegian", () => {
    expect(comparePair({ key: "k", py: comp([60, 62]) }).detail).toBe("no Rust output");
    expect(comparePair({ key: "k", rust: comp([60]) }).detail).toBe("no Python reference");
    expect(comparePair({ key: "k", py: comp([60, 62]), rust: comp([60, 62]) })).toEqual({ status: "pass", detail: "2 notes identical" });
    expect(comparePair({ key: "k", py: comp([60, 62]), rust: comp([60, 62], { title: "x" }) })).toEqual({ status: "fail", detail: "notes identical, other fields differ" });
    expect(comparePair({ key: "k", py: { a: 1 } as ConformanceReport, rust: { a: 2 } as ConformanceReport }).detail).toBe("JSON differs");
    setLang("nb");
    expect(comparePair({ key: "k", py: comp([60, 62]) }).detail).toBe("ikke noe Rust-resultat");
    expect(comparePair({ key: "k", py: { a: 1 } as ConformanceReport, rust: { a: 1 } as ConformanceReport }).detail).toBe("identisk");
    expect(comparePair({ key: "k", py: comp([60, 62]), rust: comp([60, 74]) }).detail).toMatch(/^\d+ noter er forskjellige \(/);
  });
});
