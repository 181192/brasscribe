import { describe, expect, it } from "vitest";
import { summarise } from "../src/lib/beats";
import { maxOf, minOf } from "../src/lib/extent";

describe("extent", () => {
  it("finds the largest and smallest value", () => {
    const xs = [{ v: 3 }, { v: -2 }, { v: 7 }];
    expect(maxOf(xs, (x) => x.v)).toBe(7);
    expect(minOf(xs, (x) => x.v)).toBe(-2);
  });

  it("returns the given value for an empty list", () => {
    expect(maxOf([], (x: number) => x)).toBe(-Infinity);
    expect(maxOf([], (x: number) => x, 0)).toBe(0);
    expect(minOf([], (x: number) => x, 5)).toBe(5);
  });

  it("handles lists far longer than the call-argument limit", () => {
    // A full-band score's MIDI has this many events; Math.max(...list) throws RangeError here.
    const events = Array.from({ length: 1_000_000 }, (_, i) => ({ tick: i }));
    expect(() => Math.max(...events.map((e) => e.tick))).toThrow(RangeError);
    expect(maxOf(events, (e) => e.tick)).toBe(999_999);
    expect(minOf(events, (e) => e.tick)).toBe(0);
  });

  it("keeps the bar length of an empty beat list at zero", () => {
    expect(summarise([]).barBeats).toBe(0);
  });
});
