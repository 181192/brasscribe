// Score viewer: open a MusicXML file from disk (or a run's score) and play it.
import { fetchText } from "../api/client";
import type { ScoreElement } from "../components/score";
import { announce, clear, errorNotice, h } from "../ui/dom";

export function viewerView(root: HTMLElement, params: URLSearchParams): void {
  const input = h("input", { type: "file", id: "open-musicxml", accept: ".musicxml,.xml,.mxl,application/vnd.recordare.musicxml+xml,application/xml" });
  const status = h("p", { class: "hint", id: "viewer-status", role: "status" }, "No file open.");
  const score = h("bs-score", {}) as ScoreElement;
  const holder = h("div", {}, score);

  const open = async (name: string, data: ArrayBuffer | string) => {
    status.textContent = `Rendering ${name}…`;
    try {
      const t0 = performance.now();
      await score.load(data, name);
      const ms = Math.round(performance.now() - t0);
      status.textContent = `${name}: ${score.bars.length} bars, ${score.api?.score?.tracks.length ?? 0} parts (rendered in ${ms} ms).`;
      announce(`${name} opened`);
      score.focusScore();
    } catch (e) {
      clear(holder, errorNotice(e), score);
      status.textContent = `Could not open ${name}.`;
    }
  };

  input.addEventListener("change", async () => {
    const f = input.files?.[0];
    if (!f) return;
    if (f.name.toLowerCase().endsWith(".mxl")) {
      await open(f.name, await f.arrayBuffer()); // alphaTab reads compressed MusicXML itself
    } else {
      await open(f.name, await f.text());
    }
  });

  clear(root,
    h("h1", {}, "Score viewer"),
    h("p", {}, "Open a MusicXML file to view and play it: loop bars, change speed, mute or solo parts. ",
      "The score stays on this computer; nothing is uploaded."),
    h("div", { class: "row" }, h("label", { for: "open-musicxml" }, "MusicXML file"), input,
      h("span", { class: "hint" }, "Shortcut: ", h("kbd", {}, "Ctrl"), "/", h("kbd", {}, "⌘"), " + ", h("kbd", {}, "O"))),
    status,
    holder);

  const src = params.get("src");
  if (src) {
    fetchText(src).then((t) => open(params.get("name") ?? src, t)).catch((e) => clear(holder, errorNotice(e)));
  }
}
