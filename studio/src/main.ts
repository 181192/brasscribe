// Studio entry: hash router, language, engine status, global keyboard shortcuts.
import { api } from "./api/client";
// Custom elements register themselves on import.
import "./components/audio";
import "./components/beats";
import "./components/pianoroll";
import "./components/score";
import "./components/stagegraph";
import "./components/stems";
import type { ScoreElement } from "./components/score";
import { lang, onLangChange, setLang, t, type Lang } from "./i18n";
import { choice, contrast, onThemeChange, parseChoice, setChoice, watchContrast } from "./theme";
import { clear, h, wireMenus } from "./ui/dom";
import { lockup } from "./ui/icons";
import { benchView } from "./views/bench";
import { compareView } from "./views/compare";
import { conformanceView } from "./views/conformance";
import { parityView } from "./views/parity";
import { registryView } from "./views/registry";
import { runView } from "./views/run";
import { runsView } from "./views/runs";
import { viewerView } from "./views/viewer";

type Route = { name: string; title: () => string; render: (root: HTMLElement, args: string[], q: URLSearchParams) => void | (() => void) };

const routes: Route[] = [
  { name: "runs", title: () => t("nav.runs"), render: (r, a, q) => (a[0] ? runView(r, decodeURIComponent(a[0]), a[1], q) : runsView(r)) },
  { name: "viewer", title: () => t("nav.viewer"), render: (r, _a, q) => viewerView(r, q) },
  { name: "compare", title: () => t("title.compare"), render: (r, _a, q) => compareView(r, q) },
  { name: "bench", title: () => t("nav.bench"), render: (r) => benchView(r) },
  { name: "parity", title: () => t("nav.parity"), render: (r) => parityView(r) },
  { name: "conformance", title: () => t("nav.conformance"), render: (r) => conformanceView(r) },
  { name: "registry", title: () => t("nav.registry"), render: (r) => registryView(r) },
];

let cleanup: (() => void) | void;

// Below 768 px (and so at 200 % zoom on a laptop) the nav is behind a Menu button; above it, the disclosure is always open.
const narrow = matchMedia("(max-width: 48rem)");
function syncNav(): void {
  (document.getElementById("nav-menu") as HTMLDetailsElement).open = !narrow.matches;
}
narrow.addEventListener("change", syncNav);
syncNav();
wireMenus();

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
  const quality = document.getElementById("nav-quality") as HTMLDetailsElement;
  quality.classList.toggle("current", !!quality.querySelector("[aria-current]"));
  quality.open = false;
  if (narrow.matches) (document.getElementById("nav-menu") as HTMLDetailsElement).open = false;
  if (typeof cleanup === "function") cleanup();
  clear(main);
  document.title = `${r.title()} – Brasscribe Studio`;
  cleanup = r.render(main, args, new URLSearchParams(query));
  // Move focus to the new view so keyboard and screen-reader users start there.
  const heading = main.querySelector("h1");
  if (heading && !initial) {
    heading.setAttribute("tabindex", "-1");
    heading.focus();
  }
}

let health: { version: string; device: string } | null | undefined;

function renderStatus(): void {
  const el = document.getElementById("engine-status")!;
  el.classList.toggle("up", !!health);
  el.classList.toggle("down", health === null);
  if (health) clear(el, t("app.engine", { version: health.version, device: health.device.toUpperCase() }));
  else el.textContent = health === undefined ? t("app.connecting") : t("app.engineDown");
}

async function engineStatus(): Promise<void> {
  try {
    health = await api.health();
  } catch {
    health = null;
  }
  renderStatus();
}

/** Static page chrome: header, nav, footer, and the lang attribute. */
function translateChrome(): void {
  document.documentElement.lang = lang();
  for (const el of Array.from(document.querySelectorAll<HTMLElement>("[data-i18n]"))) el.textContent = t(el.dataset.i18n!);
  for (const el of Array.from(document.querySelectorAll<HTMLElement>("[data-i18n-label]"))) el.setAttribute("aria-label", t(el.dataset.i18nLabel!));
  const kbd = (k: string) => `\u0001${k}\u0002`;
  const link = (href: string, label: string) => `\u0003${href}\u0004${label}\u0005`;
  const raw = t("app.footer", { f1: kbd("F1"), q: kbd("?"), docs: link("/docs", "/docs"), openapi: link("/openapi.json", "openapi.json"), alphatab: link("https://alphatab.net", "alphaTab") });
  const footer = document.getElementById("footer-text")!;
  footer.replaceChildren();
  for (const part of raw.split(/(\u0001[^\u0002]*\u0002|\u0003[^\u0005]*\u0005)/)) {
    if (part.startsWith("\u0001")) footer.append(h("kbd", {}, part.slice(1, -1)));
    else if (part.startsWith("\u0003")) {
      const [href, label] = part.slice(1, -1).split("\u0004");
      footer.append(h("a", { href }, label));
    } else if (part) footer.append(part);
  }
  renderStatus();
  const sel = document.getElementById("lang-select") as HTMLSelectElement;
  sel.value = lang();
  renderTheme();
}

