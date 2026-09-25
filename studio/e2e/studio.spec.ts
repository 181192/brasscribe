import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const shots = join(here, "..", "docs", "screenshots");
const repo = join(here, "..", "..");
const golden = join(repo, "data", "golden", "mikkel-arranged-band");
mkdirSync(shots, { recursive: true });

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function axe(page: Page, label: string): Promise<void> {
  const res = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const bad = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const summary = res.violations.map((v) => `${v.impact} ${v.id} (${v.nodes.length}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  console.log(`axe ${label}: ${res.violations.length} violations, ${bad.length} serious or critical${summary.length ? `\n  ${summary.join("\n  ")}` : ""}`);
  expect(bad, `serious axe violations on ${label}`).toEqual([]);
}

async function shot(page: Page, name: string, fullPage = true): Promise<void> {
  await page.screenshot({ path: join(shots, `${name}.png`), fullPage });
}

interface JobLite {
  id: string;
  title?: string | null;
  status: string;
  outputs?: string[];
  golden?: boolean;
}

async function mikkelRun(page: Page): Promise<JobLite> {
  const jobs = (await (await page.request.get("/v1/jobs")).json()) as JobLite[];
  const runs = jobs.filter((j) => /mikkel/i.test(j.title ?? "") && j.status === "succeeded" && j.outputs?.includes("brass-band.musicxml"));
  expect(runs.length, "a finished Mikkel run in the data directory").toBeGreaterThan(0);
  // Prefer the newest run that reproduces data/golden note for note.
  for (const r of runs) {
    const c = await page.request.get(`/v1/jobs/${r.id}/compare?reference=mikkel-arranged-band`);
    if (c.ok() && (await c.json()).ok) return { ...r, golden: true };
  }
  return { ...runs[0], golden: false };
}

async function waitRendered(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const s = document.querySelector("#main bs-score") as unknown as { rendered?: boolean } | null;
    return !!s?.rendered;
  }, undefined, { timeout: 150_000 });
}

test("the Mikkel run: stage graph, score, play one bar, axe", async ({ page }) => {
  const run = await mikkelRun(page);
  await page.goto("/#/runs");
  await expect(page.getByRole("heading", { level: 1, name: "Runs" })).toBeVisible();
  await expect(page.getByRole("link", { name: run.title! }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Start run" })).toBeVisible();
  await shot(page, "runs");
  await axe(page, "runs");

  await page.goto(`/#/runs/${run.id}/score`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Mikkel");
  // Stage graph from the manifest: timings, devices, cache hits.
  await expect(page.locator(".stage-node").first()).toBeVisible();
  const nodes = await page.locator(".stage-node").count();
  expect(nodes).toBeGreaterThanOrEqual(8);
  await expect(page.locator(".stage-node", { hasText: "cache hit" }).first()).toBeVisible();

  const t0 = Date.now();
  await waitRendered(page);
  console.log(`score rendered in ${Date.now() - t0} ms`);
  const info = await page.evaluate(() => {
    const s = document.querySelector("#main bs-score") as unknown as { bars: unknown[]; api: { score: { tracks: unknown[] } } };
    return { bars: s.bars.length, tracks: s.api.score.tracks.length };
  });
  console.log(`score: ${info.bars} bars, ${info.tracks} parts`);
  expect(info.bars).toBeGreaterThan(100);
  expect(info.tracks).toBe(18);
  await shot(page, "run-score", false);

  // Play bar 9 with the keyboard: focus the score, go there, press P.
  await page.waitForFunction(() => (document.querySelector("#main bs-score") as unknown as { ready?: boolean })?.ready === true, undefined, { timeout: 120_000 });
  await page.locator(".score-view").focus();
  for (let i = 0; i < 8; i++) await page.keyboard.press("Alt+ArrowDown");
  const before = await page.evaluate(() => {
    const s = document.querySelector("#main bs-score") as unknown as { current: number; bars: { start: number; end: number }[] };
    return { bar: s.current, start: s.bars[s.current].start, end: s.bars[s.current].end };
  });
  expect(before.bar).toBe(8);
  await page.keyboard.press("p");
  await page.waitForFunction((start) => {
    const s = document.querySelector("#main bs-score") as unknown as { position: { tick: number }; playing: boolean };
    return s.position.tick > start + 960;
  }, before.start, { timeout: 30_000 });
  const during = await page.evaluate(() => (document.querySelector("#main bs-score") as unknown as { position: { tick: number; time: number } }).position);
  console.log(`playing bar 9: tick ${during.tick} in [${before.start}, ${before.end}), time ${during.time.toFixed(0)} ms`);
  expect(during.tick).toBeGreaterThan(before.start + 960);
  expect(during.tick).toBeLessThanOrEqual(before.end);
  await shot(page, "run-score-playing", false);
  // It stops by itself at the end of the bar.
  await page.waitForFunction(() => (document.querySelector("#main bs-score") as unknown as { playing: boolean }).playing === false, undefined, { timeout: 30_000 });
  await axe(page, "run score");

  // Loop and speed from the keyboard.
  await page.locator(".score-view").focus();
  await page.keyboard.press("[");
  await page.keyboard.press("Alt+ArrowDown");
  await page.keyboard.press("Alt+ArrowDown");
  await page.keyboard.press("]");
  await page.keyboard.press("l");
  for (let i = 0; i < 5; i++) await page.keyboard.press("-");
  await expect(page.getByRole("button", { name: /Loop 9–11/ })).toHaveAttribute("aria-pressed", "true");
  const speed = await page.evaluate(() => (document.querySelector("#main bs-score") as unknown as { api: { playbackSpeed: number } }).api.playbackSpeed);
  expect(speed).toBeCloseTo(0.75, 2);
});

