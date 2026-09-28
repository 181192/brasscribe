import { describe, expect, it } from "vitest";
import { soundFontBytes, type FontStore, type StoredFont } from "../src/lib/soundfontstore";

class MemoryStore implements FontStore {
  entries = new Map<string, StoredFont>();
  async get(url: string) { return this.entries.get(url); }
  async put(e: StoredFont) { this.entries.set(e.url, e); }
}

interface Call { url: string; init?: RequestInit }

/** A server with one file and an ETag: answers If-None-Match with 304. */
function server(body: string, etag: string) {
  const calls: Call[] = [];
  const f = async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const h = (init?.headers ?? {}) as Record<string, string>;
    if (h["If-None-Match"] === etag) return new Response(null, { status: 304 });
    return new Response(body, { status: 200, headers: { ETag: etag, "Last-Modified": "Sun, 27 Sep 2026 13:17:05 GMT" } });
  };
  return { f, calls };
}

const text = (b: ArrayBuffer) => new TextDecoder().decode(b);

describe("SoundFont kept across visits", () => {
  it("downloads once, then revalidates with the ETag and uses the kept copy on 304", async () => {
    const store = new MemoryStore();
    const s = server("sf2-v1", '"v1"');
    expect(text(await soundFontBytes("/band.sf2", store, s.f))).toBe("sf2-v1");
    expect(store.entries.get("/band.sf2")?.etag).toBe('"v1"');
    expect(text(await soundFontBytes("/band.sf2", store, s.f))).toBe("sf2-v1");
    expect(s.calls).toHaveLength(2);
    const second = s.calls[1].init!;
    expect((second.headers as Record<string, string>)["If-None-Match"]).toBe('"v1"');
    expect(second.cache).toBe("no-store");
  });

  it("replaces the kept copy when the file changed", async () => {
    const store = new MemoryStore();
    await soundFontBytes("/band.sf2", store, server("old", '"v1"').f);
    expect(text(await soundFontBytes("/band.sf2", store, server("new", '"v2"').f))).toBe("new");
    expect(store.entries.get("/band.sf2")?.etag).toBe('"v2"');
  });

  it("uses the kept copy when the server cannot be reached", async () => {
    const store = new MemoryStore();
    await soundFontBytes("/band.sf2", store, server("kept", '"v1"').f);
    const offline = async () => { throw new TypeError("Failed to fetch"); };
    expect(text(await soundFontBytes("/band.sf2", store, offline))).toBe("kept");
  });

  it("without a store it is a plain download", async () => {
    const s = server("plain", '"v1"');
    expect(text(await soundFontBytes("/band.sf2", null, s.f))).toBe("plain");
    expect(s.calls[0].init).toBeUndefined();
  });
});
