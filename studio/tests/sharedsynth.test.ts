import { describe, expect, it } from "vitest";
import { SharedSynth, type ApiLike, type SynthLike } from "../src/lib/sharedsynth";

/** A worker synth: ready at once, counts what it is asked to do. */
class FakeSynth implements SynthLike {
  isReady = true;
  destroyed = 0;
  stops = 0;
  fonts: Uint8Array[] = [];
  ready = { on: (f: () => void) => { f(); return () => {}; } };
  stop(): void { this.stops++; }
  destroy(): void { this.destroyed++; }
  loadSoundFont(data: Uint8Array): void { this.fonts.push(data); }
}

/** alphaTab's AlphaSynthWrapper: subscribes to the instance it is given; destroy() destroys it. */
class FakeWrapper {
  private inst: SynthLike | undefined;
  subscribed: SynthLike | undefined;
  get instance(): SynthLike | undefined { return this.inst; }
  set instance(v: SynthLike | undefined) { this.inst = v; this.subscribed = v; }
  playOneTimeMidiFile(): void {}
  destroy(): void { this.inst?.destroy(); this.inst = undefined; }
}

/** The parts of an AlphaTabApi the shared synth uses, with a renderer wrapper as a decoy. */
class FakeApi implements ApiLike {
  settings = { player: { playerMode: 0 } };
  readonly _renderer = new (class { set instance(_v: unknown) {} get instance() { return undefined; } })();
  readonly _player = new FakeWrapper();
  created: FakeSynth[] = [];
  uiFacade = { createWorkerPlayer: (): SynthLike | null => { const s = new FakeSynth(); this.created.push(s); return s; } };
  updateSettings(): void {
    // alphaTab's _setupOrDestroyPlayer: a new player from the ui facade when the mode changes.
    if (this.settings.player.playerMode !== 0 && !this._player.instance) this._player.instance = this.uiFacade.createWorkerPlayer() ?? undefined;
  }
  destroy(): void { this._player.destroy(); }
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("one synthesizer per page", () => {
  it("creates one synth and loads the SoundFont once for every score", async () => {
    let fetched = 0;
    const synth = new SharedSynth(async () => { fetched++; return new ArrayBuffer(8); });
    const a = new FakeApi();
    const b = new FakeApi();
    synth.attach(a, "band.sf2", () => {});
    await flush();
    synth.release(a);
    a.destroy();
    synth.attach(b, "band.sf2", () => {});
    await flush();
    expect(a.created.length + b.created.length).toBe(1);
    expect(synth.synthsCreated).toBe(1);
    expect(fetched).toBe(1);
    expect(synth.soundFontLoads).toBe(1);
    expect(a.created[0].fonts).toHaveLength(1);
    expect(b._player.instance).toBe(a.created[0]);
  });

  it("destroying a score that gave the synth back leaves the synth alive", () => {
    const synth = new SharedSynth(async () => new ArrayBuffer(8));
    const a = new FakeApi();
    synth.attach(a, "band.sf2", () => {});
    const player = a.created[0];
    synth.release(a);
    a.destroy();
    expect(player.destroyed).toBe(0);
    expect(synth.ownerApi).toBeNull();
  });

  it("moving the synth unsubscribes the score that had it and tells it", () => {
    const synth = new SharedSynth(async () => new ArrayBuffer(8));
    const a = new FakeApi();
    const b = new FakeApi();
    let lost = 0;
    synth.attach(a, "band.sf2", () => lost++);
    const player = a.created[0];
    synth.attach(b, "band.sf2", () => {});
    expect(lost).toBe(1);
    expect(a._player.instance).toBeUndefined();
    expect(b._player.instance).toBe(player);
    expect(player.stops).toBeGreaterThan(0);
    // And back: a reuses the same synth, no new one.
    synth.attach(a, "band.sf2", () => lost++);
    expect(a._player.instance).toBe(player);
    expect(b._player.instance).toBeUndefined();
    expect(b.created).toHaveLength(0);
    // A score that lost the synth cannot destroy it.
    synth.release(b);
    b.destroy();
    expect(player.destroyed).toBe(0);
  });

  it("another SoundFont replaces the synth", async () => {
    const urls: string[] = [];
    const synth = new SharedSynth(async (u) => { urls.push(u); return new ArrayBuffer(8); });
    const a = new FakeApi();
    const b = new FakeApi();
    synth.attach(a, "sonivox.sf2", () => {});
    synth.attach(b, "band.sf2", () => {});
    await flush();
    expect(a.created[0].destroyed).toBe(1);
    expect(urls).toEqual(["sonivox.sf2", "band.sf2"]);
    expect(synth.synthsCreated).toBe(2);
  });

  it("a SoundFont that fails to load is reported, and the next attach tries again with one new synth", async () => {
    let fail = true;
    const synth = new SharedSynth(async () => {
      if (fail) throw new Error("offline");
      return new ArrayBuffer(8);
    });
    const a = new FakeApi();
    const errors: unknown[] = [];
    let lost = 0;
    synth.attach(a, "band.sf2", () => lost++, (e) => errors.push(e));
    await flush();
    const first = a.created[0];
    expect(errors).toHaveLength(1);
    expect(lost).toBe(0);
    expect(first.destroyed).toBe(1);
    expect(a._player.instance).toBeUndefined();
    expect(synth.ownerApi).toBeNull();
    expect(synth.soundFontLoads).toBe(0);

    fail = false;
    synth.attach(a, "band.sf2", () => lost++, (e) => errors.push(e));
    await flush();
    expect(synth.synthsCreated).toBe(2);
    expect(a.created).toHaveLength(2);
    expect(a._player.instance).toBe(a.created[1]);
    expect(synth.soundFontLoads).toBe(1);
    expect(a.created[1].fonts).toHaveLength(1);
    expect(errors).toHaveLength(1);
  });
});
