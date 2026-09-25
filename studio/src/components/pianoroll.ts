// Piano roll: notes of several layers (final voices and raw model outputs)
// over time. Colour says which model; shape says it too, and confidence is
// drawn as fill (confident), hatching (uncertain) or a dashed outline (very
// uncertain), so nothing relies on colour alone.
import { announce, clear, fmt, h, token } from "../ui/dom";
import { pitchName } from "../lib/validate";
import { hatch, plot, timeAxis, type Plot } from "./canvas";

export interface RollNote {
  pitch: number;
  start: number; // seconds
  end: number;
  confidence?: number;
  mark?: "added" | "removed" | "moved" | "octave";
}

export type RollStyle = "block" | "line" | "dashed" | "dotted" | "outline";

export interface RollLayer {
  id: string;
  label: string;
  colour: string; // token name
  style: RollStyle;
  notes: RollNote[];
  visible?: boolean;
}

const UNCERTAIN = 0.7;
const VERY_UNCERTAIN = 0.4;

export class PianoRoll extends HTMLElement {
  private layers: RollLayer[] = [];
  private t0 = 0;
  private span = 30;
  private lo = 36;
  private hi = 84;
  private chart!: Plot;
  private info!: HTMLElement;
  private summaryEl!: HTMLElement;

  set data(layers: RollLayer[]) {
    this.layers = layers.map((l) => ({ ...l, visible: l.visible ?? true }));
    const all = this.layers.flatMap((l) => l.notes);
    if (all.length) {
      this.lo = Math.max(0, Math.min(...all.map((n) => n.pitch)) - 2);
      this.hi = Math.min(127, Math.max(...all.map((n) => n.pitch)) + 2);
      this.t0 = Math.max(0, Math.min(...all.map((n) => n.start)) - 1);
    }
    this.render();
  }

  private get duration(): number {
    return Math.max(1, ...this.layers.flatMap((l) => l.notes.map((n) => n.end)));
  }

