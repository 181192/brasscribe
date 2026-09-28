// Workarounds for alphaTab bugs, applied to the UMD namespace before the first AlphaTabApi.

interface WorkerApiClass {
  prototype: object;
}

interface AlphaTabNamespace {
  synth?: { AlphaSynthWebWorkerApi?: WorkerApiClass };
}

const PATCHED = Symbol.for("brasscribe.alphatab.loadedMidiInfo");

/**
 * alphaTab 1.8.4: `AlphaSynthWebWorkerApi.loadedMidiInfo` returns itself, so reading it
 * overflows the stack. `api.midiLoaded.on(...)` reads it when the player already exists (the
 * emitter replays the last value to new listeners), which made every score fail to open with
 * "Maximum call stack size exceeded". The getter is replaced by one that returns the info from
 * the worker's last "alphaSynth.midiLoaded" message. Does nothing once alphaTab is fixed.
 *
 * Returns true when the getter was replaced.
 */
export function patchAlphaTab(ns: unknown): boolean {
  // The worker synth is exported at runtime but not in alphaTab's type definitions.
  const cls = (ns as AlphaTabNamespace | undefined)?.synth?.AlphaSynthWebWorkerApi;
  if (!cls) return false;
  const proto = cls.prototype as Record<PropertyKey, unknown> & { handleWorkerMessage?: (e: MessageEvent) => void };
  if (proto[PATCHED]) return false;
  const getter = Object.getOwnPropertyDescriptor(proto, "loadedMidiInfo")?.get;
  if (!getter || !/return\s*this\.loadedMidiInfo\b/.test(getter.toString())) return false;

  const info = new WeakMap<object, unknown>();
  const handle = proto.handleWorkerMessage;
  if (typeof handle === "function") {
    proto.handleWorkerMessage = function (this: object, e: MessageEvent) {
      const data = e?.data as { cmd?: string; args?: unknown } | undefined;
      if (data?.cmd === "alphaSynth.midiLoaded") info.set(this, data.args);
      return handle.call(this, e);
    };
  }
  Object.defineProperty(proto, "loadedMidiInfo", {
    configurable: true,
    get(this: object) {
      return info.get(this);
    },
  });
  proto[PATCHED] = true;
  return true;
}
