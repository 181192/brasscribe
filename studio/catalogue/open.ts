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
  // The score's cursors (the bar and beat it is at) are left out of the pictures: a 100 px box that alphaTab scales
  // and slides into place, whose edge falls between pixels and comes out differently from run to run, and which
  // alphaTab may place again at any moment. Not drawn at all (hidden, its layer would still split the score's
  // raster at its edge). Everything else of the score is pictured as drawn.
  await page.addInitScript(() => document.addEventListener("DOMContentLoaded", () => {
    const s = document.createElement("style");
    s.textContent = ".at-cursors { display: none !important; }";
    document.head.append(s);
  }));
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
  // alphaTab scrolls a score to its cursor, smoothly and when it likes (after a render, on focus), and the part of
  // the score drawn while it scrolled is kept: the same engraving then comes out a pixel different from run to run
  // (a barline's edge), and the score sits higher or lower. In the catalogue a score does not follow its cursor; it
  // is engraved once more with every font in and the score at its top, and pictured as that engraving.
  await page.evaluate(async () => {
    await document.fonts.ready;
    type Api = {
      settings: { player: { scrollMode: number } };
      updateSettings(): void;
      scrollToCursor(): void;
      render(): void;
      postRenderFinished: { on(h: () => void): void; off(h: () => void): void };
    };
    const apis = Array.from(document.querySelectorAll("bs-score")).map((s) => (s as unknown as { api?: Api }).api).filter((a): a is Api => !!a);
    // First let a scroll alphaTab has started (it animates on a timer) run to its end: still for half a second.
    const scrolled = () => Array.from(document.querySelectorAll<HTMLElement>("bs-score .score-view")).map((v) => `${v.scrollLeft},${v.scrollTop}`).join(" ");
    for (let last = scrolled(), still = 0, n = 0; still < 5 && n < 60; n++) {
      await new Promise((r) => setTimeout(r, 100));
      const now = scrolled();
      still = now === last ? still + 1 : 0;
      last = now;
    }
    // Done when a render has finished and no other has finished for half a second (new settings render too).
    await Promise.all(apis.map((api) => new Promise<void>((done) => {
      let quiet: ReturnType<typeof setTimeout> | undefined;
      const finish = () => {
        api.postRenderFinished.off(finished);
        clearTimeout(quiet);
        done();
      };
      const finished = () => {
        clearTimeout(quiet);
        quiet = setTimeout(finish, 500);
      };
      api.postRenderFinished.on(finished);
      setTimeout(finish, 15_000);
      // Neither alphaTab nor Studio (which asks alphaTab to bring the cursor into view after a move) scrolls it.
      api.settings.player.scrollMode = 0; // ScrollMode.Off
      api.scrollToCursor = () => undefined;
      api.updateSettings();
      for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) if (el.scrollTop || el.scrollLeft) el.scrollTo(0, 0);
      api.render();
    })));
  });
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
    // A view that focuses its score scrolls the page to it, and how far depends on when the score was laid out;
    // the toolbar that sticks to the top then lands in a different place. Every screenshot starts at the top.
    window.scrollTo(0, 0);
    // So does every part that scrolls (an open dialog scrolled to its focused button by however far the fonts
    // had got when it opened).
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
      if (el.scrollTop || el.scrollLeft) el.scrollTo(0, 0);
    }
  });
  // Let any transition still running end before the picture.
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))).then(() => undefined));
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
}

/** A screenshot taken once two in a row are the same (a score may still move into place after it is drawn). */
export async function stableScreenshot(page: Page, path: string): Promise<void> {
  // alphaTab scrolls the score to its cursor, smoothly and when it likes (after a render, on focus), so every
  // picture starts from every scroll at the top again, and counts only if no scroll moved while it was taken.
  const scrolls = () => page.evaluate(() => {
    window.scrollTo(0, 0);
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) if (el.scrollTop || el.scrollLeft) el.scrollTo(0, 0);
    return new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
  });
  const where = () => page.evaluate(() => [scrollX, scrollY, ...Array.from(document.querySelectorAll<HTMLElement>("*"))
    .filter((el) => el.scrollTop || el.scrollLeft).map((el) => `${el.localName}.${el.className}:${el.scrollLeft},${el.scrollTop}`)].join(" "));
  // Every font the page asked for is in, none still loading.
  const fonts = () => page.waitForFunction(async () => {
    await document.fonts.ready;
    return Array.from(document.fonts).every((f) => f.status !== "loading");
  }, undefined, { timeout: 10_000 });
  // A picture of the whole page reaches beyond the window, and on Linux the browser makes the window 1 × 1 px for
  // a moment while it takes one. alphaTab watches the width of the score: at times it caught the window on its way
  // back (the page at its full width, still with the narrow window's margins) and laid the score out again, for
  // that width and then for the real one. A score laid out again after a resize does not get the widths its first
  // engraving gave it (a first bar 247.57 px wide where it was 248; the same happens when a reader resizes the
  // window), so the same score came out a fraction of a pixel different from one page load to the next (#218).
  // While the pictures are taken, a score keeps the engraving it has.
  const width = page.viewportSize()?.width;
  const keepEngraving = (keep: boolean) => page.evaluate((keep) => {
    for (const s of Array.from(document.querySelectorAll("bs-score"))) {
      const api = (s as unknown as { api?: { triggerResize?: () => void } }).api;
      if (api && keep) api.triggerResize = () => undefined;
      // Back to alphaTab's own (on its prototype), for the checks that follow.
      else if (api) delete api.triggerResize;
    }
  }, keep);
  await keepEngraving(true);
  const take = async () => {
    await fonts();
    await scrolls();
    const before = await where();
    const png = await page.screenshot({ fullPage: true, animations: "disabled", caret: "hide" });
    return { png, still: before === (await where()) && before === "0 0" };
  };
  let last = await take();
  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(200);
    const now = await take();
    if (now.still && last.still && now.png.equals(last.png)) break;
    last = now;
  }
  writeFileSync(path, last.png);
  // The window is its own size again, and what alphaTab had waiting for the resize has run, before it watches again.
  await page.waitForFunction((w) => innerWidth === w, width, { timeout: 10_000 });
  await page.waitForTimeout(100);
  await keepEngraving(false);
}
