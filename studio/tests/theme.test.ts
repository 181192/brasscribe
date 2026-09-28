import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { messages } from "../src/i18n";

/** matchMedia stub: the listed queries match, the rest don't. */
function stubMedia(matching: string[]): void {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: matching.includes(q),
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

async function fresh() {
  vi.resetModules();
  return import("../src/theme");
}

describe("appearance", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    stubMedia([]);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("defaults to Match system and parses only known values", async () => {
    const th = await fresh();
    expect(th.choice()).toBe("system");
    expect(th.parseChoice("dark")).toBe("dark");
    expect(th.parseChoice("light")).toBe("light");
    expect(th.parseChoice("sepia")).toBe("system");
    expect(th.parseChoice(null)).toBe("system");
  });

  it("pins data-theme and stores the choice in this browser", async () => {
    const th = await fresh();
    th.setChoice("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(th.THEME_STORE)).toBe("dark");
    th.setChoice("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    th.setChoice("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(th.THEME_STORE)).toBeNull();
  });

  it("reads the stored choice on load", async () => {
    localStorage.setItem("brasscribe.studio.theme", "dark");
    const th = await fresh();
    expect(th.choice()).toBe("dark");
  });

  it("lets forced colours win over the choice, and keeps the choice", async () => {
    const th = await fresh();
    expect(th.resolveTheme("dark", "forced")).toBeNull();
    expect(th.resolveTheme("light", "forced")).toBeNull();
    expect(th.resolveTheme("dark", null)).toBe("dark");
    expect(th.resolveTheme("system", null)).toBeNull();

    stubMedia(["(forced-colors: active)"]);
    expect(th.contrast()).toBe("forced");
    th.setChoice("dark");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(th.choice()).toBe("dark");
    expect(localStorage.getItem(th.THEME_STORE)).toBe("dark");

    stubMedia([]);
    th.apply();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("keeps Light or Dark under more contrast, so the matching high-contrast palette applies", async () => {
    const th = await fresh();
    expect(th.resolveTheme("light", "more")).toBe("light");
    expect(th.resolveTheme("dark", "more")).toBe("dark");
    expect(th.resolveTheme("system", "more")).toBeNull();

    stubMedia(["(prefers-contrast: more)"]);
    expect(th.contrast()).toBe("more");
    th.setChoice("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    th.setChoice("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    th.setChoice("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("notifies listeners when the choice changes", async () => {
    const th = await fresh();
    const seen: string[] = [];
    th.onThemeChange(() => seen.push(th.choice()));
    th.setChoice("light");
    expect(seen).toEqual(["light"]);
  });

  it("has the §10 copy in both languages", () => {
    expect(messages.en["app.theme.system"]).toBe("Match system");
    expect(messages.nb["app.theme.system"]).toBe("Følg systemet");
    expect(messages.nb["app.appearance"]).toBe("Utseende");
    expect([messages.nb["app.theme.light"], messages.nb["app.theme.dark"]]).toEqual(["Lyst", "Mørkt"]);
  });
});
