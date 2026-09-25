// Live stage graph: one node per stage, grouped into columns by kind in
// pipeline order. Each node is a toggle button that selects the stage for
// the inspector; status is text plus border style, never colour alone.
import type { RunView, StageView } from "../lib/events";
import { clear, fmt, h } from "../ui/dom";

const ORDER = ["beats", "stems", "separate", "layers", "transcribe", "vote", "arrange", "export"];

export function columns(stages: StageView[]): StageView[][] {
  const cols = new Map<string, StageView[]>();
  for (const s of stages) {
    const k = s.kind ?? s.name.split(".")[0];
    (cols.get(k) ?? cols.set(k, []).get(k)!).push(s);
  }
  return [...cols.entries()]
    .sort(([a], [b]) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99))
    .map(([, v]) => v);
}

export class StageGraph extends HTMLElement {
  selected: string | null = null;
  private view: RunView | null = null;

  update(view: RunView): void {
    this.view = view;
    this.render();
  }

  select(name: string | null): void {
    this.selected = name;
    this.render();
  }

  private render(): void {
    const v = this.view;
    if (!v) return;
    const focused = (document.activeElement as HTMLElement | null)?.dataset?.stage;
    const cols = columns(v.stages);
    const list = h("ol", { class: "stage-graph", "aria-label": "Pipeline stages in order" },
      cols.map((col, i) => [
        i ? h("li", { class: "stage-arrow", "aria-hidden": "true" }, "→") : null,
        h("li", {}, h("ol", { class: "stage-col", style: "list-style:none;padding:0;margin:0" }, col.map((s) => h("li", {}, this.node(s))))),
      ]));
    clear(this, list);
    if (focused) this.querySelector<HTMLElement>(`[data-stage="${CSS.escape(focused)}"]`)?.focus();
  }

  private node(s: StageView): HTMLButtonElement {
    const meta = [
      s.status === "started" ? "running" : s.status === "cached" ? "cache hit" : s.status === "imported" ? "imported (cache hit)" : s.status,
      s.seconds !== undefined && s.seconds !== null ? fmt.seconds(s.seconds) : null,
      s.device ?? null,
    ].filter(Boolean).join(" · ");
    return h("button", {
      type: "button", class: `stage-node status-${s.status}`, "data-stage": s.name,
      "aria-pressed": String(this.selected === s.name),
      onclick: () => this.dispatchEvent(new CustomEvent("select", { detail: s.name })),
    }, h("span", { class: "name" }, s.name), h("span", { class: "meta" }, meta));
  }
}

customElements.define("bs-stage-graph", StageGraph);

declare global {
  interface HTMLElementTagNameMap {
    "bs-stage-graph": StageGraph;
  }
}
