import { expect, test } from "@playwright/test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Screenshots of the Pink palette for design/pink/. Runs only with PINK_SHOTS=<dir>.
const here = dirname(fileURLToPath(import.meta.url));
const fixture = join(here, "..", "..", "apps", "fixtures", "old-hundredth", "brass-band.musicxml");
const out = process.env.PINK_SHOTS;

for (const system of ["light", "dark"] as const) {
  test(`Pink score viewer, ${system}`, async ({ page }) => {
    test.skip(!out, "set PINK_SHOTS to write the screenshots");
    await page.addInitScript(() => localStorage.setItem("brasscribe.studio.theme", "pink"));
    await page.emulateMedia({ colorScheme: system, contrast: "no-preference" });
    await page.goto("/#/viewer");
    await page.setInputFiles("#open-musicxml", fixture);
    await expect.poll(() => page.evaluate(() => (document.querySelector("bs-score") as HTMLElement & { rendered: boolean }).rendered)).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: join(out!, `studio-viewer-${system === "light" ? "pink" : "pink-dark"}.png`) });
  });
}
