// Live stage graph: one node per stage, grouped into columns by kind in
// pipeline order. Each node is a toggle button that selects the stage for
// the inspector; status is text plus border style, never colour alone.
import type { RunView, StageView } from "../lib/events";
import { t } from "../i18n";
import { stageTime, stageTimeTip } from "../lib/stagetime";
import { clear, h } from "../ui/dom";

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

const MODELS: Record<string, string> = { muscriptor: "MuScriptor", "basic-pitch": "Basic Pitch", "swift-f0": "SwiftF0", "beat-this": "Beat This" };

/** A stage's plain name ("Notes: solo (MuScriptor)"); the identifier is shown under it. */
export function stageLabel(name: string): string {
  const [kind, layer, ...rest] = name.split(".");
  const tr = (key: string, fallback: string) => (t(key) === key ? fallback : t(key));
  const k = tr(`stage.k.${kind}`, kind);
  if (!layer) return k;
  const model = rest.join(".");
  const l = tr(`stage.layer.${layer}`, layer);
  return t("stage.withLayer", { kind: k, layer: l }) + (model ? ` (${MODELS[model] ?? model})` : "");
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
    const list = h("ol", { class: "stage-graph", "aria-label": t("run.stagesList") },
      cols.map((col, i) => [
        i ? h("li", { class: "stage-arrow", "aria-hidden": "true" }, "→") : null,
        h("li", {}, h("ol", { class: "stage-col", style: "list-style:none;padding:0;margin:0" }, col.map((s) => h("li", {}, this.node(s))))),
      ]));
    clear(this, list);
    if (focused) this.querySelector<HTMLElement>(`[data-stage="${CSS.escape(focused)}"]`)?.focus();
  }

  private node(s: StageView): HTMLButtonElement {
    const fromCache = s.status === "cached" || s.status === "imported";
    const meta = [
      fromCache ? null : t(`status.${s.status}`),
      s.seconds !== undefined && s.seconds !== null ? stageTime(s) : null,
    ].filter(Boolean).join(" · ");
    return h("button", {
      type: "button", class: `stage-node status-${s.status}`, "data-stage": s.name, title: stageTimeTip(s),
      "aria-pressed": String(this.selected === s.name),
      onclick: () => this.dispatchEvent(new CustomEvent("select", { detail: s.name })),
    },
    h("span", { class: "label" }, stageLabel(s.name)),
    h("span", { class: "name" }, s.name),
    h("span", { class: "meta" }, fromCache ? h("span", { class: "tag" }, t("run.cachedTag")) : null, meta));
  }
}

customElements.define("bs-stage-graph", StageGraph);

declare global {
  interface HTMLElementTagNameMap {
    "bs-stage-graph": StageGraph;
  }
}
