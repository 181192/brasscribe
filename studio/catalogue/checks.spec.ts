// Each check of the catalogue finds what it should: a view broken on purpose fails it, naming what was
// broken, and the same view unbroken does not.
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { axe, clipped, keyboard, reflow, textSpacing, type Finding } from "./checks";
import { compare } from "./compare.mjs";
import { serveApi } from "./api";
import { KNOWN, stale } from "./known";
import { openView } from "./open";
import { VARIANTS, type Variant } from "./views";

const light = VARIANTS.find((v) => v.name === "light")!;
const narrow = VARIANTS.find((v) => v.name === "reflow320")!;

/** The Runs view, the findings of `check` on it, then the same after `breakIt`. */
async function beforeAfter(page: Page, check: (p: Page) => Promise<Finding[]>, breakIt: (p: Page) => Promise<void>, variant: Variant = light) {
  await openView(page, { route: "runs" }, variant);
  const before = (await check(page)).map((f) => `${f.check}: ${f.what}`);
  // The keyboard walk leaves focus at the end of the page; the broken view is walked from the top again.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await breakIt(page);
  const after = (await check(page)).map((f) => `${f.check}: ${f.what}`);
  return { before, after };
}

const add = (html: string) => (p: Page) => p.evaluate((h) => document.getElementById("main")!.insertAdjacentHTML("beforeend", h), html);

