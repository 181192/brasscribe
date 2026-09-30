import { afterEach, describe, expect, it, vi } from "vitest";
import { audioPanel, playFrom } from "../src/components/audio";

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

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

describe("the audio panel", () => {
  it("shows every source that fails to load, and keeps its status line", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));
    const el = audioPanel([{ label: "stem", url: "/a.wav" }, { label: "original", url: "/b.wav" }]);
    document.body.append(el);
    await vi.waitFor(() => expect(el.querySelectorAll(".notice-error")).toHaveLength(2));
    expect(el.textContent).toContain("A: stem could not be loaded.");
    expect(el.textContent).toContain("B: original could not be loaded.");
    expect(el.querySelector("[role=status]")?.textContent).toBe("No audio could be loaded.");
  });
});
