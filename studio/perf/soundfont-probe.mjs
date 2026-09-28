// Studio's score load in headless Chromium: time to render and to a ready player, whether the band
// SoundFont came over the network or from the disk cache, and the browser's resident memory.
//
//   cd studio && STUDIO_URL=http://127.0.0.1:8765/ RUNS=<run-id>,<run-id> node perf/soundfont-probe.mjs
//
// RUNS: two finished runs with a score. Each probe starts from an empty browser profile. Opens run 1,
// run 2 and run 1 again by changing the hash (as the Runs view does), then Compare with both runs,
// then moves the player to Compare's second score (as its Play button does). Last, it reloads the
// page and opens run 1 once more: a SoundFont Studio kept (IndexedDB) shows as a 304 with no body.
// "synths" and "soundFontLoads" count what the page's shared synthesizer did (lib/sharedsynth.ts).
import { execSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

const base = process.env.STUDIO_URL ?? "http://127.0.0.1:8765/";
const runs = (process.env.RUNS ?? "").split(",").filter(Boolean);
if (runs.length < 2) throw new Error("set RUNS=<run-id>,<run-id>");
const profile = mkdtempSync(join(tmpdir(), "studio-probe-"));
const ctx = await chromium.launchPersistentContext(profile, { headless: true, args: ["--autoplay-policy=no-user-gesture-required"] });
const page = await ctx.newPage();
const cdp = await ctx.newCDPSession(page);
await cdp.send("Network.enable");
const sf = [];
const byId = new Map();
cdp.on("Network.responseReceived", (e) => {
  if (!e.response.url.endsWith(".sf2")) return;
  const r = { status: e.response.status, fromDiskCache: e.response.fromDiskCache, bytes: 0 };
  byId.set(e.requestId, r);
  sf.push(r);
});
cdp.on("Network.loadingFinished", (e) => { const r = byId.get(e.requestId); if (r) r.bytes = e.encodedDataLength; });

/** Resident memory of every process of this browser (all renderers, GPU and network processes). */
function browserRssMB() {
  const rows = execSync("ps -axo pid=,ppid=,rss=,command=", { encoding: "utf8", maxBuffer: 1 << 24 })
    .split("\n").filter(Boolean).map((l) => {
      const [pid, ppid, rss, ...cmd] = l.trim().split(/\s+/);
      return { pid: Number(pid), ppid: Number(ppid), rss: Number(rss), cmd: cmd.join(" ") };
    });
  const tree = new Set(rows.filter((r) => r.cmd.includes(profile)).map((r) => r.pid));
  for (let grew = true; grew;) {
    grew = false;
    for (const r of rows) if (!tree.has(r.pid) && tree.has(r.ppid)) { tree.add(r.pid); grew = true; }
  }
  return Math.round(rows.filter((r) => tree.has(r.pid)).reduce((s, r) => s + r.rss, 0) / 1024);
}

/** Every score has a ready player (before the shared synth), or the score that has the synth is ready. */
const ready = (sel) => page.waitForFunction((s) => {
  const all = [...document.querySelectorAll(s)];
  if (!all.length) return false;
  const shared = customElements.get("bs-score")?.synth;
  return shared ? all.some((x) => x.ownsPlayer && x.ready === true) : all.every((x) => x.ready === true);
}, sel, { timeout: 240_000 });

const synthStats = () => page.evaluate(() => {
  const s = customElements.get("bs-score")?.synth;
  return s ? { synths: s.synthsCreated, soundFontLoads: s.soundFontLoads } : {};
});

async function step(label, go, sel) {
  const before = sf.length;
  const t0 = Date.now();
  await go();
  await page.waitForFunction((s) => [...document.querySelectorAll(s)].some((x) => x.rendered), sel, { timeout: 240_000 });
  const renderMs = Date.now() - t0;
  await ready(sel);
  const readyMs = Date.now() - t0;
  await page.waitForTimeout(1500);
  const got = sf.slice(before).map((r) => `${r.status}${r.fromDiskCache ? " disk-cache" : ""} ${Math.round(r.bytes / 1e6)} MB`);
  console.log(JSON.stringify({ step: label, renderMs, playerReadyMs: readyMs, soundFont: got, ...(await synthStats()), browserRssMB: browserRssMB() }));
}

try {
  await page.goto(base);
  await page.waitForLoadState("networkidle");
  console.log(JSON.stringify({ step: "studio open", browserRssMB: browserRssMB() }));
  await step(`score ${runs[0]}`, () => page.evaluate((h) => (location.hash = h), `#/runs/${runs[0]}/score`), "#main bs-score");
  await step(`score ${runs[1]}`, () => page.evaluate((h) => (location.hash = h), `#/runs/${runs[1]}/score`), "#main bs-score");
  await step(`score ${runs[0]} again`, () => page.evaluate((h) => (location.hash = h), `#/runs/${runs[0]}/score`), "#main bs-score");
  await step("compare", () => page.evaluate((h) => (location.hash = h), `#/compare?a=${runs[0]}&b=${runs[1]}`), "#main bs-score");
  await step("compare, player to the second score", () => page.evaluate(() => {
    const b = document.querySelectorAll("#main bs-score")[1];
    if (b.claimPlayer) b.claimPlayer();
  }), "#main bs-score");
  await step(`reload, score ${runs[0]}`, async () => {
    await page.goto(`${base}#/runs/${runs[0]}/score`);
    await page.reload();
  }, "#main bs-score");
} finally {
  await ctx.close();
  rmSync(profile, { recursive: true, force: true });
}
