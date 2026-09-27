// Render every mockup to PNG: node design/mockups/render.mjs [screen ...]
// Uses Playwright (Chromium). Resolves it from studio/node_modules, or set PLAYWRIGHT_MODULE to its path.
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DESIGN = resolve(HERE, "..");
const OUT = join(HERE, "png");

async function loadPlaywright() {
  const req = createRequire(join(DESIGN, "..", "studio", "package.json"));
  for (const name of [process.env.PLAYWRIGHT_MODULE, "playwright", "@playwright/test"].filter(Boolean)) {
    try { return req(name); } catch {}
  }
  throw new Error("Playwright not found: run `npm ci` in studio/ or set PLAYWRIGHT_MODULE=/path/to/node_modules/playwright");
}

const PHONE = { width: 390, height: 844, deviceScaleFactor: 2 };
const DESKTOP = { width: 1440, height: 900, deviceScaleFactor: 1 };
const both = [["phone", "light"], ["phone", "dark"], ["desktop", "light"], ["desktop", "dark"]];
const SCREENS = {
  "home": both,
  "what-is-this": both,
  "transcribing": both,
  "review": both,
  "score": both,
  "part": both,
  "choose-output": both,
  "export": both,
  "finish-later": [["phone", "light"], ["desktop", "dark"]],
  "what-is-this-nb": [["phone", "light"], ["desktop", "light"]],
  "choose-output-nb": [["phone", "light"]],
  "first-run": [["phone", "light"], ["phone", "dark"]],
  "error": [["phone", "light"], ["desktop", "dark"]],
  "studio-run": [["desktop", "light"], ["desktop", "dark"]],
  "server-mac-popover": [["desktop", "light"], ["desktop", "dark"], ["desktop", "hc"]],
  "server-win-flyout": [["desktop", "light"], ["desktop", "dark"]],
  "server-first-run": [["desktop", "light"], ["desktop", "dark"]],
  "server-first-run-nb": [["desktop", "light"]],
  "server-pair": [["desktop", "light"], ["desktop", "dark"], ["desktop", "hc"]],
  "server-pair-nb": [["desktop", "light"]],
  "server-needs-attention": [["desktop", "light"], ["desktop", "dark"]],
  "my-instrument-first-run": [["phone", "light"], ["phone", "dark"]],
  "my-instrument-first-run-nb": [["phone", "light"]],
  "my-instrument-settings": [["phone", "light"], ["desktop", "light"]],
  "my-instrument-score": [["phone", "light"], ["phone", "dark"], ["desktop", "light"]],
  "my-instrument-review": [["phone", "light"], ["desktop", "dark"]],
};

const TYPES = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2", ".ttf": "font/ttf", ".svg": "image/svg+xml", ".png": "image/png" };
const server = createServer(async (req, res) => {
  try {
    const path = join(DESIGN, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!path.startsWith(DESIGN)) throw new Error("outside");
    res.writeHead(200, { "content-type": TYPES[extname(path)] || "application/octet-stream" });
    res.end(await readFile(path));
  } catch {
    res.writeHead(404); res.end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;

const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
await mkdir(OUT, { recursive: true });
const only = process.argv.slice(2);
for (const [screen, variants] of Object.entries(SCREENS)) {
  if (only.length && !only.includes(screen)) continue;
  for (const [device, theme] of variants) {
    const vp = device === "phone" ? PHONE : DESKTOP;
    // "hc" renders the high-contrast tokens (data-theme="high-contrast"), the palette macOS Increase Contrast uses.
    const hc = theme === "hc";
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.deviceScaleFactor, colorScheme: hc ? "dark" : theme });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => console.error(screen, e.message));
    const nb = screen.endsWith("-nb");
    const base = nb ? screen.slice(0, -3) : screen;
    await page.goto(`http://127.0.0.1:${port}/mockups/${base}.html?device=${device}${nb ? "&lang=nb" : ""}${hc ? "&theme=high-contrast" : ""}`);
    await page.waitForSelector("body[data-ready]");
    await page.evaluate(() => document.fonts.ready);
    const file = join(OUT, `${screen}-${device}-${theme}.png`);
    await page.screenshot({ path: file, fullPage: false });
    console.log(file.replace(DESIGN + "/", "design/"));
    await ctx.close();
  }
}
await browser.close();
server.close();