test("inspector tabs render and pass axe", async ({ page }) => {
  const run = await mikkelRun(page);
  for (const tab of ["audio", "stems", "roll", "beats", "voices", "musicxml", "manifest"]) {
    await page.goto(`/#/runs/${run.id}/${tab}`);
    const panel = page.locator(".tabpanel:not([hidden])");
    await expect(panel).toBeVisible();
    await page.waitForFunction(() => !document.querySelector(".tabpanel:not([hidden]) .loading"), undefined, { timeout: 120_000 });
    if (tab === "audio") await expect(panel.getByRole("status").first()).toContainText(/Hz/, { timeout: 120_000 });
    if (tab === "stems") await expect(panel.getByRole("img", { name: /Energy over time.*for / })).toBeVisible({ timeout: 180_000 });
    if (tab === "musicxml") {
      await expect(panel.getByText(/parts identical/)).toBeVisible({ timeout: 60_000 });
      await panel.getByRole("button", { name: /Run the round trip|Run again/ }).click();
      await expect(panel.getByText(/read back by MuseScore/)).toBeVisible({ timeout: 180_000 });
      console.log(`round trip: ${await panel.getByText(/read back by MuseScore/).textContent()}`);
    }
    await page.waitForTimeout(500);
    await shot(page, `run-${tab}`);
    await axe(page, `run ${tab}`);
  }
});

test("score viewer opens data/golden and plays", async ({ page }) => {
  test.skip(!existsSync(join(golden, "brass-band.musicxml")), "data/golden is not available");
  await page.goto("/#/viewer");
  await page.setInputFiles("#open-musicxml", join(golden, "brass-band.musicxml"));
  await waitRendered(page);
  await expect(page.locator("#viewer-status")).toContainText("parts");
  await page.waitForFunction(() => (document.querySelector("#main bs-score") as unknown as { ready?: boolean })?.ready === true, undefined, { timeout: 120_000 });
  await page.getByRole("button", { name: "Play bar" }).click();
  await page.waitForFunction(() => (document.querySelector("#main bs-score") as unknown as { position: { time: number } }).position.time > 0, undefined, { timeout: 30_000 });
  await shot(page, "viewer-golden", false);
  await axe(page, "viewer");
});

