// Small DOM helpers shared by the views.
import { ApiError, MissingEndpoint } from "../api/client";
import { locale, t } from "../i18n";
import { icon } from "./icons";

type Child = Node | string | number | null | undefined | false | Child[];
type Attrs = Record<string, string | number | boolean | null | undefined | EventListener>;

/** Create an element: h("button", { class: "x", onclick: fn }, "Label"). */
export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = String(v);
    else if (k in el && typeof v !== "string" && typeof v !== "number") (el as unknown as Record<string, unknown>)[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  append(el, children);
  return el;
}

function append(el: Node, children: Child[]): void {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else el.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
  }
}

export function clear(el: Element, ...children: Child[]): void {
  el.replaceChildren();
  append(el, children);
}

let uid = 0;
export const nextId = (prefix: string): string => `${prefix}-${++uid}`;

/** Announce a message politely through the global status region. */
export function announce(message: string): void {
  const region = document.getElementById("announcer");
  if (!region) return;
  region.textContent = "";
  // A new text node after clearing makes screen readers repeat identical messages.
  setTimeout(() => (region.textContent = message), 30);
}

/** The state shown in place of a view (or a panel) whose data could not be loaded. */
export function errorNotice(err: unknown): HTMLElement {
  if (err instanceof MissingEndpoint) {
    return h("div", { class: "notice notice-missing", role: "note" },
      h("strong", {}, `${t("common.notAvailable")} `),
      ...t("common.needsEndpoint", { endpoint: "\u0000" }).split("\u0000").flatMap((s, i) => (i ? [h("code", {}, err.endpoint), s] : [s])));
  }
  const msg = err instanceof ApiError ? `${err.status}: ${err.message}` : err instanceof Error ? err.message : String(err);
  return h("div", { class: "notice notice-error", role: "alert" }, h("strong", {}, `${t("common.couldNotLoad")} `), msg);
}

export function loading(label?: string): HTMLElement {
  return h("p", { class: "loading", role: "status" }, label ?? t("common.loading"));
}

/** Render `load()` into `el`, showing a loading state and errors in place. */
export async function panel<T>(el: Element, load: () => Promise<T>, render: (v: T) => Child): Promise<T | undefined> {
  clear(el, loading());
  try {
    const v = await load();
    clear(el, render(v));
    return v;
  } catch (e) {
    clear(el, errorNotice(e));
    return undefined;
  }
}

export const fmt = {
  seconds(s: number | null | undefined): string {
    if (s === null || s === undefined) return "–";
    if (s < 1) return `${(s * 1000).toFixed(0)} ms`;
    if (s < 60) return `${s.toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
    return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  },
  bytes(b: number | null | undefined): string {
    if (b === null || b === undefined) return "–";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    let v = b;
    while (v >= 1024 && i < u.length - 1) {
      v /= 1024;
      i++;
    }
    return `${v.toFixed(i ? 1 : 0)} ${u[i]}`;
  },
  date(t: number | string | null | undefined): string {
    if (t === null || t === undefined) return "–";
    const d = typeof t === "number" ? new Date(t * 1000) : new Date(t);
    return d.toLocaleString(locale(), { dateStyle: "medium", timeStyle: "short" });
  },
  num(v: number | null | undefined, digits = 3): string {
    return v === null || v === undefined || Number.isNaN(v) ? "–" : v.toLocaleString(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false });
  },
  signed(v: number | null | undefined, digits = 3): string {
    if (v === null || v === undefined) return "–";
    return `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toLocaleString(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false })}`;
  },
  hash(h: string | null | undefined): string {
    return h ? h.slice(0, 12) : "–";
  },
};

/** A status pill: text always carries the meaning; the icon and colour repeat it. */
export function pill(status: string): HTMLElement {
  const icons: Record<string, string> = {
    pass: "mark-checked", succeeded: "mark-checked", ran: "done", ok: "done", identical: "mark-checked", improved: "done",
    fail: "error", failed: "error", regressed: "error", error: "error", different: "info", warning: "error",
    running: "play", started: "play", cached: "retry", imported: "retry", missing: "help", cancelled: "close",
  };
  const glyph: Record<string, string> = { queued: "…", pending: "…", skipped: "–", not_run: "–", new: "+" };
  const label = t(`status.${status}`) === `status.${status}` ? status.replace("_", " ") : t(`status.${status}`);
  const mark = icons[status] ? icon(icons[status]) : h("span", { "aria-hidden": "true" }, glyph[status] ?? "•");
  return h("span", { class: `pill pill-${status}` }, mark, label);
}

/** A table with a caption; rows are arrays of cells. */
export function table(caption: string, head: string[], rows: Child[][], opts: { hideCaption?: boolean; className?: string } = {}): HTMLElement {
  return h("div", { class: `table-wrap ${opts.className ?? ""}`, tabindex: 0, role: "region", "aria-label": caption },
    h("table", {},
      h("caption", { class: opts.hideCaption ? "visually-hidden" : "" }, caption),
      h("thead", {}, h("tr", {}, head.map((c) => h("th", { scope: "col" }, c)))),
      h("tbody", {}, rows.length ? rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c)))) :
        h("tr", {}, h("td", { colspan: head.length }, t("common.nothing"))))));
}

/** Accessible tabs with a roving tabindex (WAI-ARIA tabs pattern, manual activation). */
export function tabs(label: string, items: { id: string; label: string; render: (panel: HTMLElement) => void }[], selected: string, onSelect?: (id: string) => void): HTMLElement {
  const base = nextId("tabs");
  const list = h("div", { role: "tablist", "aria-label": label, class: "tablist" });
  const panels = h("div", { class: "tabpanels" });
  const buttons: HTMLButtonElement[] = [];
  const rendered = new Set<string>();
  const panelEls = new Map<string, HTMLElement>();
  const select = (id: string, focus = false) => {
    for (const b of buttons) {
      const on = b.dataset.id === id;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
      if (on && focus) b.focus();
    }
    for (const [pid, p] of panelEls) p.hidden = pid !== id;
    if (!rendered.has(id)) {
      rendered.add(id);
      items.find((i) => i.id === id)?.render(panelEls.get(id)!);
    }
    onSelect?.(id);
  };
  for (const it of items) {
    const b = h("button", {
      role: "tab", id: `${base}-${it.id}-tab`, "aria-controls": `${base}-${it.id}`, "data-id": it.id, type: "button",
      onclick: () => select(it.id),
    }, it.label);
    b.addEventListener("keydown", (e: KeyboardEvent) => {
      const i = buttons.indexOf(b);
      let j = -1;
      if (e.key === "ArrowRight") j = (i + 1) % buttons.length;
      else if (e.key === "ArrowLeft") j = (i - 1 + buttons.length) % buttons.length;
      else if (e.key === "Home") j = 0;
      else if (e.key === "End") j = buttons.length - 1;
      if (j >= 0) {
        e.preventDefault();
        buttons[j].focus();
      }
    });
    buttons.push(b);
    list.append(b);
    const p = h("div", { role: "tabpanel", id: `${base}-${it.id}`, "aria-labelledby": `${base}-${it.id}-tab`, tabindex: 0, hidden: true, class: "tabpanel" });
    panelEls.set(it.id, p);
    panels.append(p);
  }
  select(items.some((i) => i.id === selected) ? selected : items[0].id);
  return h("div", { class: "tabs" }, list, panels);
}

/** Read a CSS custom property (design token) from the document. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim() || "#000";
}

export function prefersReducedMotion(): boolean {
  return matchMedia("(prefers-reduced-motion: reduce)").matches;
}
