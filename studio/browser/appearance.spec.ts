import { expect, test, type Page } from "@playwright/test";

// Appearance (design/system.md §10): with more contrast, Light and Dark keep their theme
// and get the high-contrast palette for it; forced colours still hand over to the system.
const bg = (page: Page) => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--bc-bg").trim().toUpperCase());
const scheme = (page: Page) => page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
const theme = (page: Page) => page.evaluate(() => document.documentElement.getAttribute("data-theme"));

const CASES = [
  { choice: "light", system: "dark", pinned: "light", palette: "light" },
  { choice: "dark", system: "light", pinned: "dark", palette: "dark" },
  { choice: null, system: "light", pinned: null, palette: "light" },
  { choice: null, system: "dark", pinned: null, palette: "dark" },
] as const;

for (const c of CASES) {
  test(`more contrast: ${c.choice ?? "Match system"} on a ${c.system} system uses ${c.palette} high contrast`, async ({ page }) => {
    if (c.choice) await page.addInitScript((v) => localStorage.setItem("brasscribe.studio.theme", v), c.choice);
    await page.emulateMedia({ colorScheme: c.system, contrast: "more" });
    await page.goto("/#/viewer");
    expect(await theme(page)).toBe(c.pinned);
    expect(await bg(page)).toBe(c.palette === "light" ? "#FFFFFF" : "#000000");
    expect(await scheme(page)).toBe(c.palette);
  });
}

test("without more contrast the ordinary palettes apply", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("brasscribe.studio.theme", "light"));
  await page.emulateMedia({ colorScheme: "dark", contrast: "no-preference" });
  await page.goto("/#/viewer");
  expect(await theme(page)).toBe("light");
  expect(await bg(page)).toBe("#FBFAF7");
});

test("forced colours still drop the pinned theme", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("brasscribe.studio.theme", "dark"));
  await page.emulateMedia({ forcedColors: "active", contrast: "more" });
  await page.goto("/#/viewer");
  expect(await theme(page)).toBeNull();
});
