import { expect, test, type Page } from "@playwright/test";

// The navigation on a narrow screen: a Menu over the page that never has focus hidden under it.
const menu = (page: Page) => page.locator("#nav-menu");
const isOpen = (page: Page) => menu(page).evaluate((d) => (d as HTMLDetailsElement).open);

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/#/viewer");
  await page.locator(".nav-toggle").click();
  await expect(page.locator("#lang-select")).toBeVisible();
});

test("Escape closes the open menu and puts focus back on the Menu button", async ({ page }) => {
  await page.locator("#nav-menu a[data-route=runs]").focus();
  await page.keyboard.press("Escape");
  expect(await isOpen(page)).toBe(false);
  await expect(page.locator(".nav-toggle")).toBeFocused();
});

test("Escape in the open Quality menu closes only that menu", async ({ page }) => {
  await page.locator("#nav-quality > summary").click();
  await page.keyboard.press("Escape");
  expect(await page.locator("#nav-quality").evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  expect(await isOpen(page)).toBe(true);
});

test("focus that moves to the page without passing through the menu closes it", async ({ page }) => {
  // Opened with a click, focus then nowhere (as after a click on the page's background), then on the page.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.locator("#main").focus();
  expect(await isOpen(page)).toBe(false);
});

test("Tab past the end of the open menu closes it", async ({ page }) => {
  await page.locator("#lang-select").focus();
  await page.keyboard.press("Tab");
  expect(await isOpen(page)).toBe(false);
});

test("on a wide screen the navigation stays open whatever has focus", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.locator("#main").focus();
  await page.keyboard.press("Escape");
  expect(await isOpen(page)).toBe(true);
});

test("closing the shortcut sheet opened from the menu puts focus on the Menu button, not nowhere", async ({ page }) => {
  await page.locator("#nav-menu a[data-route=runs]").focus();
  await page.keyboard.press("F1");
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  // Focus went into the sheet, so the menu closed and the link that had focus is hidden.
  expect(await isOpen(page)).toBe(false);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.locator(".nav-toggle")).toBeFocused();
});

test("the shortcut sheet opens at its heading, not scrolled to its Close button", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 500 });
  await page.keyboard.press("F1");
  const sheet = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(sheet.getByRole("heading", { name: "Keyboard shortcuts" })).toBeFocused();
  expect(await sheet.evaluate((d) => [d.scrollTop, d.scrollWidth - d.clientWidth])).toEqual([0, 0]);
  // Tab goes on to the one thing to act on.
  await page.keyboard.press("Tab");
  await expect(sheet.getByRole("button", { name: "Close" })).toBeFocused();
});

test("closing the shortcut sheet gives focus back to what had it when that is still there", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.locator("#lang-select").focus();
  await page.keyboard.press("F1");
  await page.keyboard.press("Escape");
  await expect(page.locator("#lang-select")).toBeFocused();
});
