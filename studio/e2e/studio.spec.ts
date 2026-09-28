import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { crc32 } from "node:zlib";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const shots = join(here, "..", "docs", "screenshots");
const repo = join(here, "..", "..");
const golden = join(repo, "data", "golden", "mikkel-arranged-band");
mkdirSync(shots, { recursive: true });

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

// Runs a test created; removed afterwards even when the test fails.
const createdRuns: string[] = [];
test.afterAll(async ({ request }) => {
  for (const id of createdRuns.splice(0)) await request.delete(`/v1/runs/${id}`);
});

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

/** A zip archive with the files stored uncompressed (enough for .mxl). */
function zipStored(files: [string, Buffer][]): Buffer {
  const locals: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const [name, data] of files) {
    const n = Buffer.from(name);
    const crc = crc32(data);
    const head = Buffer.alloc(30);
    head.writeUInt32LE(0x04034b50, 0);
    head.writeUInt16LE(20, 4);
    head.writeUInt32LE(crc, 14);
    head.writeUInt32LE(data.length, 18);
    head.writeUInt32LE(data.length, 22);
    head.writeUInt16LE(n.length, 26);
    locals.push(head, n, data);
    const c = Buffer.alloc(46);
    c.writeUInt32LE(0x02014b50, 0);
    c.writeUInt16LE(20, 4);
    c.writeUInt16LE(20, 6);
    c.writeUInt32LE(crc, 16);
    c.writeUInt32LE(data.length, 20);
    c.writeUInt32LE(data.length, 24);
    c.writeUInt16LE(n.length, 28);
    c.writeUInt32LE(offset, 42);
    central.push(c, n);
    offset += 30 + n.length + data.length;
  }
  const cd = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(cd.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cd, end]);
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
  // Only the control for the chosen source shows.
  await expect(page.locator("#run-source")).toBeHidden();
  await shot(page, "runs");
  await axe(page, "runs");

  await page.goto(`/#/runs/${run.id}/score`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/mikkel/i);
  // The stage graph sits behind "Stages", closed when the run succeeded.
  await expect(page.locator(".stage-node").first()).toBeHidden();
  await page.locator(".stages-box > summary").click();
  await expect(page.locator(".stage-node").first()).toBeVisible();
  const nodes = await page.locator(".stage-node").count();
  expect(nodes).toBeGreaterThanOrEqual(5);
  await expect(page.locator(".stage-node", { hasText: "from cache" }).first()).toBeVisible();
  // Stage outlines are at least 3:1 against the page (WCAG 1.4.11).
  const ratio = await page.evaluate(() => {
    const lum = (c: string) => {
      const [r, g, b] = (c.match(/[\d.]+/g) ?? []).slice(0, 3).map((x) => Number(x) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const node = document.querySelector(".stage-node.status-cached, .stage-node.status-imported") as HTMLElement;
    const edge = getComputedStyle(node).outlineColor;
    const bg = getComputedStyle(document.body).backgroundColor;
    const [a, b] = [lum(edge), lum(bg)].sort((x, y) => y - x);
    return (a + 0.05) / (b + 0.05);
  });
  console.log(`stage outline contrast ${ratio.toFixed(2)}:1`);
  expect(ratio).toBeGreaterThanOrEqual(3);

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
  await expect(page.getByRole("button", { name: "Stop repeating" })).toBeVisible();
  await expect(page.locator("#main .score-status")).toContainText("Repeating bars 9–11");
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
      // Running the round trip launches MuseScore on the desktop, so only on request; the stored result shows otherwise.
      await expect(panel.getByRole("button", { name: /Run the round trip|Run again/ })).toBeVisible({ timeout: 60_000 });
      if (process.env.STUDIO_E2E_MUSESCORE) {
        await panel.getByRole("button", { name: /Run the round trip|Run again/ }).click();
        await expect(panel.getByText(/read back by MuseScore/)).toBeVisible({ timeout: 180_000 });
        console.log(`round trip: ${await panel.getByText(/read back by MuseScore/).textContent()}`);
      }
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
  // "Play bar" lives under the toolbar's More menu.
  await page.locator("#main bs-score .transport details.menu > summary").click();
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
});

