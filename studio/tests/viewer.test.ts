import { describe, expect, it } from "vitest";
import { isEnginePath } from "../src/api/client";

describe("the score viewer's ?src=", () => {
  it("opens the engine's own files", () => {
    expect(isEnginePath("/v1/jobs/20260101-120000-solo-a1b2c3/musicxml")).toBe(true);
    expect(isEnginePath("/v1/references/demo/files/brass-band.musicxml")).toBe(true);
  });

  it("opens nothing from elsewhere", () => {
    for (const src of ["https://example.com/x.musicxml", "//example.com/v1/x", "/\\example.com/v1/x",
      "/v1/\\example.com", "v1/jobs/x", "/assets/x", "javascript:alert(1)", "/v1/ x"]) {
      expect(isEnginePath(src)).toBe(false);
    }
  });
});
