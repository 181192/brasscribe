// Score viewer: open a MusicXML file from disk (or a run's score) and play it.
import { fetchText } from "../api/client";
import { t } from "../i18n";
import { announce, clear, errorNotice, filePicker, h, viewHead } from "../ui/dom";

/**
 * The engine path a `?src=` link may open: a path on this engine under /v1/ (a run's or a
 * reference's score). Anything else (another site, another part of this one) gives null.
 */
export function engineScorePath(src: string, origin: string): string | null {
  if (!src.startsWith("/v1/") || src.includes("\\")) return null;
  let u: URL;
  try {
    u = new URL(src, origin);
  } catch {
    return null;
  }
  if (u.origin !== new URL(origin).origin || !u.pathname.startsWith("/v1/")) return null;
  return u.pathname + u.search;
}

export function viewerView(root: HTMLElement, params: URLSearchParams): void {
  const input = h("input", { type: "file", id: "open-musicxml", accept: ".musicxml,.xml,.mxl,application/vnd.recordare.musicxml+xml,application/xml" });
  const status = h("p", { class: "hint", id: "viewer-status", role: "status" });
  const score = h("bs-score", {});
  // Until a score is open, an empty state (drop zone and the one primary) stands in for the player.
  const holder = h("div", { hidden: true }, score);
  // Why a score could not be opened; beside the score, never in its place.
  const notice = h("div", {});
  const picker = filePicker(input, { primary: true, label: t("viewer.open") });
  const drop = h("div", { class: "drop-zone" },
    h("p", {}, h("strong", {}, t("viewer.dropTitle"))),
    h("p", { class: "hint" }, t("viewer.dropBody")),
    picker,
    h("p", { class: "hint" }, t("viewer.orRun"), " ", h("a", { href: "#/runs" }, t("nav.runs")), " · ",
      t("viewer.shortcut"), h("kbd", {}, "Ctrl"), "/", h("kbd", {}, "⌘"), " + ", h("kbd", {}, "O")));

  const open = async (name: string, data: ArrayBuffer | string) => {
    status.textContent = t("viewer.rendering", { name });
    holder.hidden = false;
    // Once a score is open, Play is the primary; the chooser steps back.
    picker.querySelector(".button")?.classList.replace("primary", "ghost");
    drop.classList.add("compact");
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
  const openFile = async (f: File) => {
    // Compressed MusicXML (.mxl) goes to alphaTab as bytes.
    await open(f.name, f.name.toLowerCase().endsWith(".mxl") ? await f.arrayBuffer() : await f.text());
  };

  input.addEventListener("change", async () => {
    const f = input.files?.[0];
    if (f) await openFile(f);
  });
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    const f = e.dataTransfer?.files?.[0];
    if (f) void openFile(f);
  });

  clear(root,
    viewHead(t("viewer.title"), t("viewer.purpose")),
    drop,
    status,
    notice,
    holder);

  const src = params.get("src");
  if (src) {
    const path = engineScorePath(src, location.origin);
    if (!path) {
      clear(notice, h("div", { class: "notice notice-error", role: "alert" },
        h("p", { class: "notice-title" }, h("strong", {}, t("viewer.notEngine"))),
        h("p", {}, t("viewer.notEngineBody"))));
      return;
    }
    fetchText(path).then((txt) => open(params.get("name") ?? path, txt)).catch((e) => clear(holder, errorNotice(e)));
  }
}
