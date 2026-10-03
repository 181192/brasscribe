// The views of the catalogue and the variants each is seen in.
import { expect, type Page } from "@playwright/test";

export type View = {
  name: string;
  route: string;
  /** Waits for what the view shows once it has its data (beyond "no .loading left"). */
  ready?: (page: Page) => Promise<void>;
  /** Brings the view into the state that is shown (opens a dialog or a menu). */
  prepare?: (page: Page) => Promise<void>;
  /** Only in these variants. */
  only?: string[];
};

export type Variant = {
  name: string;
  colorScheme: "light" | "dark";
  contrast: "no-preference" | "more";
  lang: "en" | "nb";
  viewport: { width: number; height: number };
  /** The keyboard walk runs where the layout differs: the wide desktop and the narrowest. */
  keyboard?: boolean;
  /** Text spacing (WCAG 1.4.12) is checked once per view, at the desktop width. */
  spacing?: boolean;
  /** The page must not scroll sideways (WCAG 1.4.10, 1.4.4). */
  reflow?: boolean;
};

const desktop = { width: 1280, height: 900 };

export const VARIANTS: Variant[] = [
  { name: "light", colorScheme: "light", contrast: "no-preference", lang: "en", viewport: desktop, keyboard: true, spacing: true, reflow: true },
  { name: "dark", colorScheme: "dark", contrast: "no-preference", lang: "en", viewport: desktop },
  { name: "contrast", colorScheme: "light", contrast: "more", lang: "en", viewport: desktop },
  { name: "contrast-dark", colorScheme: "dark", contrast: "more", lang: "en", viewport: desktop },
  { name: "nb", colorScheme: "light", contrast: "no-preference", lang: "nb", viewport: desktop, reflow: true },
  // 200 % zoom of a 1440 × 1000 window is 720 × 500 CSS px.
  { name: "zoom200", colorScheme: "light", contrast: "no-preference", lang: "en", viewport: { width: 720, height: 500 }, reflow: true },
  { name: "reflow320", colorScheme: "light", contrast: "no-preference", lang: "en", viewport: { width: 320, height: 800 }, keyboard: true, reflow: true },
];

/** Engraved, and with `player` the player loaded too (its status line changes once it has its sounds). */
const scoreRendered = (selector: string, player = true) => async (page: Page) => {
  await expect.poll(() => page.evaluate(([s, player]) => {
    const scores = Array.from(document.querySelectorAll(s)) as (HTMLElement & { rendered?: boolean; ready?: boolean })[];
    return scores.length > 0 && scores.every((x) => x.rendered && (!player || x.ready));
  }, [selector, player] as const), { timeout: 30_000 }).toBe(true);
};

const run = "runs/old-hundredth-a";

export const VIEWS: View[] = [
  { name: "runs", route: "runs", ready: async (p) => { await expect(p.locator(".runs-table tbody tr").first()).toBeVisible(); } },
  { name: "run-score", route: `${run}/score`, ready: scoreRendered("#main bs-score") },
  { name: "run-audio", route: `${run}/audio` },
  { name: "run-stems", route: `${run}/stems` },
  { name: "run-roll", route: `${run}/roll` },
  { name: "run-beats", route: `${run}/beats` },
  { name: "run-voices", route: `${run}/voices` },
  { name: "run-musicxml", route: `${run}/musicxml` },
  { name: "run-manifest", route: `${run}/manifest` },
  { name: "run-failed", route: "runs/old-hundredth-failed", ready: async (p) => { await expect(p.locator(".notice-error").first()).toBeVisible(); } },
  { name: "viewer", route: "viewer" },
  { name: "viewer-score", route: "viewer?example=old-hundredth", ready: scoreRendered("#main bs-score") },
  { name: "compare", route: "compare?a=old-hundredth-a&b=old-hundredth-b", ready: scoreRendered("#main bs-score", false) },
  { name: "bench", route: "bench" },
  { name: "parity", route: "parity" },
  { name: "conformance", route: "conformance" },
  { name: "registry", route: "registry" },
  {
    name: "shortcuts", route: "runs",
    prepare: async (p) => {
      await p.keyboard.press("F1");
      await expect(p.getByRole("dialog")).toBeVisible();
    },
  },
  {
    name: "menu", route: "runs", only: ["zoom200", "reflow320"],
    prepare: async (p) => {
      await p.locator(".nav-toggle").click();
      await expect(p.locator("#lang-select")).toBeVisible();
      // Open, with focus nowhere: the keyboard walk starts from the top of the page with the menu open.
      await p.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
  },
];