test("runs page by page, parity names the failing formats, the run actions fit at 320 px", async ({ page }) => {
  const jobs = (await (await page.request.get("/v1/jobs")).json()) as JobLite[];
  await page.goto("/#/runs");
  const rows = page.locator(".runs-table tbody tr");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBe(Math.min(20, jobs.length));
  if (jobs.length > 20) {
    await page.locator("#runs-more").click();
    expect(await rows.count()).toBe(Math.min(40, jobs.length));
    await expect(page.locator(".runs-table a.run-link").nth(20)).toBeFocused();
  }
  // Untitled re-runs of one recording carry the run's own time, so their titles differ.
  const titles = await page.locator(".runs-table a.run-link").allTextContents();
  const untitled = titles.filter((x) => x.startsWith("Recording of"));
  expect(new Set(untitled).size).toBe(untitled.length);

  await page.goto("/#/parity");
  await expect(page.locator("details.card").first()).toBeVisible();
  const below = page.locator(".parity-below tbody tr");
  const n = await below.count();
  for (let i = 0; i < n; i++) {
    const cells = below.nth(i).locator("td");
    expect((await cells.first().textContent())?.trim(), `variant in failing row ${i}`).not.toBe("");
    await expect(cells.last()).toContainText("below");
  }
  console.log(`parity: ${n} rows below the threshold, each with its variant`);

  const run = await mikkelRun(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto(`/#/runs/${run.id}/score`);
  const acts = page.locator(".view-head .actions");
  await expect(acts.getByRole("button", { name: "Re-run" })).toBeVisible();
  const tops = await acts.locator(":scope > *:visible").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  expect(new Set(tops).size, "run actions on one line at 320 px").toBe(1);
  await acts.locator("details.menu:not(.wide-only) > summary").click();
  await expect(acts.getByRole("link", { name: /MusicXML/ })).toBeVisible();
  await expect(acts.getByRole("link", { name: /^Compare/ }).filter({ visible: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await page.screenshot({ path: join(shots, "zoom", "run-actions-320px.png") });
});

// WCAG 1.4.10 reflow at 320 CSS px, 1.4.4 at 200 % zoom (a 1440 px window at 200 % is 720 CSS px),
// and 1.4.12 text spacing: no sideways page scroll (tables, the score and plots scroll inside their
// own regions), the nav collapses to a Menu button, and axe finds nothing serious.
test("reflow at 320 px, 200 % zoom and text spacing", async ({ page }) => {
  test.setTimeout(600_000);
  const run = await mikkelRun(page);
  const routes: [string, string][] = [
    ["runs", "runs"], [`runs/${run.id}/score`, "run"], [`runs/${run.id}/manifest`, "run-manifest"], ["viewer", "viewer"],
    [`compare?a=${run.id}&b=ref:mikkel-arranged-band`, "compare"], ["bench", "bench"], ["parity", "parity"], ["conformance", "conformance"], ["registry", "registry"],
  ];
  const zoom = join(shots, "zoom");
  mkdirSync(zoom, { recursive: true });
  for (const [width, height, label] of [[320, 800, "320"], [720, 500, "200"]] as const) {
    await page.setViewportSize({ width, height });
    for (const [route, name] of routes) {
      await page.goto(`/#/${route}`);
      await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 120_000 });
      if (route.endsWith("/score")) await waitRendered(page);
      await page.waitForTimeout(500);
      await expect(page.locator(".nav-toggle")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `horizontal overflow on ${route} at ${label}`).toBeLessThanOrEqual(1);
      await page.screenshot({ path: join(zoom, `${name}-${label === "320" ? "320px" : "zoom200"}.png`) });
      await axe(page, `${name} at ${label === "320" ? "320 px" : "200 %"}`);
    }
  }
  // The Menu button opens the nav, with the engine status and the language inside it.
  await page.goto("/#/runs");
  await page.locator(".nav-toggle").click();
  await expect(page.getByRole("link", { name: "Score viewer" })).toBeVisible();
  await expect(page.locator("#lang-select")).toBeVisible();
  await page.screenshot({ path: join(zoom, "menu-open-zoom200.png") });
  // 1.4.12: the text-spacing override must not make the page scroll sideways.
  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const [route, name] of routes) {
    await page.goto(`/#/${route}`);
    await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 120_000 });
    await page.addStyleTag({ content: "* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }" });
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `text spacing overflow on ${name}`).toBeLessThanOrEqual(1);
  }
});

