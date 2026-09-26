import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, MissingEndpoint, TimedOut, Unreachable } from "../src/api/client";
import { setLang } from "../src/i18n";
import { errorNotice } from "../src/ui/dom";

afterEach(() => {
  vi.unstubAllGlobals();
  setLang("en");
});

describe("fetch errors", () => {
  it("turns a network failure into Unreachable", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));
    await expect(api.parity()).rejects.toBeInstanceOf(Unreachable);
  });

  it("turns an unknown route into MissingEndpoint and a server error into ApiError", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response("Not Found", { status: 404 })));
    await expect(api.parity()).rejects.toBeInstanceOf(MissingEndpoint);
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({ detail: "boom" }), { status: 500 })));
    const e = await api.parity().catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).status).toBe(500);
  });

  it("never shows a bare browser message; each notice says what to do and offers Try again", () => {
    const cases: [unknown, RegExp][] = [
      [new Unreachable("Failed to fetch"), /Couldn't reach Brasscribe on this computer\..*brasscribe serve.*running\?/],
      [new TimedOut(20), /taking too long.*20 seconds/],
      [new MissingEndpoint("GET /v1/conformance"), /Not available in this version\..*GET \/v1\/conformance.*Update it/],
      [new ApiError(500, "boom"), /hit a problem\..*error 500.*boom/],
    ];
    for (const [err, re] of cases) {
      const el = errorNotice(err);
      expect(el.textContent).toMatch(re);
      expect(el.textContent).not.toContain("Failed to fetch");
      expect(el.querySelector("button")?.textContent).toBe("Try again");
    }
  });

  it("calls the given retry, and speaks Norwegian", () => {
    const retry = vi.fn();
    setLang("nb");
    const el = errorNotice(new Unreachable("x"), { retry });
    expect(el.textContent).toContain("Fikk ikke kontakt med Brasscribe på datamaskinen.");
    el.querySelector("button")!.click();
    expect(retry).toHaveBeenCalledOnce();
    expect(el.querySelector("button")?.textContent).toBe("Prøv igjen");
  });
});
