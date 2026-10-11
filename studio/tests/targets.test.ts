import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { Job, ProfileInfo } from "../src/api/types";
import { hasScore, scoreFile, TARGETS } from "../src/lib/targets";

const here = dirname(fileURLToPath(import.meta.url));
const read = (...path: string[]) => JSON.parse(readFileSync(join(here, "..", ...path), "utf8"));

describe("targets", () => {
  it("are the ones the engine's interface names", () => {
    const named = read("..", "engine", "openapi.json").components.schemas.ProfileInfo.properties.target.enum as string[];
    expect([...TARGETS].sort()).toEqual([...named].sort());
  });

  it("name their score as the engine's jobs do", () => {
    // The answers an engine gave (the catalogue's fixtures): a job that wrote a score wrote it under its target's name.
    const answers = read("e2e", "fixtures", "api", "responses.json");
    const jobs = (answers["/v1/jobs"].body as Job[]).filter((j) => j.outputs?.some((o) => /^[^/]+\.musicxml$/.test(o)));
    expect(new Set(jobs.map((j) => j.target))).toEqual(new Set(TARGETS));
    for (const job of jobs) {
      expect(job.outputs, job.id).toContain(scoreFile(job.target!, "musicxml"));
      expect(hasScore(job.outputs, "musicxml")).toBe(true);
    }
    const profiles = answers["/v1/profiles"].body as ProfileInfo[];
    for (const job of answers["/v1/jobs"].body as Job[]) {
      expect(job.target, job.id).toBe(profiles.find((p) => p.name === job.profile)?.target);
    }
  });
});
