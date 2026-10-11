import { expect, test, type Page } from "@playwright/test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = join(here, "..", "..", "apps", "fixtures", "old-hundredth", "brass-band.musicxml");

/** Uncaught page errors, collected for the whole test. */
function pageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

test("the score viewer opens a MusicXML file and renders it", async ({ page }) => {
  const errors = pageErrors(page);
  await page.goto("/#/viewer");
  await page.setInputFiles("#open-musicxml", fixture);
  await expect(page.locator("#viewer-status")).toContainText("parts");
  await expect(page.locator("#viewer-status")).not.toContainText("Could not open");
  await expect(page.locator("#main .notice")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (document.querySelector("bs-score") as HTMLElement & { rendered: boolean }).rendered)).toBe(true);
  await expect(page.locator("bs-score .score-surface svg, bs-score .score-surface canvas").first()).toBeVisible();
  // The player finishes loading its soundfont and MIDI (the step that used to overflow the stack).
  await expect.poll(() => page.evaluate(() => (document.querySelector("bs-score") as HTMLElement & { ready: boolean }).ready)).toBe(true);
  expect(errors).toEqual([]);
});

test("Skip to main content moves focus to the page's content without leaving the page", async ({ page }) => {
  await page.goto("/#/viewer");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  expect(new URL(page.url()).hash).toBe("#/viewer");
  await expect(page.locator("#main h1")).toHaveText("Score viewer");
});

test("the example score that ships with Studio opens in the viewer", async ({ page }) => {
  const errors = pageErrors(page);
  await page.goto("/#/viewer?example=old-hundredth");
  await expect(page.locator("#viewer-status")).toContainText("Old Hundredth");
  await expect(page.locator("#viewer-status")).toContainText("parts");
  await expect(page.locator("#main .notice")).toHaveCount(0);
  expect(errors).toEqual([]);
});

type Score = HTMLElement & {
  rendered: boolean; ready: boolean; playing: boolean; layout: string; position: { tick: number };
  api: { settings: { display: { staveProfile: number } }; score: { tracks: { staves: { showTablature: boolean; showStandardNotation: boolean }[] }[] } } | null;
};
const score = <T>(page: Page, read: (s: Score) => T) => page.evaluate(`(${read.toString()})(document.querySelector("bs-score"))`) as Promise<T>;
const fixtures = join(here, "..", "..", "apps", "fixtures");

