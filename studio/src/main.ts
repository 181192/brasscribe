// Studio entry: hash router, engine status, global keyboard shortcuts.
import { api } from "./api/client";
// Custom elements register themselves on import.
import "./components/audio";
import "./components/beats";
import "./components/pianoroll";
import "./components/score";
import "./components/stagegraph";
import "./components/stems";
import type { ScoreElement } from "./components/score";
import { clear, h } from "./ui/dom";
import { benchView } from "./views/bench";
import { compareView } from "./views/compare";
import { conformanceView } from "./views/conformance";
import { parityView } from "./views/parity";
import { registryView } from "./views/registry";
import { runView } from "./views/run";
import { runsView } from "./views/runs";
import { viewerView } from "./views/viewer";

type Route = { name: string; title: string; render: (root: HTMLElement, args: string[], q: URLSearchParams) => void | (() => void) };

const routes: Route[] = [
  { name: "runs", title: "Runs", render: (r, a, q) => (a[0] ? runView(r, decodeURIComponent(a[0]), a[1], q) : runsView(r)) },
  { name: "viewer", title: "Score viewer", render: (r, _a, q) => viewerView(r, q) },
  { name: "compare", title: "Compare runs", render: (r, _a, q) => compareView(r, q) },
  { name: "bench", title: "Benchmarks", render: (r) => benchView(r) },
  { name: "parity", title: "Conversion parity", render: (r) => parityView(r) },
  { name: "conformance", title: "Core conformance", render: (r) => conformanceView(r) },
  { name: "registry", title: "Datasets and models", render: (r) => registryView(r) },
];

let cleanup: (() => void) | void;

function route(initial = false): void {
  const main = document.getElementById("main")!;
  const raw = location.hash.replace(/^#\/?/, "") || "runs";
  const [path, query = ""] = raw.split("?");
  const [name, ...args] = path.split("/");
  const r = routes.find((x) => x.name === name) ?? routes[0];
  for (const a of Array.from(document.querySelectorAll<HTMLAnchorElement>(".app-nav a"))) {
    if (a.dataset.route === r.name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  if (typeof cleanup === "function") cleanup();
  clear(main);
  document.title = `${r.title} – Brasscribe Studio`;
  cleanup = r.render(main, args, new URLSearchParams(query));
  // Move focus to the new view so keyboard and screen-reader users start there.
  const heading = main.querySelector("h1");
  if (heading && !initial) {
    heading.setAttribute("tabindex", "-1");
    heading.focus();
  }
}

async function engineStatus(): Promise<void> {
  const el = document.getElementById("engine-status")!;
  try {
    const hlt = await api.health();
    el.textContent = `Engine ${hlt.version} · accelerator ${hlt.device}`;
  } catch {
    el.textContent = "Engine not reachable";
  }
}

function shortcutsDialog(): HTMLDialogElement {
  const row = (keys: string, what: string) => h("tr", {}, h("td", {}, keys.split(" / ").map((k, i) => [i ? " / " : "", h("kbd", {}, k)])), h("td", {}, what));
  const dlg = h("dialog", { id: "shortcuts", "aria-labelledby": "shortcuts-h" },
    h("h2", { id: "shortcuts-h" }, "Keyboard shortcuts"),
    h("h3", {}, "Anywhere"),
    h("table", {}, h("tbody", {},
      row("Ctrl/⌘+O", "Open a MusicXML file in the score viewer"),
      row("Ctrl/⌘+Shift+Space", "Play or pause the score on this page"),
      row("Ctrl/⌘+G", "Go to bar"),
      row("F1 / ?", "This list"),
      row("Esc", "Close this list, or leave the score"))),
    h("h3", {}, "While the score has focus"),
    h("table", {}, h("tbody", {},
      row("Space", "Play or pause"),
      row("Alt+↓ / Alt+↑", "Next or previous bar (Ctrl+↓/↑ also works)"),
      row("→ / ←", "Forward or back one beat"),
      row("Ctrl+Shift+↓ / Ctrl+Shift+↑", "Next or previous part"),
      row("Home / End", "First or last bar"),
      row("P", "Play the current bar"),
      row("R / W", "Read the current bar"),
      row("[ / ]", "Loop start or end at the current bar"),
      row("L", "Loop on or off"),
      row("- / = / 0", "Speed down 5%, up 5%, reset"),
      row("M / S", "Mute or solo the current part"),
      row("Ctrl+- / Ctrl+= / Ctrl+0", "Zoom out, in, reset"),
      row("Tab / Shift+Tab / Esc", "Leave the score"))),
    h("p", { class: "hint" }, "Single-letter keys only work while the score has focus, so they never fire in text fields."),
    h("form", { method: "dialog" }, h("button", { type: "submit", class: "primary" }, "Close")));
  document.body.append(dlg);
  return dlg;
}

function typing(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  return !!t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));
}

function pageScore(): ScoreElement | null {
  return document.querySelector<ScoreElement>("#main bs-score");
}

function globalKeys(dlg: HTMLDialogElement): void {
  document.addEventListener("keydown", (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === "F1" || (e.key === "?" && !typing(e) && !mod)) {
      e.preventDefault();
      if (!dlg.open) dlg.showModal();
    } else if (mod && !e.shiftKey && (e.key === "o" || e.key === "O")) {
      e.preventDefault();
      if (!location.hash.startsWith("#/viewer")) location.hash = "#/viewer";
      setTimeout(() => document.getElementById("open-musicxml")?.click(), 50);
    } else if (mod && e.shiftKey && e.code === "Space") {
      e.preventDefault();
      pageScore()?.togglePlay();
    } else if (mod && (e.key === "g" || e.key === "G")) {
      const input = document.querySelector<HTMLInputElement>("#main bs-score input[type=number]");
      if (input) {
        e.preventDefault();
        input.focus();
        input.select();
      }
    }
  });
}

engineStatus();
globalKeys(shortcutsDialog());
window.addEventListener("hashchange", () => route());
route(true);
