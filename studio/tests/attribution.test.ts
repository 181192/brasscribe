import { describe, expect, it } from "vitest";
import { attributionZone, clearOf, overlaps } from "../src/lib/attribution";

const bar = (x: number, w: number, staffTop: number) => ({ realBounds: { x, y: 30, w, h: 150 }, bars: [{ realBounds: { x, y: staffTop, w, h: 60 } }] });
const system = { visualBounds: { x: 0, y: 10, w: 800, h: 190 }, bars: [bar(0, 400, 100), bar(400, 400, 100)] };

describe("alphaTab's attribution", () => {
  it("is at the end of the first system, above the top staff", () => {
    const zone = attributionZone([system], 12, 1, 1)!;
    expect(zone).toEqual({ x: 800 - 78, y: 10, w: 78, h: 90 });
  });

  it("follows the scale", () => {
    expect(attributionZone([system], 12, 1, 1.5)!.w).toBe(117);
  });

  it("is absent from a score of 10 bars or fewer on 2 tracks or fewer", () => {
    expect(attributionZone([system], 10, 2, 1)).toBeNull();
    expect(attributionZone([system], 11, 1, 1)).not.toBeNull();
    expect(attributionZone([system], 4, 3, 1)).not.toBeNull();
    expect(attributionZone([], 12, 1, 1)).toBeNull();
  });

  it("is kept clear of: a box on it goes to just above it, any other stays", () => {
    const zone = attributionZone([system], 12, 1, 1)!;
    const on = { x: 750, y: 40, w: 12, h: 16 };
    const top = clearOf(on, zone);
    expect(top).toBe(zone.y - on.h - 2);
    expect(overlaps({ ...on, y: top }, zone)).toBe(false);
    const beside = { x: 300, y: 40, w: 12, h: 16 };
    expect(clearOf(beside, zone)).toBe(40);
    expect(clearOf(on, null)).toBe(40);
  });
});
