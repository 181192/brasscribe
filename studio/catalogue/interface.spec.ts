// Studio and the engine are built for one interface version each. With another on the engine, Studio says which
// of the two to update and asks the engine for its health only; with the same, the view opens as always.
import { expect, test, type Page } from "@playwright/test";
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

test("the same number: the view opens", async ({ page }) => {
  const paths = asked(page);
  await openView(page, view("runs"), light);
  await expect(page.locator(".runs-table tbody tr").first()).toBeVisible();
  expect(paths).toContain("/v1/jobs");
});
