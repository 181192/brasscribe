// What changed between two sets of the catalogue's screenshots (scripts/screenshots.sh compare).
//
//   node catalogue/compare.mjs <before dir> <after dir> <report dir>
//
// Writes <report dir>/index.html (before, the difference and after, for each screen that changed) and
// summary.md (the same as a list), and exits 1 when a screen changed, appeared or went away. Without a
// before dir (the commit compared with had no catalogue) nothing counts as new. The pixels are compared in
// Chromium's canvas, so no image library is needed.
import { chromium } from "@playwright/test";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

/** Differing pixels up to this many in one screenshot are noise (reported, not a change). */
export const FLOOR_PIXELS = 4;

const pngs = (dir) => (existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".png")).sort() : []);
const esc = (s) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** Pixels that differ, and a picture of where: the after image faded, with what differs in red. */
async function diff(page, a, b) {
  return page.evaluate(async ([a, b]) => {
    const load = (src) => new Promise((res, rej) => {
      const img = new Image();
      img.onload = () => res(img);
      img.onerror = rej;
      img.src = src;
    });
    const [ia, ib] = await Promise.all([load(a), load(b)]);
    const w = Math.max(ia.width, ib.width);
    const h = Math.max(ia.height, ib.height);
    const pixels = (img) => {
      const c = new OffscreenCanvas(w, h);
      const x = c.getContext("2d");
      x.drawImage(img, 0, 0);
      return x.getImageData(0, 0, w, h).data;
    };
    const pa = pixels(ia);
    const pb = pixels(ib);
    const out = new OffscreenCanvas(w, h);
    const ctx = out.getContext("2d");
    const od = ctx.createImageData(w, h);
    let n = 0;
    const step = (i) => Math.max(Math.abs(pa[i] - pb[i]), Math.abs(pa[i + 1] - pb[i + 1]), Math.abs(pa[i + 2] - pb[i + 2]), Math.abs(pa[i + 3] - pb[i + 3]));
    const lum = (p, i) => 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2];
    // The light of the 3 × 3 pixels around one, in one picture.
    const around = (p, i) => {
      const x = (i / 4) % w;
      const y = Math.floor(i / 4 / w);
      let lo = 255, hi = 0;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx, yy = y + dy;
          if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
          const v = lum(p, (yy * w + xx) * 4);
          lo = Math.min(lo, v);
          hi = Math.max(hi, v);
        }
      }
      return [lo - 2, hi + 2];
    };
    const within = (v, [lo, hi]) => v >= lo && v <= hi;
    for (let i = 0; i < pa.length; i += 4) {
      // A step of one or two in a channel is the rasteriser's rounding, not a change. Nor is a step of up to 16
      // where each picture's pixel is a shade found around the same place in the other: anti-aliasing of an edge
      // that sits a fraction of a pixel elsewhere. A colour that is new to the place (text a shade darker) counts.
      const d = step(i);
      const same = d <= 2 || (d <= 16 && within(lum(pb, i), around(pa, i)) && within(lum(pa, i), around(pb, i)));
      if (!same) n++;
      const grey = 255 - (255 - (pb[i] + pb[i + 1] + pb[i + 2]) / 3) * 0.25;
      od.data.set(same ? [grey, grey, grey, 255] : [220, 0, 0, 255], i);
    }
    ctx.putImageData(od, 0, 0);
    const blob = await out.convertToBlob({ type: "image/png" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { n, share: n / (w * h), sizeChanged: ia.width !== ib.width || ia.height !== ib.height, png: btoa(s) };
  }, [a, b]);
}

