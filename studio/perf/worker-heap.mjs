// Heap of every worker of a Studio page after opening a score: the synth worker's ArrayBuffer
// backing stores are the SoundFont alphaTab keeps (the sample chunk and the decoded samples).
//
//   cd studio && STUDIO_URL=http://127.0.0.1:8765/ RUN=<run-id> node perf/worker-heap.mjs
import { chromium } from "playwright";

const base = process.env.STUDIO_URL ?? "http://127.0.0.1:8765/";
const run = process.env.RUN;
if (!run) throw new Error("set RUN=<run-id>");
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
try {
  await page.goto(`${base}#/runs/${run}/score`);
  await page.waitForFunction(() => [...document.querySelectorAll("#main bs-score")].some((x) => x.ready), undefined, { timeout: 240_000 });
  await page.waitForTimeout(3000);
  const cdp = await browser.newBrowserCDPSession();
  const { targetInfos } = await cdp.send("Target.getTargets");
  let id = 0;
  const pending = new Map();
  cdp.on("Target.receivedMessageFromTarget", (e) => {
    const m = JSON.parse(e.message);
    pending.get(m.id)?.(m);
  });
  const send = (sessionId, method, params = {}) => new Promise((resolve) => {
    const mid = ++id;
    pending.set(mid, resolve);
    cdp.send("Target.sendMessageToTarget", { sessionId, message: JSON.stringify({ id: mid, method, params }) });
  });
  for (const t of targetInfos.filter((x) => x.type === "worker")) {
    const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: t.targetId, flatten: false });
    await send(sessionId, "HeapProfiler.collectGarbage");
    const r = await send(sessionId, "Runtime.getHeapUsage");
    const mb = (x) => Math.round((x ?? 0) / 1e6);
    console.log(JSON.stringify({ worker: t.url.slice(0, 60), jsHeapMB: mb(r.result?.usedSize), arrayBuffersMB: mb(r.result?.backingStorageSize), embedderMB: mb(r.result?.embedderHeapUsedSize) }));
  }
} finally {
  await browser.close();
}
