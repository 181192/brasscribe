// Temporary probe for #218 (the score's first bar laid out differently from one page load to the next on the
// CI runners): opens the score views several times and logs what alphaTab was told and what it engraved.
// Removed before this branch is merged.
import { test } from "@playwright/test";
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { openView } from "./open";
import { VARIANTS, VIEWS } from "./views";

const viewNames = (process.env.PROBE_VIEW ?? "viewer-score,run-score,compare").split(",");
const variantName = process.env.PROBE_VARIANT ?? "light";
const n = Number(process.env.PROBE_N ?? 12);
const out = join("build", "reports", "screenshots", "probe");

test("probe: the machine's fonts", () => {
  const fc = (f: string) => {
    try {
      return execSync(`fc-match "${f}"`).toString().trim();
    } catch {
      return "fc-match not available";
    }
  };
  console.log(`PROBEFONTS ${["Georgia", "Arial", "serif", "sans-serif"].map((f) => `${f} -> ${fc(f)}`).join(" ; ")}`);
});

for (const viewName of viewNames) for (let i = 0; i < n; i++) {
  test(`probe ${viewName} ${i}`, async ({ page }) => {
    const warnings: string[] = [];
    page.on("console", (m) => { if (m.type() === "warning" || /font/i.test(m.text())) warnings.push(m.text().slice(0, 160)); });
    await page.addInitScript(() => {
      const log: string[] = [];
      const tables: Record<string, string> = {};
      Object.assign(window, { __log: log, __tables: tables });
      const t0 = performance.now();
      const at = () => Math.round(performance.now() - t0);
      const sum = (a: Uint8Array) => { let h = 0; for (const v of a) h = (h * 31 + v) >>> 0; return h.toString(16); };
      const post = Worker.prototype.postMessage;
      Worker.prototype.postMessage = function (this: Worker, data: unknown, ...rest: unknown[]) {
        const d = data as { cmd?: string; width?: number; fontSizes?: Map<string, { characterWidths: Uint8Array; characterHeights: Uint8Array }> };
        if (typeof d?.cmd === "string" && d.cmd.startsWith("alphaTab.")) {
          let extra = "";
          if (d.cmd === "alphaTab.setWidth") extra = ` ${d.width}`;
          if (d.fontSizes) {
            extra = ` {${[...d.fontSizes].map(([k, v]) => `${k}:${sum(v.characterWidths)}/${sum(v.characterHeights)}`).join(" ")}}`;
            for (const [k, v] of d.fontSizes) tables[`${k}:${sum(v.characterWidths)}`] = Array.from(v.characterWidths).join(",");
          }
          log.push(`${at()} ${d.cmd.slice(9)}${extra}`);
        }
        return (post as (...a: unknown[]) => void).call(this, data, ...rest);
      } as typeof post;
      document.addEventListener("DOMContentLoaded", () => {
        document.fonts.addEventListener("loadingdone", (e) => log.push(`${at()} fontsdone ${(e as FontFaceSetLoadEvent).fontfaces.map((f) => f.family).join(",")}`));
        new ResizeObserver((es) => { for (const e of es) log.push(`${at()} resize ${(e.target as HTMLElement).className || e.target.localName} ${e.contentRect.width}`); }).observe(document.documentElement);
      });
    });
    await openView(page, VIEWS.find((v) => v.name === viewName)!, VARIANTS.find((v) => v.name === variantName)!);
    const got = await page.evaluate(() => {
      const surface = document.querySelector(".at-surface") as HTMLElement;
      const html = surface.innerHTML;
      const rects = Array.from(surface.querySelectorAll("rect")).slice(0, 400).map((r) => `${r.getAttribute("x")},${r.getAttribute("width")}`);
      const first = rects.filter((r) => /,24\d/.test(r)).slice(0, 2);
      // How close the widths alphaTab's tables truncate to whole pixels are to a whole pixel.
      const ctx = document.createElement("canvas").getContext("2d")!;
      const near = ["Georgia", "Arial", "alphaTab"].map((family) => {
        ctx.font = `11px ${family}`;
        let closest = 1;
        let which = "";
        for (let c = 32; c < 255; c++) {
          const w = ctx.measureText(String.fromCharCode(c)).width;
          const d = Math.abs(w - Math.round(w));
          if (w > 0 && d > 1e-9 && d < closest) { closest = d; which = `${c}=${w}`; }
        }
        return `${family} ${which}`;
      }).join(" ; ");
      const w = window as unknown as { __log: string[]; __tables: Record<string, string> };
      return { html, first, near, width: surface.getBoundingClientRect().width, log: w.__log, tables: w.__tables, dpr: devicePixelRatio,
        fonts: Array.from(document.fonts).map((f) => `${f.family}:${f.status}`).join(","),
        check: ["Arial", "Georgia", "serif", "sans-serif", "alphaTab"].map((f) => `${f}=${document.fonts.check(`1em ${f}`)}`).join(" ") };
    });
    const hash = createHash("sha1").update(got.html).digest("hex").slice(0, 8);
    mkdirSync(out, { recursive: true });
    writeFileSync(join(out, `${viewName}-${hash}.svg.html`), got.html);
    for (const [k, v] of Object.entries(got.tables)) writeFileSync(join(out, `table-${k.replace(/[^\w]/g, "_")}.txt`), v);
    console.log(`PROBE ${viewName} ${hash} w=${got.width} dpr=${got.dpr} first=${got.first.join(" ")} check: ${got.check} fonts: ${got.fonts}\n   near: ${got.near}\n   log: ${got.log.join("; ")}\n   warn: ${warnings.join(" || ")}`);
  });
}
