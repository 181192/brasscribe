import { afterEach, describe, expect, it, vi } from "vitest";
import { anySignal, api, isAbort, subscribe, SUITE_TIMEOUT_S, TimedOut, type StreamState } from "../src/api/client";
import type { JobEvent } from "../src/api/types";

/** The browser's EventSource, driven by hand. */
class FakeEventSource extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static last: FakeEventSource;
  readyState = 0;
  closed = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly url: string) {
    super();
    FakeEventSource.last = this;
  }
  close(): void {
    this.closed++;
    this.readyState = 2;
  }
  open(): void {
    this.readyState = 1;
    this.onopen?.();
  }
  send(type: string, e: Partial<JobEvent>): void {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(e) }));
  }
  drop(giveUp = false): void {
    this.readyState = giveUp ? 2 : 0;
    this.onerror?.();
  }
}

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

  it("waits hours, not minutes, for a benchmark suite to finish", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    vi.stubGlobal("fetch", () => Promise.resolve(new Response("{}", { status: 200 })));
    await api.runSuite("cpu");
    expect(timeout).toHaveBeenCalledWith(SUITE_TIMEOUT_S * 1000);
    expect(SUITE_TIMEOUT_S).toBeGreaterThanOrEqual(60 * 60);
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

describe("following a run", () => {
  it("keeps the stream open through a dropped connection and says it is reconnecting", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const events: number[] = [];
    const states: StreamState[] = [];
    const stop = subscribe("r1", (e) => events.push(e.id), (s) => states.push(s));
    const es = FakeEventSource.last;
    es.open();
    es.send("stage", { id: 1, type: "stage" });
    es.drop();
    expect(es.closed).toBe(0);
    expect(states).toEqual(["reconnecting"]);
    // The browser reconnects and the engine resumes; an event seen twice is dropped.
    es.open();
    es.send("stage", { id: 1, type: "stage" });
    es.send("log", { id: 2, type: "log" });
    expect(events).toEqual([1, 2]);
    expect(states).toEqual(["reconnecting", "open"]);
    stop();
    expect(es.closed).toBe(1);
  });

  it("reports when the browser gives up", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const states: StreamState[] = [];
    subscribe("r1", () => undefined, (s) => states.push(s));
    FakeEventSource.last.drop(true);
    expect(states).toEqual(["closed"]);
  });
});
