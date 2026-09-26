import { defineConfig, devices } from "@playwright/test";

// e2e runs against a real `brasscribe studio` on its own port. Set
// STUDIO_URL to test an engine that is already running instead.
const port = Number(process.env.STUDIO_PORT ?? 8799);
const external = process.env.STUDIO_URL;

export default defineConfig({
  testDir: "e2e",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    locale: "en-GB",
    baseURL: external ?? `http://127.0.0.1:${port}`,
    viewport: { width: 1440, height: 1000 },
    launchOptions: { args: ["--autoplay-policy=no-user-gesture-required"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } }],
  webServer: external
    ? undefined
    : {
        command: `pixi run -e default brasscribe studio --no-browser --port ${port}`,
        cwd: "..",
        url: `http://127.0.0.1:${port}/v1/health`,
        reuseExistingServer: true,
        timeout: 180_000,
        stdout: "pipe",
      },
});
