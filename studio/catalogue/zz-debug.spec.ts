// Temporary: what differs in the score between CI runs.
import { test } from "@playwright/test";
import { createHash } from "node:crypto";
import { openView } from "./open";
import { VARIANTS } from "./views";

for (const name of ["light", "dark", "nb", "contrast"]) {
  test(`zz score layout ${name}`, async ({ page }) => {
    const v = VARIANTS.find((x) => x.name === name)!;
    await openView(page, { route: "runs/old-hundredth-a/score", ready: async (p) => {
      await p.waitForFunction(() => { const s = document.querySelector("#main bs-score") as unknown as { rendered?: boolean; ready?: boolean }; return !!s?.rendered && !!s?.ready; }, undefined, { timeout: 60_000 });
    } }, v);
    const info = await page.evaluate(() => {
      const surf = document.querySelector("#main bs-score .at-surface") as HTMLElement;
      const r = surf.getBoundingClientRect();
      const parts = Array.from(surf.children).map((c) => { const b = c.getBoundingClientRect(); return `${b.left}/${b.top}`; }).join(" ");
      const lines = Array.from(surf.querySelectorAll("rect")).map((e) => e.getAttribute("x")).filter((x) => x && Number(x) > 280 && Number(x) < 340).slice(0, 6).join(",");
      return { html: surf.innerHTML, rect: `${r.left},${r.top},${r.width}`, parts, lines, dpr: devicePixelRatio, cores: navigator.hardwareConcurrency };
    });
    console.log(`zzlayout ${name} svg=${createHash("sha1").update(info.html).digest("hex").slice(0, 10)} rect=${info.rect} parts=${info.parts} rectsx=${info.lines} dpr=${info.dpr} cores=${info.cores}`);
  });
}
