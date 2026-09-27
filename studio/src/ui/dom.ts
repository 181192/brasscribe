// Small DOM helpers shared by the views.
import { ApiError, MissingEndpoint, TimedOut, Unreachable } from "../api/client";
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

/** Show text with `{code}`-style placeholders filled by elements (commands, endpoint names). */
function withCode(text: string, parts: Record<string, string>): Child[] {
  const out: Child[] = [];
  for (const piece of text.split(/(\{\w+\})/)) {
    const m = piece.match(/^\{(\w+)\}$/);
    out.push(m && m[1] in parts ? h("code", {}, parts[m[1]]) : piece);
  }
  return out;
}

export interface NoticeOptions {
  /** What "Try again" does; by default the current view is shown again. */
  retry?: () => void;
}

/**
 * The state shown in place of a view (or a panel) whose data could not be
 * loaded: what happened, why (in words), and the way forward, with a
 * Try again button. Never a bare browser message such as "Failed to fetch".
 */
export function errorNotice(err: unknown, opts: NoticeOptions = {}): HTMLElement {
  let title: string;
  let body: Child[];
  let cls = "notice notice-error";
  let role = "alert";
  if (err instanceof Unreachable) {
    title = t("err.unreachable");
    body = withCode(t("err.unreachableBody"), { serve: "brasscribe serve", studio: "brasscribe studio" });
  } else if (err instanceof TimedOut) {
    title = t("err.timeout");
    body = [t("err.timeoutBody", { s: err.seconds })];
  } else if (err instanceof MissingEndpoint) {
    title = t("err.missing");
    body = withCode(t("err.missingBody"), { endpoint: err.endpoint });
    cls = "notice notice-missing";
    role = "note";
  } else if (err instanceof ApiError && err.status >= 500) {
    title = t("err.server");
    body = [t("err.serverBody", { status: err.status }), err.message ? h("span", { class: "mono small detail" }, err.message) : null];
  } else if (err instanceof ApiError) {
    title = err.status === 404 ? t("err.notFound") : t("err.refused");
    body = [err.message];
  } else {
    title = t("err.other");
    body = [err instanceof Error ? err.message : String(err)];
  }
  const retry = h("button", { type: "button", class: "ghost" }, t("err.retry"));
  retry.addEventListener("click", () => (opts.retry ? opts.retry() : window.dispatchEvent(new CustomEvent("studio:retry"))));
  return h("div", { class: cls, role },
    h("p", { class: "notice-title" }, h("strong", {}, title)),
    h("p", {}, ...body),
    h("p", {}, retry));
}

/**
 * A file chooser with localised text: the native input (visually hidden but
 * focusable) plus a styled "Choose a file…" label and the chosen file's name.
 */
export function filePicker(input: HTMLInputElement, opts: { primary?: boolean; label?: string } = {}): HTMLElement {
  const name = h("span", { class: "file-name", "aria-live": "polite" }, t("file.none"));
  input.addEventListener("change", () => (name.textContent = input.files?.[0]?.name ?? t("file.none")));
  return h("span", { class: "file-pick" }, input, h("label", { class: `button ${opts.primary ? "primary" : "ghost"}`, for: input.id }, opts.label ?? t("file.choose")), name);
}

/**
 * The head of a view: its title, one purpose line, and (optionally) its
 * actions on the right. `title` may be an existing h1 element.
 */
export function viewHead(title: string | HTMLElement, purpose: Child, ...actions: Child[]): HTMLElement {
  const h1 = typeof title === "string" ? h("h1", {}, title) : title;
  const acts = actions.flat(Infinity as 1).filter(Boolean);
  return h("div", { class: "view-head" },
    h("div", { class: "view-title" }, h1, purpose ? h("p", { class: "purpose" }, purpose) : null),
    acts.length ? h("div", { class: "actions" }, acts) : null);
}

/**
 * An info tip (toggletip): a small "i" button that shows a plain explanation
 * of a term right after it. The text is in the page, so it reads the same
 * for pointer, keyboard and screen-reader users; Esc closes it.
 */
export function infoTip(term: string, text: string): HTMLElement {
  const out = h("span", { class: "tip-text", role: "status", hidden: true });
  const btn = h("button", { type: "button", class: "tip-btn", "aria-expanded": "false", "aria-label": t("tip.about", { term }) }, "i");
  const set = (open: boolean) => {
    btn.setAttribute("aria-expanded", String(open));
    out.hidden = !open;
    out.textContent = open ? text : "";
  };
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    set(btn.getAttribute("aria-expanded") !== "true");
  });
  btn.addEventListener("keydown", (e) => {
    if (e.key === "Escape") set(false);
  });
  return h("span", { class: "tip" }, btn, out);
}

let menusWired = false;
/** Close open menus on Esc or a click outside them. */
export function wireMenus(): void {
  if (menusWired) return;
  menusWired = true;
  document.addEventListener("click", (e) => {
    for (const d of Array.from(document.querySelectorAll<HTMLDetailsElement>("details.menu[open]"))) {
      if (!d.contains(e.target as Node)) d.open = false;
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    for (const d of Array.from(document.querySelectorAll<HTMLDetailsElement>("details.menu[open]"))) {
      if (d.contains(document.activeElement)) d.querySelector("summary")?.focus();
      d.open = false;
    }
  });
}

/** A button that opens a short list of actions (links or buttons). */
export function menu(label: Child, items: Child[], opts: { className?: string } = {}): HTMLDetailsElement {
  wireMenus();
  const d = h("details", { class: `menu ${opts.className ?? ""}` }, h("summary", {}, label), h("div", { class: "menu-list" }, items));
  // Choosing an action closes the menu (a confirm step inside it keeps it open).
  d.addEventListener("click", (e) => {
    const el = (e.target as HTMLElement).closest("a");
    if (el && d.contains(el)) d.open = false;
  });
  return d;
}

/** A closed-by-default disclosure for raw detail: "summary (count)" then the content. */
export function more(summary: string, content: Child, opts: { count?: number | string; open?: boolean } = {}): HTMLDetailsElement {
  return h("details", { class: "more", open: opts.open ?? false },
    h("summary", {}, summary, opts.count !== undefined ? h("span", { class: "count" }, ` (${opts.count})`) : null),
    content);
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
    clear(el, errorNotice(e, { retry: () => void panel(el, load, render) }));
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
  /** A path as the contributor knows it: from the repository's data/ (or another top folder), never absolute. */
  path(p: string | null | undefined): string {
    if (!p) return "–";
    const s = p.replace(/\\/g, "/");
    if (!s.startsWith("/") && !/^[A-Za-z]:\//.test(s)) return s;
    const top = s.match(/\/((?:data|eval|core|models|music|engine|studio|docs)\/.*)$/);
    return top ? top[1] : s.split("/").slice(-2).join("/");
  },
};

/** A status pill: text always carries the meaning; the icon and colour repeat it. */
export function pill(status: string): HTMLElement {
  const icons: Record<string, string> = {
    pass: "mark-checked", ready: "mark-checked", not_ready: "error", succeeded: "mark-checked", ran: "done", ok: "done", identical: "mark-checked", improved: "done",
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
