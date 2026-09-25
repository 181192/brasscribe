// <bs-score>: MusicXML score with playback (alphaTab), loop, speed, zoom,
// part selection, mute/solo and keyboard navigation by bar and part.
import type * as AT from "@coderline/alphatab";
import { parseMusicXml, type XmlScore } from "../lib/musicxml";
import { pitchName } from "../lib/validate";
import { announce, clear, h, nextId, prefersReducedMotion, token } from "../ui/dom";

declare const alphaTab: typeof AT;

interface BarSpan {
  index: number;
  number: number;
  start: number;
  end: number;
}

const ASSETS = new URL("assets/alphatab/", document.baseURI).href;

export class ScoreElement extends HTMLElement {
  api: AT.AlphaTabApi | null = null;
  xml: XmlScore | null = null;
  bars: BarSpan[] = [];
  current = 0; // bar index
  partIndex = 0; // track index for navigation, mute/solo and announcements
  loop: { from: number; to: number } | null = null;
  playing = false;
  ready = false;
  rendered = false;
  /** Last player position (ticks and ms), for tests and the status line. */
  position = { tick: 0, time: 0, endTime: 0 };
  scale = 1;
  private view!: HTMLDivElement;
  private statusEl!: HTMLElement;
  private playBtn!: HTMLButtonElement;
  private barInput!: HTMLInputElement;
  private loopFrom!: HTMLInputElement;
  private loopTo!: HTMLInputElement;
  private loopBtn!: HTMLButtonElement;
  private speed!: HTMLInputElement;
  private speedOut!: HTMLOutputElement;
  private zoomOut!: HTMLOutputElement;
  private partSelect!: HTMLSelectElement;
  private mixer!: HTMLElement;
  private uncertainCount = 0;
  private barPlay: number | null = null; // bar index while "play bar" runs
  private barPending: number | null = null; // set by playBar until the player reports playing

  connectedCallback(): void {
    if (this.view) return;
    const id = nextId("score");
    this.classList.add("score-shell");
    this.playBtn = h("button", { type: "button", class: "primary", "aria-keyshortcuts": "Space", onclick: () => this.togglePlay() }, "Play");
    this.barInput = h("input", { type: "number", min: 1, value: 1, id: `${id}-bar`, inputmode: "numeric" });
    this.loopFrom = h("input", { type: "number", min: 1, value: 1, id: `${id}-lf`, inputmode: "numeric" });
    this.loopTo = h("input", { type: "number", min: 1, value: 4, id: `${id}-lt`, inputmode: "numeric" });
    this.loopBtn = h("button", { type: "button", "aria-pressed": "false", "aria-keyshortcuts": "L", onclick: () => this.toggleLoop() }, "Loop");
    this.speed = h("input", { type: "range", min: 25, max: 200, step: 5, value: 100, id: `${id}-speed`, oninput: () => this.setSpeed(Number(this.speed.value) / 100) });
    this.speedOut = h("output", { for: `${id}-speed` }, "100%");
    this.zoomOut = h("output", {}, "100%");
    this.partSelect = h("select", { id: `${id}-part`, onchange: () => this.showPart(this.partSelect.value) });
    this.mixer = h("div", { class: "mixer" });
    this.view = h("div", {
      class: "score-view", tabindex: 0, role: "application", "aria-roledescription": "score",
      "aria-label": "Score", "aria-describedby": `${id}-help`,
    });
    this.view.addEventListener("keydown", (e) => this.onKey(e));
    this.statusEl = h("p", { class: "score-status", "aria-live": "off" }, "No score loaded.");
    const transport = h("div", { class: "transport", role: "group", "aria-label": "Player" },
      h("div", { class: "group" },
        this.playBtn,
        h("button", { type: "button", onclick: () => this.stop() }, "Stop"),
        h("button", { type: "button", "aria-keyshortcuts": "P", onclick: () => this.playBar() }, "Play bar")),
      h("div", { class: "group" },
        h("button", { type: "button", "aria-label": "Previous bar", "aria-keyshortcuts": "Alt+ArrowUp", onclick: () => this.goBar(this.current - 1) }, "◀"),
        h("label", { for: `${id}-bar` }, "Bar"), this.barInput,
        h("button", { type: "button", onclick: () => this.goBar(Number(this.barInput.value) - 1, true) }, "Go"),
        h("button", { type: "button", "aria-label": "Next bar", "aria-keyshortcuts": "Alt+ArrowDown", onclick: () => this.goBar(this.current + 1) }, "▶")),
      h("div", { class: "group", role: "group", "aria-label": "Loop" },
        h("label", { for: `${id}-lf` }, "Loop from"), this.loopFrom,
        h("label", { for: `${id}-lt` }, "to"), this.loopTo, this.loopBtn),
      h("div", { class: "group" },
        h("label", { for: `${id}-speed` }, "Speed"), this.speed, this.speedOut,
        h("button", { type: "button", onclick: () => this.setSpeed(1) }, "Reset")),
      h("div", { class: "group", role: "group", "aria-label": "Zoom" },
        h("button", { type: "button", "aria-label": "Zoom out", onclick: () => this.zoom(this.scale - 0.1) }, "−"),
        this.zoomOut,
        h("button", { type: "button", "aria-label": "Zoom in", onclick: () => this.zoom(this.scale + 0.1) }, "+")),
      h("div", { class: "group" }, h("label", { for: `${id}-part` }, "Show"), this.partSelect));
    const help = h("p", { id: `${id}-help`, class: "visually-hidden" },
      "Space plays or pauses. Alt plus arrow up or down moves by bar, Control plus Shift plus arrow up or down changes part. " +
      "P plays the current bar. Left and right bracket set the loop, L turns it on or off. Minus and equals change speed. R reads the bar.");
    this.append(transport, this.view, this.statusEl, help,
      h("details", { class: "card" }, h("summary", {}, "Parts: mute and solo"), this.mixer));
  }