test("score viewer opens compressed MusicXML (.mxl)", async ({ page }, info) => {
  const src = join(golden, "brass-band.musicxml");
  test.skip(!existsSync(src), "data/golden is not available");
  const mxl = info.outputPath("golden.mxl");
  mkdirSync(dirname(mxl), { recursive: true });
  // Build the .mxl here (a zip with META-INF/container.xml) instead of launching MuseScore.
  writeFileSync(mxl, zipStored([
    ["META-INF/container.xml", Buffer.from('<?xml version="1.0" encoding="UTF-8"?><container><rootfiles><rootfile full-path="score.musicxml"/></rootfiles></container>')],
    ["score.musicxml", readFileSync(src)],
  ]));
  await page.goto("/#/viewer");
  await page.setInputFiles("#open-musicxml", mxl);
  await waitRendered(page);
  await page.waitForFunction(() => (document.querySelector("#main bs-score") as unknown as { api: { tracks: unknown[] } }).api.tracks.length === 18, undefined, { timeout: 60_000 });
  await expect(page.locator("#viewer-status")).toContainText("18 parts");
});

// Every view in every theme: light, dark, our high-contrast palette, and Norwegian.
// Screenshots go to docs/screenshots/themes/<view>-<theme>.png (the viewport, as in the
// design mockups) and <view>-<theme>-score.png for the score panel.
const THEMES = [
  { name: "light", media: { colorScheme: "light" as const, contrast: "no-preference" as const }, lang: "en" },
  { name: "dark", media: { colorScheme: "dark" as const, contrast: "no-preference" as const }, lang: "en" },
  { name: "contrast", media: { colorScheme: "light" as const, contrast: "more" as const }, lang: "en" },
  { name: "nb", media: { colorScheme: "light" as const, contrast: "no-preference" as const }, lang: "nb" },
];

test("every view in light, dark, high contrast and Norwegian passes axe", async ({ page }) => {
  test.setTimeout(900_000);
  const run = await mikkelRun(page);
  const themes = join(shots, "themes");
  mkdirSync(themes, { recursive: true });
  const views: { name: string; route: string; score?: boolean; open?: boolean }[] = [
    { name: "runs", route: "runs" },
    { name: "run", route: `runs/${run.id}/score`, score: true },
    { name: "run-roll", route: `runs/${run.id}/roll` },
    { name: "run-beats", route: `runs/${run.id}/beats` },
    { name: "run-manifest", route: `runs/${run.id}/manifest` },
    { name: "viewer", route: "viewer", score: true, open: true },
    { name: "compare", route: `compare?a=${run.id}&b=ref:mikkel-arranged-band` },
    { name: "bench", route: "bench" },
    { name: "parity", route: "parity" },
    { name: "conformance", route: "conformance" },
    { name: "registry", route: "registry" },
  ];
  for (const th of THEMES) {
    await page.emulateMedia(th.media);
    await page.goto("/#/runs");
    await page.locator("#lang-select").selectOption(th.lang);
    for (const v of views) {
      await page.goto(`/#/${v.route}`);
      if (v.open) {
        await page.setInputFiles("#open-musicxml", join(golden, "brass-band.musicxml"));
      }
      await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 120_000 });
      if (v.score) await waitRendered(page);
      await page.waitForTimeout(700);
      await page.screenshot({ path: join(themes, `${v.name}-${th.name}.png`) });
      if (v.score) {
        await page.locator("#main bs-score .score-view").scrollIntoViewIfNeeded();
        await page.waitForTimeout(300);
        await page.locator("#main bs-score").screenshot({ path: join(themes, `${v.name}-${th.name}-score.png`) });
      }
      await axe(page, `${v.name} (${th.name})`);
    }
  }
  await page.locator("#lang-select").selectOption("en");
});

