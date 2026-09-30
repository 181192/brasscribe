import { describe, expect, it } from "vitest";
import { playFrom } from "../src/components/audio";

describe("where playback starts", () => {
  it("starts where it was asked to", () => {
    expect(playFrom(12.5, 60)).toBe(12.5);
    expect(playFrom(-1, 60)).toBe(0);
  });

  it("starts again from the beginning once it has reached the end", () => {
    expect(playFrom(60, 60)).toBe(0);
    expect(playFrom(59.99, 60)).toBe(0);
    expect(playFrom(75, 60)).toBe(0);
  });
});
