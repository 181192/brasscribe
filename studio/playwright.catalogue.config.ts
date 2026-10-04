import { defineConfig, devices } from "@playwright/test";

// The screen catalogue (catalogue/): every view of the built bundle, served as static files, in every
// variant, with the engine's API answered from committed fixtures (e2e/fixtures/api). No engine, no data/.
// `npm run build` first. CATALOGUE_SHOTS=<dir> also takes a screenshot of each view and variant.
const port = Number(process.env.STUDIO_STATIC_PORT ?? 8796);

export default defineConfig({
  testDir: "catalogue",
  outputDir: "build/catalogue/test-results",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  workers: process.env.CATALOGUE_WORKERS ? Number(process.env.CATALOGUE_WORKERS) : process.env.CI ? 4 : 6,
  reporter: [["list"]],
  use: {
    locale: "en-GB",
    timezoneId: "Europe/Oslo",
    baseURL: `http://127.0.0.1:${port}`,
    reducedMotion: "reduce",
    // A service worker would answer before page.route sees the request.
    serviceWorkers: "block",
    // Scrollbars take no width, as on a Mac: on Linux a page scrollbar that comes and goes (as the page grows, or
    // while a full-page screenshot is taken) changes the score's width, and alphaTab lays the score out again,
    // rounding its first bar differently depending on when that happened. sRGB and no subpixel text, everywhere.
    launchOptions: { args: ["--hide-scrollbars", "--force-color-profile=srgb", "--disable-lcd-text"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } }],
  webServer: {
    command: `node browser/serve.mjs ${port}`,
    url: `http://127.0.0.1:${port}/index.html`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
