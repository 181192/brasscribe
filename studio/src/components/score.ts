// <bs-score>: MusicXML score with playback (alphaTab), loop, speed, zoom,
// part selection, mute/solo, and a talking score (spec in
// docs/accessibility/talking-score-spec.md) driven from the keyboard.
import type * as AT from "@coderline/alphatab";
import { lang, t } from "../i18n";
import { parseMusicXml, type XmlNote, type XmlScore } from "../lib/musicxml";
import { Navigator, type Stop } from "../lib/navigator";
import { MASTER_VOLUME, PartSoundResolver, RELEASE_TAIL_S, playbackChannels, type Mapping, type TrackSound } from "../lib/partsound";
import type { PitchMode, Verbosity } from "../lib/talking";
import { buildTalkingScore, partNameNb, type TalkingScore } from "../lib/talkingxml";
import { announce, clear, h, menu, nextId, prefersReducedMotion } from "../ui/dom";
import { icon } from "../ui/icons";

declare const alphaTab: typeof AT;

interface BarSpan {
  index: number;
  number: number;
  start: number;
  end: number;
}

/** How a note is drawn beyond its default: colour and notehead shape. */
export interface NoteMark {
  colour: string;
  head?: "x" | "diamond" | "triangle" | "square" | "paren";
}

const ASSETS = new URL("assets/alphatab/", document.baseURI).href;
const BAND = new URL("assets/band/", document.baseURI).href;

/**
 * The band sounds (one preset per part, built by sounds/band.py) and their part map, copied into
 * the assets by build.mjs when the checkout has them. Null when they are missing: then alphaTab's
 * General MIDI set plays and the status line says so.
 */
let bandSounds: Promise<PartSoundResolver | null> | null = null;
function loadBandSounds(): Promise<PartSoundResolver | null> {
  const json = (f: string) => fetch(`${BAND}${f}`).then((r) => (r.ok ? r.json() : null));
  bandSounds ??= Promise.all([json("mapping.json"), json("band.json")])
    .then(([m, info]: [Mapping | null, { singleVoice?: boolean } | null]) =>
      (m ? new PartSoundResolver(m, info?.singleVoice ?? false) : null))
    .catch(() => null)
    .then((r) => {
      if (!r) console.warn(`Band sounds not found under ${BAND}: playing alphaTab's General MIDI sounds instead.`);
      return r;
    });
  return bandSounds;
}

/**
 * A design token as a concrete colour. Tokens can be system colours (forced
 * colours) or use var(), so the value is resolved through a probe element.
 */
export function tokenColour(name: string): string {
  const probe = document.createElement("span");
  probe.style.color = `var(--bc-${name})`;
  probe.style.display = "none";
  document.body.append(probe);
  const c = getComputedStyle(probe).color;
  probe.remove();
  const m = c.match(/\d+(\.\d+)?/g);
  if (!m || m.length < 3) return "#000000";
  return `#${m.slice(0, 3).map((x) => Math.round(Number(x)).toString(16).padStart(2, "0")).join("")}`;
}

/** Label text inside an icon button, so the label can change without losing the icon. */
function labelled(name: string, text: string): [SVGSVGElement, HTMLSpanElement] {
  return [icon(name), h("span", { class: "label" }, text)];
}

export class ScoreElement extends HTMLElement {
  api: AT.AlphaTabApi | null = null;
  xml: XmlScore | null = null;
  talking: TalkingScore | null = null;
  nav: Navigator | null = null;
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
  /** Render only these tracks (default: all). */
  tracks: number[] | null = null;
  /** Extra marks per note (track index, note index in the MusicXML part). */
  decorate: ((track: number, note: number, n: XmlNote) => NoteMark | null) | null = null;
  /** Last talking-score announcement (also shown in the panel). */
  lastAnnouncement = "";
  private view!: HTMLDivElement;
  private statusEl!: HTMLElement;
  /** Band sounds, or null when they are missing (undefined before the first load). */
  private band: PartSoundResolver | null | undefined;
  private trackSounds: (TrackSound | null)[] = [];
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
  private talkPanel!: HTMLDetailsElement;
  private talkNow!: HTMLElement;
  private talkText!: HTMLElement;
  private pitchSel!: HTMLSelectElement;
  private verbSel!: HTMLSelectElement;
  private uncertainCount = 0;
  private legend!: HTMLElement;
  private marks: HTMLDivElement | null = null;
  private bands: HTMLDivElement | null = null;
  private themeWatch: (() => void) | null = null;
  private barPlay: number | null = null; // bar index while "play bar" runs
  private barPending: number | null = null; // set by playBar until the player reports playing

