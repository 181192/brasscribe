// The engine's API for the catalogue: every /v1 request is answered from e2e/fixtures/api/responses.json
// (responses an engine gave for the public-domain runs in e2e/fixtures/compare, plus a failed run, a short
// benchmark history and a conformance report written for the catalogue; host names and paths taken out).
// A request the fixture does not have is answered 404 and reported, so a view that starts calling a new
// route fails until the fixture has it.
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "..", "e2e", "fixtures", "api");

type Entry = { status: number; type?: string; body?: unknown; file?: string };
const responses = JSON.parse(readFileSync(join(fixtures, "responses.json"), "utf8")) as Record<string, Entry>;

/** Answers /v1 from the fixtures; returns the requests that had no fixture (or were not GETs). */
export async function serveApi(page: Page): Promise<string[]> {
  const unanswered: string[] = [];
  await page.route("**/v1/**", async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const key = u.pathname + u.search;
    const e = req.method() === "GET" ? responses[key] : undefined;
    if (!e) {
      unanswered.push(`${req.method()} ${key}`);
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `no fixture for ${key}` }) });
      return;
    }
    const body = e.file ? readFileSync(join(fixtures, e.file)) : typeof e.body === "string" ? e.body : JSON.stringify(e.body);
    await route.fulfill({ status: e.status, contentType: e.type ?? "application/json", body });
  });
  return unanswered;
}
