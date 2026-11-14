// The Apple tab page (apps/apple/features/tab/.../page: the page the app's web view shows, with alphaTab) on its own, in
// Chromium with the web view's message channel stubbed: alphaTab 1.9 draws "♪ alphaTab.net" in a long score, and nothing of
// the page's own (the playback cursor, the beat wash) or of the app's marks (the boxes the page reports) may cover it.
import { expect, test } from "@playwright/test";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../..");
const pageDir = join(repo, "apps/apple/features/tab/Sources/TabKit/Resources/page");
const alphatab = join(repo, "engine/src/scribe_engine/static/assets/alphatab");
const origin = "http://tab-page.test";

type Box = { left: number; top: number; right: number; bottom: number };
const meets = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

for (const scale of [1, 1.5]) test(`nothing of the tab page's or the app's is drawn over alphaTab's mark (scale ${scale})`, async ({ page }) => {
  await page.route(`${origin}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    const file = path.startsWith("/alphatab/") ? join(alphatab, path.slice("/alphatab/".length)) : join(pageDir, path === "/" ? "index.html" : path.slice(1));
    if (!existsSync(file)) return route.fulfill({ status: 404 });
    const type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".html") ? "text/html" : file.endsWith(".woff2") ? "font/woff2" : "application/octet-stream";
    return route.fulfill({ body: readFileSync(file), contentType: type });
  });
  type Rendered = { kind: "rendered"; marks: { x: number; top: number; bottom: number; w: number }[]; bars: { bar: number; x: number; y: number; w: number; h: number }[]; lines: { first: number; last: number }[] };
  let rendered: Rendered | null = null;
  await page.exposeFunction("__post", (m: Rendered | { kind: string }) => { if (m.kind === "rendered") rendered = m as Rendered; });
  await page.addInitScript(() => { (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { tab: { postMessage: (m: unknown) => (window as unknown as { __post: (m: unknown) => void }).__post(m) } } }; });
  await page.setViewportSize({ width: 390, height: 600 });
  await page.goto(`${origin}/index.html`);
  const song = readFileSync(join(repo, "apps/fixtures/bass-line-marks/tab.musicxml")).toString("base64");
  // Marks on the notes at the far right of the first system (the fourth bar of the bass line, counted from 0: 3).
  // (A tick is counted from the bar's start; strings from the top line.)
  const marks = [{ tick: 0, string: 3, fret: 0 }, { tick: 960, string: 4, fret: 3 }].map((m) => ({ staff: 0, bar: 3, tick: m.tick, notes: [{ string: m.string, fret: m.fret, pitchClass: null, doubt: true }] }));
  const palette = { ink: "#000000", string: "#555555", uncertain: "#0000ff", cursor: "#cc0000", cursorTint: "rgba(204,0,0,0.3)" };
  await page.evaluate(([s, p, m, sc]) => (window as unknown as { tab: { show: (s: string, o: unknown) => void } }).tab.show(s as string, { scale: sc, palette: p, staff: "tab", doubtful: [], marks: m, markStaff: 0 }), [song, palette, marks, scale]);
  await expect.poll(() => rendered !== null, { timeout: 20_000 }).toBe(true);
  await page.waitForTimeout(1500);

  // alphaTab's mark: the curved outlines of the one path that holds it.
  const mark: Box | null = await page.evaluate(() => {
    for (const path of document.querySelectorAll("#tab svg path")) {
      const d = path.getAttribute("d") ?? "";
      if (!/[Cc]/.test(d) || (path as SVGGraphicsElement).getBBox().width < 40) continue;
      const probe = document.createElementNS("http://www.w3.org/2000/svg", "path");
      probe.setAttribute("d", d.split(/(?=M)/).filter((part) => /[Cc]/.test(part)).join(""));
      path.parentNode!.appendChild(probe);
      const r = probe.getBoundingClientRect();
      probe.remove();
      if (r.width > 0) return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    }
    return null;
  });
  expect(mark, "the long bass line carries alphaTab's mark").not.toBeNull();
  const r = rendered as unknown as Rendered;
  // The app's marks (its "?" and boxed "!" go where the page says).
  expect(r.marks.length, "the marks at the end of the first system are placed").toBeGreaterThan(0);
  for (const m of r.marks) expect(meets({ left: m.x - m.w / 2, top: m.top, right: m.x + m.w / 2, bottom: m.bottom }, mark!), `a mark at x ${Math.round(m.x)}`).toBe(false);
  // The cursor and the beat wash, in each bar of the first system.
  const first = r.lines[0];
  for (let bar = first.first; bar <= first.last; bar++) {
    for (const tick of [0, 480]) {
      await page.evaluate(([b, t]) => (window as unknown as { tab: { cursorAt: (b: number, t: number) => unknown } }).tab.cursorAt(b as number, t as number), [bar, tick]);
      const found = await page.evaluate(() => ["cursor", "beat"].map((id) => { const b = document.getElementById(id)!.getBoundingClientRect(); return { id, left: b.left, top: b.top, right: b.right, bottom: b.bottom, h: b.height }; }));
      for (const f of found) if (f.h > 0) expect(meets(f, mark!), `${f.id} in bar ${bar} at ${tick}`).toBe(false);
    }
  }
});
