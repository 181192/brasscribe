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

// Pink, the hidden palette: follows the system's light or dark, and steps aside for more contrast.
const palette = (page: Page) => page.evaluate(() => document.documentElement.getAttribute("data-palette"));

for (const [system, expected] of [["light", "#FFF6F9"], ["dark", "#1B1017"]] as const) {
  test(`Pink on a ${system} system uses pink ${system}`, async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("brasscribe.studio.theme", "pink"));
    await page.emulateMedia({ colorScheme: system, contrast: "no-preference" });
    await page.goto("/#/viewer");
    expect(await palette(page)).toBe("pink");
    expect(await theme(page)).toBeNull();
    expect(await bg(page)).toBe(expected);
    expect(await scheme(page)).toBe(system);
    await expect(page.locator("#theme-select")).toHaveValue("pink");
  });
}

test("more contrast wins over Pink", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("brasscribe.studio.theme", "pink"));
  await page.emulateMedia({ colorScheme: "light", contrast: "more" });
  await page.goto("/#/viewer");
  expect(await palette(page)).toBeNull();
  expect(await bg(page)).toBe("#FFFFFF");
});

test("five activations of the lockup unlock Pink, from the keyboard too", async ({ page }) => {
  // On Runs, the lockup's own page, so activating it does not move focus to a new view.
  await page.goto("/#/runs");
  const pink = page.locator('#theme-select option[value="pink"]');
  await expect(pink).toHaveCount(0);
  await page.locator("#brand").focus();
  for (let i = 0; i < 5; i++) await page.keyboard.press("Enter");
  await expect(pink).toHaveCount(1);
  await expect(pink).toHaveText("Pink");
  await expect(page.locator("#announcer")).toHaveText("🎺 Pink unlocked");
  await expect(page.locator(".pink-note")).toBeVisible();
  await page.selectOption("#theme-select", "pink");
  expect(await palette(page)).toBe("pink");
  await page.reload();
  await expect(pink).toHaveCount(1);
  // Switching it off: any other choice.
  await page.selectOption("#theme-select", "system");
  expect(await palette(page)).toBeNull();
  await expect(pink).toHaveCount(1);
});
