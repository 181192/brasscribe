import { describe, expect, it } from "vitest";
import { patchAlphaTab } from "../src/lib/alphatabfix";

/** Replays the last value to new listeners, like alphaTab's EventEmitterOfT. */
class Emitter<T> {
  constructor(private last: () => T | null) {}
  on(f: (v: T) => void): void {
    const v = this.last();
    if (v !== null) f(v);
  }
}

/** The shape of alphaTab 1.8.4's worker synth: the getter returns itself. */
function brokenNamespace() {
  class AlphaSynthWebWorkerApi {
    _loadedMidiInfo: unknown;
    get loadedMidiInfo(): unknown {
      return this.loadedMidiInfo;
    }
    handleWorkerMessage(e: { data: { cmd: string; args?: unknown } }): void {
      if (e.data.cmd === "alphaSynth.midiLoaded") this._loadedMidiInfo = e.data.args;
    }
  }
  return { synth: { AlphaSynthWebWorkerApi } };
}

describe("patchAlphaTab", () => {
  it("reproduces the overflow when unpatched", () => {
    const ns = brokenNamespace();
    const synth = new ns.synth.AlphaSynthWebWorkerApi();
    const midiLoaded = new Emitter(() => synth.loadedMidiInfo ?? null);
    expect(() => midiLoaded.on(() => {})).toThrow(RangeError);
  });

  it("lets listeners register before and after the MIDI loads", () => {
    const ns = brokenNamespace();
    expect(patchAlphaTab(ns)).toBe(true);
    const synth = new ns.synth.AlphaSynthWebWorkerApi();
    const midiLoaded = new Emitter(() => synth.loadedMidiInfo ?? null);
    const seen: unknown[] = [];
    midiLoaded.on((v) => seen.push(v));
    expect(seen).toEqual([]);

    const info = { endTick: 3840 };
    synth.handleWorkerMessage({ data: { cmd: "alphaSynth.midiLoaded", args: info } });
    expect(synth.loadedMidiInfo).toBe(info);
    midiLoaded.on((v) => seen.push(v));
    expect(seen).toEqual([info]);
    // Per instance.
    expect(new ns.synth.AlphaSynthWebWorkerApi().loadedMidiInfo).toBeUndefined();
  });

  it("patches once and leaves a fixed alphaTab alone", () => {
    const ns = brokenNamespace();
    expect(patchAlphaTab(ns)).toBe(true);
    expect(patchAlphaTab(ns)).toBe(false);

    class Fixed {
      private _info = 1;
      get loadedMidiInfo(): number {
        return this._info;
      }
    }
    const before = Object.getOwnPropertyDescriptor(Fixed.prototype, "loadedMidiInfo");
    expect(patchAlphaTab({ synth: { AlphaSynthWebWorkerApi: Fixed } })).toBe(false);
    expect(Object.getOwnPropertyDescriptor(Fixed.prototype, "loadedMidiInfo")).toEqual(before);
    expect(patchAlphaTab(undefined)).toBe(false);
    expect(patchAlphaTab({})).toBe(false);
  });
});
