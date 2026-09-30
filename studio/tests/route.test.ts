import { describe, expect, it } from "vitest";
import { decodeSegment, parseHash } from "../src/lib/route";

describe("the hash route", () => {
  it("splits name, decoded arguments and query", () => {
    const r = parseHash("#/runs/2026%2009%20run/score?a=1&b=ref%3Ax");
    expect(r.name).toBe("runs");
    expect(r.args).toEqual(["2026 09 run", "score"]);
    expect(r.query.get("b")).toBe("ref:x");
  });

  it("falls back to Runs for an empty hash", () => {
    expect(parseHash("").name).toBe("runs");
    expect(parseHash("#/").args).toEqual([]);
  });

  it("keeps a malformed escape as written instead of failing", () => {
    expect(decodeSegment("%E0%A4%A")).toBe("%E0%A4%A");
    expect(parseHash("#/runs/%E0%A4%A").args).toEqual(["%E0%A4%A"]);
  });
});
