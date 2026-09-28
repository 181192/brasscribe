import { defineConfig, devices } from "@playwright/test";

// Browser tests against the built bundle served as static files: no engine, no data/.
// `npm run build` first; the bundle under engine/src/brasscribe_engine/static is what runs.
const port = Number(process.env.STUDIO_STATIC_PORT ?? 8798);

export default defineConfig({
  testDir: "browser",
  timeout: 60_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [["list"]],
  use: { locale: "en-GB", baseURL: `http://127.0.0.1:${port}` },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } }],
  webServer: {
    command: `node browser/serve.mjs ${port}`,
    url: `http://127.0.0.1:${port}/index.html`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