test("re-run from a manifest, follow it live, compare with the original", async ({ page }) => {
  test.setTimeout(600_000);
  // The newest finished Mikkel run: its stage keys match the current engine, so a re-run hits the cache.
  const all = (await (await page.request.get("/v1/jobs")).json()) as JobLite[];
  const run = all.find((j) => /mikkel/i.test(j.title ?? "") && j.status === "succeeded" && j.outputs?.includes("brass-band.musicxml"))!;
  await page.goto(`/#/runs/${run.id}/manifest`);
  const panel = page.locator(".tabpanel:not([hidden])");
  await expect(panel.getByRole("button", { name: "Re-run" })).toBeVisible();
  await expect(panel.getByLabel("Use the large models if nothing is cached (slower, needs the GPU)")).not.toBeChecked();
  const t0 = Date.now();
  await panel.getByRole("button", { name: "Re-run" }).click();
  await page.waitForURL((u) => !u.hash.includes(run.id) && u.hash.startsWith("#/runs/"), { timeout: 30_000 });
  const id = decodeURIComponent(page.url().split("#/runs/")[1].split("/")[0]);
  createdRuns.push(id);
  await expect(page.locator(".pill-succeeded, .pill-failed").first()).toBeVisible({ timeout: 540_000 });
  const job = await (await page.request.get(`/v1/jobs/${id}`)).json();
  const stages = job.stages.map((s: { name: string; status: string; seconds?: number; device?: string }) =>
    `${s.name}=${s.status}${s.seconds != null ? ` ${s.seconds.toFixed(1)}s` : ""}${s.device ? ` ${s.device}` : ""}`).join(", ");
  console.log(`re-run ${id} of ${run.id}: ${job.status} in ${((Date.now() - t0) / 1000).toFixed(1)} s; ${stages}${job.error ? `; error: ${job.error}` : ""}`);
  if (job.status === "failed" && /HeavyRunRefused/.test(job.error ?? "")) {
    // The cache no longer holds this run's model outputs; re-running would need the heavy models.
    await page.request.delete(`/v1/runs/${id}`);
    createdRuns.splice(createdRuns.indexOf(id), 1);
    test.skip(true, "the re-run needs heavy models (cache miss); not run in e2e");
  }
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

  // Clean up: remove the run this test created (the cache stays).
  const del = await page.request.delete(`/v1/runs/${id}`);
  expect(del.status()).toBe(204);
  createdRuns.splice(createdRuns.indexOf(id), 1);
  expect((await page.request.get(`/v1/jobs/${id}`)).status()).toBe(404);
});

// Compare runs against its own engine (playwright.config.ts), whose data holds only the committed pair
// in e2e/fixtures/compare: the Old Hundredth fixture and a copy with two Solo Cornet notes changed
// (bar 2 E4 -> D4, bar 4 C#5 -> B4).
const compareURL = process.env.STUDIO_COMPARE_URL ?? `http://127.0.0.1:${process.env.STUDIO_COMPARE_PORT ?? 8797}`;

test("both scores side by side with the differences marked", async ({ page }) => {
  const cmp = await (await page.request.get(`${compareURL}/v1/jobs/old-hundredth-a/compare?job=old-hundredth-b`)).json();
  expect(cmp.ok).toBe(false);
  await page.goto(`${compareURL}/#/compare?a=old-hundredth-a&b=old-hundredth-b`);
  await page.waitForFunction(() => {
    const s = document.querySelectorAll("#main bs-score");
    return s.length === 2 && Array.from(s).every((x) => (x as unknown as { rendered: boolean }).rendered);
  }, undefined, { timeout: 120_000 });
  const status = page.locator("#cmp-notation-status");
  await expect(page.locator("#cmp-part")).toHaveValue("Solo Cornet");
  await expect(status).toHaveText("2 bars differ in Solo Cornet.");
  console.log(`notation: ${await status.textContent()}`);
  await page.getByRole("button", { name: "Next difference" }).click();
  await expect(status).toHaveText("Bar 2: 1 changed in A, 1 in B.");
  console.log(`notation: ${await status.textContent()}`);
  const marked = await page.evaluate(() => Array.from(document.querySelectorAll("#main bs-score")).map((s) => {
    const api = (s as unknown as { api: { score: { tracks: { staves: { bars: { voices: { beats: { notes: { style?: { noteHead?: number } }[] }[] }[] }[] }[] }[] } } }).api;
    return api.score.tracks.flatMap((tr) => tr.staves[0].bars.flatMap((b) => b.voices.flatMap((v) => v.beats.flatMap((be) => be.notes)))).filter((n) => n.style?.noteHead !== undefined).length;
  }));
  console.log(`notes with a changed notehead: A ${marked[0]}, B ${marked[1]}`);
  expect(marked).toEqual([2, 2]);
  await page.waitForTimeout(800);
  const views = page.locator("#main bs-score .score-view");
  await views.nth(0).screenshot({ path: join(shots, "compare-notation-a.png") });
  await views.nth(1).screenshot({ path: join(shots, "compare-notation-b.png") });
  await axe(page, "compare with notation");
});

async function said(page: Page): Promise<string> {
  return page.evaluate(() => (document.querySelector("#main bs-score") as unknown as { lastAnnouncement: string }).lastAnnouncement);
}

