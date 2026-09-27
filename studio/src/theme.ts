/** Appearance (design/system.md §10): Match system, Light or Dark, stored per browser.
 *  The choice becomes data-theme on <html>; brasscribe.css reads it. A system contrast
 *  setting (forced colours, or prefers-contrast: more) always wins, so while one is on
 *  the attribute is removed and the system decides. index.html repeats `apply` inline so
 *  the first paint already has the right theme. */

export type ThemeChoice = "system" | "light" | "dark";
export type Contrast = "forced" | "more" | null;

export const THEME_STORE = "brasscribe.studio.theme";
const CONTRAST_QUERIES = ["(forced-colors: active)", "(prefers-contrast: more)"] as const;

export function parseChoice(v: unknown): ThemeChoice {
  return v === "light" || v === "dark" ? v : "system";
}

export function loadChoice(): ThemeChoice {
  try {
    return parseChoice(localStorage.getItem(THEME_STORE));
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

/** The data-theme value for a choice; null means "let the system decide". */
export function resolveTheme(choice: ThemeChoice, c: Contrast): "light" | "dark" | null {
  if (c || choice === "system") return null;
  return choice;
}

let current: ThemeChoice = loadChoice();
const listeners = new Set<() => void>();

export function choice(): ThemeChoice {
  return current;
}

/** Set data-theme on the root from the current choice and contrast. */
export function apply(root: HTMLElement = document.documentElement): void {
  const t = resolveTheme(current, contrast());
  if (t) root.setAttribute("data-theme", t);
  else root.removeAttribute("data-theme");
}

export function setChoice(c: ThemeChoice): void {
  current = c;
  saveChoice(c);
  apply();
  for (const f of listeners) f();
}

/** Called when the choice or the system contrast changes. */
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