  private render(): void {
    this.chart = plot("Piano roll", 360, (c, w, hh) => this.draw(c, w, hh));
    this.info = h("p", { class: "hint", role: "status" });
    const toggles = h("fieldset", {}, h("legend", {}, "Layers"),
      h("ul", { class: "legend" }, this.layers.map((l) => {
        const box = h("input", { type: "checkbox", checked: l.visible, onchange: () => {
          l.visible = box.checked;
          this.chart.redraw();
          this.summary();
        } });
        return h("li", {}, h("label", {}, box, swatch(l), `${l.label} (${l.notes.length})`));
      })));
    const confLegend = h("ul", { class: "legend", "aria-label": "Confidence" },
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: "background:var(--ink)" }), "confident (≥ 0.7): filled"),
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: "background:repeating-linear-gradient(135deg,var(--uncertain) 0 2px,transparent 2px 5px)" }), "uncertain (0.4–0.7): hatched"),
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: "border-style:dashed;background:transparent" }), "very uncertain (< 0.4): dashed outline"));
    const nav = h("div", { class: "row" },
      h("button", { type: "button", onclick: () => this.pan(-0.8) }, "◀ Earlier"),
      h("button", { type: "button", onclick: () => this.pan(0.8) }, "Later ▶"),
      h("button", { type: "button", onclick: () => this.zoom(0.5) }, "Zoom in"),
      h("button", { type: "button", onclick: () => this.zoom(2) }, "Zoom out"),
      h("button", { type: "button", onclick: () => { this.t0 = 0; this.span = this.duration; this.update(); } }, "Whole piece"));
    this.summaryEl = h("div", {});
    clear(this, toggles, confLegend, nav, this.info, this.chart.box, this.summaryEl);
    this.update();
  }

  private pan(f: number): void {
    this.t0 = Math.max(0, Math.min(this.duration - this.span * 0.2, this.t0 + f * this.span));
    this.update();
  }

  private zoom(f: number): void {
    const mid = this.t0 + this.span / 2;
    this.span = Math.max(2, Math.min(this.duration + 2, this.span * f));
    this.t0 = Math.max(0, mid - this.span / 2);
    this.update();
  }

  private update(): void {
    this.info.textContent = `Showing ${fmt.seconds(this.t0)} to ${fmt.seconds(this.t0 + this.span)}, pitches ${pitchName(this.lo)} to ${pitchName(this.hi)} (concert).`;
    this.chart.redraw();
    this.summary();
    announce(this.info.textContent);
  }

  /** Text alternative: counts per layer and confidence band in the visible window. */
  private summary(): void {
    const rows = this.layers.filter((l) => l.visible).map((l) => {
      const inWin = l.notes.filter((n) => n.end >= this.t0 && n.start <= this.t0 + this.span);
      const band = (lo: number, hi: number) => inWin.filter((n) => (n.confidence ?? 1) >= lo && (n.confidence ?? 1) < hi).length;
      const marks = ["added", "removed", "moved", "octave"].map((m) => inWin.filter((n) => n.mark === m).length);
      return h("tr", {}, h("th", { scope: "row" }, l.label), h("td", { class: "num" }, inWin.length),
        h("td", { class: "num" }, band(UNCERTAIN, 2)), h("td", { class: "num" }, band(VERY_UNCERTAIN, UNCERTAIN)), h("td", { class: "num" }, band(-1, VERY_UNCERTAIN)),
        marks.some(Boolean) ? h("td", {}, marks.map((m, i) => (m ? `${["added", "removed", "moved", "octave"][i]} ${m}` : "")).filter(Boolean).join(", ")) : h("td", {}, "–"));
    });
    clear(this.summaryEl, h("div", { class: "table-wrap", tabindex: 0, role: "region", "aria-label": "Notes in view" },
      h("table", {}, h("caption", {}, "Notes in view"),
        h("thead", {}, h("tr", {}, ["Layer", "Notes", "Confident", "Uncertain", "Very uncertain", "Diff marks"].map((c) => h("th", { scope: "col" }, c)))),
        h("tbody", {}, rows))));
    this.chart.setLabel(`Piano roll from ${fmt.seconds(this.t0)} to ${fmt.seconds(this.t0 + this.span)}; the table below lists the notes in view.`);
  }

  private draw(c: CanvasRenderingContext2D, w: number, hh: number): void {
    const plotH = hh - 16;
    const left = 34;
    const pw = w - left;
    const rows = this.hi - this.lo + 1;
    const rh = plotH / rows;
    const x = (t: number) => left + ((t - this.t0) / this.span) * pw;
    const y = (p: number) => (this.hi - p) * rh;
    // Pitch grid: C lines labelled.
    c.font = "10px system-ui, sans-serif";
    c.textBaseline = "middle";
    for (let p = this.lo; p <= this.hi; p++) {
      if (p % 12 === 0) {
        c.fillStyle = token("text-muted");
        c.fillText(pitchName(p), 2, y(p) + rh / 2);
        c.strokeStyle = token("staff");
        c.globalAlpha = 0.35;
        c.beginPath();
        c.moveTo(left, y(p) + rh);
        c.lineTo(w, y(p) + rh);
        c.stroke();
        c.globalAlpha = 1;
      }
    }
    for (const l of this.layers) {
      if (!l.visible) continue;
      const col = token(l.colour);
      const pat = hatch(c, col);
      for (const n of l.notes) {
        if (n.end < this.t0 || n.start > this.t0 + this.span) continue;
        const x0 = Math.max(left, x(n.start));
        const x1 = Math.max(x0 + 2, x(n.end));
        const top = y(n.pitch);
        const conf = n.confidence ?? 1;
        c.setLineDash([]);
        c.lineWidth = 1;
        if (l.style === "block") {
          if (conf >= UNCERTAIN) {
            c.fillStyle = col;
            c.fillRect(x0, top + 0.5, x1 - x0, Math.max(2, rh - 1));
          } else if (conf >= VERY_UNCERTAIN) {
            c.fillStyle = pat;
            c.fillRect(x0, top + 0.5, x1 - x0, Math.max(2, rh - 1));
            c.strokeStyle = col;
            c.strokeRect(x0 + 0.5, top + 0.5, x1 - x0 - 1, Math.max(2, rh - 1));
          } else {
            c.strokeStyle = col;
            c.setLineDash([3, 2]);
            c.lineWidth = 1.5;
            c.strokeRect(x0 + 0.5, top + 0.5, x1 - x0 - 1, Math.max(2, rh - 1));
          }
        } else if (l.style === "outline") {
          c.strokeStyle = col;
          c.lineWidth = 2;
          c.strokeRect(x0 + 1, top + 1, x1 - x0 - 2, Math.max(2, rh - 2));
        } else {
          // Raw model output: a line through the note's pitch row, dashed or dotted per model.
          c.strokeStyle = col;
          c.lineWidth = 2;
          c.setLineDash(l.style === "dashed" ? [6, 3] : l.style === "dotted" ? [2, 2] : []);
          const ym = top + rh / 2 + (l.style === "dashed" ? -rh / 4 : l.style === "dotted" ? rh / 4 : 0);
          c.beginPath();
          c.moveTo(x0, ym);
          c.lineTo(x1, ym);
          c.stroke();
          c.setLineDash([]);
          c.fillStyle = col;
          c.fillRect(x0 - 1, ym - 3, 2, 6); // onset tick
        }
        if (n.mark) markNote(c, n.mark, x0, top, x1, rh);
      }
    }
    c.setLineDash([]);
    timeAxis(c, pw, plotH, this.t0, this.t0 + this.span, token("text-muted"));
  }
}

/** Diff marks: a letter beside the note so the kind is readable without colour. */
function markNote(c: CanvasRenderingContext2D, mark: string, x0: number, top: number, _x1: number, rh: number): void {
  const letter = { added: "+", removed: "−", moved: "↔", octave: "8" }[mark] ?? "?";
  c.fillStyle = token(mark === "added" ? "ok" : mark === "removed" ? "error" : mark === "moved" ? "uncertain" : "very-uncertain");
  c.font = `bold ${Math.max(9, Math.min(13, rh + 4))}px system-ui, sans-serif`;
  c.textBaseline = "bottom";
  c.fillText(letter, x0, top);
}

function swatch(l: RollLayer): HTMLElement {
  const style = l.style === "block" ? `background:var(--${l.colour});border-color:var(--${l.colour})`
    : `background:transparent;border-color:var(--${l.colour});border-style:${l.style === "dashed" ? "dashed" : l.style === "dotted" ? "dotted" : "solid"}`;
  return h("span", { class: "sw", "aria-hidden": "true", style });
}

customElements.define("bs-pianoroll", PianoRoll);

declare global {
  interface HTMLElementTagNameMap {
    "bs-pianoroll": PianoRoll;
  }
}