test("talking score in the viewer, in English and Norwegian", async ({ page }) => {
  test.skip(!existsSync(join(golden, "brass-band.musicxml")), "data/golden is not available");
  await page.goto("/#/viewer");
  await page.locator("#lang-select").selectOption("en");
  await page.setInputFiles("#open-musicxml", join(golden, "brass-band.musicxml"));
  await waitRendered(page);
  const view = page.locator(".score-view");
  await view.focus();
  // Bar navigation, then note by note through the Solo Cornet part.
  await page.keyboard.press("Alt+ArrowDown");
  const bar = await said(page);
  await page.keyboard.press("ArrowRight");
  const note = await said(page);
  await page.keyboard.press("u");
  const unc = await said(page);
  await page.keyboard.press("w");
  const where = await said(page);
  await page.keyboard.press("Control+Shift+ArrowDown");
  const part = await said(page);
  console.log(`talking score (en):\n  ${[bar, note, unc, where, part].join("\n  ")}`);
  expect(bar).toMatch(/^bar 2(, [^:]+)?: /);
  expect(note).toMatch(/^(bar \d+, )?beat \d/);
  expect(unc).toMatch(/uncertain/);
  expect(where).toMatch(/ of \d+, /);
  expect(part).toMatch(/^Repiano Cornet\. bar \d+, key /);
  // The announcements go to the live region.
  await expect(page.locator("#announcer")).toHaveText(part);
  // Alt+T opens the text form with the current line marked.
  await page.keyboard.press("Alt+t");
  await expect(page.locator(".talk-text [aria-current=true]")).toBeVisible();
  await shot(page, "viewer-talking", false);
  await axe(page, "viewer talking score");

  // Norwegian: the whole UI and the talking score switch.
  await page.locator("#lang-select").selectOption("nb");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Notevisning");
  await expect(page.locator("html")).toHaveAttribute("lang", "nb");
  await page.setInputFiles("#open-musicxml", join(golden, "brass-band.musicxml"));
  await waitRendered(page);
  await page.locator(".score-view").focus();
  await page.keyboard.press("Alt+ArrowDown");
  const nbBar = await said(page);
  await page.keyboard.press("u");
  const nbUnc = await said(page);
  console.log(`talking score (nb):\n  ${nbBar}\n  ${nbUnc}`);
  expect(nbBar).toMatch(/^takt 2(, [^:]+)?: /);
  expect(nbUnc).toMatch(/usikker/);
  await shot(page, "viewer-nb", false);
  await axe(page, "viewer (nb)");
  await page.goto("/#/runs");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Kjøringer");
  await expect(page.getByRole("button", { name: "Start kjøring" })).toBeVisible();
  await shot(page, "runs-nb");
  await axe(page, "runs (nb)");
  await page.locator("#lang-select").selectOption("en");
});

test("fetch errors explain what happened and recover with Try again", async ({ page }) => {
  // The engine is unreachable for this one route: a plain message, the command, and Try again.
  await page.route("**/v1/parity", (r) => r.abort("connectionrefused"));
  await page.goto("/#/parity");
  const notice = page.locator("#main .notice-error");
  await expect(notice).toContainText("Couldn't reach Brasscribe on this computer.");
  await expect(notice).toContainText("brasscribe serve");
  await expect(page.locator("#main")).not.toContainText("Failed to fetch");
  await shot(page, "error-unreachable", false);
  await axe(page, "unreachable notice");
  await page.unroute("**/v1/parity");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator("#main .notice-error")).toHaveCount(0);
  // Norwegian wording for the same state.
  await page.route("**/v1/parity", (r) => r.abort("connectionrefused"));
  await page.locator("#lang-select").selectOption("nb");
  await expect(page.locator("#main .notice-error")).toContainText("Fikk ikke kontakt med Brasscribe på datamaskinen.");
  await page.unroute("**/v1/parity");
  await page.locator("#lang-select").selectOption("en");

  // Core conformance loads its summary quickly and offers a run (or the command).
  const t0 = Date.now();
  await page.goto("/#/conformance");
  await page.waitForFunction(() => !document.querySelector("#main .loading"), undefined, { timeout: 60_000 });
  console.log(`conformance page loaded in ${Date.now() - t0} ms: ${(await page.locator("#main").innerText()).split("\n").slice(2, 4).join(" | ")}`);
  await expect(page.locator("#main .notice-error")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Run conformance|Running/ })).toBeVisible();
  await shot(page, "conformance-run", false);
});
