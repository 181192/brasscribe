import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

// e2e runs against a real `brasscribe studio` on its own port. Set
// STUDIO_URL to test an engine that is already running instead.
const port = Number(process.env.STUDIO_PORT ?? 8799);
const external = process.env.STUDIO_URL;

// The Compare test gets a second engine of its own whose data directory holds only the committed
// pair of runs in e2e/fixtures/compare (copied to a temporary folder, since the engine writes
// there), so it never depends on what data/runs holds. STUDIO_COMPARE_URL points it elsewhere.
const comparePort = Number(process.env.STUDIO_COMPARE_PORT ?? 8797);
const compareData = join(tmpdir(), `brasscribe-e2e-compare-${comparePort}`);

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
  webServer: [
    ...(external
      ? []
      : [{
          command: `pixi run -e default brasscribe studio --no-browser --port ${port}`,
          cwd: "..",
          url: `http://127.0.0.1:${port}/v1/health`,
          reuseExistingServer: true,
          timeout: 180_000,
          stdout: "pipe" as const,
        }]),
    ...(process.env.STUDIO_COMPARE_URL
      ? []
      : [{
          command: `rm -rf "${compareData}" && mkdir -p "${compareData}" && cp -R studio/e2e/fixtures/compare/runs "${compareData}/runs"`
            + ` && pixi run -e default brasscribe studio --no-browser --port ${comparePort}`,
          cwd: "..",
          env: { BRASSCRIBE_DATA: compareData },
          url: `http://127.0.0.1:${comparePort}/v1/health`,
          reuseExistingServer: false,
          timeout: 180_000,
          stdout: "pipe" as const,
        }]),
  ],
});
