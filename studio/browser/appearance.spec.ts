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

// Pink, the hidden palette: Pink light and Pink dark pick their own light or dark, and the palette
// steps aside for more contrast.
const palette = (page: Page) => page.evaluate(() => document.documentElement.getAttribute("data-palette"));

for (const [choice, mode, system, expected] of [
  ["pink-light", "light", "dark", "#FFF6F9"],
  ["pink-dark", "dark", "light", "#1B1017"],
] as const) {
  test(`${choice} on a ${system} system uses pink ${mode}`, async ({ page }) => {
    await page.addInitScript((v) => localStorage.setItem("brasscribe.studio.theme", v), choice);
    await page.emulateMedia({ colorScheme: system, contrast: "no-preference" });
    await page.goto("/#/viewer");
    expect(await palette(page)).toBe("pink");
    expect(await theme(page)).toBe(mode);
    expect(await bg(page)).toBe(expected);
    expect(await scheme(page)).toBe(mode);
    await expect(page.locator("#theme-select")).toHaveValue(choice);
  });
}

for (const [system, migrated, expected] of [["light", "pink-light", "#FFF6F9"], ["dark", "pink-dark", "#1B1017"]] as const) {
  test(`an earlier Pink on a ${system} system becomes ${migrated}`, async ({ page }) => {
    await page.addInitScript(() => {
      if (!sessionStorage.getItem("seeded")) localStorage.setItem("brasscribe.studio.theme", "pink");
      sessionStorage.setItem("seeded", "1");
    });
    await page.emulateMedia({ colorScheme: system, contrast: "no-preference" });
    await page.goto("/#/viewer");
    expect(await palette(page)).toBe("pink");
    expect(await bg(page)).toBe(expected);
    await expect(page.locator("#theme-select")).toHaveValue(migrated);
    expect(await page.evaluate(() => [localStorage.getItem("brasscribe.studio.theme"), localStorage.getItem("brasscribe.studio.pink")])).toEqual([migrated, "1"]);
    // Kept once migrated: the system's mode no longer matters.
    await page.emulateMedia({ colorScheme: system === "light" ? "dark" : "light" });
    await page.reload();
    expect(await bg(page)).toBe(expected);
  });
}

test("more contrast wins over the Pink palette and keeps its light or dark", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("brasscribe.studio.theme", "pink-dark"));
  await page.emulateMedia({ colorScheme: "light", contrast: "more" });
  await page.goto("/#/viewer");
  expect(await palette(page)).toBeNull();
  expect(await theme(page)).toBe("dark");
  expect(await bg(page)).toBe("#000000");
});

test("five activations of the lockup unlock Pink light and Pink dark, from the keyboard too", async ({ page }) => {
  // On Runs, the lockup's own page, so activating it does not move focus to a new view.
  await page.goto("/#/runs");
  const options = page.locator("#theme-select option");
  const pink = page.locator('#theme-select option[value^="pink"]');
  await expect(pink).toHaveCount(0);
  await page.locator("#brand").focus();
  for (let i = 0; i < 5; i++) await page.keyboard.press("Enter");
  // Listed after Match system, Light and Dark, each named by its label.
  await expect(options).toHaveText(["Match system", "Light", "Dark", "Pink light", "Pink dark"]);
  await expect(page.locator("#announcer")).toHaveText("🎺 Pink unlocked");
  await expect(page.locator(".pink-note")).toBeVisible();
  await expect(page.getByLabel("Appearance")).toBeVisible();
  await page.selectOption("#theme-select", "pink-dark");
  expect(await palette(page)).toBe("pink");
  expect(await theme(page)).toBe("dark");
  await page.selectOption("#theme-select", "pink-light");
  expect(await theme(page)).toBe("light");
  await page.reload();
  await expect(pink).toHaveCount(2);
  // Switching it off: any other choice.
  await page.selectOption("#theme-select", "system");
  expect(await palette(page)).toBeNull();
  await expect(pink).toHaveCount(2);
});