test("compare the Mikkel run with data/golden", async ({ page }) => {
  const run = await mikkelRun(page);
  await page.goto(`/#/compare?a=${run.id}&b=ref:mikkel-arranged-band`);
  const summary = page.getByText(/notes identical, \d+ added, \d+ removed, \d+ moved, \d+ octave/);
  await expect(summary).toBeVisible({ timeout: 60_000 });
  console.log(`compare ${run.id} with data/golden: ${await summary.textContent()}`);
  if (run.golden) await expect(summary).toContainText("0 added, 0 removed, 0 moved, 0 octave");
  await shot(page, "compare-golden");
  await axe(page, "compare");
});

test("other views render and pass axe", async ({ page }) => {
  for (const [route, name] of [["bench", "Benchmarks"], ["parity", "Conversion parity"], ["conformance", "Core conformance"], ["registry", "Datasets and models"]]) {
    await page.goto(`/#/${route}`);
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 120_000 });
    if (route === "bench") {
      // Run one CPU suite from the UI and see its gate.
      await page.getByRole("button", { name: "Run quant-urmp", exact: true }).click();
      await expect(page.getByText(/Gate (passed|failed) for quant-urmp/)).toBeVisible({ timeout: 120_000 });
      console.log(`bench: ${await page.getByText(/Gate (passed|failed) for quant-urmp/).textContent()}`);
    }
    await shot(page, route);
    await axe(page, route);
  }
});

test("start a run on a capture and follow the live stage graph", async ({ page }) => {
  // Runs real models (a cache miss can take minutes behind the GPU mutex), so it is opt-in.
  test.skip(!process.env.STUDIO_E2E_LIVE, "set STUDIO_E2E_LIVE=1 to run a pipeline");
  test.setTimeout(600_000);
  await page.goto("/#/runs");
  await page.getByLabel("Capture or dataset item", { exact: true }).first().check();
  const source = page.locator("#run-source");
  await expect(source).toBeEnabled();
  await source.selectOption("capture:smoke.wav");
  await page.locator("#run-profile").selectOption("solo");
  await shot(page, "runs-start");
  await page.getByRole("button", { name: "Start run" }).click();
  await page.waitForURL(/#\/runs\/[^/]+-solo-/, { timeout: 30_000 });
  const id = decodeURIComponent(page.url().split("#/runs/")[1].split("/")[0]);
  console.log(`started ${id}`);
  // The graph updates from SSE: some stage leaves "pending" while the job runs.
  await expect(page.locator(".stage-node:not(.status-pending)").first()).toBeVisible({ timeout: 120_000 });
  await shot(page, "run-live", false);
  await expect(page.locator(".pill-succeeded, .pill-failed").first()).toBeVisible({ timeout: 540_000 });
  const job = await (await page.request.get(`/v1/jobs/${id}`)).json();
  console.log(`run ${id}: ${job.status}; ${job.stages.map((s: { name: string; status: string; seconds?: number; device?: string }) => `${s.name}=${s.status}${s.seconds != null ? ` ${s.seconds.toFixed(1)}s` : ""}${s.device ? ` ${s.device}` : ""}`).join(", ")}${job.error ? `; error: ${job.error}` : ""}`);
  await shot(page, "run-live-done");
  expect(job.stages.every((s: { status: string }) => s.status !== "pending")).toBe(job.status === "succeeded");
});

test("keyboard: skip link, shortcut sheet, narrow layout", async ({ page }) => {
  await page.goto("/#/runs");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("F1");
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  // Reflow (WCAG 1.4.10): no horizontal page scroll at 360 CSS px; wide tables scroll inside their own region.
  await page.setViewportSize({ width: 360, height: 800 });
  const run = await mikkelRun(page);
  for (const [route, name] of [["runs", "runs-narrow"], [`runs/${run.id}/score`, "run-narrow"], ["compare", "compare-narrow"], ["bench", "bench-narrow"]]) {
    await page.goto(`/#/${route}`);
    await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 60_000 });
    await page.waitForTimeout(500);
    await shot(page, name, false);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${route}`).toBeLessThanOrEqual(1);
  }
});

test("score viewer opens compressed MusicXML (.mxl)", async ({ page }, info) => {
  const src = join(golden, "brass-band.musicxml");
  test.skip(!existsSync(src), "data/golden is not available");
  const mxl = info.outputPath("golden.mxl");
  mkdirSync(dirname(mxl), { recursive: true });
  // MuseScore 4 aborts on shutdown after writing: check the file, not the exit code.
  try {
    execFileSync("mscore", ["-o", mxl, src], { stdio: "ignore", timeout: 120_000 });
  } catch {
    /* see above */
  }
  test.skip(!existsSync(mxl), "mscore could not write .mxl");
  await page.goto("/#/viewer");
  await page.setInputFiles("#open-musicxml", mxl);
  await waitRendered(page);
  await page.waitForFunction(() => (document.querySelector("#main bs-score") as unknown as { api: { tracks: unknown[] } }).api.tracks.length === 18, undefined, { timeout: 60_000 });
  await expect(page.locator("#viewer-status")).toContainText("18 parts");
});

test("dark and high-contrast themes pass axe", async ({ page }) => {
  const run = await mikkelRun(page);
  for (const [name, media] of [["dark", { colorScheme: "dark" }], ["contrast", { contrast: "more" }]] as const) {
    await page.emulateMedia(media);
    for (const route of ["runs", `runs/${run.id}/score`, "compare", "bench"]) {
      await page.goto(`/#/${route}`);
      await page.reload();
      await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 60_000 });
      if (route.endsWith("score")) await waitRendered(page);
      await page.waitForTimeout(300);
      if (route === "runs") await shot(page, `runs-${name}`, false);
      if (route.endsWith("score")) await page.locator("#main bs-score").screenshot({ path: join(shots, `run-score-${name}.png`) });
      await axe(page, `${route} (${name})`);
    }
  }
});

