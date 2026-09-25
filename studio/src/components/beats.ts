// Beat inspector: the tracker's beats and downbeats against the beat grid the
// Composition was written on, with free-time and irregular-tempo regions.
import { irregularRegions, summarise, type Beat, type Region } from "../lib/beats";
import { t } from "../i18n";
import { clear, fmt, h, table, token } from "../ui/dom";
import { plot, timeAxis } from "./canvas";

export interface BeatRow {
  label: string;
  beats: Beat[];
}

export class BeatView extends HTMLElement {
  private rows: BeatRow[] = [];
  private free: (Region & { label?: string })[] = [];
  private irregular: Region[] = [];
  private t0 = 0;
  private span = 40;

  setData(rows: BeatRow[], free: (Region & { label?: string })[]): void {
    this.rows = rows;
    this.free = free;
    this.irregular = rows[0] ? irregularRegions(rows[0].beats) : [];
    this.render();
  }

  private render(): void {
    const chart = plot(t("tab.beats"), 40 + this.rows.length * 50, (c, w, hh) => this.draw(c, w, hh));
    const info = h("p", { class: "hint", role: "status" });
    const update = () => {
      info.textContent = t("common.showing", { from: fmt.seconds(this.t0), to: fmt.seconds(this.t0 + this.span) });
      chart.setLabel(t("beats.label", { from: fmt.seconds(this.t0), to: fmt.seconds(this.t0 + this.span), rows: this.rows.map((r) => r.label).join(", ") }));
      chart.redraw();
    };
    const dur = Math.max(1, ...this.rows.flatMap((r) => r.beats.map((b) => b.time)));
    const nav = h("div", { class: "row" },
      h("button", { type: "button", onclick: () => { this.t0 = Math.max(0, this.t0 - this.span * 0.8); update(); } }, t("common.earlier")),
      h("button", { type: "button", onclick: () => { this.t0 = Math.min(dur - 5, this.t0 + this.span * 0.8); update(); } }, t("common.later")),
      h("button", { type: "button", onclick: () => { this.span = Math.max(5, this.span / 2); update(); } }, t("common.zoomIn")),
      h("button", { type: "button", onclick: () => { this.span = Math.min(dur + 5, this.span * 2); update(); } }, t("common.zoomOut")));
    const sums = this.rows.map((r) => ({ r, s: summarise(r.beats) }));
    const level = sums.length === 2 && sums[0].s.beats ? sums[1].s.beats / sums[0].s.beats : null;
    const legend = h("ul", { class: "legend" },
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: "height:1rem;width:3px;border:none;background:var(--ink)" }), t("beats.downbeat")),
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: "height:0.5rem;width:1px;border:none;background:var(--staff)" }), t("beats.beat")),
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: "background:var(--adlib-tint);border:2px dashed var(--very-uncertain)" }), t("beats.free")),
      h("li", {}, h("span", { class: "sw", "aria-hidden": "true", style: "background:transparent;border:2px dotted var(--uncertain)" }), t("beats.irregular")));
    clear(this,
      legend, nav, info, chart.box,
      table(t("beats.tempo"), [t("beats.col.track"), t("beats.col.beats"), t("beats.col.downbeats"), t("beats.col.perBar"), t("beats.col.tempo")],
        sums.map(({ r, s }) => [r.label, String(s.beats), String(s.downbeats), String(s.barBeats || "–"), s.bpm ? `${fmt.num(s.bpm, 1)} bpm` : "–"])),
      level !== null ? h("p", {}, t("beats.level", { x: `${fmt.num(level, 2)}×` }),
        Math.abs(level - 1) < 0.1 ? t("beats.level.same") : Math.abs(level - 2) < 0.2 ? t("beats.level.half") : Math.abs(level - 0.5) < 0.1 ? t("beats.level.double") : ".") : null,
      table(t("beats.freeRegions"), [t("beats.col.from"), t("beats.col.to"), t("beats.col.label"), t("beats.col.source")],
        this.free.map((r) => [fmt.seconds(r.start), fmt.seconds(r.end), r.label ?? "ad lib.", t("beats.composition")])),
      this.free.length ? null : h("p", { class: "hint" }, t("beats.noFree")),
      table(t("beats.irregularTitle"), [t("beats.col.from"), t("beats.col.to")], this.irregular.map((r) => [fmt.seconds(r.start), fmt.seconds(r.end)])));
    update();
  }

  private draw(c: CanvasRenderingContext2D, w: number, hh: number): void {
    const t1 = this.t0 + this.span;
    const x = (t: number) => ((t - this.t0) / this.span) * w;
    const plotH = hh - 16;
    const regionBox = (r: Region, fill: string, stroke: string, dash: number[]) => {
      if (r.end < this.t0 || r.start > t1) return;
      const a = Math.max(0, x(r.start));
      const b = Math.min(w, x(r.end));
      if (fill) {
        c.fillStyle = fill;
        c.fillRect(a, 0, b - a, plotH);
      }
      c.strokeStyle = stroke;
      c.setLineDash(dash);
      c.lineWidth = 2;
      c.strokeRect(a + 1, 1, b - a - 2, plotH - 2);
      c.setLineDash([]);
    };
    for (const r of this.free) regionBox(r, token("adlib-tint"), token("very-uncertain"), [6, 3]);
    for (const r of this.irregular) regionBox(r, "", token("uncertain"), [2, 3]);
    c.font = "11px system-ui, sans-serif";
    this.rows.forEach((row, i) => {
      const top = 8 + i * 50;
      c.fillStyle = token("text");
      c.textBaseline = "top";
      c.fillText(row.label, 4, top);
      let bar = 0;
      for (const b of row.beats) {
        if (b.position === 1) bar++;
        if (b.time < this.t0 || b.time > t1) continue;
        const bx = Math.round(x(b.time)) + 0.5;
        const down = b.position === 1;
        c.strokeStyle = down ? token("ink") : token("staff");
        c.lineWidth = down ? 3 : 1;
        c.beginPath();
        c.moveTo(bx, top + (down ? 14 : 26));
        c.lineTo(bx, top + 40);
        c.stroke();
        if (down && (this.span < 60 || bar % 4 === 1)) {
          c.fillStyle = token("text-muted");
          c.fillText(String(bar), bx + 3, top + 14);
        }
      }
    });
    timeAxis(c, w, plotH, this.t0, t1, token("text-muted"));
  }
}

customElements.define("bs-beats", BeatView);

declare global {
  interface HTMLElementTagNameMap {
    "bs-beats": BeatView;
  }
}
