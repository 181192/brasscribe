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