test("re-run from a manifest, follow it live, compare with the original", async ({ page }) => {
  test.setTimeout(600_000);
  const run = await mikkelRun(page);
  await page.goto(`/#/runs/${run.id}/manifest`);
  const panel = page.locator(".tabpanel:not([hidden])");
  await expect(panel.getByRole("button", { name: "Re-run" })).toBeVisible();
  await expect(panel.getByLabel("Allow heavy models on cache misses")).not.toBeChecked();
  const t0 = Date.now();
  await panel.getByRole("button", { name: "Re-run" }).click();
  await page.waitForURL((u) => !u.hash.includes(run.id) && u.hash.startsWith("#/runs/"), { timeout: 30_000 });
  const id = decodeURIComponent(page.url().split("#/runs/")[1].split("/")[0]);
  await expect(page.locator(".pill-succeeded, .pill-failed").first()).toBeVisible({ timeout: 540_000 });
  const job = await (await page.request.get(`/v1/jobs/${id}`)).json();
  const stages = job.stages.map((s: { name: string; status: string; seconds?: number; device?: string }) =>
    `${s.name}=${s.status}${s.seconds != null ? ` ${s.seconds.toFixed(1)}s` : ""}${s.device ? ` ${s.device}` : ""}`).join(", ");
  console.log(`re-run ${id} of ${run.id}: ${job.status} in ${((Date.now() - t0) / 1000).toFixed(1)} s; ${stages}${job.error ? `; error: ${job.error}` : ""}`);
  expect(job.status).toBe("succeeded");
  expect(job.previous_run_id).toBe(run.id);
  await shot(page, "run-rerun", false);
  await page.getByRole("link", { name: "Compare with the run it re-ran" }).click();
  const summary = page.getByText(/notes identical, \d+ added, \d+ removed, \d+ moved, \d+ octave/);
  await expect(summary).toBeVisible({ timeout: 60_000 });
  console.log(`re-run vs original: ${await summary.textContent()}`);
  const engine = page.getByText(/Engine check: composition.json (identical|different)/);
  await expect(engine).toBeVisible();
  console.log(await engine.textContent());
  await shot(page, "compare-rerun");
});
