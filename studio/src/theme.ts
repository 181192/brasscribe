/** Appearance (design/system.md §10): Match system, Light or Dark, stored per browser, and the
 *  hidden Pink light and Pink dark once Pink is unlocked (activate the Brasscribe Studio lockup five
 *  times in a row). The choice becomes data-theme on <html>; brasscribe.css reads it. Pink light and
 *  Pink dark also set data-palette="pink". With more contrast (prefers-contrast: more) the choice
 *  stays and brasscribe.css swaps in the light or dark high-contrast palette for it; the Pink palette
 *  steps aside. Forced colours (Windows contrast themes) always win: the attributes are removed and
 *  the system decides. index.html repeats `apply` inline so the first paint already has the right
 *  theme. */

export type ThemeChoice = "system" | "light" | "dark" | "pink-light" | "pink-dark";
export type Contrast = "forced" | "more" | null;

export const THEME_STORE = "brasscribe.studio.theme";
export const PINK_STORE = "brasscribe.studio.pink";
const CONTRAST_QUERIES = ["(forced-colors: active)", "(prefers-contrast: more)"] as const;

/** The one Pink choice of earlier versions, which followed the system's light or dark. */
export const LEGACY_PINK = "pink";

/** An unknown value is Match system, so an earlier version reads "pink-light" and "pink-dark" as its default. */
export function parseChoice(v: unknown): ThemeChoice {
  return v === "light" || v === "dark" || v === "pink-light" || v === "pink-dark" ? v : "system";
}

export function isPink(c: ThemeChoice): boolean {
  return c === "pink-light" || c === "pink-dark";
}

/** What an earlier version's "pink" becomes: Pink dark while the system is dark, else Pink light
 *  (also when that is unknown). Null for every other value. */
export function migrateChoice(v: unknown, systemDark: boolean | null): ThemeChoice | null {
  if (v !== LEGACY_PINK) return null;
  return systemDark ? "pink-dark" : "pink-light";
}

function systemDark(): boolean | null {
  return typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)").matches : null;
}

/** The stored choice. An earlier "pink" is rewritten once, with the unlock, so an earlier version
 *  (which reads the new value as Match system) still lists Pink. */
export function loadChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_STORE);
    const migrated = migrateChoice(stored, systemDark());
    if (!migrated) return parseChoice(stored);
    localStorage.setItem(PINK_STORE, "1");
    localStorage.setItem(THEME_STORE, migrated);
    return migrated;
  } catch {
    return "system"; /* storage may be blocked */
  }
}

function saveChoice(c: ThemeChoice): void {
  try {
    if (c === "system") localStorage.removeItem(THEME_STORE);
    else localStorage.setItem(THEME_STORE, c);
  } catch {
    /* storage may be blocked */
  }
}

/** The system's contrast setting right now, if any. */
export function contrast(): Contrast {
  if (typeof matchMedia !== "function") return null;
  if (matchMedia(CONTRAST_QUERIES[0]).matches) return "forced";
  if (matchMedia(CONTRAST_QUERIES[1]).matches) return "more";
  return null;
}

/** The data-theme value for a choice; null means "let the system decide". Only forced colours override the choice. */
export function resolveTheme(choice: ThemeChoice, c: Contrast): "light" | "dark" | null {
  if (c === "forced" || choice === "system") return null;
  return choice === "light" || choice === "pink-light" ? "light" : "dark";
}

/** The data-palette value: "pink" for Pink light and Pink dark, unless a system contrast setting wins. */
export function resolvePalette(choice: ThemeChoice, c: Contrast): "pink" | null {
  return isPink(choice) && !c ? "pink" : null;
}

let current: ThemeChoice = loadChoice();
/** Unlocked in this page even when storage is blocked. */
let unlockedHere = false;
const listeners = new Set<() => void>();

export function choice(): ThemeChoice {
  return current;
}

/** Whether Pink light and Pink dark are listed under Appearance: unlocked in this browser, or already chosen. */
export function pinkUnlocked(): boolean {
  if (isPink(current) || unlockedHere) return true;
  try {
    return localStorage.getItem(PINK_STORE) === "1";
  } catch {
    return false;
  }
}

/** Unlock Pink in this browser. Returns false when it was already unlocked, so there is nothing to announce. */
export function unlockPink(): boolean {
  if (pinkUnlocked()) return false;
  unlockedHere = true;
  try {
    localStorage.setItem(PINK_STORE, "1");
  } catch {
    /* storage may be blocked: it stays unlocked until the page reloads */
  }
  for (const f of listeners) f();
  return true;
}

/** Counts activations in a row: after `taps` of them, each within `windowMs` of the one before, `tap` returns true. */
export class TapCounter {
  private count = 0;
  private last = -Infinity;
  constructor(
    private readonly taps = 5,
    private readonly windowMs = 1500,
  ) {}

  tap(now: number): boolean {
    this.count = now - this.last <= this.windowMs ? this.count + 1 : 1;
    this.last = now;
    if (this.count < this.taps) return false;
    this.count = 0;
    return true;
  }
}

/** Set data-theme and data-palette on the root from the current choice and contrast. */
export function apply(root: HTMLElement = document.documentElement): void {
  const c = contrast();
  const t = resolveTheme(current, c);
  if (t) root.setAttribute("data-theme", t);
  else root.removeAttribute("data-theme");
  if (resolvePalette(current, c)) root.setAttribute("data-palette", "pink");
  else root.removeAttribute("data-palette");
}

export function setChoice(c: ThemeChoice): void {
  current = c;
  saveChoice(c);
  apply();
  for (const f of listeners) f();
}

/** Called when the choice, the system contrast or the Pink unlock changes. */
export function onThemeChange(f: () => void): () => void {
  listeners.add(f);
  return () => listeners.delete(f);
}

/** Re-apply when the system contrast setting changes. Returns a stop function. */
export function watchContrast(): () => void {
  if (typeof matchMedia !== "function") return () => {};
  const qs = CONTRAST_QUERIES.map((q) => matchMedia(q));
  const on = () => {
    apply();
    for (const f of listeners) f();
  };
  for (const q of qs) q.addEventListener("change", on);
  return () => qs.forEach((q) => q.removeEventListener("change", on));
}