test("axe: text with too little contrast", async ({ page }) => {
  const { before, after } = await beforeAfter(page, axe, add('<p id="broken-contrast" style="color:#ccc;background:#fff">Hard to read</p>'));
  expect(before).toEqual([]);
  expect(after).toContainEqual(expect.stringMatching(/^axe: color-contrast: #broken-contrast$/));
});

test("clipped: an ellipsis, and text cut by the box it is in", async ({ page }) => {
  const { before, after } = await beforeAfter(page, (p) => clipped(p), add(
    '<p id="broken-ellipsis" style="width:5rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">A sentence far too long for its box</p>' +
    '<div id="broken-box" style="height:0.6em;overflow:hidden"><span id="broken-cut">Cut in half</span></div>'));
  expect(before).toEqual([]);
  expect(after).toContainEqual(expect.stringMatching(/^clipped: p#broken-ellipsis "A sentence/));
  expect(after).toContainEqual(expect.stringMatching(/^clipped: span#broken-cut "Cut in half" \(cut by div#broken-box\)$/));
});

test("clipped: text out of view in a part that scrolls is not cut", async ({ page }) => {
  const { after } = await beforeAfter(page, (p) => clipped(p), add(
    '<div style="width:5rem;overflow-x:auto"><p id="scrolls" style="white-space:nowrap">A sentence that scrolls in its box</p></div>'));
  expect(after.filter((f) => f.includes("scrolls"))).toEqual([]);
});

test("clipped: text a part that scrolls shows, cut by a box outside that part", async ({ page }) => {
  const { after } = await beforeAfter(page, (p) => clipped(p), add(
    '<div id="broken-outer" style="height:2.5em;overflow:hidden"><div style="height:8em;overflow-y:auto">' +
    '<p style="margin:0">First line</p><p style="margin:0">Second line</p><p style="margin:0" id="shown-but-cut">Third line</p></div></div>'));
  expect(after).toContainEqual('clipped: p#shown-but-cut "Third line" (cut by div#broken-outer)');
});

test("clipped: the run's manifest JSON, which scrolls, cut by a box around it", async ({ page }) => {
  await openView(page, { route: "runs/old-hundredth-a/manifest" }, light);
  const json = page.locator("#main pre.json").first();
  await json.evaluate((pre) => {
    pre.closest("details")!.open = true;
    const box = pre.parentElement!;
    box.id = "broken-manifest-box";
    box.style.cssText = "max-height:4em;overflow:hidden";
  });
  expect((await clipped(page)).map((f) => f.what)).toContainEqual(expect.stringMatching(/pre\.json "\{ .*" \(cut by details#broken-manifest-box\)$/));
});

test("keyboard: something to act on that Tab never reaches", async ({ page }) => {
  const { before, after } = await beforeAfter(page, keyboard, add(
    '<div role="button" id="broken-div-button" onclick="void 0">Do it</div><button type="button" tabindex="-1" id="broken-button">Or this</button>'));
  expect(before).toEqual([]);
  expect(after).toContainEqual('reach: Tab never reaches div#broken-div-button "Do it"');
  expect(after).toContainEqual('reach: Tab never reaches button#broken-button "Or this"');
});

test("keyboard: Tab out of the order of the page (tabindex)", async ({ page }) => {
  const { after } = await beforeAfter(page, keyboard, add('<button type="button" tabindex="1" id="broken-first">Jumps the queue</button>'));
  expect(after).toContainEqual("order: button#broken-first (tabindex 1) is taken out of the order of the page");
});

test("keyboard: Tab back up the page (an order reversed by the styles)", async ({ page }) => {
  const { after } = await beforeAfter(page, keyboard, add(
    '<div style="display:flex;flex-direction:column-reverse;align-items:start"><button type="button" id="broken-lower">First in the page</button><button type="button" id="broken-upper">Second</button></div>'));
  expect(after).toContainEqual('order: Tab goes from button#broken-lower "First in the page" up to button#broken-upper "Second", above it');
});

test("keyboard: focus on something that cannot be seen, or that is covered", async ({ page }) => {
  const { after } = await beforeAfter(page, keyboard, add(
    '<a href="#/runs" id="broken-hidden" style="display:inline-block;width:0;height:0;overflow:hidden"></a>' +
    '<p style="position:relative"><button type="button" id="broken-covered">Under a cover</button><span id="broken-cover" style="position:absolute;inset:-4px;width:12rem;background:#eee">cover</span></p>' +
    '<button type="button" id="broken-transparent" style="opacity:0">Invisible</button>'));
  expect(after).toContainEqual("hidden-focus: Tab stops on a#broken-hidden, which cannot be seen");
  expect(after).toContainEqual("hidden-focus: Tab stops on button#broken-transparent, which cannot be seen");
  expect(after).toContainEqual("obscured: button#broken-covered has focus under span#broken-cover");
});

test("reflow: the page scrolls sideways at 320 px", async ({ page }) => {
  const { before, after } = await beforeAfter(page, reflow, add('<div id="broken-wide" style="width:40rem">Too wide</div>'), narrow);
  expect(before).toEqual([]);
  expect(after).toContainEqual(expect.stringMatching(/^reflow: the page is \d+ px wide in a 320 px window$/));
  expect(after).toContainEqual(expect.stringMatching(/^reflow: div#broken-wide reaches \d+ px$/));
});

test("reflow: a part of the page that scrolls sideways within itself at 320 px, but not a data table or code", async ({ page }) => {
  const { before, after } = await beforeAfter(page, reflow, add(
    '<div id="broken-panel" style="overflow:auto"><p style="width:30rem;margin:0">A panel wider than the window</p></div>' +
    '<div class="table-wrap"><table style="width:30rem"><tbody><tr><td>A data table scrolls in its wrapper</td></tr></tbody></table></div>' +
    '<pre style="overflow-x:auto">const preformatted = "text keeps its lines, however long they are, and scrolls sideways";</pre>'), narrow);
  expect(before).toEqual([]);
  expect(after).toEqual([expect.stringMatching(/^reflow: div#broken-panel scrolls sideways: \d+ px wide in \d+ px$/)]);
});

test("text spacing: a box sized to its text cuts it once the spacing grows", async ({ page }) => {
  await openView(page, { route: "runs" }, light);
  await page.evaluate(() => {
    const s = document.createElement("span");
    s.id = "broken-spacing";
    s.textContent = "Exactly as wide as this";
    s.style.cssText = "display:inline-block;white-space:nowrap;overflow:hidden";
    document.getElementById("main")!.append(s);
    s.style.width = `${s.scrollWidth + 1}px`;
  });
  expect(await clipped(page)).toEqual([]);
  expect((await textSpacing(page)).map((f) => `${f.check}: ${f.what}`)).toContainEqual('spacing: span#broken-spacing "Exactly as wide as this"');
});

test("the fixtures: a request they do not answer is reported", async ({ page }) => {
  const unanswered = await serveApi(page);
  await page.goto("/#/runs/no-such-run");
  await expect.poll(() => unanswered).toContainEqual("GET /v1/jobs/no-such-run");
});

test("screenshots: changed, new, gone and the same are told apart", async ({ page }) => {
  const dir = mkdtempSync(join(tmpdir(), "catalogue-compare-"));
  try {
    const [before, after, report] = ["before", "after", "report"].map((d) => join(dir, d));
    for (const d of [before, after]) mkdirSync(d);
    const shot = async (path: string, html: string) => {
      await page.setViewportSize({ width: 200, height: 100 });
      await page.setContent(`<body style="margin:0;background:#fff;font:20px sans-serif">${html}</body>`);
      await page.screenshot({ path });
    };
    await shot(join(before, "same.png"), "Same");
    await shot(join(after, "same.png"), "Same");
    await shot(join(before, "changed.png"), "Before");
    await shot(join(after, "changed.png"), "After");
    await shot(join(before, "gone.png"), "Gone");
    await shot(join(after, "new.png"), "New");
    // The smallest change that must not pass for noise: a full stop.
    await shot(join(before, "stop.png"), "A sentence");
    await shot(join(after, "stop.png"), "A sentence.");
    // A muted text colour a dozen levels darker (a token change) is a change too, though every glyph pixel is an edge.
    await shot(join(before, "colour.png"), '<span style="color:#6b6b6b">Muted text in the page</span>');
    await shot(join(after, "colour.png"), '<span style="color:#5f5f5f">Muted text in the page</span>');
    const r = await compare(before, after, report);
    expect(r).toMatchObject({ screens: 5, changed: ["changed.png", "colour.png", "stop.png"], added: ["new.png"], gone: ["gone.png"] });
    const summary = readFileSync(join(report, "summary.md"), "utf8");
    expect(summary).toContain("changed: `changed.png`");
    expect(summary).not.toContain("same.png");
    // A base without a catalogue: nothing to compare with, so nothing counts as changed.
    const none = await compare(join(dir, "missing"), after, join(dir, "report-none"));
    expect(none).toMatchObject({ changed: [], added: [], gone: [] });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("known findings: an entry that matches nothing is reported, so a fixed one is removed", () => {
  const [k] = KNOWN;
  expect(stale([], k.view, k.variant)).toContainEqual(k);
  expect(stale([{ check: k.check, what: "anything else" }], k.view, k.variant)).toContainEqual(k);
  expect(stale([{ check: k.check, what: k.what.source.replace(/^\^|\$$/g, "").replace(/\\/g, "") }], k.view, k.variant)).not.toContainEqual(k);
});