  disconnectedCallback(): void {
    this.api?.destroy();
    this.api = null;
  }

  /** Load a MusicXML document (text) and render it. Resolves when the first render finishes. */
  async load(xml: string | ArrayBuffer, label = "Score"): Promise<void> {
    const text = typeof xml === "string" ? xml : new TextDecoder().decode(xml);
    try {
      this.xml = parseMusicXml(text);
    } catch {
      this.xml = null;
    }
    this.view.setAttribute("aria-label", `Score: ${this.xml?.title || label}`);
    this.api?.destroy();
    clear(this.view);
    this.ready = false;
    this.rendered = false;
    const surface = h("div", {});
    this.view.append(surface);
    const settings: AT.json.SettingsJson = {
      core: { fontDirectory: `${ASSETS}font/`, logLevel: "warning" },
      display: { layoutMode: "page", scale: this.scale, staveProfile: "score" },
      player: {
        playerMode: "enabledSynthesizer",
        soundFont: `${ASSETS}soundfont/sonivox.sf2`,
        scrollElement: this.view,
        enableCursor: true,
        enableAnimatedBeatCursor: !prefersReducedMotion(),
        enableElementHighlighting: true,
        scrollMode: "continuous",
        nativeBrowserSmoothScroll: !prefersReducedMotion(),
      },
    } as unknown as AT.json.SettingsJson;
    const api = new alphaTab.AlphaTabApi(surface, settings);
    this.api = api;
    const rendered = new Promise<void>((resolve, reject) => {
      api.postRenderFinished.on(() => {
        this.rendered = true;
        this.dispatchEvent(new CustomEvent("rendered"));
        resolve();
      });
      api.error.on((e: Error) => reject(e));
    });
    api.scoreLoaded.on((score: AT.model.Score) => this.onScore(score));
    api.playerReady.on(() => {
      this.ready = true;
      this.dispatchEvent(new CustomEvent("playerready"));
      this.updateStatus();
    });
    api.playerStateChanged.on((e: { state: number }) => {
      this.playing = e.state === 1;
      if (this.playing && this.barPending !== null) {
        this.barPlay = this.barPending;
        this.barPending = null;
      } else if (!this.playing && this.barPlay !== null && this.api) {
        // Back to the start of the bar that was played, with the range cleared.
        const b = this.barPlay;
        this.barPlay = null;
        this.api.playbackRange = null;
        this.goBar(b, false);
      }
      this.playBtn.textContent = this.playing ? "Pause" : "Play";
      this.updateStatus();
    });
    api.playerPositionChanged.on((e: { currentTick: number; currentTime: number; endTime: number; isSeek: boolean }) => {
      this.position = { tick: e.currentTick, time: e.currentTime, endTime: e.endTime };
      const bar = this.barAt(e.currentTick);
      // Seeks come from goBar, which already set the bar; late seek events must not undo a newer move.
      if (!e.isSeek && bar !== this.current) {
        this.current = bar;
        this.barInput.value = String(bar + 1);
      }
      this.updateStatus();
    });
    api.load(new TextEncoder().encode(text), this.xml ? this.xml.parts.map((_, i) => i) : undefined);
    await rendered;
  }

