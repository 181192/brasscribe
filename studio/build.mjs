// Builds Studio into the engine package's static directory, which the engine
// serves at "/". alphaTab is shipped as its UMD build next to the bundle so it
// can locate its own worker and audio-worklet scripts, fonts and soundfont.
import { build, context } from "esbuild";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "engine", "src", "brasscribe_engine", "static");
const assets = join(out, "assets");
const alphaTab = join(here, "node_modules", "@coderline", "alphatab", "dist");
const watch = process.argv.includes("--watch");

rmSync(out, { recursive: true, force: true });
mkdirSync(join(assets, "alphatab"), { recursive: true });

cpSync(join(alphaTab, "alphaTab.min.js"), join(assets, "alphatab", "alphaTab.min.js"));
for (const f of ["Bravura.woff2", "Bravura-OFL.txt"]) {
  cpSync(join(alphaTab, "font", f), join(assets, "alphatab", "font", f));
}
for (const f of ["sonivox.sf2", "LICENSE"]) {
  cpSync(join(alphaTab, "soundfont", f), join(assets, "alphatab", "soundfont", f));
}
writeFileSync(
  join(assets, "alphatab", "NOTICE.txt"),
  "alphaTab (https://alphatab.net) is licensed under the Mozilla Public License 2.0.\n" +
    "Bravura is licensed under the SIL Open Font License 1.1 (font/Bravura-OFL.txt).\n" +
    "The Sonivox soundfont is licensed under the Apache License 2.0 (soundfont/LICENSE).\n",
);

cpSync(join(here, "src", "index.html"), join(out, "index.html"));
cpSync(join(here, "src", "styles.css"), join(assets, "studio.css"));

const options = {
  entryPoints: [join(here, "src", "main.ts")],
  bundle: true,
  format: "esm",
  target: "es2022",
  sourcemap: watch,
  minify: !watch,
  outfile: join(assets, "studio.js"),
  logLevel: "info",
};

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
} else {
  await build(options);
  const size = readFileSync(join(assets, "studio.js")).length;
  console.log(`studio.js ${(size / 1024).toFixed(0)} KiB -> ${out}`);
}
