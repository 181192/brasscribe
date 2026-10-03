// Opens a view of the catalogue in a variant, with the API answered from the fixtures, and waits until it
// has settled.
import type { Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { serveApi } from "./api";
import type { Variant, View } from "./views";

/** What the fixtures answer 404 on purpose: a run without its recording, a failed run without its score, no band sounds. */
const EXPECTED_404 = [/\/v1\/jobs\/[^/]+\/input$/, /\/v1\/jobs\/old-hundredth-failed\/(musicxml|composition)$/, /\/assets\/band\//];

export type Opened = {
  /** Page errors, console errors and requests the fixtures do not answer. */
  problems: string[];
};

export async function openView(page: Page, view: Pick<View, "route" | "ready" | "prepare">, variant: Variant): Promise<Opened> {
  const problems: string[] = [];
  const unanswered = await serveApi(page);
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const url = m.location().url ?? "";
    if (/status of 404/.test(m.text()) && EXPECTED_404.some((r) => r.test(new URL(url, "http://x").pathname))) return;
    problems.push(`console error: ${m.text()}${url ? ` (${url})` : ""}`);
  });
  // Dates shown are the fixtures' own; a fixed clock keeps anything relative to now still.
  await page.clock.setFixedTime(new Date("2026-01-04T12:00:00Z"));
  await page.addInitScript((lang) => localStorage.setItem("brasscribe.studio.lang", lang), variant.lang);
  await page.setViewportSize(variant.viewport);
  await page.emulateMedia({ colorScheme: variant.colorScheme, contrast: variant.contrast, reducedMotion: "reduce" });
  await page.goto(`/#/${view.route}`);
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 30_000 });
  if (view.ready) await view.ready(page);
  // A narrow variant is also reached the way a reader gets there: the window made narrow (or zoomed in)
  // after the view opened wide. What lays itself out once (the score) must fit after that too.
  if (variant.viewport.width < 1280) {
    await page.setViewportSize({ width: 1280, height: variant.viewport.height });
    await page.waitForTimeout(300);
    await page.setViewportSize(variant.viewport);
    await page.waitForTimeout(300);
    if (view.ready) await view.ready(page);
  }
  if (view.prepare) await view.prepare(page);
  await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 30_000 });
  // Two frames for the last layout, then the fonts again (a view may have asked for a new face).
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  return {
    get problems() {
      return [...problems, ...unanswered.map((u) => `no fixture for ${u}`)];
    },
  };
}

/** Takes out what differs from one run to the next (how long a score took to draw) before a screenshot. */
export async function steady(page: Page): Promise<void> {
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (n.textContent && /\d+ ms\b/.test(n.textContent)) n.textContent = n.textContent.replace(/\d+ ms\b/g, "– ms");
    }
  });
}

/** A screenshot taken once two in a row are the same (a score may still move into place after it is drawn). */
export async function stableScreenshot(page: Page, path: string): Promise<void> {
  const take = () => page.screenshot({ fullPage: true, animations: "disabled", caret: "hide" });
  let last = await take();
  for (let i = 0; i < 10; i++) {
    await page.waitForTimeout(150);
    const now = await take();
    if (now.equals(last)) break;
    last = now;
  }
  writeFileSync(path, last);
}
