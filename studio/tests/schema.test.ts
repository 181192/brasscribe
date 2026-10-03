// @vitest-environment node
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const studio = join(import.meta.dirname, "..");

describe("API types", () => {
  it("are what `npm run gen:api` makes from the engine's openapi.json", () => {
    const dir = mkdtempSync(join(tmpdir(), "studio-schema-"));
    try {
      const out = join(dir, "schema.d.ts");
      execFileSync(process.execPath, [join(studio, "node_modules/openapi-typescript/bin/cli.js"),
        join(studio, "../engine/openapi.json"), "-o", out], { stdio: "pipe" });
      const committed = readFileSync(join(studio, "src/api/schema.d.ts"), "utf8");
      expect(committed === readFileSync(out, "utf8"), "src/api/schema.d.ts is stale: run `npm run gen:api` in studio/").toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 30_000);
});
