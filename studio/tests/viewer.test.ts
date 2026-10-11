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

  it("shows a score that can't be fetched beside the viewer, which still opens files", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({ detail: "no such run" }), { status: 404 })));
    const root = document.createElement("main");
    document.body.append(root);
    viewerView(root, new URLSearchParams({ src: "/v1/jobs/gone/musicxml", name: "Gone" }));
    await vi.waitFor(() => expect(root.querySelector(".notice-error")).not.toBeNull());
    expect(root.querySelector("#viewer-status")?.textContent).toBe("Could not open Gone.");
    // What the reader can do, in the page's words; the engine's own under Details.
    const notice = root.querySelector(".notice-error")!;
    expect(notice.querySelector(":scope > p:not(.notice-title)")?.textContent).toContain("Open the run from Runs");
    expect(notice.querySelector("details")?.textContent).toContain("no such run");
    expect(root.querySelector("bs-score")).not.toBeNull();
    expect(root.querySelector("#open-musicxml")).not.toBeNull();
  });

  it("says what to do when a file cannot be shown, with the technical message under Details", async () => {
    setLang("nb");
    vi.stubGlobal("fetch", () => Promise.resolve(new Response("<not-a-score/>", { status: 200 })));
    const root = document.createElement("main");
    document.body.append(root);
    // <bs-score> is not defined here, so loading the file fails with a message from the code.
    viewerView(root, new URLSearchParams({ src: "/v1/jobs/odd/musicxml", name: "Mix" }));
    await vi.waitFor(() => expect(root.querySelector(".notice-error")).not.toBeNull());
    const notice = root.querySelector(".notice-error")!;
    expect(notice.querySelector(".notice-title")?.textContent).toBe("Mix kunne ikke vises.");
    expect(notice.querySelector(":scope > p:not(.notice-title)")?.textContent).toContain("Sjekk at det er en MusicXML-fil");
    const details = notice.querySelector("details")!;
    expect(details.open).toBe(false);
    expect(details.querySelector("summary")?.textContent).toBe("Detaljer");
    expect(details.textContent).toContain("is not a function");
    // The raw message is nowhere outside Details.
    const outside = notice.cloneNode(true) as HTMLElement;
    outside.querySelector("details")!.remove();
    expect(outside.textContent).not.toContain("is not a function");
    expect(notice.querySelector("button")?.textContent).toBe("Prøv igjen");
    // No player under the notice: the chooser is the page's primary again.
    expect((root.querySelector("bs-score")!.parentElement as HTMLElement).hidden).toBe(true);
    expect(root.querySelector(".drop-zone .button")?.classList.contains("primary")).toBe(true);
    expect(root.querySelector("#viewer-status")?.textContent).toBe("Kunne ikke åpne Mix.");
  });

  it("opens the bundled example, and only that, by its id", () => {
    const fetch = vi.fn(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetch);
    const root = document.createElement("main");
    document.body.append(root);
    viewerView(root, new URLSearchParams({ example: "old-hundredth" }));
    expect(fetch).toHaveBeenCalledOnce();
    expect(String((fetch.mock.calls[0] as unknown[])[0])).toBe("examples/old-hundredth.musicxml");
    viewerView(root, new URLSearchParams({ example: "constructor" }));
    expect(fetch).toHaveBeenCalledOnce();
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
