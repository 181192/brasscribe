import { describe, expect, it } from "vitest";
import { SizedLru } from "../src/lib/lru";

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("a size-limited cache", () => {
  it("loads a key once and reuses it", async () => {
    const lru = new SizedLru<string, number>(100, (v) => v);
    let loads = 0;
    const load = async () => { loads++; return 10; };
    expect(await lru.get("a", load)).toBe(10);
    expect(await lru.get("a", load)).toBe(10);
    expect(loads).toBe(1);
  });

  it("drops the least recently used values once over the budget", async () => {
    const lru = new SizedLru<string, number>(100, (v) => v);
    await lru.get("a", async () => 40);
    await lru.get("b", async () => 40);
    await lru.get("a", async () => 0); // a is now the most recently used
    await lru.get("c", async () => 40);
    await flush();
    expect(lru.has("a")).toBe(true);
    expect(lru.has("b")).toBe(false);
    expect(lru.has("c")).toBe(true);
    expect(lru.size).toBe(80);
  });

  it("keeps the value just loaded even when it alone is over the budget", async () => {
    const lru = new SizedLru<string, number>(100, (v) => v);
    await lru.get("a", async () => 50);
    await lru.get("big", async () => 500);
    await flush();
    expect(lru.has("a")).toBe(false);
    expect(lru.has("big")).toBe(true);
  });

  it("never drops a load still in progress, and forgets a failed one", async () => {
    const lru = new SizedLru<string, number>(10, (v) => v);
    let finish: (v: number) => void = () => {};
    const slow = lru.get("slow", () => new Promise<number>((r) => { finish = r; }));
    await lru.get("x", async () => 50);
    await flush();
    expect(lru.has("slow")).toBe(true);
    finish(1);
    expect(await slow).toBe(1);
    await expect(lru.get("bad", async () => { throw new Error("404"); })).rejects.toThrow("404");
    await flush();
    expect(lru.has("bad")).toBe(false);
  });
});
