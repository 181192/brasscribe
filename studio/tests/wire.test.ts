import { describe, expect, it } from "vitest";
import { INTERFACE_VERSION, interfaceMatch } from "../src/api/wire";

describe("the interface version", () => {
  it("is 1 for this release", () => {
    expect(INTERFACE_VERSION).toBe(1);
  });

  it("matches the same number", () => {
    expect(interfaceMatch(INTERFACE_VERSION)).toBe("match");
  });

  it("says to reload Studio when the engine is newer", () => {
    expect(interfaceMatch(INTERFACE_VERSION + 1)).toBe("update-studio");
  });

  it("says to update the engine when it is older", () => {
    expect(interfaceMatch(INTERFACE_VERSION - 1)).toBe("update-engine");
    expect(interfaceMatch(3, 4)).toBe("update-engine");
  });

  it("says to update the engine when it sends no number", () => {
    expect(interfaceMatch(undefined)).toBe("update-engine");
    expect(interfaceMatch(null)).toBe("update-engine");
  });
});
