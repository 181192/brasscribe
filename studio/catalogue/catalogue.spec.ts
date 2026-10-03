// The screen catalogue: every view in every variant (light, dark, high contrast light and dark, bokmål,
// 200 % zoom, 320 px), with axe-core, cut-off text, the page fitting its width, the keyboard walk and text
// spacing, and a screenshot of each when CATALOGUE_SHOTS names a folder. CATALOGUE_CHECKS=0 only takes the
// screenshots (the merge base's side of scripts/screenshots.sh compare).
import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { axe, clipped, keyboard, reflow, textSpacing, type Finding } from "./checks";
import { isKnown } from "./known";
import { openView, stableScreenshot, steady } from "./open";
import { VARIANTS, VIEWS } from "./views";

const shots = process.env.CATALOGUE_SHOTS;
const checks = process.env.CATALOGUE_CHECKS !== "0";
if (shots) mkdirSync(shots, { recursive: true });

for (const variant of VARIANTS) {
  for (const view of VIEWS) {
    if (view.only && !view.only.includes(variant.name)) continue;
    test(`${view.name} · ${variant.name}`, async ({ page }) => {
      const opened = await openView(page, view, variant);
      if (shots) {
        await steady(page);
        await stableScreenshot(page, join(shots, `${view.name}--${variant.name}.png`));
      }
      if (!checks) return;
      expect(opened.problems, "errors and requests without a fixture").toEqual([]);
      const findings: Finding[] = [...await axe(page), ...await clipped(page)];
      if (variant.reflow) findings.push(...await reflow(page));
      if (variant.keyboard) findings.push(...await keyboard(page));
      if (variant.spacing) findings.push(...await textSpacing(page));
      const known = findings.filter((f) => isKnown(f, view.name, variant.name));
      if (known.length) console.log(`${view.name} · ${variant.name}: ${known.length} known: ${known.map((f) => `${f.check} ${f.what}`).join("; ")}`);
      expect(findings.filter((f) => !isKnown(f, view.name, variant.name)).map((f) => `${f.check}: ${f.what}`)).toEqual([]);
    });
  }
}
