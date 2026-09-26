// Score viewer: open a MusicXML file from disk (or a run's score) and play it.
import { fetchText } from "../api/client";
import { t } from "../i18n";
import { announce, clear, errorNotice, filePicker, h } from "../ui/dom";

export function viewerView(root: HTMLElement, params: URLSearchParams): void {
  const input = h("input", { type: "file", id: "open-musicxml", accept: ".musicxml,.xml,.mxl,application/vnd.recordare.musicxml+xml,application/xml" });
  const status = h("p", { class: "hint", id: "viewer-status", role: "status" }, t("viewer.none"));
  const score = h("bs-score", {});
  const holder = h("div", {}, score);

  const open = async (name: string, data: ArrayBuffer | string) => {
    status.textContent = t("viewer.rendering", { name });
    try {
      const t0 = performance.now();
      await score.load(data, name);
      const ms = Math.round(performance.now() - t0);
      status.textContent = t("viewer.done", { name, bars: score.bars.length, parts: score.api?.score?.tracks.length ?? 0, ms });
      announce(t("viewer.opened", { name }));
      score.focusScore();
    } catch (e) {
      clear(holder, errorNotice(e), score);
      status.textContent = t("viewer.failed", { name });
    }
  };

  input.addEventListener("change", async () => {
    const f = input.files?.[0];
    if (!f) return;
    // Compressed MusicXML (.mxl) goes to alphaTab as bytes.
    await open(f.name, f.name.toLowerCase().endsWith(".mxl") ? await f.arrayBuffer() : await f.text());
  });

  clear(root,
    h("h1", {}, t("viewer.title")),
    h("p", {}, t("viewer.intro")),
    h("div", { class: "row" }, h("label", { for: "open-musicxml" }, t("viewer.file")), filePicker(input),
      h("span", { class: "hint" }, t("viewer.shortcut"), h("kbd", {}, "Ctrl"), "/", h("kbd", {}, "⌘"), " + ", h("kbd", {}, "O"))),
    status,
    holder);

  const src = params.get("src");
  if (src) {
    fetchText(src).then((txt) => open(params.get("name") ?? src, txt)).catch((e) => clear(holder, errorNotice(e)));
  }
}
