// Audio inspector: waveform overview and spectrogram of a window, with A/B
// playback that keeps the position when switching sources.
import { fetchBytes } from "../api/client";
import { mixdown, peaks, spectrogram } from "../lib/dsp";
import { SizedLru } from "../lib/lru";
import { t } from "../i18n";
import { announce, clear, errorNotice, fmt, h, loading, nextId, onPanelHidden, token } from "../ui/dom";
import { plot, timeAxis, type Plot } from "./canvas";

let ctx: AudioContext | null = null;
export function audioContext(): AudioContext {
  ctx ??= new AudioContext();
  return ctx;
}

/**
 * Decoded audio is large (a few minutes of stereo take about 100 MB), so only the most recently
 * used files are kept for switching back and forth; a player holds on to the ones it plays itself.
 */
const DECODED_BUDGET = 256 * 1024 * 1024;
const cache = new SizedLru<string, AudioBuffer>(DECODED_BUDGET, (b) => b.length * b.numberOfChannels * 4);
/** Fetch and decode a file, reusing a recent decode of it. */
export function decode(url: string): Promise<AudioBuffer> {
  return cache.get(url, () => fetchBytes(url).then((b) => audioContext().decodeAudioData(b)));
}

export interface AudioSource {
  label: string;
  url: string;
}

interface Loaded {
  source: AudioSource;
  buffer: AudioBuffer;
  mono: Float32Array;
  overview: Float32Array;
}

const OVERVIEW = 1600;

export class AudioAB extends HTMLElement {
  private sources: AudioSource[] = [];
  private loaded: (Loaded | null)[] = [];
  private active = 0;
  private node: AudioBufferSourceNode | null = null;
  private startedAt = 0;
  private offset = 0;
  private window = 10; // seconds shown in the spectrogram
  private viewStart = 0;
  private raf = 0;
  private wave!: Plot;
  private spec!: Plot;
  private status!: HTMLElement;
  private playBtn!: HTMLButtonElement;
  private radios!: HTMLElement;
  private specCache: { key: string; img: ImageData } | null = null;

  set data(sources: AudioSource[]) {
    this.sources = sources;
    this.loaded = sources.map(() => null);
    this.active = 0;
    this.render();
  }

  private offHidden: (() => void) | null = null;

  connectedCallback(): void {
    // Another tab chosen: pause, so it doesn't play on under a panel no one sees.
    this.offHidden?.();
    this.offHidden = onPanelHidden(this, () => {
      if (this.node) this.pause();
    });
  }

  disconnectedCallback(): void {
    this.stopPlayback();
    this.offHidden?.();
    this.offHidden = null;
  }

  private get duration(): number {
    return Math.max(0, ...this.loaded.map((l) => l?.buffer.duration ?? 0));
  }

  private render(): void {
    const name = nextId("ab");
    this.playBtn = h("button", { type: "button", class: "primary", onclick: () => this.toggle() }, t("score.play"));
    this.radios = h("div", { class: "row", role: "radiogroup", "aria-label": t("audio.listenTo") },
      this.sources.map((s, i) => h("label", {},
        h("input", { type: "radio", name, value: String(i), checked: i === 0, onchange: () => this.switchTo(i) }),
        `${String.fromCharCode(65 + i)}: ${s.label}`)));
    this.status = h("p", { class: "hint", role: "status" }, t("audio.loading"));
    this.wave = plot("Waveform", 110, (c, w, hh) => this.drawWave(c, w, hh));
    this.spec = plot("Spectrogram", 220, (c, w, hh) => this.drawSpec(c, w, hh));
    this.wave.canvas.addEventListener("click", (e) => {
      const r = this.wave.canvas.getBoundingClientRect();
      this.seek(((e.clientX - r.left) / r.width) * this.duration);
    });
    const nav = h("div", { class: "row" },
      h("button", { type: "button", onclick: () => this.pan(-0.8) }, t("common.earlier")),
      h("button", { type: "button", onclick: () => this.pan(0.8) }, t("common.later")),
      h("button", { type: "button", onclick: () => this.zoom(0.5) }, t("common.zoomIn")),
      h("button", { type: "button", onclick: () => this.zoom(2) }, t("common.zoomOut")),
      h("button", { type: "button", onclick: () => this.seek(this.viewStart) }, t("audio.fromWindow")));
    clear(this,
      h("div", { class: "row" }, this.playBtn, h("button", { type: "button", onclick: () => this.seek(0) }, t("audio.backToStart")), this.radios),
      this.status,
      h("p", { class: "small muted" }, t("audio.hint")),
      this.wave.box,
      h("div", { style: "height:0.5rem" }),
      this.spec.box,
      nav);
    this.sources.forEach((s, i) => this.load(i, s));
  }