  connectedCallback(): void {
    if (this.view) return;
    const id = nextId("score");
    this.classList.add("score-shell");
    // One primary per screen: pages that show two scores pass data-play="secondary".
    this.playBtn = h("button", { type: "button", class: this.dataset.play === "secondary" ? null : "primary", "aria-keyshortcuts": "Space", onclick: () => this.togglePlay() }, ...labelled("play", t("score.play")));
    this.barInput = h("input", { type: "number", min: 1, value: 1, id: `${id}-bar`, inputmode: "numeric" });
    this.loopFrom = h("input", { type: "number", min: 1, value: 1, id: `${id}-lf`, inputmode: "numeric" });
    this.loopTo = h("input", { type: "number", min: 1, value: 4, id: `${id}-lt`, inputmode: "numeric" });
    this.loopBtn = h("button", { type: "button", "aria-keyshortcuts": "L", onclick: () => this.toggleLoop() }, ...labelled("loop", t("score.loop")));
    this.speed = h("input", { type: "range", min: 25, max: 200, step: 5, value: 100, id: `${id}-speed`, oninput: () => this.setSpeed(Number(this.speed.value) / 100) });
    this.speedOut = h("output", { for: `${id}-speed` }, "100%");
    this.zoomOut = h("output", {}, "100%");
    this.partSelect = h("select", { id: `${id}-part`, onchange: () => this.showPart(this.partSelect.value) });
    this.mixer = h("div", { class: "mixer" });
    this.view = h("div", {
      class: "score-view", tabindex: 0, role: "application", "aria-roledescription": t("score.roledescription"),
      "aria-label": t("score.label", { title: "" }), "aria-describedby": `${id}-help`,
    });
    this.view.addEventListener("keydown", (e) => this.onKey(e));
    this.statusEl = h("p", { class: "score-status", "aria-live": "off" }, t("score.none"));
    // Enter (or leaving the field) in "Bar" jumps there.
    this.barInput.addEventListener("change", () => this.goBar(Number(this.barInput.value) - 1, true));
    // Four groups stay visible (Play, Position, Repeat, View); the rest is under "More".
    const transport = h("div", { class: "transport", role: "group", "aria-label": t("score.player") },
      h("div", { class: "group", role: "group", "aria-label": t("score.groupPlay") },
        this.playBtn,
        h("button", { type: "button", onclick: () => this.stop() }, ...labelled("stop", t("score.stop")))),
      h("div", { class: "group", role: "group", "aria-label": t("score.groupPosition") },
        h("button", { type: "button", class: "icon-only", "aria-label": t("score.prevBar"), "aria-keyshortcuts": "Alt+ArrowUp", onclick: () => this.goBar(this.current - 1) }, icon("previous-bar")),
        h("label", { for: `${id}-bar` }, t("score.bar")), this.barInput,
        h("button", { type: "button", class: "icon-only", "aria-label": t("score.nextBar"), "aria-keyshortcuts": "Alt+ArrowDown", onclick: () => this.goBar(this.current + 1) }, icon("next-bar"))),
      h("div", { class: "group", role: "group", "aria-label": t("score.loop") },
        h("label", { for: `${id}-lf` }, t("score.loopFrom")), this.loopFrom,
        h("label", { for: `${id}-lt` }, t("score.loopTo")), this.loopTo, this.loopBtn),
      h("div", { class: "group", role: "group", "aria-label": t("score.groupView") }, h("label", { for: `${id}-part` }, t("score.show")), this.partSelect),
      menu(t("score.more"), [
        h("button", { type: "button", "aria-keyshortcuts": "P", onclick: () => this.playBar() }, ...labelled("listen-bar", t("score.playBar"))),
        h("div", { class: "group", role: "group", "aria-label": t("score.speed") },
          h("label", { for: `${id}-speed`, class: "group-label" }, t("score.speed")), this.speed, this.speedOut,
          h("button", { type: "button", class: "ghost", onclick: () => this.setSpeed(1) }, t("score.reset"))),
        h("div", { class: "group", role: "group", "aria-label": t("score.zoom") },
          h("span", { class: "group-label", "aria-hidden": "true" }, t("score.zoom")),
          h("button", { type: "button", class: "icon-only", "aria-label": t("common.zoomOut"), onclick: () => this.zoom(this.scale - 0.1) }, icon("zoom-out")),
          this.zoomOut,
          h("button", { type: "button", class: "icon-only", "aria-label": t("common.zoomIn"), onclick: () => this.zoom(this.scale + 0.1) }, icon("zoom-in"))),
      ]));
    const help = h("p", { id: `${id}-help`, class: "visually-hidden" }, t("score.help"));

    // Talking score panel.
    this.pitchSel = h("select", { id: `${id}-pm`, onchange: () => this.setPitchMode(this.pitchSel.value as PitchMode) },
      h("option", { value: "written" }, t("score.written")), h("option", { value: "concert" }, t("score.concert")));
    this.verbSel = h("select", { id: `${id}-vb`, onchange: () => { if (this.nav) this.nav.settings = { ...this.nav.settings, verbosity: this.verbSel.value as Verbosity }; } },
      h("option", { value: "brief" }, t("score.brief")), h("option", { value: "standard", selected: true }, t("score.standard")), h("option", { value: "full" }, t("score.full")));
    this.talkNow = h("p", { class: "talk-now", id: `${id}-now` });
    this.talkText = h("div", { class: "talk-text", tabindex: 0, role: "region", "aria-label": t("score.talking") });
    this.talkPanel = h("details", { class: "card talking" },
      h("summary", {}, icon("talking-score"), " ", t("score.talking")),
      h("p", { class: "hint" }, t("score.talkingHint")),
      h("div", { class: "row" },
        h("label", { for: `${id}-pm` }, t("score.pitchMode")), this.pitchSel,
        h("label", { for: `${id}-vb` }, t("score.verbosity")), this.verbSel),
      this.talkNow, this.talkText);
    this.talkPanel.addEventListener("toggle", () => {
      if (this.talkPanel.open) this.renderTalkingText();
    });
    this.legend = h("p", { class: "score-legend" });
    this.append(transport, this.view, this.statusEl, this.legend, help, this.talkPanel,
      h("details", { class: "card" }, h("summary", {}, icon("parts"), " ", t("score.mixer")), this.mixer));
  }