  private onScore(score: AT.model.Score): void {
    this.bars = score.masterBars.map((mb, index) => ({
      index, number: index + 1, start: mb.start, end: mb.start + mb.calculateDuration(),
    }));
    this.barInput.max = String(this.bars.length);
    this.loopFrom.max = this.loopTo.max = String(this.bars.length);
    this.uncertainCount = this.markUncertain(score);
    const firstWithNotes = this.xml?.parts.findIndex((p) => p.notes.length > 0) ?? -1;
    this.partIndex = firstWithNotes >= 0 && firstWithNotes < score.tracks.length ? firstWithNotes : 0;
    clear(this.partSelect,
      h("option", { value: "all" }, "All parts"),
      score.tracks.map((t, i) => h("option", { value: String(i) }, t.name || `Part ${i + 1}`)));
    clear(this.mixer, score.tracks.map((t, i) => {
      const name = t.name || `Part ${i + 1}`;
      const mute = h("input", { type: "checkbox", "aria-label": `Mute ${name}`, onchange: () => this.api?.changeTrackMute([t], mute.checked) });
      const solo = h("input", { type: "checkbox", "aria-label": `Solo ${name}`, onchange: () => this.api?.changeTrackSolo([t], solo.checked) });
      return h("div", { class: `part${i === this.partIndex ? " current" : ""}`, "data-track": i },
        h("span", { class: "part-name" }, t.name || `Part ${i + 1}`),
        h("span", { class: "row" }, h("label", {}, mute, "Mute"), h("label", {}, solo, "Solo")));
    }));
    this.current = 0;
    this.updateStatus();
  }

  /**
   * Notes the engine coloured in the MusicXML are uncertain. alphaTab keeps no
   * MusicXML colours, so recolour them with the `uncertain` token and add
   * parentheses (shape as well as colour; WCAG 1.4.1).
   */
  private markUncertain(score: AT.model.Score): number {
    if (!this.xml) return 0;
    const colour = alphaTab.model.Color.fromJson(token("uncertain"));
    let marked = 0;
    score.tracks.forEach((track, ti) => {
      const part = this.xml!.parts[ti];
      if (!part || !part.notes.some((n) => n.color)) return;
      const byBar = new Map<number, boolean[]>();
      for (const n of part.notes) (byBar.get(n.barIndex) ?? byBar.set(n.barIndex, []).get(n.barIndex)!).push(!!n.color);
      const staff = track.staves[0];
      staff?.bars.forEach((bar, bi) => {
        const flags = byBar.get(bi);
        if (!flags?.some(Boolean)) return;
        const notes = bar.voices.flatMap((v) => v.beats.flatMap((b) => b.notes));
        if (notes.length !== flags.length) return; // cannot align this bar safely
        notes.forEach((note, i) => {
          if (!flags[i]) return;
          note.isGhost = true;
          const style = new alphaTab.model.NoteStyle();
          style.colors.set(alphaTab.model.NoteSubElement.StandardNotationNoteHead, colour);
          note.style = style;
          marked++;
        });
      });
    });
    return marked;
  }

  private barAt(tick: number): number {
    let lo = 0;
    let hi = this.bars.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.bars[mid].start <= tick) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  focusScore(): void {
    this.view.focus();
  }

  togglePlay(): void {
    if (!this.api) return;
    if (!this.ready) {
      announce("The player is still loading the sound font.");
      return;
    }
    this.api.playPause();
  }

  stop(): void {
    this.api?.stop();
  }

  goBar(index: number, announceIt = true): void {
    if (!this.api || !this.bars.length) return;
    const i = Math.max(0, Math.min(this.bars.length - 1, index));
    this.current = i;
    this.barInput.value = String(i + 1);
    this.api.tickPosition = this.bars[i].start;
    if (announceIt) announce(this.describeBar(i));
    this.updateStatus();
  }

  /** Play the current bar once. */
  playBar(index = this.current): void {
    if (!this.api || !this.bars.length) return;
    if (!this.ready) {
      announce("The player is still loading the sound font.");
      return;
    }
    const b = this.bars[Math.max(0, Math.min(this.bars.length - 1, index))];
    this.api.stop();
    this.api.isLooping = false;
    this.api.playbackRange = { startTick: b.start, endTick: b.end } as AT.synth.PlaybackRange;
    this.api.tickPosition = b.start;
    this.loop = null;
    this.loopBtn.setAttribute("aria-pressed", "false");
    this.barPlay = null;
    this.barPending = b.index;
    this.api.play();
  }

