import { afterEach, describe, expect, it, vi } from "vitest";
import { anySignal, api, isAbort, TimedOut } from "../src/api/client";

/** A fetch that never answers and rejects the way a browser does when its signal aborts. */
function hangingFetch(seen: { signal?: AbortSignal | null } = {}) {
  return (_url: string, init: RequestInit = {}) => new Promise<Response>((_resolve, reject) => {
    seen.signal = init.signal;
    init.signal?.addEventListener("abort", () => reject(new DOMException("The operation was aborted.", "AbortError")));
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("cancelling requests", () => {
  it("passes the caller's cancel on as an AbortError, not a time-out", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    const ctl = new AbortController();
    const p = api.job("r1", { signal: ctl.signal }).catch((e) => e);
    ctl.abort();
    const e = await p;
    expect(isAbort(e)).toBe(true);
    expect(e).not.toBeInstanceOf(TimedOut);
  });

  it("still says the engine timed out when the deadline passes", async () => {
    const deadline = new AbortController();
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(deadline.signal);
    vi.stubGlobal("fetch", hangingFetch());
    const ctl = new AbortController();
    const p = api.job("r1", { signal: ctl.signal }).catch((e) => e);
    deadline.abort(new DOMException("timed out", "TimeoutError"));
    const e = await p;
    expect(e).toBeInstanceOf(TimedOut);
    expect(isAbort(e)).toBe(false);
  });

  it("times out a call made without a signal of its own", async () => {
    const deadline = new AbortController();
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(deadline.signal);
    vi.stubGlobal("fetch", hangingFetch());
    const p = api.parity().catch((e) => e);
    deadline.abort(new DOMException("timed out", "TimeoutError"));
    expect(await p).toBeInstanceOf(TimedOut);
  });

  it("combines signals where AbortSignal.any is missing", () => {
    const any = AbortSignal.any;
    try {
      (AbortSignal as { any?: unknown }).any = undefined;
      const a = new AbortController();
      const b = new AbortController();
      const s = anySignal([a.signal, b.signal]);
      expect(s.aborted).toBe(false);
      b.abort();
      expect(s.aborted).toBe(true);
      const done = new AbortController();
      done.abort();
      expect(anySignal([new AbortController().signal, done.signal]).aborted).toBe(true);
    } finally {
      AbortSignal.any = any;
    }
  });
});
