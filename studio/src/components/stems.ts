// Stems mixer: load stems on demand, play them in sync with solo and mute,
// and show each stem's energy over time.
import { energy, mixdown } from "../lib/dsp";
import { t } from "../i18n";
import { announce, clear, fmt, h, token } from "../ui/dom";
import { audioContext, decode } from "./audio";
import { plot, timeAxis } from "./canvas";

export interface StemSource {
  name: string;
  url: string;
  bytes?: number;
  group: string;
}

interface Row {
  src: StemSource;
  buffer?: AudioBuffer;
  energy?: Float32Array;
  gain?: GainNode;
  mute: boolean;
  solo: boolean;
  status: HTMLElement;
  loadBtn: HTMLButtonElement;
  muteBox: HTMLInputElement;
  soloBox: HTMLInputElement;
}

const FRAMES = 400;

export class StemsMixer extends HTMLElement {
  private rows: Row[] = [];
  private nodes: AudioBufferSourceNode[] = [];
  private startedAt = 0;
  private offset = 0;
  private playBtn!: HTMLButtonElement;
  private chart = plot(t("stems.energy"), 140, (c, w, hh) => this.drawEnergy(c, w, hh));
  private legend = h("ul", { class: "legend" });

  set data(stems: StemSource[]) {
    this.playBtn = h("button", { type: "button", class: "primary", onclick: () => this.toggle() }, t("stems.play"));
    this.rows = stems.map((src) => {
      const status = h("span", { class: "small muted" }, t("stems.notLoaded"));
      const row: Row = {
        src, mute: false, solo: false, status,
        loadBtn: h("button", { type: "button", "aria-label": t("stems.loadName", { name: src.name }), onclick: () => this.load(row) }, t("stems.load")),
        muteBox: h("input", { type: "checkbox", "aria-label": t("score.muteName", { name: src.name }), onchange: () => this.setFlag(row, "mute") }),
        soloBox: h("input", { type: "checkbox", "aria-label": t("score.soloName", { name: src.name }), onchange: () => this.setFlag(row, "solo") }),
      };
      return row;
    });
    const groups = [...new Set(stems.map((s) => s.group))];
    const hint = h("p", { class: "hint" }, t("stems.hint"));
    const loadGroup = (g: string) => h("button", { type: "button", onclick: () => Promise.all(this.rows.filter((r) => r.src.group === g).map((r) => this.load(r))) }, t("stems.loadAll", { group: g }));
    clear(this,
      h("div", { class: "row" }, this.playBtn, h("button", { type: "button", onclick: () => this.stop(true) }, t("score.stop")), groups.map(loadGroup)),
      hint,
      h("h3", {}, t("stems.energy")),
      this.chart.box, this.legend,
      groups.map((g) => h("div", { class: "table-wrap", role: "region", "aria-label": t("stems.group", { group: g }), tabindex: 0 },
        h("table", {},
          h("caption", {}, `${g} (${this.rows.filter((r) => r.src.group === g).length})`),
          h("thead", {}, h("tr", {}, [t("stems.col.stem"), t("stems.col.size"), t("stems.col.loaded"), t("stems.col.mute"), t("stems.col.solo"), ""].map((c) => h("th", { scope: "col" }, c)))),
          h("tbody", {}, this.rows.filter((r) => r.src.group === g).map((r) =>
            h("tr", {}, h("td", { class: "mono" }, r.src.name), h("td", { class: "num" }, fmt.bytes(r.src.bytes)), h("td", {}, r.status),
              h("td", {}, r.muteBox), h("td", {}, r.soloBox), h("td", {}, r.loadBtn))))))));
  }

  /** Load the first `n` stems of a group (the layer stems by default). */
  async preload(group: string, n = 8): Promise<void> {
    await Promise.all(this.rows.filter((r) => r.src.group === group).slice(0, n).map((r) => this.load(r)));
  }

  disconnectedCallback(): void {
    this.stop(true);
  }

  private async load(r: Row): Promise<void> {
    if (r.buffer) return;
    r.loadBtn.disabled = true;
    r.status.textContent = t("stems.loadingOne");
    try {
      r.buffer = await decode(r.src.url);
      const mono = mixdown(Array.from({ length: r.buffer.numberOfChannels }, (_, c) => r.buffer!.getChannelData(c)));
      r.energy = energy(mono, FRAMES);
      r.status.textContent = `${fmt.seconds(r.buffer.duration)}`;
      r.loadBtn.textContent = t("stems.loaded");
      this.chart.redraw();
      this.renderLegend();
      if (this.nodes.length) this.restart();
    } catch (e) {
      r.status.textContent = t("stems.failed", { e: e instanceof Error ? e.message : String(e) });
      r.loadBtn.disabled = false;
    }
  }