/** The Appearance picker and, while a system contrast setting wins, the line that says so. */
function renderTheme(): void {
  (document.getElementById("theme-select") as HTMLSelectElement).value = choice();
  const note = document.getElementById("theme-note")!;
  const c = contrast();
  note.hidden = !c;
  note.textContent = c === "forced" ? t("app.theme.forced") : c === "more" ? t("app.theme.more") : "";
}

let dialog: HTMLDialogElement | null = null;

function shortcutsDialog(): HTMLDialogElement {
  dialog?.remove();
  const row = (keys: string, what: string) => h("tr", {}, h("td", {}, keys.split(" / ").map((k, i) => [i ? " / " : "", h("kbd", {}, k)])), h("td", {}, what));
  const dlg = h("dialog", { id: "shortcuts", "aria-labelledby": "shortcuts-h" },
    h("h2", { id: "shortcuts-h" }, t("shortcuts.title")),
    h("h3", {}, t("shortcuts.anywhere")),
    h("table", {}, h("tbody", {},
      row("Ctrl/⌘+O", t("shortcuts.open")),
      row("Ctrl/⌘+Shift+Space", t("shortcuts.playPause")),
      row("Ctrl/⌘+G", t("shortcuts.goToBar")),
      row("Alt+T", t("shortcuts.talking")),
      row("F1 / ?", t("shortcuts.thisList")),
      row("Esc", t("shortcuts.close")))),
    h("h3", {}, t("shortcuts.inScore")),
    h("table", {}, h("tbody", {},
      row("Space", t("shortcuts.s.play")),
      row("→ / ←", t("shortcuts.s.note")),
      row("Ctrl+→ / Ctrl+←", t("shortcuts.s.beat")),
      row("Alt+↓ / Alt+↑", t("shortcuts.s.bar")),
      row("Ctrl+Shift+↓ / Ctrl+Shift+↑", t("shortcuts.s.part")),
      row("Home / End", t("shortcuts.s.home")),
      row("U / Shift+U", t("shortcuts.s.uncertain")),
      row("P", t("shortcuts.s.playBar")),
      row("R", t("shortcuts.s.read")),
      row("W", t("shortcuts.s.where")),
      row("[ / ]", t("shortcuts.s.loop")),
      row("L", t("shortcuts.s.loopToggle")),
      row("- / = / 0", t("shortcuts.s.speed")),
      row("M / S", t("shortcuts.s.mute")),
      row("Ctrl+- / Ctrl+= / Ctrl+0", t("shortcuts.s.zoom")),
      row("Tab / Shift+Tab / Esc", t("shortcuts.s.leave")))),
    h("p", { class: "hint" }, t("shortcuts.hint")),
    h("form", { method: "dialog" }, h("button", { type: "submit", class: "primary" }, t("shortcuts.closeBtn"))));
  document.body.append(dlg);
  dialog = dlg;
  return dlg;
}

function typing(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

function pageScore(): ScoreElement | null {
  return document.querySelector<ScoreElement>("#main bs-score");
}

function globalKeys(): void {
  document.addEventListener("keydown", (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === "F1" || (e.key === "?" && !typing(e) && !mod)) {
      e.preventDefault();
      if (dialog && !dialog.open) dialog.showModal();
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
    } else if (e.altKey && !mod && e.code === "KeyT") {
      const s = pageScore();
      if (s) {
        e.preventDefault();
        s.showTalking();
      }
    }
  });
}

document.getElementById("theme-select")!.addEventListener("change", (e) => setChoice(parseChoice((e.target as HTMLSelectElement).value)));
onThemeChange(renderTheme);
watchContrast();
document.getElementById("lang-select")!.addEventListener("change", (e) => setLang((e.target as HTMLSelectElement).value as Lang));
onLangChange(() => {
  translateChrome();
  shortcutsDialog();
  route(true);
});
document.getElementById("brand")!.replaceChildren(lockup());
translateChrome();
shortcutsDialog();
engineStatus();
globalKeys();
// "Try again" in an error notice shows the current view again.
window.addEventListener("studio:retry", () => {
  void engineStatus();
  route(true);
});
window.addEventListener("hashchange", () => route());
route(true);