  private async load(i: number, s: AudioSource): Promise<void> {
    try {
      const buffer = await decode(s.url);
      const chans = Array.from({ length: buffer.numberOfChannels }, (_, c) => buffer.getChannelData(c));
      const mono = mixdown(chans);
      this.loaded[i] = { source: s, buffer, mono, overview: peaks(mono, OVERVIEW) };
      this.specCache = null;
      this.updateStatus();
      this.wave.redraw();
      this.spec.redraw();
    } catch (e) {
      this.status.replaceWith(errorNotice(e));
    }
  }

  private current(): Loaded | null {
    return this.loaded[this.active] ?? this.loaded.find(Boolean) ?? null;
  }

  private position(): number {
    if (!this.node) return this.offset;
    return this.offset + (audioContext().currentTime - this.startedAt);
  }

  private toggle(): void {
    if (this.node) this.pause();
    else this.play(this.offset);
  }

  private play(at: number): void {
    const l = this.loaded[this.active];
    if (!l) {
      announce(t("audio.stillLoading"));
      return;
    }
    const ac = audioContext();
    void ac.resume();
    this.stopPlayback();
    const node = ac.createBufferSource();
    node.buffer = l.buffer;
    node.connect(ac.destination);
    // Play from the end means play again from the start.
    const start = playFrom(at, l.buffer.duration);
    node.start(0, start);
    node.onended = () => {
      // Played to the end (a pause or a seek stops a node that is no longer this.node).
      if (this.node === node) {
        this.stopPlayback();
        this.offset = 0;
        this.playBtn.textContent = t("score.play");
        this.wave.redraw();
        this.updateStatus();
      }
    };
    this.node = node;
    this.offset = start;
    this.startedAt = ac.currentTime;
    this.playBtn.textContent = t("score.pause");
    const tick = () => {
      this.follow();
      this.wave.redraw();
      this.updateStatus();
      if (this.node) this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  private pause(): void {
    this.offset = this.position();
    this.stopPlayback();
    this.playBtn.textContent = t("score.play");
    this.updateStatus();
  }

  private stopPlayback(): void {
    cancelAnimationFrame(this.raf);
    if (this.node) {
      const n = this.node;
      this.node = null;
      try {
        n.stop();
      } catch {
        /* already stopped */
      }
    }
  }

  private switchTo(i: number): void {
    const wasPlaying = !!this.node;
    const at = this.position();
    this.active = i;
    this.specCache = null;
    if (wasPlaying) this.play(at);
    else this.offset = at;
    this.spec.redraw();
    this.updateStatus();
    announce(t("audio.listening", { which: String.fromCharCode(65 + i), label: this.sources[i].label }));
  }

  private seek(t: number): void {
    const at = Math.max(0, Math.min(this.duration, t));
    if (at < this.viewStart || at > this.viewStart + this.window) this.viewStart = Math.max(0, at - this.window * 0.1);
    this.specCache = null;
    if (this.node) this.play(at);
    else this.offset = at;
    this.wave.redraw();
    this.spec.redraw();
    this.updateStatus();
  }

  private follow(): void {
    const p = this.position();
    if (p > this.viewStart + this.window) {
      this.viewStart = p;
      this.specCache = null;
      this.spec.redraw();
    }
  }

  private pan(f: number): void {
    this.viewStart = Math.max(0, Math.min(Math.max(0, this.duration - this.window), this.viewStart + f * this.window));
    this.specCache = null;
    this.wave.redraw();
    this.spec.redraw();
    this.updateStatus();
  }

  private zoom(f: number): void {
    this.window = Math.max(1, Math.min(120, this.window * f));
    this.specCache = null;
    this.wave.redraw();
    this.spec.redraw();
    this.updateStatus();
  }

  private updateStatus(): void {
    const l = this.current();
    if (!l) return;
    const b = l.buffer;
    this.status.textContent = t("audio.status", { which: String.fromCharCode(65 + this.active), label: l.source.label, dur: fmt.seconds(b.duration), rate: b.sampleRate, ch: b.numberOfChannels, pos: fmt.seconds(this.position()), from: fmt.seconds(this.viewStart), to: fmt.seconds(this.viewStart + this.window) });
    this.wave.setLabel(t("audio.waveform", { label: l.source.label, dur: fmt.seconds(b.duration) }));
    this.spec.setLabel(t("audio.spectrogram", { label: l.source.label, from: fmt.seconds(this.viewStart), to: fmt.seconds(this.viewStart + this.window) }));
  }

  private drawWave(c: CanvasRenderingContext2D, w: number, hh: number): void {
    const dur = this.duration;
    if (!dur) {
      c.fillStyle = token("text-muted");
      c.fillText(t("common.loading"), 8, 16);
      return;
    }
    const mid = (hh - 16) / 2;
    const colours = [token("m1"), token("m2"), token("m3")];
    this.loaded.forEach((l, i) => {
      if (!l) return;
      const frac = l.buffer.duration / dur;
      c.strokeStyle = colours[i % 3];
      c.globalAlpha = i === this.active ? 1 : 0.45;
      c.lineWidth = 1;
      c.beginPath();
      const n = l.overview.length / 2;
      for (let x = 0; x < w * frac; x++) {
        const b = Math.floor((x / (w * frac)) * n);
        c.moveTo(x + 0.5, mid - l.overview[2 * b + 1] * mid);
        c.lineTo(x + 0.5, mid - l.overview[2 * b] * mid + 1);
      }
      c.stroke();
    });
    c.globalAlpha = 1;
    // Visible spectrogram window (outline, not only tint) and the play head.
    const x0 = (this.viewStart / dur) * w;
    const x1 = ((this.viewStart + this.window) / dur) * w;
    c.strokeStyle = token("loop-edge");
    c.lineWidth = 2;
    c.strokeRect(x0, 1, Math.max(2, x1 - x0), hh - 18);
    const px = (this.position() / dur) * w;
    c.fillStyle = token("cursor");
    c.fillRect(px - 1.5, 0, 3, hh - 16);
    timeAxis(c, w, hh - 16, 0, dur, token("text-muted"));
  }

  private drawSpec(c: CanvasRenderingContext2D, w: number, hh: number): void {
    const l = this.current();
    if (!l) return;
    const sr = l.buffer.sampleRate;
    const plotH = hh - 16;
    const key = `${this.active}:${this.viewStart}:${this.window}:${w}:${hh}`;
    if (this.specCache?.key !== key) {
      const start = Math.floor(this.viewStart * sr);
      const end = Math.min(l.mono.length, Math.floor((this.viewStart + this.window) * sr));
      const frames = Math.min(w, 600);
      const s = spectrogram(l.mono, frames, 2048, start, Math.max(start + 2048, end));
      const maxBin = Math.floor((8000 / (sr / 2)) * s.bins);
      const img = c.createImageData(frames, plotH);
      let hi = -Infinity;
      for (const v of s.data) if (v > hi) hi = v;
      const lo = hi - 80;
      for (let x = 0; x < frames; x++) {
        for (let y = 0; y < plotH; y++) {
          const k = Math.floor(((plotH - 1 - y) / plotH) * maxBin);
          const v = Math.max(0, Math.min(1, (s.data[x * s.bins + k] - lo) / (hi - lo)));
          const [r, g, b] = viridis(v);
          const o = (y * frames + x) * 4;
          img.data[o] = r;
          img.data[o + 1] = g;
          img.data[o + 2] = b;
          img.data[o + 3] = 255;
        }
      }
      this.specCache = { key, img };
    }
    const img = this.specCache.img;
    const tmp = document.createElement("canvas");
    tmp.width = img.width;
    tmp.height = img.height;
    tmp.getContext("2d")?.putImageData(img, 0, 0);
    c.imageSmoothingEnabled = false;
    c.drawImage(tmp, 0, 0, w, plotH);
    const p = this.position();
    if (p >= this.viewStart && p <= this.viewStart + this.window) {
      c.fillStyle = "#FFFFFF";
      c.fillRect(((p - this.viewStart) / this.window) * w - 1, 0, 2, plotH);
    }
    c.fillStyle = "#FFFFFF";
    c.font = "11px system-ui, sans-serif";
    c.fillText("8 kHz", 4, 12);
    c.fillText("0", 4, plotH - 4);
    timeAxis(c, w, plotH, this.viewStart, this.viewStart + this.window, token("text-muted"));
  }
}

/** Where playback starts when asked for `at`: from the start once `at` is at (or past) the end. */
export function playFrom(at: number, duration: number): number {
  return at >= duration - 0.05 ? 0 : Math.max(0, at);
}

/** Viridis colour map (perceptually uniform, colour-blind safe), 0..1 -> RGB. */
function viridis(t: number): [number, number, number] {
  const stops: [number, number, number][] = [
    [68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142],
    [31, 158, 137], [53, 183, 121], [109, 205, 89], [180, 222, 44], [253, 231, 37],
  ];
  const x = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

customElements.define("bs-audio-ab", AudioAB);

export function audioPanel(sources: AudioSource[]): HTMLElement {
  if (!sources.length) return h("p", {}, t("audio.none"));
  const el = h("bs-audio-ab", {}) as AudioAB;
  el.append(loading(t("audio.loading")));
  el.data = sources;
  return el;
}

declare global {
  interface HTMLElementTagNameMap {
    "bs-audio-ab": AudioAB;
  }
}