  private setFlag(r: Row, flag: "mute" | "solo"): void {
    r[flag] = flag === "mute" ? r.muteBox.checked : r.soloBox.checked;
    this.applyGains();
    announce(t("score.toggled", { name: r.src.name, what: flag === "mute" ? t("score.mute") : t("score.solo"), state: r[flag] ? t("score.on") : t("score.off") }));
    this.chart.redraw();
  }

  private audible(r: Row): boolean {
    const anySolo = this.rows.some((x) => x.solo);
    return !r.mute && (!anySolo || r.solo);
  }

  private applyGains(): void {
    for (const r of this.rows) if (r.gain) r.gain.gain.value = this.audible(r) ? 1 : 0;
  }

  private toggle(): void {
    if (this.nodes.length) this.stop(false);
    else this.start(this.offset);
  }

  private restart(): void {
    const at = this.offset + (audioContext().currentTime - this.startedAt);
    this.stop(false);
    this.start(at);
  }

  private start(at: number): void {
    const ac = audioContext();
    void ac.resume();
    const loaded = this.rows.filter((r) => r.buffer);
    if (!loaded.length) {
      announce(t("stems.needOne"));
      return;
    }
    const when = ac.currentTime + 0.05;
    for (const r of loaded) {
      const n = ac.createBufferSource();
      n.buffer = r.buffer!;
      r.gain = ac.createGain();
      n.connect(r.gain).connect(ac.destination);
      n.start(when, Math.min(at, r.buffer!.duration - 0.01));
      this.nodes.push(n);
    }
    this.applyGains();
    this.offset = at;
    this.startedAt = when;
    this.playBtn.textContent = t("score.pause");
  }

  private stop(rewind: boolean): void {
    if (this.nodes.length) this.offset += audioContext().currentTime - this.startedAt;
    for (const n of this.nodes) {
      try {
        n.stop();
      } catch {
        /* already stopped */
      }
    }
    this.nodes = [];
    if (rewind) this.offset = 0;
    if (this.playBtn) this.playBtn.textContent = t("stems.play");
  }

  private colours(): string[] {
    return [token("m1"), token("m2"), token("m3"), token("m4"), token("ink")];
  }

  private renderLegend(): void {
    const cs = this.colours();
    const dash = ["solid", "dashed", "dotted", "double", "solid"];
    clear(this.legend, this.rows.filter((r) => r.energy).map((r, i) =>
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: `border-color:${cs[i % cs.length]};border-style:${dash[Math.floor(i / cs.length) % dash.length]};background:transparent` }), r.src.name)));
  }

  private drawEnergy(c: CanvasRenderingContext2D, w: number, hh: number): void {
    const rows = this.rows.filter((r) => r.energy);
    const plotH = hh - 16;
    this.chart.box.style.height = "";
    if (!rows.length) {
      c.fillStyle = token("text-muted");
      c.font = "12px system-ui, sans-serif";
      c.fillText(t("stems.energyEmpty"), 8, 20);
      return;
    }
    const dur = Math.max(...rows.map((r) => r.buffer!.duration));
    const cs = this.colours();
    const dashes = [[], [6, 3], [2, 3], [8, 2, 2, 2]];
    rows.forEach((r, i) => {
      c.strokeStyle = cs[i % cs.length];
      c.setLineDash(dashes[Math.floor(i / cs.length) % dashes.length]);
      c.globalAlpha = this.audible(r) ? 1 : 0.3;
      c.lineWidth = 1.5;
      c.beginPath();
      const e = r.energy!;
      const span = (r.buffer!.duration / dur) * w;
      for (let f = 0; f < e.length; f++) {
        const x = (f / e.length) * span;
        const y = plotH - (Math.max(-60, Math.min(0, e[f])) + 60) / 60 * (plotH - 2);
        if (f) c.lineTo(x, y);
        else c.moveTo(x, y);
      }
      c.stroke();
    });
    c.setLineDash([]);
    c.globalAlpha = 1;
    timeAxis(c, w, plotH, 0, dur, token("text-muted"));
    this.chart.setLabel(t("stems.energyLabel", { names: rows.map((r) => r.src.name).join(", ") }));
  }
}

customElements.define("bs-stems", StemsMixer);

declare global {
  interface HTMLElementTagNameMap {
    "bs-stems": StemsMixer;
  }
}
