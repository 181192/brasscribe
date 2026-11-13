// Drives every chart of a built research page with the keyboard, in a real browser, and fails when
// a key throws, a row cannot be reached, a view cannot be switched or Escape leaves the readout on.
//
//   site/build.sh && python3 -m http.server -d site/_site 8000 &
//   node site/shared/research/tests/keyboard.mjs http://localhost:8000/research/ [more pages]
//
// It needs Playwright (the one Studio's tests use: run `npm ci` in studio/ once) and its Chromium.
// STUDIO_DIR names another checkout's studio/ folder; CHROME names a Chromium to use instead of Playwright's.
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const studio = process.env.STUDIO_DIR ? new URL(`file://${process.env.STUDIO_DIR.replace(/\/?$/, "/")}`) : new URL("../../../../studio/", import.meta.url);
const require = createRequire(studio);
const { chromium } = require("playwright");
const pages = process.argv.slice(2);
if (!pages.length) { console.error(`usage: node ${fileURLToPath(import.meta.url)} <url> [<url> …]`); process.exit(2); }

const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
let failed = 0;
for (const url of pages) {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(url, { waitUntil: "networkidle" });
  const figures = await page.locator("figure[data-chart].is-live").all();
  if (!figures.length) errors.push("no live chart on the page");
  for (const figure of figures) {
    const id = await figure.getAttribute("id");
    const fail = (what) => errors.push(`${id}: ${what}`);
    const views = await figure.locator(".chart-views input").count();
    for (let v = 0; v < Math.max(1, views); v++) {
      if (views) {
        await figure.locator(".chart-views input").first().focus();
        for (let i = 0; i < v; i++) await page.keyboard.press("ArrowRight");
        if (!(await figure.locator(".chart-views input").nth(v).isChecked())) fail(`view ${v + 1} is not reached with the arrow keys`);
      }
      const rows = await figure.locator(".chart-row").count();
      await figure.locator(".chart-row").first().focus();
      for (let r = 1; r < rows; r++) {
        await page.keyboard.press("ArrowDown");
        const here = await figure.locator(".chart-row").nth(r).evaluate((el) => el === document.activeElement);
        if (!here) { fail(`row ${r + 1} of view ${v + 1} is not reached with ArrowDown`); break; }
      }
      const title = await figure.locator(".chart-tip-title").count();
      if (!title) fail(`no readout for the focused row in view ${v + 1}`);
      await page.keyboard.press("Home");
      if (!(await figure.locator(".chart-row").first().evaluate((el) => el === document.activeElement))) fail("Home does not go to the first row");
      await page.keyboard.press("Escape");
      if (await figure.locator(".chart-tip.is-on").count()) fail("Escape leaves the readout on");
    }
  }
  console.log(`${url}: ${figures.length} charts, ${errors.length ? "FAILED" : "keyboard ok"}`);
  errors.slice(0, 12).forEach((e) => console.log("  " + e));
  failed += errors.length;
  await page.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