  setLoop(from: number, to: number, on = true): void {
    if (!this.api || !this.bars.length) return;
    const a = Math.max(0, Math.min(from, to, this.bars.length - 1));
    const b = Math.min(this.bars.length - 1, Math.max(from, to));
    this.loopFrom.value = String(a + 1);
    this.loopTo.value = String(b + 1);
    if (on) {
      this.loop = { from: a, to: b };
      this.api.playbackRange = { startTick: this.bars[a].start, endTick: this.bars[b].end } as AT.synth.PlaybackRange;
      this.api.isLooping = true;
      this.api.tickPosition = this.bars[a].start;
      this.highlightLoop(a, b);
      announce(`Loop set, bars ${a + 1} to ${b + 1}`);
    } else {
      this.loop = null;
      this.api.playbackRange = null;
      this.api.isLooping = false;
      announce("Loop off");
    }
    this.loopBtn.setAttribute("aria-pressed", String(on));
    this.loopBtn.textContent = on ? `Loop ${a + 1}–${b + 1}` : "Loop";
    this.updateStatus();
  }

  private highlightLoop(a: number, b: number): void {
    const track = this.api?.tracks?.[0];
    const bars = track?.staves[0]?.bars;
    const first = bars?.[a]?.voices[0]?.beats[0];
    const lastBeats = bars?.[b]?.voices[0]?.beats;
    const last = lastBeats?.[lastBeats.length - 1];
    if (first && last) {
      try {
        this.api!.highlightPlaybackRange(first, last);
      } catch {
        /* the loop text in the transport is the primary indicator */
      }
    }
  }

  toggleLoop(): void {
    this.setLoop(Number(this.loopFrom.value) - 1, Number(this.loopTo.value) - 1, !this.loop);
  }

  setSpeed(v: number): void {
    const s = Math.max(0.25, Math.min(2, Math.round(v * 20) / 20));
    if (this.api) this.api.playbackSpeed = s;
    this.speed.value = String(Math.round(s * 100));
    this.speedOut.textContent = `${Math.round(s * 100)}%`;
    this.updateStatus();
  }

  zoom(v: number): void {
    this.scale = Math.max(0.5, Math.min(4, Math.round(v * 10) / 10));
    this.zoomOut.textContent = `${Math.round(this.scale * 100)}%`;
    if (this.api) {
      this.api.settings.display.scale = this.scale;
      this.api.updateSettings();
      this.api.render();
    }
  }

  showPart(value: string): void {
    if (!this.api?.score) return;
    const tracks = value === "all" ? this.api.score.tracks : [this.api.score.tracks[Number(value)]];
    if (value !== "all") this.setPart(Number(value), false);
    this.api.renderTracks(tracks);
  }

  setPart(i: number, announceIt = true): void {
    const n = this.api?.score?.tracks.length ?? 0;
    if (!n) return;
    this.partIndex = (i + n) % n;
    for (const el of Array.from(this.mixer.children)) el.classList.toggle("current", Number((el as HTMLElement).dataset.track) === this.partIndex);
    if (announceIt) announce(`Part: ${this.api!.score!.tracks[this.partIndex].name}`);
    this.updateStatus();
  }

  toggleMute(solo: boolean): void {
    const row = this.mixer.children[this.partIndex];
    const box = row?.querySelectorAll("input")[solo ? 1 : 0] as HTMLInputElement | undefined;
    if (!box) return;
    box.checked = !box.checked;
    box.dispatchEvent(new Event("change"));
    announce(`${this.api?.score?.tracks[this.partIndex].name}: ${solo ? "solo" : "mute"} ${box.checked ? "on" : "off"}`);
  }

  /** A spoken summary of a bar in the current part: written pitches with uncertainty. */
  describeBar(i: number): string {
    const name = this.api?.score?.tracks[this.partIndex]?.name ?? "";
    const part = this.xml?.parts[this.partIndex];
    const notes = part?.notes.filter((n) => n.barIndex === i) ?? [];
    const head = `Bar ${i + 1} of ${this.bars.length}, ${name}`;
    if (!part) return head;
    if (!notes.length) return `${head}: rest`;
    const words = notes.slice(0, 12).map((n) => `beat ${Math.floor(n.beat)}: ${pitchName(n.written)}${n.color ? ", uncertain" : ""}`);
    return `${head}: ${words.join("; ")}${notes.length > 12 ? `; and ${notes.length - 12} more` : ""}`;
  }

