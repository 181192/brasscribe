// Changes the language of built pages back and forth in a real browser, and fails when what the scripts add to a
// page (a stepper's buttons, a rail's tabs, a strip, a viewer's controls, the cards' counter) is not there exactly
// as often after each change as it was at the start, when a figure is left in the other language, or when a script
// throws. It does so from a first visit in English and from one in Norwegian, changing twice each time. And on a
// first visit in Norwegian where the other figures' words (nb-more.json) fail once: those figures say they are
// English until the next change to Norwegian asks for the words again and puts them in.
//
//   site/build.sh && python3 -m http.server -d site/_site 8000 &
//   node site/shared/tests/languages.mjs http://localhost:8000/brasscribe/ http://localhost:8000/ [more pages]
//
// It needs Playwright (the one Studio's tests use: run `npm ci` in studio/ once) and its Chromium.
// STUDIO_DIR names another checkout's studio/ folder; CHROME names a Chromium to use instead of Playwright's.
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const studio = process.env.STUDIO_DIR ? new URL(`file://${process.env.STUDIO_DIR.replace(/\/?$/, "/")}`) : new URL("../../../studio/", import.meta.url);
const require = createRequire(studio);
const { chromium } = require("playwright");
const pages = process.argv.slice(2);
if (!pages.length) { console.error(`usage: node ${fileURLToPath(import.meta.url)} <url> [<url> …]`); process.exit(2); }

// What the scripts add, by what it is.
const ADDED = {
  "stepper buttons": ".stages-nav",
  "stepper Previous and Next": ".stages-foot",
  "rail tabs": '.rail[role="tablist"]',
  strips: "[data-strip] .strip-stage",
  "viewer controls": ".tabdemo-controls:not(.await-js)",
  "cards' counter": ".sure-count:not(.await-js)",
};
const count = (page) => page.evaluate((added) => {
  const out = { lang: document.documentElement.lang, english: [] };
  for (const [name, selector] of Object.entries(added)) out[name] = document.querySelectorAll(selector).length;
  // A figure of a Norwegian page still in English says so (lang="en"); once the page has settled, none may.
  if (out.lang === "nb") out.english = [...document.querySelectorAll('[data-slot][lang="en"]')].map((el) => el.dataset.slot);
  return out;
}, ADDED);

// The page's language button is shown once scribe.js has put the words in: until then nothing is to be counted.
const settled = (page) => page.waitForSelector("[data-lang-switch]:not([hidden])", { timeout: 20000 }).then(() => true, () => false);

const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
let failed = 0;
for (const url of pages) {
  for (const first of ["en", "nb"]) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(`${url}${url.includes("?") ? "&" : "?"}lang=${first}`, { waitUntil: "networkidle" });
    if (!(await settled(page))) { failed++; console.log(`FAIL ${url} (first in ${first})\n  the words were never put in`); await page.close(); continue; }
    await page.waitForTimeout(800);
    const start = await count(page);
    const seen = [start];
    for (let i = 0; i < 2; i++) {
      await page.locator("[data-lang-switch]").first().click();
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(800);
      seen.push(await count(page));
    }
    const wrong = [];
    seen.forEach((now, i) => {
      const want = (i % 2 === 0) === (first === "en") ? "en" : "nb";
      if (now.lang !== want) wrong.push(`after ${i} changes the page is in ${now.lang}, not ${want}`);
      for (const name of Object.keys(ADDED)) if (now[name] !== start[name]) wrong.push(`after ${i} changes: ${now[name]} × ${name}, at the start ${start[name]}`);
      if (now.english.length) wrong.push(`after ${i} changes: figures ${now.english.join(", ")} still in English`);
    });
    wrong.push(...errors.map((e) => `script error: ${e}`));
    if (wrong.length) {
      failed++;
      console.log(`FAIL ${url} (first in ${first})\n  ${wrong.join("\n  ")}`);
    } else console.log(`ok   ${url} (first in ${first})`);
    await page.close();
  }
}
// The other figures' words fail once, then come.
for (const url of pages) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let asked = 0;
  await page.route("**/nb-more.json", (route) => (asked++ === 0 ? route.fulfill({ status: 404, body: "" }) : route.continue()));
  await page.goto(`${url}${url.includes("?") ? "&" : "?"}lang=nb`, { waitUntil: "networkidle" });
  if (!(await settled(page))) { failed++; console.log(`FAIL ${url} (Norwegian, the other figures' words failing once)\n  the words were never put in`); await page.close(); continue; }
  await page.waitForTimeout(500);
  const before = (await count(page)).english;
  const slots = await page.evaluate(() => document.querySelectorAll("[data-slot]").length);
  for (let i = 0; i < 2; i++) {
    await page.locator("[data-lang-switch]").first().click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
  }
  const after = await count(page);
  const wrong = [];
  // A page with one figure or none has no other figures' words to wait for.
  if (slots > 1 && !before.length) wrong.push("with the other figures' words missing, no figure says it is English");
  if (slots > 1 && asked < 2) wrong.push(`the other figures' words were asked for ${asked} time(s), not again`);
  if (after.lang !== "nb") wrong.push(`after two changes the page is in ${after.lang}`);
  if (after.english.length) wrong.push(`figures ${after.english.join(", ")} still in English after the words were asked for again`);
  if (wrong.length) {
    failed++;
    console.log(`FAIL ${url} (Norwegian, the other figures' words failing once)\n  ${wrong.join("\n  ")}`);
  } else console.log(`ok   ${url} (Norwegian, the other figures' words failing once)`);
  await page.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
