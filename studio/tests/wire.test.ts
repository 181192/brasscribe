import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, assumeEngineInterface, engineInterface, InterfaceMismatch, onEngineInterface, Unreachable } from "../src/api/client";
import { INTERFACE_VERSION, interfaceMatch } from "../src/api/wire";

describe("the interface version", () => {
  it("is 1 for this release, as the engine's own file says", () => {
    expect(INTERFACE_VERSION).toBe(1);
    const wire = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "engine", "src", "scribe_engine", "wire.py"), "utf8");
    expect(Number(/^INTERFACE_VERSION\s*=\s*(\d+)\s*$/m.exec(wire)?.[1])).toBe(INTERFACE_VERSION);
  });

  it("matches the same number", () => {
    expect(interfaceMatch(INTERFACE_VERSION)).toBe("match");
  });

  it("says to reload Studio when the engine is newer", () => {
    expect(interfaceMatch(INTERFACE_VERSION + 1)).toBe("update-studio");
  });

  it("says to update the engine when it is older", () => {
    expect(interfaceMatch(INTERFACE_VERSION - 1)).toBe("update-engine");
    expect(interfaceMatch(3, 4)).toBe("update-engine");
  });

  it("says to update the engine when it sends no number, or something that is no whole number", () => {
    for (const odd of [undefined, null, "1", 1.5, true, [1], {}, Number.NaN]) expect(interfaceMatch(odd), String(odd)).toBe("update-engine");
  });
});

describe("the client's gate", () => {
  const health = (version?: unknown) => JSON.stringify({ status: "ok", version: "0.1.0", device: "cpu", auth_required: false,
    server_id: "s", server_name: "n", ...(version === undefined ? {} : { interface_version: version }) });

  /** An engine that answers health with `body()` (or cannot be reached when it gives none) and remembers what it was asked. */
  function engine(body: () => string | undefined): string[] {
    const asked: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      asked.push(url);
      if (url !== "/v1/health") return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
      const b = body();
      if (b === undefined) throw new TypeError("Failed to fetch");
      return new Response(b, { status: 200, headers: { "Content-Type": "application/json" } });
    });
    return asked;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
    assumeEngineInterface(undefined);
  });

  it("asks the engine's health before the first request, once", async () => {
    assumeEngineInterface(undefined);
    const asked = engine(() => health(INTERFACE_VERSION));
    await api.jobs();
    await api.profiles();
    expect(asked).toEqual(["/v1/health", "/v1/jobs", "/v1/profiles"]);
    expect(engineInterface()).toBe("match");
  });

  it("asks an engine with another number for its health only", async () => {
    for (const [version, which] of [[INTERFACE_VERSION + 1, "update-studio"], [INTERFACE_VERSION - 1, "update-engine"], [undefined, "update-engine"], ["1", "update-engine"]] as const) {
      assumeEngineInterface(undefined);
      const asked = engine(() => health(version));
      for (const call of [() => api.jobs(), () => api.profiles(), () => api.job("j"), () => api.manifest("j")]) {
        const refused = await call().then(() => undefined, (e: unknown) => e);
        expect(refused, String(version)).toBeInstanceOf(InterfaceMismatch);
        expect((refused as InterfaceMismatch).which).toBe(which);
      }
      expect(asked, String(version)).toEqual(["/v1/health"]);
    }
  });

  it("asks again after a request that did not get through, and tells who listens", async () => {
    assumeEngineInterface(undefined);
    let body: string | undefined = health(INTERFACE_VERSION);
    const asked = engine(() => body);
    const heard: unknown[] = [];
    const off = onEngineInterface((s) => heard.push(s));
    await api.jobs();
    // The engine goes away for its update, and comes back as another version.
    body = undefined;
    await expect(api.health()).rejects.toBeInstanceOf(Unreachable);
    expect(engineInterface()).toBeUndefined();
    body = health(INTERFACE_VERSION + 1);
    asked.length = 0;
    await expect(api.jobs()).rejects.toBeInstanceOf(InterfaceMismatch);
    expect(asked).toEqual(["/v1/health"]);
    // Both up to date again: the next health answer opens it.
    body = health(INTERFACE_VERSION);
    await api.health();
    await api.jobs();
    off();
    expect(heard).toEqual(["match", undefined, "update-studio", "match"]);
  });
});