  disconnectedCallback(): void {
    this.api?.destroy();
    this.api = null;
    this.themeWatch?.();
    this.themeWatch = null;
  }

  /** alphaTab colours from the design tokens (ink, staff), so the notation follows the theme. */
  private resources(): Record<string, string> {
    const ink = tokenColour("ink");
    const staff = tokenColour("staff");
    const muted = tokenColour("text-muted");
    return { mainGlyphColor: ink, secondaryGlyphColor: ink, scoreInfoColor: tokenColour("text"), staffLineColor: staff, barSeparatorColor: staff, barNumberColor: muted };
  }

  /** Re-colour the notation when the theme changes (dark mode, more contrast, forced colours). */
  private watchTheme(): void {
    if (this.themeWatch) return;
    const queries = ["(prefers-color-scheme: dark)", "(prefers-contrast: more)", "(forced-colors: active)"].map((q) => matchMedia(q));
    const onChange = () => {
      if (!this.api?.score) return;
      Object.assign(this.api.settings.display.resources, Object.fromEntries(Object.entries(this.resources()).map(([k, v]) => [k, alphaTab.model.Color.fromJson(v)])));
      this.markNotes(this.api.score);
      this.api.updateSettings();
      this.api.render();
    };
    for (const q of queries) q.addEventListener("change", onChange);
    this.themeWatch = () => queries.forEach((q) => q.removeEventListener("change", onChange));
  }

