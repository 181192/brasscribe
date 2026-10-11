// Studio and the engine are built for one interface version each. With another on the engine, Studio says which
// of the two to update and asks the engine for its health only; with the same, the view opens as always.
import { expect, test, type Page } from "@playwright/test";
import { serveApi } from "./api";
import { openView } from "./open";
import { VARIANTS, VIEWS } from "./views";

const light = VARIANTS.find((v) => v.name === "light")!;
const view = (name: string) => VIEWS.find((v) => v.name === name)!;

/** The engine paths the page asks for from now on. */
function asked(page: Page): string[] {
  const paths: string[] = [];
  page.on("request", (r) => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith("/v1/")) paths.push(path);
  });
  return paths;
}

test("an engine without the number: update the engine, and only its health is asked for", async ({ page }) => {
  const paths = asked(page);
  await openView(page, view("update-engine"), light);
  await expect(page.locator("#main h1")).toHaveText("Update the engine on this computer");
  await expect(page.locator("#engine-status")).toHaveText("Update the engine on this computer");
  await expect(page.locator(".runs-table")).toHaveCount(0);
  // Another view is no way round it, and Try again asks for the health once more and nothing else.
  await page.goto("/#/registry");
  await expect(page.locator("#main h1")).toHaveText("Update the engine on this computer");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator("#main h1")).toHaveText("Update the engine on this computer");
  expect(new Set(paths)).toEqual(new Set(["/v1/health"]));
});

test("a newer engine: reload the page, and only its health is asked for", async ({ page }) => {
  const paths = asked(page);
  await openView(page, view("update-studio"), light);
  await expect(page.locator("#main h1")).toHaveText("Reload this page");
  await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
  expect(new Set(paths)).toEqual(new Set(["/v1/health"]));
});

test("a page left open while the engine is replaced by a newer one says to reload when it is looked at again", async ({ page }) => {
  await openView(page, view("runs"), light);
  await expect(page.locator(".runs-table tbody tr").first()).toBeVisible();
  // The engine is updated under the open page: its health now says a higher number.
  await page.route("**/v1/health", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    status: "ok", version: "0.2.0", build: "catalogue", device: "cpu", auth_required: false,
    server_id: "00000000000000000000000000000000", server_name: "Brasscribe Studio catalogue", interface_version: 2,
  }) }));
  const paths = asked(page);
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(page.locator("#main h1")).toHaveText("Reload this page");
  await expect(page.locator(".runs-table")).toHaveCount(0);
  // Going to another view asks the engine for nothing.
  await page.goto("/#/registry");
  await expect(page.locator("#main h1")).toHaveText("Reload this page");
  expect(new Set(paths)).toEqual(new Set(["/v1/health"]));
});

test("no view opens, and nothing is asked, before the engine has said its number", async ({ page }) => {
  let answer: (() => void) | undefined;
  const held = new Promise<void>((r) => (answer = r));
  await serveApi(page);
  // Health is held back (an engine from before the number, slow to answer); the reader goes to another view meanwhile.
  await page.route("**/v1/health", async (route) => {
    await held;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      status: "ok", version: "0.1.0", device: "cpu", auth_required: false, server_id: "00000000000000000000000000000000", server_name: "Brasscribe Studio catalogue",
    }) });
  });
  const paths = asked(page);
  await page.goto("/#/runs");
  await page.evaluate(() => { location.hash = "#/registry"; });
  await page.waitForTimeout(300);
  expect(new Set(paths)).toEqual(new Set(["/v1/health"]));
  await expect(page.locator("#main h1")).toHaveCount(0);
  answer!();
  await expect(page.locator("#main h1")).toHaveText("Update the engine on this computer");
  expect(new Set(paths)).toEqual(new Set(["/v1/health"]));
});

test("the same number: the view opens", async ({ page }) => {
  const paths = asked(page);
  await openView(page, view("runs"), light);
  await expect(page.locator(".runs-table tbody tr").first()).toBeVisible();
  expect(paths).toContain("/v1/jobs");
});
