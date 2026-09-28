import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// One synthesizer per page (src/lib/sharedsynth.ts): opening scores again, leaving the viewer and
// coming back, and two scores on one page all use one synth and one SoundFont download, and a
// reload revalidates the SoundFont kept in IndexedDB instead of downloading it again.

const here = dirname(fileURLToPath(import.meta.url));
const fixture = join(here, "..", "..", "apps", "fixtures", "old-hundredth", "brass-band.musicxml");
const full = readFileSync(fixture, "utf8");
/** The same score cut to its first 4 of 12 bars, to tell the two scores' MIDI apart. */
const short = full.replace(/<measure implicit="no" number="(?:[5-9]|1[0-2])">[\s\S]*?<\/measure>\s*/g, "");

type Score = HTMLElement & { ready: boolean; rendered: boolean; ownsPlayer: boolean; position: { endTime: number }; claimPlayer(): void; load(x: string, l?: string): Promise<void> };

/** Requests for a SoundFont, with their status. */
function soundFontRequests(page: Page): { url: string; status: number }[] {
  const seen: { url: string; status: number }[] = [];
  page.on("response", (r) => {
    if (r.url().endsWith(".sf2")) seen.push({ url: r.url(), status: r.status() });
  });
  return seen;
}

const stats = (page: Page) => page.evaluate(() => {
  const s = (customElements.get("bs-score") as unknown as { synth: { synthsCreated: number; soundFontLoads: number } }).synth;
  return { synths: s.synthsCreated, loads: s.soundFontLoads };
});

async function openInViewer(page: Page): Promise<void> {
  await page.setInputFiles("#open-musicxml", fixture);
  await expect.poll(() => page.evaluate(() => (document.querySelector("bs-score") as unknown as Score | null)?.ready === true)).toBe(true);
}

test("scores opened one after another share one synth and one SoundFont download", async ({ page }) => {
  const sf = soundFontRequests(page);
  await page.goto("/#/viewer");
  await openInViewer(page);
  await openInViewer(page); // the same element loads a second score
  await page.evaluate(() => (location.hash = "#/runs"));
  await expect(page.locator("#main bs-score")).toHaveCount(0);
  await page.evaluate(() => (location.hash = "#/viewer"));
  await openInViewer(page); // a new element after navigation
  expect(await stats(page)).toEqual({ synths: 1, loads: 1 });
  expect(sf.filter((r) => r.status === 200)).toHaveLength(1);
});

test("two scores on one page: one synth, moved to the score that plays, with that score's MIDI", async ({ page }) => {
  await page.goto("/#/viewer");
  const ends = await page.evaluate(async ([a, b]) => {
    const main = document.querySelector("#main")!;
    main.replaceChildren();
    const one = document.createElement("bs-score") as unknown as Score;
    const two = document.createElement("bs-score") as unknown as Score;
    main.append(one, two);
    await Promise.all([one.load(a, "full"), two.load(b, "short")]);
    return null;
  }, [full, short] as const);
  expect(ends).toBeNull();
  const state = () => page.evaluate(() => [...document.querySelectorAll("#main bs-score")].map((e) => {
    const s = e as unknown as Score;
    return { owns: s.ownsPlayer, ready: s.ready, end: s.position.endTime };
  }));
  await expect.poll(async () => (await state())[0].ready).toBe(true);
  let [a, b] = await state();
  expect(a.owns && !b.owns && !b.ready).toBe(true);
  await page.evaluate(() => (document.querySelectorAll("#main bs-score")[1] as unknown as Score).claimPlayer());
  await expect.poll(async () => (await state())[1].ready).toBe(true);
  [a, b] = await state();
  expect(!a.owns && !a.ready && b.owns).toBe(true);
  // The synth plays the short score now: its end is about a third of the full one.
  expect(b.end).toBeGreaterThan(0);
  expect(b.end).toBeLessThan(a.end * 0.5);
  expect(await stats(page)).toEqual({ synths: 1, loads: 1 });
});

test("a reload revalidates the kept SoundFont instead of downloading it again", async ({ page }) => {
  const sf = soundFontRequests(page);
  await page.goto("/#/viewer");
  await openInViewer(page);
  await page.reload();
  await openInViewer(page);
  expect(sf.map((r) => r.status)).toEqual([200, 304]);
});
