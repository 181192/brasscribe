// One alphaTab synthesizer per page, handed to whichever score plays.
//
// Each AlphaTabApi normally builds its own synth worker and loads the SoundFont into it, and
// alphaTab holds several copies of the file per worker (the downloaded bytes, the copy posted to
// the worker, the sample chunk and the decoded samples). Here the page keeps a single worker synth
// with the SoundFont loaded once; a score attaches to it before it plays, and the score that had
// it lets go.
//
// alphaTab's player wrapper (a private field of the api) takes any synth as its `instance` and
// replays `ready` when the synth is already ready, which makes the api generate and load its own
// MIDI. Nothing in alphaTab's public API does this, so it relies on alphaTab 1.8 internals: the
// wrapper's `instance` accessor, `uiFacade.createWorkerPlayer`, and the synth's Worker. The minified
// build renames private fields, so the wrapper and the Worker are found by shape, not by name.

/** The worker synth (alphaTab's AlphaSynthWebWorkerApi), as far as this module uses it. */
export interface SynthLike {
  readonly isReady: boolean;
  ready: { on(f: () => void): () => void };
  stop(): void;
  destroy(): void;
  loadSoundFont(data: Uint8Array, append: boolean): void;
  resetChannelStates?(): void;
}

/** The parts of an AlphaTabApi used here. */
export interface ApiLike {
  settings: { player: { playerMode: number } };
  updateSettings(): void;
  uiFacade: { createWorkerPlayer(): SynthLike | null };
}

interface Wrapper {
  instance: SynthLike | undefined;
}

/** alphaTab's PlayerMode.EnabledSynthesizer. */
const ENABLED_SYNTHESIZER = 2;

const wrappers = new WeakMap<ApiLike, Wrapper>();

/**
 * The api's player wrapper (AlphaSynthWrapper): the own field whose class has an `instance`
 * setter and the player methods (the renderer wrapper has `instance` too, but no `playOneTimeMidiFile`).
 */
export function playerWrapper(api: ApiLike): Wrapper {
  let w = wrappers.get(api);
  if (w) return w;
  for (const v of Object.values(api as object)) {
    if (!v || typeof v !== "object") continue;
    const proto = Object.getPrototypeOf(v) as object | null;
    if (proto && Object.getOwnPropertyDescriptor(proto, "instance")?.set && typeof (v as Record<string, unknown>).playOneTimeMidiFile === "function") {
      w = v as Wrapper;
      break;
    }
  }
  if (!w) throw new Error("alphaTab's player wrapper was not found (alphaTab changed?)");
  wrappers.set(api, w);
  return w;
}

/** The synth's Worker, to post the SoundFont to it without a copy; null when there is none. */
function workerOf(player: SynthLike): Worker | null {
  if (typeof Worker === "undefined") return null;
  return (Object.values(player as object).find((v) => v instanceof Worker) as Worker | undefined) ?? null;
}

interface Owner {
  api: ApiLike;
  onRelease: () => void;
  onError?: (e: unknown) => void;
}

export class SharedSynth {
  private player: SynthLike | null = null;
  private url: string | null = null;
  private owner: Owner | null = null;
  /** Each patched api's own createWorkerPlayer, as alphaTab set it up. */
  private readonly creators = new WeakMap<ApiLike, () => SynthLike | null>();
  /** How many times a SoundFont was sent to a synth (for tests and the probe). */
  soundFontLoads = 0;
  /** How many synths were created (for tests and the probe). */
  synthsCreated = 0;

  constructor(private readonly bytes: (url: string) => Promise<ArrayBuffer>) {}

  /** The api that has the synth now, if any. */
  get ownerApi(): ApiLike | null {
    return this.owner?.api ?? null;
  }

  /**
   * Give the page's synth to `api`, creating it on first use with the SoundFont at `url`.
   * The previous owner loses it (its `onRelease` runs). The api must have been built with
   * `playerMode: "disabled"`, so that alphaTab did not start a synth of its own.
   *
   * If the SoundFont can't be loaded, `onError` runs and the synth is dropped, so the next
   * `attach` starts over with a new one.
   */
  attach(api: ApiLike, url: string, onRelease: () => void, onError?: (e: unknown) => void): void {
    if (this.owner?.api === api) return;
    if (this.player && this.url !== url) this.dispose();
    this.detachOwner(true);
    this.owner = { api, onRelease, onError };
    const create = this.creators.get(api);
    if (!create) {
      // The first time: alphaTab sets the player up itself (cursors included), asking the ui
      // facade for a synth, which is the shared one.
      const own = api.uiFacade.createWorkerPlayer.bind(api.uiFacade);
      this.creators.set(api, own);
      api.uiFacade.createWorkerPlayer = () => this.ensure(url, own);
      api.settings.player.playerMode = ENABLED_SYNTHESIZER;
      api.updateSettings();
      return;
    }
    const player = this.ensure(url, create);
    if (player) playerWrapper(api).instance = player;
  }

  /** Take the synth away from `api` without destroying it (call before `api.destroy()`). */
  release(api: ApiLike): void {
    if (this.owner?.api === api) {
      this.detachOwner(false);
      return;
    }
    // Never let an api destroy the shared synth, even one that lost it earlier.
    const w = playerWrapper(api);
    if (this.player && w.instance === this.player) w.instance = undefined;
  }

  /** Destroy the synth (another SoundFont, or tests). */
  dispose(): void {
    this.detachOwner(true);
    this.player?.destroy();
    this.player = null;
    this.url = null;
  }

  private detachOwner(notify: boolean): void {
    const o = this.owner;
    if (!o) return;
    this.owner = null;
    this.player?.stop();
    this.player?.resetChannelStates?.();
    const w = playerWrapper(o.api);
    if (w.instance === this.player) w.instance = undefined;
    if (notify) o.onRelease();
  }

  private ensure(url: string, create: () => SynthLike | null): SynthLike | null {
    if (this.player) return this.player;
    const player = create();
    if (!player) return null;
    this.synthsCreated++;
    this.player = player;
    this.url = url;
    const bytes = this.bytes(url);
    player.ready.on(() => {
      void bytes.then((buf) => {
        if (this.player !== player) return;
        this.soundFontLoads++;
        const data = new Uint8Array(buf);
        // Hand the bytes to the worker instead of copying them: the page keeps no copy.
        const worker = workerOf(player);
        if (worker) worker.postMessage({ cmd: "alphaSynth.loadSoundFontBytes", data, append: false }, [buf]);
        else player.loadSoundFont(data, false);
      }, (e: unknown) => this.failed(player, url, e));
    });
    return player;
  }

  /** The SoundFont didn't load: drop the synth (the next attach makes a new one) and tell its owner. */
  private failed(player: SynthLike, url: string, e: unknown): void {
    console.warn(`SoundFont ${url} could not be loaded`, e);
    if (this.player !== player) return;
    const o = this.owner;
    this.owner = null;
    if (o) {
      const w = playerWrapper(o.api);
      if (w.instance === player) w.instance = undefined;
    }
    this.player = null;
    this.url = null;
    player.destroy();
    o?.onError?.(e);
  }
}
