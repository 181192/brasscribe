// Drives every chart of a built research page with the keyboard, in a real browser, and fails when
// a key throws, a row cannot be reached, a view cannot be switched or Escape leaves the readout on.
// It does so in English, after a change to Norwegian, after the change back and after a change to Norwegian
// again, at the width of a phone, and on a first visit in Norwegian, both asked for in the address and from the
// browser's own language: in each, every figure of the page must be drawn, once, in the language of the page,
// its view buttons and legend included.
//
//   site/build.sh && python3 -m http.server -d site/_site 8000 &
//   node site/shared/research/tests/keyboard.mjs http://localhost:8000/brasscribe/how-it-works/ [more pages]
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

// Every figure drawn once and in the page's language; then every row and view of each with the keyboard.
async function drive(page, lang, errors) {
  const state = await page.evaluate(() => ({
    lang: document.documentElement.lang,
    figures: [...document.querySelectorAll("figure[data-chart]")].map((f) => ({
      id: f.id, live: f.classList.contains("is-live") && !f.querySelector(".chart-plot").hidden,
      controls: f.querySelectorAll(".chart-controls").length, canvases: f.querySelectorAll(".chart-canvas svg").length,
      rows: f.querySelectorAll(".chart-row").length, caption: f.querySelector("figcaption b").textContent,
      tableOpen: f.querySelector(".chart-data").open,
      // What the buttons and the legend say, and what the figure's own data says they are in this language.
      said: [f.querySelector(".chart-views legend")?.textContent ?? "", ...[...f.querySelectorAll(".chart-views label")].map((l) => l.textContent)],
      meant: ((d) => d.views.length > 1 ? [d.viewLabel, ...d.views.map((v) => v.l)] : [""])(JSON.parse(f.querySelector('script[type="application/json"]').textContent)),
    })),
  }));
  const fail = (what) => errors.push(`${lang}: ${what}`);
  if (state.lang !== lang) fail(`the page says it is in '${state.lang}'`);
  if (!state.figures.length) fail("no chart on the page");
  for (const f of state.figures) {
    if (!f.live || !f.rows) fail(`${f.id} is not drawn`);
    if (f.controls !== 1 || f.canvases !== 1) fail(`${f.id} is drawn ${Math.max(f.controls, f.canvases)} times`);
    if (f.tableOpen) fail(`${f.id} shows its data table beside the drawing`);
    if (!f.caption.startsWith(lang === "nb" ? "Figur " : "Figure ")) fail(`${f.id} has the caption '${f.caption}'`);
    if (f.said.join("|") !== f.meant.join("|")) fail(`${f.id} has the view buttons '${f.said.join(", ")}', not '${f.meant.join(", ")}'`);
  }
  for (const figure of await page.locator("figure[data-chart].is-live").all()) {
    const id = await figure.getAttribute("id");
    const views = await figure.locator(".chart-views input").count();
    for (let v = 0; v < Math.max(1, views); v++) {
      if (views) {
        await figure.locator(".chart-views input").first().focus();
        for (let i = 0; i < v; i++) await page.keyboard.press("ArrowRight");
        if (!(await figure.locator(".chart-views input").nth(v).isChecked())) fail(`${id}: view ${v + 1} is not reached with the arrow keys`);
      }
      const rows = await figure.locator(".chart-row").count();
      await figure.locator(".chart-row").first().focus();
      for (let r = 1; r < rows; r++) {
        await page.keyboard.press("ArrowDown");
        const here = await figure.locator(".chart-row").nth(r).evaluate((el) => el === document.activeElement);
        if (!here) { fail(`${id}: row ${r + 1} of view ${v + 1} is not reached with ArrowDown`); break; }
      }
      const title = await figure.locator(".chart-tip-title").count();
      if (!title) fail(`${id}: no readout for the focused row in view ${v + 1}`);
      await page.keyboard.press("Home");
      if (!(await figure.locator(".chart-row").first().evaluate((el) => el === document.activeElement))) fail(`${id}: Home does not go to the first row`);
      await page.keyboard.press("Escape");
      if (await figure.locator(".chart-tip.is-on").count()) fail(`${id}: Escape leaves the readout on`);
    }
  }
  return state.figures.length;
}

// The language button, and the page when it has changed.
async function change(page, lang) {
  await page.locator("[data-lang-switch]").first().click();
  await page.waitForFunction((to) => document.documentElement.lang === to && !document.documentElement.hasAttribute("data-lang-wanted"), lang);
}

for (const url of pages) {
  const errors = [];
  // A new reader each time: `lang` in the address, or none, where the browser's own language decides.
  const open = async (lang, width = 1280, locale = "en-GB") => {
    const page = await (await browser.newContext({ viewport: { width, height: 900 }, locale })).newPage();
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(lang ? `${url}?lang=${lang}` : url, { waitUntil: "networkidle" });
    return page;
  };
  let charts = 0;
  for (const width of [1280, 390]) {
    const page = await open("en", width);
    charts = await drive(page, "en", errors);
    for (const lang of ["nb", "en", "nb"]) {
      await change(page, lang);
      await drive(page, lang, errors);
    }
    await page.close();
  }
  for (const page of [await open("nb"), await open("", 1280, "nb-NO")]) {  // a first visit in Norwegian
    await drive(page, "nb", errors);
    await page.close();
  }
  console.log(`${url}: ${charts} charts, ${errors.length ? "FAILED" : "keyboard ok in both languages, through three changes of language, at 1280 and 390 px, and on a Norwegian first visit"}`);
  errors.slice(0, 12).forEach((e) => console.log("  " + e));
  failed += errors.length;
}
await browser.close();
process.exit(failed ? 1 : 0);