  /** Load a MusicXML document (text) and render it. Resolves when the first render finishes. */
  async load(xml: string | ArrayBuffer, label = "Score"): Promise<void> {
    // Compressed MusicXML (.mxl) is a zip: alphaTab reads it; the text-level checks are skipped.
    const bytes = typeof xml === "string" ? new TextEncoder().encode(xml) : new Uint8Array(xml);
    const zipped = bytes[0] === 0x50 && bytes[1] === 0x4b;
    const text = zipped ? "" : typeof xml === "string" ? xml : new TextDecoder().decode(xml);
    try {
      this.xml = zipped ? null : parseMusicXml(text);
      this.talking = zipped ? null : buildTalkingScore(text);
    } catch {
      this.xml = null;
      this.talking = null;
    }
    this.nav = this.talking ? new Navigator(this.talking, { verbosity: this.verbSel.value as Verbosity, pitch_mode: this.pitchSel.value as PitchMode }, lang()) : null;
    this.view.setAttribute("aria-label", t("score.label", { title: this.xml?.title || label }));
    this.api?.destroy();
    clear(this.view);
    this.ready = false;
    this.rendered = false;
    const surface = h("div", {});
    this.marks = h("div", { class: "score-marks", "aria-hidden": "true" });
    this.bands = h("div", { class: "score-bands", "aria-hidden": "true" });
    // alphaTab owns its container's attributes, so the stacking wrapper is a separate element.
    this.view.append(this.bands, h("div", { class: "score-surface" }, surface), this.marks);
    this.watchTheme();
    const band = await loadBandSounds();
    this.band = band;
    const settings: AT.json.SettingsJson = {
      core: { fontDirectory: `${ASSETS}font/`, logLevel: "warning", includeNoteBounds: true, enableLazyLoading: false },
      display: { layoutMode: "page", scale: this.scale, staveProfile: "score", resources: this.resources() },
      player: {
        playerMode: "enabledSynthesizer",
        soundFont: band ? `${BAND}brasscribe-band.sf2` : `${ASSETS}soundfont/sonivox.sf2`,
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
    api.masterVolume = MASTER_VOLUME;
    const rendered = new Promise<void>((resolve, reject) => {
      api.postRenderFinished.on(() => {
        this.drawMarks();
        this.rendered = true;
        this.dispatchEvent(new CustomEvent("rendered"));
        resolve();
      });
      api.error.on((e: Error) => reject(e));
    });
    api.scoreLoaded.on((score: AT.model.Score) => {
      this.applyBandSounds(score);
      this.onScore(score);
    });
    api.midiLoad.on((midi: AT.midi.MidiFile) => addReleaseTail(midi));
    api.midiLoaded.on(() => this.applyTrackGains());
    api.playerReady.on(() => {
      this.applyTrackGains();
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
      this.playBtn.replaceChildren(...labelled(this.playing ? "pause" : "play", this.playing ? t("score.pause") : t("score.play")));
      this.updateStatus();
    });
    api.playerPositionChanged.on((e: { currentTick: number; currentTime: number; endTime: number; isSeek: boolean }) => {
      this.position = { tick: e.currentTick, time: e.currentTime, endTime: e.endTime };
      const bar = this.barAt(e.currentTick);
      // Seeks come from our own moves, which already set the bar; late seek events must not undo a newer move.
      if (!e.isSeek && bar !== this.current) {
        this.current = bar;
        this.barInput.value = String(bar + 1);
      }
      if (!e.isSeek && this.playing) this.nav?.syncToTick(e.currentTick);
      this.updateStatus();
    });
    const indexes = this.tracks ?? (this.xml ? this.xml.parts.map((_, i) => i) : undefined);
    api.load(bytes, indexes);
    await rendered;
  }

  /**
   * Every part on its own channel with its band preset (mapping.json `resolve`), before the MIDI
   * is generated; the MusicXML's own program and bank changes would override it, so they go.
   */
  private applyBandSounds(score: AT.model.Score): void {
    this.trackSounds = [];
    if (!this.band) return;
    const channels = playbackChannels(score.tracks.map((t) => t.staves.some((st) => st.isPercussion)));
    score.tracks.forEach((track, i) => {
      const sound = this.band!.resolve(track.name, null, track.playbackInfo.program)?.sound ?? null;
      this.trackSounds.push(sound);
      track.playbackInfo.primaryChannel = channels[i];
      track.playbackInfo.secondaryChannel = channels[i];
      if (!sound) {
        console.warn(`No band sound for part "${track.name}" (program ${track.playbackInfo.program}).`);
        return;
      }
      track.playbackInfo.program = sound.percussion ? 0 : sound.program;
      track.playbackInfo.bank = sound.percussion ? 0 : sound.bank;
      for (const staff of track.staves)
        for (const bar of staff.bars)
          for (const voice of bar.voices)
            for (const beat of voice.beats)
              beat.automations = beat.automations.filter(
                (a) => a.type !== alphaTab.model.AutomationType.Instrument && a.type !== alphaTab.model.AutomationType.Bank);
    });
  }

  /** Part balance as channel volume (channel_gain_db): the band SoundFont does not carry it. */
  private applyTrackGains(): void {
    const score = this.api?.score;
    if (!score || !this.trackSounds.length) return;
    score.tracks.forEach((track, i) => {
      const s = this.trackSounds[i];
      if (s) this.api!.changeTrackVolume([track], Math.pow(10, s.gainDb / 20));
    });
  }

  /** Where each part comes from (engine part-sources), shown with the part's name; set before or after load. */
  set sources(v: Record<string, string> | null) {
    this.partSources = v;
    Array.from(this.partSelect?.options ?? []).forEach((o) => {
      if (/^\d+$/.test(o.value)) o.textContent = this.partLabel(Number(o.value));
    });
  }

  private partSources: Record<string, string> | null = null;

  private partLabel(i: number): string {
    const name = this.api?.score?.tracks[i]?.name || `${i + 1}`;
    const shown = lang() === "nb" ? partNameNb(name) ?? name : name;
    const src = this.partSources?.[name];
    return src ? `${shown} · ${t(`score.source.${src}`)}` : shown;
  }

  private onScore(score: AT.model.Score): void {
    this.bars = score.masterBars.map((mb, index) => ({
      index, number: index + 1, start: mb.start, end: mb.start + mb.calculateDuration(),
    }));
    this.barInput.max = String(this.bars.length);
    this.loopFrom.max = this.loopTo.max = String(this.bars.length);
    this.uncertainCount = this.markNotes(score);
    const firstWithNotes = this.tracks?.[0] ?? this.xml?.parts.findIndex((p) => p.notes.length > 0) ?? -1;
    this.partIndex = firstWithNotes >= 0 && firstWithNotes < score.tracks.length ? firstWithNotes : 0;
    this.nav?.setPart(this.partIndex);
    clear(this.partSelect,
      h("option", { value: "all" }, t("score.allParts")),
      score.tracks.map((_, i) => h("option", { value: String(i), selected: this.tracks?.length === 1 && this.tracks[0] === i }, this.partLabel(i))));
    clear(this.mixer, score.tracks.map((tr, i) => {
      const name = this.partLabel(i);
      const toggle = (kind: "mute" | "solo") => {
        const b: HTMLButtonElement = h("button", {
          type: "button", class: "toggle", "aria-pressed": "false", "data-kind": kind,
          "aria-label": kind === "mute" ? t("score.muteName", { name }) : t("score.soloName", { name }),
          title: kind === "solo" ? t("score.soloTip") : null,
          onclick: () => {
            const on = b.getAttribute("aria-pressed") !== "true";
            b.setAttribute("aria-pressed", String(on));
            if (kind === "mute") this.api?.changeTrackMute([tr], on);
            else this.api?.changeTrackSolo([tr], on);
          },
        }, icon(kind === "mute" ? "mute" : "solo"), kind === "mute" ? t("score.mute") : t("score.solo"));
        return b;
      };
      return h("div", { class: `part${i === this.partIndex ? " current" : ""}`, "data-track": i },
        h("span", { class: "part-name" }, name),
        h("span", { class: "row" }, toggle("mute"), toggle("solo")));
    }));
    this.current = 0;
    // Without the part list from our own reader alphaTab renders only the first track; show them all.
    if (!this.xml && !this.tracks && score.tracks.length > 1) setTimeout(() => this.api?.renderTracks(score.tracks), 0);
    this.updateStatus();
  }

  /**
   * Notes the engine marked uncertain get the `uncertain` or `very-uncertain`
   * colour here; the "?" (boxed below 0.4) is drawn over the notation by
   * drawMarks(), so colour is never the only signal (visual-design-tokens.md §2).
   * `decorate` adds marks on top (Compare).
   */
  private markNotes(score: AT.model.Score): number {
    if (!this.xml) return 0;
    const M = alphaTab.model;
    const colours = { u: M.Color.fromJson(tokenColour("uncertain")), vu: M.Color.fromJson(tokenColour("very-uncertain")) };
    let marked = 0;
    score.tracks.forEach((track, ti) => {
      const part = this.xml!.parts[ti];
      if (!part) return;
      const byBar = new Map<number, number[]>();
      part.notes.forEach((n, i) => (byBar.get(n.barIndex) ?? byBar.set(n.barIndex, []).get(n.barIndex)!).push(i));
      const staff = track.staves[0];
      staff?.bars.forEach((bar, bi) => {
        // The "?" words directions are drawn by drawMarks() in the note colour, not as plain text.
        for (const v of bar.voices) for (const b of v.beats) if (b.text?.trim() === "?") b.text = null;
        const idx = byBar.get(bi);
        if (!idx) return;
        const notes = bar.voices.flatMap((v) => v.beats.flatMap((b) => b.notes));
        if (notes.length !== idx.length) return; // cannot align this bar safely
        notes.forEach((note, k) => {
          const xn = part.notes[idx[k]];
          const extra = this.decorate?.(ti, idx[k], xn) ?? null;
          note.isGhost = false;
          if (!xn.level && !extra) {
            note.style = undefined;
            return;
          }
          const style = new M.NoteStyle();
          if (xn.level) marked++;
          style.colors.set(M.NoteSubElement.StandardNotationNoteHead, extra ? M.Color.fromJson(extra.colour) : colours[xn.level!]);
          if (extra?.head && extra.head !== "paren") {
            const d = note.beat.duration as number; // 1 whole, 2 half, 4 quarter …
            const kind = d <= 1 ? "Whole" : d === 2 ? "Half" : "Black";
            const names: Record<string, string> = {
              x: `NoteheadX${kind}`, diamond: kind === "Black" ? "NoteheadDiamondBlack" : `NoteheadDiamond${kind}`,
              triangle: `NoteheadTriangleUp${kind}`, square: kind === "Black" ? "NoteheadSquareBlack" : "NoteheadSquareWhite",
            };
            const sym = (M.MusicFontSymbol as unknown as Record<string, number>)[names[extra.head]];
            if (sym !== undefined) style.noteHead = sym as unknown as AT.model.MusicFontSymbol;
          }
          note.style = style;
        });
      });
    });
    return marked;
  }

  /**
   * Draw the "?" above each uncertain note (a boxed "?" when very uncertain),
   * outside the staff, in the note's colour, plus the ad lib band behind
   * free-time bars. Positions come from alphaTab's bounds lookup.
   */
  private drawMarks(): void {
    const layer = this.marks;
    const api = this.api;
    const lookup = (api?.renderer as unknown as { boundsLookup?: AT.rendering.BoundsLookup } | undefined)?.boundsLookup;
    if (!layer || !api?.score || !lookup || !this.xml) return;
    layer.replaceChildren();
    const surface = this.view.querySelector<HTMLElement>(".score-surface");
    this.bands?.replaceChildren();
    const ox = surface?.offsetLeft ?? 0;
    const oy = surface?.offsetTop ?? 0;
    // Ad lib bands (tints never stack: the loop tint is drawn above them by alphaTab).
    for (const [from, to] of this.xml.adlib) {
      for (let i = from; i <= to; i++) {
        const mb = lookup.findMasterBarByIndex(i);
        if (!mb) continue;
        const r = mb.realBounds;
        this.bands?.append(h("span", { class: "adlib", style: `left:${ox + r.x}px;top:${oy + r.y}px;width:${r.w}px;height:${r.h}px` }));
      }
    }
    api.score.tracks.forEach((track, ti) => {
      const part = this.xml!.parts[ti];
      if (!part?.notes.some((n) => n.level)) return;
      const byBar = new Map<number, number[]>();
      part.notes.forEach((n, i) => (byBar.get(n.barIndex) ?? byBar.set(n.barIndex, []).get(n.barIndex)!).push(i));
      track.staves[0]?.bars.forEach((bar, bi) => {
        const idx = byBar.get(bi);
        if (!idx) return;
        const notes = bar.voices.flatMap((v) => v.beats.flatMap((b) => b.notes));
        if (notes.length !== idx.length) return;
        let lastX = -1e9;
        notes.forEach((note, k) => {
          const level = part.notes[idx[k]].level;
          if (!level) return;
          const bb = lookup.findBeat(note.beat);
          const nb = bb?.notes?.find((x) => x.note === note);
          if (!bb || !nb) return;
          const x = nb.noteHeadBounds.x + nb.noteHeadBounds.w / 2;
          if (Math.abs(x - lastX) < 4) return; // one mark per chord
          lastX = x;
          const space = Math.max(6, nb.noteHeadBounds.h);
          const glyph = 1.6 * space; // cap height of the "?"
          const font = Math.round(glyph / 0.72);
          const staffTop = bb.barBounds.visualBounds.y;
          const y = Math.min(staffTop, nb.noteHeadBounds.y) - font - space * 0.4;
          layer.append(h("span", { class: `q ${level}`, style: `left:${ox + x}px;top:${oy + y}px;font-size:${font}px` }, "?"));
        });
      });
    });
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

  /** Open the talking-score panel and put focus on the current line. */
  showTalking(): void {
    this.talkPanel.open = true;
    this.renderTalkingText();
    const cur = this.talkText.querySelector<HTMLElement>("[aria-current=true]") ?? this.talkText.querySelector<HTMLElement>("li");
    (cur ?? this.talkPanel.querySelector("summary"))?.focus();
  }

  togglePlay(): void {
    if (!this.api) return;
    if (!this.ready) {
      announce(t("score.loadingPlayer"));
      return;
    }
    this.api.playPause();
  }

  stop(): void {
    this.api?.stop();
  }

  private seek(tick: number): void {
    if (!this.api) return;
    this.api.tickPosition = tick;
    // Keep the cursor in view when moving without playback.
    requestAnimationFrame(() => {
      try {
        this.api?.scrollToCursor();
      } catch {
        /* nothing rendered yet */
      }
    });
    const b = this.barAt(tick);
    this.current = b;
    this.barInput.value = String(b + 1);
    this.updateStatus();
  }

  /** Speak a talking-score stop and move the playback cursor there. */
  private speak(stop: Stop | string | null, fallback?: string): void {
    const text = stop === null ? fallback ?? "" : typeof stop === "string" ? stop : stop.text;
    if (stop && typeof stop !== "string") this.seek(stop.cursor.tick);
    if (!text) return;
    this.lastAnnouncement = text;
    this.talkNow.textContent = text;
    announce(text);
    if (this.talkPanel.open) this.renderTalkingText();
  }

  goBar(index: number, announceIt = true): void {
    if (!this.api || !this.bars.length) return;
    const i = Math.max(0, Math.min(this.bars.length - 1, index));
    if (this.nav && this.talking?.parts[this.partIndex]?.bars[i]) {
      const s = this.nav.goBar(i);
      if (announceIt) this.speak(s);
      else this.seek(this.bars[i].start);
      this.current = i;
      this.barInput.value = String(i + 1);
      return;
    }
    this.seek(this.bars[i].start);
    if (announceIt) announce(t("score.status.bar", { n: i + 1, total: this.bars.length }));
  }

  /** Play the current bar once. */
  playBar(index = this.current): void {
    if (!this.api || !this.bars.length) return;
    if (!this.ready) {
      announce(t("score.loadingPlayer"));
      return;
    }
    const b = this.bars[Math.max(0, Math.min(this.bars.length - 1, index))];
    this.api.stop();
    this.api.isLooping = false;
    this.api.playbackRange = { startTick: b.start, endTick: b.end } as AT.synth.PlaybackRange;
    this.api.tickPosition = b.start;
    this.loop = null;
    this.loopBtn.replaceChildren(...labelled("loop", t("score.loop")));
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
      announce(t("score.loopSet", { a: a + 1, b: b + 1 }));
    } else {
      this.loop = null;
      this.api.playbackRange = null;
      this.api.isLooping = false;
      announce(t("score.loopOff"));
    }
    this.loopBtn.replaceChildren(...labelled(on ? "close" : "loop", on ? t("score.loopStop") : t("score.loop")));
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
    this.nav?.setPart(this.partIndex);
    for (const el of Array.from(this.mixer.children)) el.classList.toggle("current", Number((el as HTMLElement).dataset.track) === this.partIndex);
    if (announceIt) announce(t("score.part", { name: this.partLabel(this.partIndex) }));
    if (this.talkPanel.open) this.renderTalkingText();
    this.updateStatus();
  }

  private setPitchMode(mode: PitchMode): void {
    if (!this.nav) return;
    this.speak(this.nav.setPitchMode(mode));
  }

  toggleMute(solo: boolean): void {
    const row = this.mixer.children[this.partIndex];
    const btn = row?.querySelector<HTMLButtonElement>(`button[data-kind="${solo ? "solo" : "mute"}"]`);
    if (!btn) return;
    btn.click();
    const on = btn.getAttribute("aria-pressed") === "true";
    announce(t("score.toggled", { name: this.partLabel(this.partIndex), what: solo ? t("score.solo") : t("score.mute"), state: on ? t("score.on") : t("score.off") }));
  }

  /** The talking-score text for the current part: a heading per bar and one line per event (spec §6). */
  private renderTalkingText(): void {
    if (!this.talking || !this.nav) {
      clear(this.talkText);
      return;
    }
    const part = this.talking.parts[this.partIndex];
    if (!part) return;
    // A separate navigator renders the lines, so the live context is not disturbed.
    const lines = new Navigator(this.talking, { ...this.nav.settings, verbosity: "standard" }, lang());
    lines.setPart(this.partIndex);
    const cur = this.nav.cursor;
    const name = lang() === "nb" ? part.name_nb ?? part.name : part.name;
    // The line to mark: the last listed stop at or before the cursor (a skipped bar rest points to its run).
    let mark = "";
    part.bars.forEach((b, bi) => b.events.forEach((e, ei) => {
      if (!e.skip && (bi < cur.bar || (bi === cur.bar && ei <= Math.max(0, cur.event)))) mark = `${bi}:${ei}`;
    }));
    const items = part.bars.map((b, bi) => {
      const evs = b.events.map((e, ei) => ({ e, ei })).filter(({ e }) => !e.skip);
      if (!evs.length) return null;
      const li = evs.map(({ ei }) => {
        const s = lines.goBarEvent(bi, ei);
        const here = mark === `${bi}:${ei}`;
        return h("li", { tabindex: -1, "aria-current": here ? "true" : null, class: here ? "current" : null }, s);
      });
      return h("section", {}, h("h4", {}, `${t("score.bar")} ${b.number}`), h("ul", {}, li));
    });
    clear(this.talkText, h("h3", {}, t("score.textPart", { name })), items);
    this.talkText.querySelector<HTMLElement>("[aria-current=true]")?.scrollIntoView({ block: "nearest" });
  }

  private onKey(e: KeyboardEvent): void {
    const k = e.key;
    const nav = this.nav;
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
      const dir = k === "ArrowDown" ? 1 : -1;
      if (nav) {
        const s = nav.nextPart(dir);
        this.setPart(nav.cursor.part, false);
        this.speak(s);
      } else this.setPart(this.partIndex + dir);
    } else if ((e.ctrlKey || e.altKey) && !e.shiftKey && (k === "ArrowRight" || k === "ArrowLeft")) {
      handled();
      if (nav) this.speak(nav.nextBeat(k === "ArrowRight" ? 1 : -1), k === "ArrowRight" ? t("score.end") : t("score.start"));
    } else if (k === "Home" || k === "End") {
      handled();
      this.goBar(k === "Home" ? 0 : this.bars.length - 1);
    } else if (e.ctrlKey || e.metaKey || e.altKey) {
      if ((e.ctrlKey || e.metaKey) && (k === "=" || k === "+" || k === "-" || k === "0")) {
        handled();
        this.zoom(k === "0" ? 1 : this.scale + (k === "-" ? -0.1 : 0.1));
      }
    } else if (k === "ArrowRight" || k === "ArrowLeft") {
      handled();
      if (nav) this.speak(nav.nextNote(k === "ArrowRight" ? 1 : -1), k === "ArrowRight" ? t("score.end") : t("score.start"));
      else if (this.api) this.seek(Math.max(0, this.api.tickPosition + (k === "ArrowRight" ? 960 : -960)));
    } else if (k === "u" || k === "U") {
      handled();
      if (nav) this.speak(nav.nextUncertain(e.shiftKey ? -1 : 1), t("score.noUncertain"));
    } else if (k === "p" || k === "P") {
      handled();
      this.playBar();
    } else if (k === "[") {
      handled();
      this.loopFrom.value = String(this.current + 1);
      if (Number(this.loopTo.value) < this.current + 1) this.loopTo.value = String(this.current + 1);
      announce(t("score.loopStart", { n: this.current + 1 }));
      if (this.loop) this.setLoop(Number(this.loopFrom.value) - 1, Number(this.loopTo.value) - 1);
    } else if (k === "]") {
      handled();
      this.loopTo.value = String(this.current + 1);
      if (Number(this.loopFrom.value) > this.current + 1) this.loopFrom.value = String(this.current + 1);
      announce(t("score.loopEnd", { n: this.current + 1 }));
      if (this.loop) this.setLoop(Number(this.loopFrom.value) - 1, Number(this.loopTo.value) - 1);
    } else if (k === "l" || k === "L") {
      handled();
      this.toggleLoop();
    } else if (k === "-" || k === "=" || k === "+" || k === "0") {
      handled();
      this.setSpeed(k === "0" ? 1 : (this.api?.playbackSpeed ?? 1) + (k === "-" ? -0.05 : 0.05));
      announce(t("score.speedIs", { v: this.speedOut.textContent ?? "" }));
    } else if (k === "r" || k === "R") {
      handled();
      if (nav) {
        nav.syncToTick(this.bars[this.current]?.start ?? 0);
        this.speak(nav.readBar());
      }
    } else if (k === "w" || k === "W") {
      handled();
      if (nav) this.speak(nav.whereAmI());
    } else if (k === "m" || k === "M" || k === "s" || k === "S") {
      handled();
      this.toggleMute(k === "s" || k === "S");
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
      t("score.status.bar", { n: this.current + 1, total: this.bars.length || "–" }),
      `${mmss(this.position.time)} / ${mmss(this.position.endTime)}`,
      this.playing ? t("score.status.playing") : this.ready ? t("score.status.stopped") : t("score.status.loadingPlayer"),
      this.api && this.band === null ? t("score.status.basicSounds") : "",
      t("score.status.speed", { v: this.speedOut?.textContent ?? "100%" }),
      this.loop ? t("score.loopRange", { a: this.loop.from + 1, b: this.loop.to + 1 }) : "",
      this.api?.score ? t("score.status.part", { name: this.partLabel(this.partIndex) }) : "",
    ];
    this.statusEl.textContent = parts.filter(Boolean).join(" · ");
    // Legend: the same "?" marks as on the score, and how many there are.
    this.legend.hidden = !this.uncertainCount;
    if (this.uncertainCount) {
      clear(this.legend,
        h("span", {}, h("span", { class: "q u", "aria-hidden": "true" }, "?"), t("score.legendU")),
        h("span", {}, h("span", { class: "q vu", "aria-hidden": "true" }, "?"), t("score.legendVu")),
        h("span", {}, t("score.legendCount", { n: this.uncertainCount })));
    }
  }
}

customElements.define("bs-score", ScoreElement);

declare global {
  interface HTMLElementTagNameMap {
    "bs-score": ScoreElement;
  }
}

/** alphaSynth stops every voice dead at the last MIDI event; a no-op controller event after the last note lets the final release sound. */
function addReleaseTail(midi: AT.midi.MidiFile): void {
  const events = midi.events;
  if (!events.length) return;
  const last = Math.max(...events.map((e) => e.tick));
  const tempos = events.filter((e): e is AT.midi.TempoChangeEvent => e instanceof alphaTab.midi.TempoChangeEvent && e.tick <= last);
  const usPerBeat = tempos.length ? tempos[tempos.length - 1].microSecondsPerQuarterNote : 500000;
  const tail = Math.round((RELEASE_TAIL_S * 1e6) / usPerBeat * midi.division);
  midi.addEvent(new alphaTab.midi.ControlChangeEvent(0, last + tail, 0, alphaTab.midi.ControllerType.ExpressionControllerFine, 0));
}