export async function compare(beforeDir, afterDir, reportDir) {
  const images = join(reportDir, "images");
  mkdirSync(images, { recursive: true });
  const had = pngs(beforeDir);
  const now = pngs(afterDir);
  const changed = [];
  const minor = [];
  const shares = {};
  const counts = {};
  const added = had.length ? now.filter((f) => !had.includes(f)) : [];
  const gone = now.length ? had.filter((f) => !now.includes(f)) : [];
  const both = now.filter((f) => had.includes(f));
  const differ = both.filter((f) => !readFileSync(join(beforeDir, f)).equals(readFileSync(join(afterDir, f))));
  if (differ.length) {
    const browser = await chromium.launch();
    try {
      const page = await browser.newPage();
      const url = (p) => `data:image/png;base64,${readFileSync(p).toString("base64")}`;
      for (const f of differ) {
        const d = await diff(page, url(join(beforeDir, f)), url(join(afterDir, f)));
        if (!d.n) continue;
        shares[f] = d.share;
        counts[f] = d.n;
        // A handful of pixels on an anti-aliased edge (a glyph, a rounded corner, the score's bar shading) can
        // come out differently from one run to the next on the same machine. Under the floor a difference is
        // reported, but is not a change.
        if (d.n <= FLOOR_PIXELS && !d.sizeChanged) {
          minor.push(f);
          continue;
        }
        changed.push(f);
        const stem = f.replace(/\.png$/, "");
        copyFileSync(join(beforeDir, f), join(images, `${stem}-before.png`));
        writeFileSync(join(images, `${stem}-diff.png`), Buffer.from(d.png, "base64"));
        copyFileSync(join(afterDir, f), join(images, `${stem}-after.png`));
      }
    } finally {
      await browser.close();
    }
  }
  for (const f of added) copyFileSync(join(afterDir, f), join(images, f));

  const lines = [`Screenshots: ${now.length} screens, ${changed.length} changed, ${added.length} new, ${gone.length} gone.`];
  if (!had.length) lines.push("The commit compared with has no screen catalogue: there was nothing to compare with.");
  lines.push(...changed.map((f) => `- changed: \`${f}\` (${counts[f]} pixels, ${(shares[f] * 100).toFixed(2)} %)`));
  lines.push(...minor.map((f) => `- within the noise floor, not a change: \`${f}\` (${counts[f]} pixels)`));
  lines.push(...added.map((f) => `- new: \`${f}\``), ...gone.map((f) => `- gone: \`${f}\``));
  writeFileSync(join(reportDir, "summary.md"), `${lines.join("\n")}\n`);
  const img = (src) => `<img src="images/${esc(src)}" alt="">`;
  const block = (title, rows) => (rows ? `<h2>${esc(title)}</h2>${rows}` : "");
  writeFileSync(join(reportDir, "index.html"), [
    "<!doctype html><meta charset=utf-8><title>Screenshots</title>",
    "<style>body{font:16px system-ui;margin:16px}.row{display:flex;gap:8px;align-items:flex-start}.row img{max-width:32%;border:1px solid #ccc}</style>",
    `<h1>Screenshots</h1><p>${esc(lines[0])}</p><p>Each changed screen: before, the difference (in red), after.</p>`,
    block("Changed", changed.map((f) => {
      const stem = f.replace(/\.png$/, "");
      return `<h3>${esc(f)}</h3><div class="row">${img(`${stem}-before.png`)}${img(`${stem}-diff.png`)}${img(`${stem}-after.png`)}</div>`;
    }).join("")),
    block("New", added.map((f) => `<h3>${esc(f)}</h3>${img(f)}`).join("")),
    block("Gone", gone.map((f) => `<p>${esc(f)}</p>`).join("")),
  ].join("\n"));
  console.log(lines.join("\n"));
  const result = { screens: now.length, changed, added, gone, minor };
  // Written last: the script reads the answer from this file, so a comparison that could not finish gives none.
  writeFileSync(join(reportDir, "result.json"), JSON.stringify({ any: changed.length + added.length + gone.length > 0, ...result }, null, 1));
  return result;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [before, after, report] = process.argv.slice(2);
  if (!before || !after || !report) {
    console.error("usage: node catalogue/compare.mjs <before dir> <after dir> <report dir>");
    process.exit(2);
  }
  try {
    const r = await compare(before, after, report);
    process.exit(r.changed.length || r.added.length || r.gone.length ? 1 : 0);
  } catch (e) {
    console.error(e);
    process.exit(3);
  }
}