  private onKey(e: KeyboardEvent): void {
    const k = e.key;
    const handled = () => {
      e.preventDefault();
      e.stopPropagation();
    };
    if (k === " " && !e.ctrlKey && !e.metaKey) {
      handled();
      this.togglePlay();
    } else if ((e.altKey || e.ctrlKey) && !e.shiftKey && (k === "ArrowDown" || k === "ArrowUp")) {
      handled();
      this.goBar(this.current + (k === "ArrowDown" ? 1 : -1));
    } else if (e.ctrlKey && e.shiftKey && (k === "ArrowDown" || k === "ArrowUp")) {
      handled();
      this.setPart(this.partIndex + (k === "ArrowDown" ? 1 : -1));
    } else if (k === "Home" || k === "End") {
      handled();
      this.goBar(k === "Home" ? 0 : this.bars.length - 1);
    } else if (e.ctrlKey || e.metaKey || e.altKey) {
      if ((e.ctrlKey || e.metaKey) && (k === "=" || k === "+" || k === "-" || k === "0")) {
        handled();
        this.zoom(k === "0" ? 1 : this.scale + (k === "-" ? -0.1 : 0.1));
      }
    } else if (k === "p" || k === "P") {
      handled();
      this.playBar();
    } else if (k === "[") {
      handled();
      this.loopFrom.value = String(this.current + 1);
      if (Number(this.loopTo.value) < this.current + 1) this.loopTo.value = String(this.current + 1);
      announce(`Loop start: bar ${this.current + 1}`);
      if (this.loop) this.setLoop(Number(this.loopFrom.value) - 1, Number(this.loopTo.value) - 1);
    } else if (k === "]") {
      handled();
      this.loopTo.value = String(this.current + 1);
      if (Number(this.loopFrom.value) > this.current + 1) this.loopFrom.value = String(this.current + 1);
      announce(`Loop end: bar ${this.current + 1}`);
      if (this.loop) this.setLoop(Number(this.loopFrom.value) - 1, Number(this.loopTo.value) - 1);
    } else if (k === "l" || k === "L") {
      handled();
      this.toggleLoop();
    } else if (k === "-" || k === "=" || k === "+" || k === "0") {
      handled();
      this.setSpeed(k === "0" ? 1 : (this.api?.playbackSpeed ?? 1) + (k === "-" ? -0.05 : 0.05));
      announce(`Speed ${this.speedOut.textContent}`);
    } else if (k === "r" || k === "R" || k === "w" || k === "W") {
      handled();
      announce(this.describeBar(this.current));
    } else if (k === "m" || k === "M" || k === "s" || k === "S") {
      handled();
      this.toggleMute(k === "s" || k === "S");
    } else if (k === "ArrowRight" || k === "ArrowLeft") {
      handled();
      if (!this.api || !this.bars.length) return;
      const quarter = 960;
      const t = Math.max(0, this.api.tickPosition + (k === "ArrowRight" ? quarter : -quarter));
      this.api.tickPosition = t;
      this.current = this.barAt(t);
      this.barInput.value = String(this.current + 1);
      this.updateStatus();
    } else if (k === "Escape") {
      handled();
      this.view.blur();
    }
  }

  private updateStatus(): void {
    const mmss = (ms: number) => {
      const s = Math.max(0, Math.round(ms / 1000));
      return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };
    const parts = [
      `Bar ${this.current + 1} of ${this.bars.length || "–"}`,
      `${mmss(this.position.time)} / ${mmss(this.position.endTime)}`,
      this.playing ? "Playing" : this.ready ? "Stopped" : "Loading player…",
      `Speed ${this.speedOut?.textContent ?? "100%"}`,
      this.loop ? `Loop ${this.loop.from + 1}–${this.loop.to + 1}` : "",
      this.api?.score ? `Part: ${this.api.score.tracks[this.partIndex]?.name ?? ""}` : "",
      this.uncertainCount ? `${this.uncertainCount} uncertain notes shown in parentheses` : "",
    ];
    this.statusEl.textContent = parts.filter(Boolean).join(" · ");
  }
}

customElements.define("bs-score", ScoreElement);

declare global {
  interface HTMLElementTagNameMap {
    "bs-score": ScoreElement;
  }
}
