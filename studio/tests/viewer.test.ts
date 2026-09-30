import { afterEach, describe, expect, it, vi } from "vitest";
import { setLang } from "../src/i18n";
import { engineScorePath, viewerView } from "../src/views/viewer";

const origin = "http://127.0.0.1:8765";

afterEach(() => {
  vi.unstubAllGlobals();
  setLang("en");
  document.body.replaceChildren();
});

describe("which scores a viewer link may open", () => {
  it("opens a run's or a reference's score on this engine", () => {
    expect(engineScorePath("/v1/jobs/abc/musicxml", origin)).toBe("/v1/jobs/abc/musicxml");
    expect(engineScorePath("/v1/references/old/files/brass-band.musicxml?x=1", origin)).toBe("/v1/references/old/files/brass-band.musicxml?x=1");
  });

  it("refuses other sites, other paths and tricks that leave /v1/", () => {
    for (const src of [
      "https://example.com/score.musicxml",
      "//example.com/v1/jobs/a/musicxml",
      "/\\example.com/v1/x",
      "/v1\\..\\index.html",
      "/v1/../index.html",
      "/v1/%2e%2e/index.html",
      "index.html",
      "/assets/studio.js",
      "javascript:alert(1)",
      "",
    ]) expect(engineScorePath(src, origin), src).toBeNull();
  });

  it("says so instead of fetching a link it refuses", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const root = document.createElement("main");
    document.body.append(root);
    viewerView(root, new URLSearchParams({ src: "https://example.com/evil.musicxml", name: "Mikkel" }));
    expect(fetch).not.toHaveBeenCalled();
    expect(root.querySelector("[role=alert]")?.textContent).toContain("doesn't point to a score in Brasscribe");
  });
});
