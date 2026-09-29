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
    document.documentElement.removeAttribute("data-palette");
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

  it("keeps Pink hidden until it is unlocked, and remembers the unlock", async () => {
    let th = await fresh();
    expect(th.pinkUnlocked()).toBe(false);
    expect(th.unlockPink()).toBe(true);
    expect(th.pinkUnlocked()).toBe(true);
    expect(th.unlockPink()).toBe(false); // nothing new to announce
    expect(localStorage.getItem(th.PINK_STORE)).toBe("1");
    th = await fresh();
    expect(th.pinkUnlocked()).toBe(true);
  });

  it("counts a stored Pink as unlocked", async () => {
    localStorage.setItem("brasscribe.studio.theme", "pink");
    const th = await fresh();
    expect(th.choice()).toBe("pink");
    expect(th.pinkUnlocked()).toBe(true);
  });

  it("tells listeners when Pink is unlocked", async () => {
    const th = await fresh();
    let calls = 0;
    th.onThemeChange(() => calls++);
    th.unlockPink();
    th.unlockPink();
    expect(calls).toBe(1);
  });

  it("sets data-palette for Pink, follows the system's light or dark, and can be switched off", async () => {
    const th = await fresh();
    th.setChoice("dark");
    th.setChoice("pink");
    const root = document.documentElement;
    expect(root.getAttribute("data-palette")).toBe("pink");
    expect(root.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(th.THEME_STORE)).toBe("pink");
    th.setChoice("light");
    expect(root.hasAttribute("data-palette")).toBe(false);
    expect(root.getAttribute("data-theme")).toBe("light");
  });

  it("lets more contrast and forced colours win over Pink", async () => {
    const th = await fresh();
    expect(th.resolvePalette("pink", null)).toBe("pink");
    expect(th.resolvePalette("pink", "more")).toBeNull();
    expect(th.resolvePalette("pink", "forced")).toBeNull();
    expect(th.resolvePalette("dark", null)).toBeNull();
    expect(th.resolveTheme("pink", null)).toBeNull();

    stubMedia(["(prefers-contrast: more)"]);
    th.setChoice("pink");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    expect(th.choice()).toBe("pink");
    stubMedia([]);
    th.apply();
    expect(document.documentElement.getAttribute("data-palette")).toBe("pink");
  });

  it("unlocks after five activations in a row, each within 1.5 s", async () => {
    const th = await fresh();
    const c = new th.TapCounter();
    expect([0, 400, 800, 1200].map((t) => c.tap(t))).toEqual([false, false, false, false]);
    expect(c.tap(1600)).toBe(true);

    const slow = new th.TapCounter();
    for (const t of [0, 1000, 2000, 3000]) slow.tap(t);
    expect(slow.tap(5000)).toBe(false); // the 2 s gap started a new run
    expect([5500, 6000, 6500].map((t) => slow.tap(t))).toEqual([false, false, false]);
    expect(slow.tap(7000)).toBe(true);
  });

  it("has the §10 copy in both languages", () => {
    expect(messages.en["app.theme.pink"]).toBe("Pink");
    expect(messages.nb["app.theme.pink"]).toBe("Rosa");
    expect(messages.nb["app.theme.pinkUnlocked"]).toBe("🎺 Rosa låst opp");
    expect(messages.en["app.theme.system"]).toBe("Match system");
    expect(messages.nb["app.theme.system"]).toBe("Følg systemet");
    expect(messages.nb["app.appearance"]).toBe("Utseende");
    expect([messages.nb["app.theme.light"], messages.nb["app.theme.dark"]]).toEqual(["Lyst", "Mørkt"]);
  });
});
