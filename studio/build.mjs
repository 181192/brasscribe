// Builds Studio into the engine package's static directory, which the engine
// serves at "/". alphaTab is shipped as its UMD build next to the bundle so it
// can locate its own worker and audio-worklet scripts, fonts and soundfont.
import { build, context } from "esbuild";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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

// The band sounds (sounds/band.py; the phone-sized build, smallest to download) and their part
// map, when the checkout has them. Without them Studio plays the Sonivox set above and says so.
const bandSf2 = ["brasscribe-band-mobile.sf2", "brasscribe-band-16bit.sf2", "brasscribe-band.sf2"]
  .map((f) => join(here, "..", "data", "sounds", "band", f))
  .find((f) => existsSync(f));
if (bandSf2) {
  mkdirSync(join(assets, "band"), { recursive: true });
  cpSync(bandSf2, join(assets, "band", "brasscribe-band.sf2"));
  cpSync(join(here, "..", "sounds", "mapping.json"), join(assets, "band", "mapping.json"));
  // The phone-sized build keeps one layer of the layered cornet presets: their balance differs.
  writeFileSync(join(assets, "band", "band.json"), JSON.stringify({ singleVoice: bandSf2.includes("-mobile") }) + "\n");
  writeFileSync(
    join(assets, "band", "NOTICE.txt"),
    "Band sounds adapted from VSCO 2 Community Edition (CC0) and the University of Iowa Musical Instrument Samples;\n" +
      "drum kit from MuseScore MS Basic (MIT). Sources and licences: sounds/manifest.json.\n",
  );
  // Too large for git: the committed static build carries no band sounds.
  writeFileSync(join(assets, "band", ".gitignore"), "*\n");
  console.log(`band sounds: ${bandSf2}`);
} else {
  console.warn("band sounds: data/sounds/band/*.sf2 not found, Studio will play General MIDI sounds");
}

cpSync(join(here, "src", "index.html"), join(out, "index.html"));
// Brand icons from the design system (design/dist/icons/web), rendered by design/brand/build.py.
const icons = join(here, "..", "design", "dist", "icons", "web");
for (const f of ["favicon.svg", "favicon.ico", "favicon-32.png", "apple-touch-icon.png", "icon-192.png"]) {
  cpSync(join(icons, f), join(out, f));
}

// Scripts and styles are bundled from their sources: the design tokens
// (design/dist/web/*.css), the brand fonts and the icon paths are imported,
// not copied by hand.
const options = {
  entryPoints: { studio: join(here, "src", "main.ts"), "studio-style": join(here, "src", "styles.css") },
  bundle: true,
  format: "esm",
  target: "es2022",
  sourcemap: watch,
  minify: !watch,
  outdir: assets,
  entryNames: "[name]",
  assetNames: "fonts/[name]",
  loader: { ".ttf": "file", ".svg": "text" },
  logLevel: "info",
};

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
} else {
  await build(options);
  cpSync(join(here, "..", "design", "dist", "web", "fonts", "OFL.txt"), join(assets, "fonts", "OFL.txt"));
  const size = readFileSync(join(assets, "studio.js")).length;
  console.log(`studio.js ${(size / 1024).toFixed(0)} KiB -> ${out}`);
}