// A tablature-only part, as the engine's tab profiles write it (one staff with the strings' tuning).
// Under the notation stave profile alphaTab had no staff to draw for it and the viewer showed
// "Cannot read properties of undefined (reading 'staves')" under an enabled player.
test("a tab opens as tablature and plays with the score's controls", async ({ page }) => {
  const errors = pageErrors(page);
  page.on("console", (m) => { if (m.type() === "error" && /AlphaTab/.test(m.text())) errors.push(m.text()); });
  await page.goto("/#/viewer");
  await page.setInputFiles("#open-musicxml", join(fixtures, "guitar-line", "tab.musicxml"));
  await expect(page.locator("#viewer-status")).toContainText("7 bars, 1 parts");
  await expect(page.locator("#main .notice")).toHaveCount(0);
  await expect.poll(() => score(page, (s) => s.rendered && s.ready)).toBe(true);
  expect(await score(page, (s) => [s.layout, s.api!.score.tracks.map((t) => t.staves.map((st) => [st.showTablature, st.showStandardNotation]))])).toEqual(["tab", [[[true, false]]]]);
  // alphaTab's StaveProfile.Tab.
  expect(await score(page, (s) => s.api!.settings.display.staveProfile)).toBe(3);
  await expect(page.locator("bs-score .score-surface svg").first()).toBeVisible();
  // The uncertain notes' "?" and their legend, as on a score.
  await expect(page.locator("bs-score .score-marks .q")).toHaveCount(2);
  await expect(page.locator("bs-score .score-legend")).toContainText("notes marked ?");

  // Play, repeat bars and hearing a part work as for a score.
  for (const name of ["Play", "Stop", "Repeat"]) await expect(page.getByRole("button", { name, exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(() => score(page, (s) => s.playing && s.position.tick > 0)).toBe(true);
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect.poll(() => score(page, (s) => s.playing)).toBe(false);
  await page.getByRole("button", { name: "Repeat", exact: true }).click();
  await expect(page.locator("bs-score .score-status")).toContainText("1–4");
  await expect(page.locator("bs-score .mixer .part-name")).toHaveText("Guitar");

  // Reading aloud has no tablature yet: the panel gives way to the reason, and a reading key says it.
  await expect(page.locator("bs-score details.talking")).toBeHidden();
  await expect(page.locator("bs-score .talking-off")).toHaveText(/Tablature cannot be read aloud yet/);
  await page.locator("bs-score .score-view").focus();
  await page.keyboard.press("r");
  await expect(page.locator("[aria-live]").filter({ hasText: "Tablature cannot be read aloud yet" }).first()).toBeAttached();
  expect(errors).toEqual([]);
});

test("tablature under a notation staff shows both, and a band score stays notation", async ({ page }) => {
  const errors = pageErrors(page);
  await page.goto("/#/viewer");
  await page.setInputFiles("#open-musicxml", join(fixtures, "bass-line-marks", "tab-and-notation.musicxml"));
  await expect.poll(() => score(page, (s) => s.rendered && s.layout)).toBe("tab-and-notation");
  // alphaTab's StaveProfile.ScoreTab, then Score.
  expect(await score(page, (s) => s.api!.settings.display.staveProfile)).toBe(1);
  await expect(page.locator("#main .notice")).toHaveCount(0);
  // Each uncertain note is counted once, not once per staff.
  await expect(page.locator("bs-score .score-legend")).toContainText("4 notes marked ?");
  await page.setInputFiles("#open-musicxml", fixture);
  await expect.poll(() => score(page, (s) => s.rendered && s.layout)).toBe("notation");
  expect(await score(page, (s) => s.api!.settings.display.staveProfile)).toBe(2);
  await expect(page.locator("bs-score details.talking")).toBeVisible();
  expect(errors).toEqual([]);
});

test("a file that cannot be shown says what to do, keeps the message under Details and leaves no player to press", async ({ page }) => {
  await page.goto("/#/viewer");
  await expect(page.locator("bs-score")).toBeHidden();
  await page.setInputFiles("#open-musicxml", { name: "notes.musicxml", mimeType: "application/xml", buffer: Buffer.from('<?xml version="1.0"?><not-a-score/>') });
  const notice = page.locator("#main .notice-error");
  await expect(notice.locator(".notice-title")).toHaveText("notes.musicxml could not be shown.");
  await expect(notice).toContainText("Check that it is a MusicXML file");
  const details = notice.locator("details");
  await expect(details.locator("summary")).toHaveText("Details");
  expect(await details.evaluate((d: HTMLDetailsElement) => d.open)).toBe(false);
  expect((await details.locator(".detail").textContent())!.length).toBeGreaterThan(0);
  await expect(page.locator("#viewer-status")).toHaveText("Could not open notes.musicxml.");
  await expect(page.locator("bs-score")).toBeHidden();
  // The player itself is back to "no score": nothing enabled, and the empty score is no stop for the Tab key.
  expect(await page.evaluate(() => {
    const s = document.querySelector("bs-score")!;
    const controls = Array.from(s.querySelectorAll<HTMLButtonElement>(".transport button, .transport input, .transport select"));
    return [controls.length > 8, controls.every((c) => c.disabled), s.querySelector<HTMLElement>(".score-view")!.tabIndex, s.querySelector(".score-status")!.textContent, (s as unknown as { api: unknown }).api];
  })).toEqual([true, true, -1, "No score loaded.", null]);

  // A good file after it opens as usual, and the controls come back.
  await page.setInputFiles("#open-musicxml", fixture);
  await expect(page.locator("#viewer-status")).toContainText("parts");
  await expect(page.locator("#main .notice")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
});

/** A cornet part in notation and a guitar part in tablature, two bars each (made up for this test). */
function bandAndTab(): string {
  const note = (step: string, octave: number, extra = "") =>
    `<note><pitch><step>${step}</step><octave>${octave}</octave></pitch><duration>2</duration><voice>1</voice><type>half</type>${extra}</note>`;
  const fret = (string: number, n: number) => `<notations><technical><string>${string}</string><fret>${n}</fret></technical></notations>`;
  const tuning = [["E", 2], ["A", 2], ["D", 3], ["G", 3], ["B", 3], ["E", 4]]
    .map(([s, o], i) => `<staff-tuning line="${i + 1}"><tuning-step>${s}</tuning-step><tuning-octave>${o}</tuning-octave></staff-tuning>`).join("");
  const attrs = (clef: string, more = "") => `<attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>${clef}${more}</attributes>`;
  return `<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><work><work-title>Band and tab</work-title></work>
<part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part><score-part id="P2"><part-name>Guitar</part-name></score-part></part-list>
<part id="P1"><measure number="1">${attrs("<clef><sign>G</sign><line>2</line></clef>")}${note("C", 5)}${note("D", 5)}</measure><measure number="2">${note("E", 5)}${note("C", 5)}</measure></part>
<part id="P2"><measure number="1">${attrs("<clef><sign>TAB</sign><line>5</line></clef>", `<staff-details><staff-lines>6</staff-lines>${tuning}</staff-details>`)}${note("C", 3, fret(5, 3))}${note("D", 3, fret(4, 0))}</measure><measure number="2">${note("E", 3, fret(4, 2))}${note("C", 3, fret(5, 3))}</measure></part>
</score-partwise>`;
}

test("in a score with a band part and a tab part, the band part is still read aloud and the tab part says why not", async ({ page }) => {
  const errors = pageErrors(page);
  await page.goto("/#/viewer");
  await page.setInputFiles("#open-musicxml", { name: "band-and-tab.musicxml", mimeType: "application/xml", buffer: Buffer.from(bandAndTab()) });
  await expect.poll(() => score(page, (s) => s.rendered && s.layout)).toBe("tab-and-notation");
  await expect(page.locator("#main .notice")).toHaveCount(0);
  // The cornet part is the current one: the reading panel is there, and R reads its bar.
  await expect(page.locator("bs-score details.talking")).toBeVisible();
  await expect(page.locator("bs-score .talking-off")).toBeHidden();
  await page.locator("bs-score .score-view").focus();
  await page.keyboard.press("r");
  await expect.poll(() => score(page, (s) => (s as unknown as { lastAnnouncement: string }).lastAnnouncement)).toMatch(/C/);
  // The guitar part: the panel gives way to the reason, and R says it.
  await page.locator("bs-score .transport select").selectOption({ label: "Guitar" });
  await expect(page.locator("bs-score details.talking")).toBeHidden();
  await expect(page.locator("bs-score .talking-off")).toHaveText(/Tablature cannot be read aloud yet/);
  await page.locator("bs-score .score-view").focus();
  await page.keyboard.press("r");
  await expect(page.locator("[aria-live]").filter({ hasText: "Tablature cannot be read aloud yet" }).first()).toBeAttached();
  // And back.
  await page.locator("bs-score .transport select").selectOption({ label: "Solo Cornet" });
  await expect(page.locator("bs-score details.talking")).toBeVisible();
  expect(errors).toEqual([]);
});
