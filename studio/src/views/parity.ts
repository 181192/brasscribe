// Conversion parity: converted models (Core ML, ONNX, LiteRT) against PyTorch
// or the reference runtime, note F1 and latency per device. A model is ready
// on a device when at least one converted format meets the threshold on every
// eval set; formats below it are secondary information.
import { api } from "../api/client";
import type { ParityReport } from "../api/types";
import { t } from "../i18n";
import { clear, errorNotice, fmt, h, infoTip, loading, more, pill, table, viewHead } from "../ui/dom";

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

const TOKENS: Record<string, string> = {
  coreml: "Core ML", onnx: "ONNX", onnx1500: "ONNX (1500 frames)", tflite: "TFLite", litert: "LiteRT", ort: "ONNX Runtime",
  dyn: "dynamic", b1: "batch 1",
};
/** Compute units: Core ML's MLComputeUnits, or the ONNX Runtime execution provider. */
const UNITS: Record<string, string> = { CPU_ONLY: "CPU", CPU_AND_GPU: "GPU", CPU_AND_NE: "Neural Engine", ALL: "all units", cpu: "CPU" };

/**
 * A converted format in words: "coreml-b1-fp32-CPU_AND_GPU" → "Core ML batch 1 fp32 (GPU)",
 * "small0/onnx-ort-cpu" → "small0: ONNX Runtime (CPU)", "ort-coreml-static" → "ONNX Runtime static (Core ML)".
 */
export function variantLabel(id: string): string {
  const slash = id.lastIndexOf("/");
  const prefix = slash >= 0 ? `${id.slice(0, slash)}: ` : "";
  const parts = id.slice(slash + 1).split("-");
  const units: string[] = [];
  const words: string[] = [];
  parts.forEach((p, i) => {
    if (p in UNITS) units.push(UNITS[p]);
    // After ONNX Runtime, "coreml" is its Core ML execution provider, so it is where the model runs.
    else if (p === "coreml" && parts.slice(0, i).includes("ort")) units.push("Core ML");
    else words.push(TOKENS[p] ?? p);
  });
  // "onnx" + "ort" is one thing: ONNX Runtime.
  const body = words.filter((w) => !(w === "ONNX" && words.includes("ONNX Runtime"))).join(" ");
  return `${prefix}${body}${units.length ? ` (${units.join(", ")})` : ""}`;
}

interface Row {
  variant: string;
  metric: string;
  m: Record<string, unknown>;
  ok: boolean | null;
}

export interface ModelParity {
  el: HTMLElement;
  /** No converted format meets the threshold. */
  notReady: boolean;
}

export function parityView(root: HTMLElement): void {
  const el = h("div", {}, loading());
  clear(root, viewHead(t("page.parity"), [t("parity.purpose"), " ", infoTip("F1", t("parity.f1Tip"))]),
    el);
  api.parity().then((reports) => {
    if (!reports.length) {
      clear(el, h("div", { class: "empty", role: "note" }, h("p", {}, h("strong", {}, t("parity.none"))), h("p", { class: "hint" }, t("parity.noneBody"))));
      return;
    }
    const built = reports.map((r) => parityReport(r)).sort((a, b) => Number(b.notReady) - Number(a.notReady));
    const notReady = built.filter((b) => b.notReady).length;
    // Only the first model with no ready format opens; the rest are summary lines.
    const first = built.find((b) => b.notReady);
    if (first) (first.el as HTMLDetailsElement).open = true;
    clear(el,
      h("p", { class: "run-summary" }, pill(notReady ? "not_ready" : "ready"),
        t(notReady ? "parity.summaryFail" : "parity.summaryPass", { n: built.length, f: notReady }), infoTip(t("parity.readyTerm"), t("parity.readyTip"))),
      built.map((b) => b.el));
  }).catch((e) => clear(el, errorNotice(e)));
}

export function parityReport(r: ParityReport): ModelParity {
  const thr = num(r.threshold_f1);
  const rows: Row[] = Object.entries(r.parity ?? {}).flatMap(([variant, metrics]) =>
    Object.entries(metrics).filter(([, v]) => v && typeof v === "object" && "f1" in (v as object)).map(([metric, v]) => {
      const m = v as Record<string, unknown>;
      const ok = thr === null ? null : (num(m.min_f1) ?? num(m.f1) ?? 0) >= thr;
      return { variant, metric, m, ok };
    }));
  // A format is ready when it meets the threshold on every eval set.
  const formats = [...new Set(rows.map((x) => x.variant))];
  const ready = formats.filter((v) => rows.filter((x) => x.variant === v).every((x) => x.ok !== false));
  const failingRows = rows.filter((x) => x.ok === false);
  const worst = failingRows.length ? Math.min(...failingRows.map((x) => num(x.m.min_f1) ?? num(x.m.f1) ?? 0)) : null;
  const notReady = formats.length > 0 && ready.length === 0;
  const model = r.model ?? r._file ?? "model";
  const head = [t("parity.col.variant"), t("parity.col.set"), "F1", "P", "R", t("parity.col.worst"), t("parity.col.worstClip"), t("parity.col.clips"), t("parity.col.meets")];
  // Cells are built per table: a DOM node can only sit in one place.
  const cells = (x: Row) => [
    h("span", {}, variantLabel(x.variant), h("span", { class: "sub mono" }, x.variant)),
    x.metric, fmt.num(num(x.m.f1)), fmt.num(num(x.m.p)), fmt.num(num(x.m.r)), fmt.num(num(x.m.min_f1)),
    String(x.m.min_clip ?? "–"), String(x.m.n_clips ?? "–"),
    x.ok === null ? "–" : x.ok ? pill("pass") : h("span", { class: "pill pill-fail" }, t("parity.belowCell", { t: thr ?? "–" })),
  ];
  const shown = ready.slice(0, 4).map(variantLabel);
  const latency = latencyRows(r);
  const ref = r.reference ?? {};
  const el = h("details", { class: "card", "aria-label": t("parity.for", { model }) },
    h("summary", {}, h("span", { class: "row" }, h("h2", { class: "in-summary" }, model),
      pill(notReady ? "not_ready" : "ready"),
      h("span", { class: "muted" }, notReady
        ? t("parity.lineNotReady", { n: formats.length, w: fmt.num(worst), t: thr ?? "–" })
        : t("parity.lineReady", { p: ready.length, n: formats.length, t: thr ?? "–", device: r.device ?? "–" })))),
    ready.length
      ? h("p", { class: "ready-on" }, h("strong", {}, t("parity.readyOn")), " ", shown.join(", "),
        ready.length > shown.length ? t("parity.andMore", { n: ready.length - shown.length }) : "")
      : h("p", {}, h("strong", {}, t("parity.noReady"))),
    h("p", { class: "hint" }, t("parity.reference", { ref: [ref.runtime, ref.model].filter(Boolean).join(", ") }) + (ref.note_segmentation ? t("parity.notesBy", { seg: String(ref.note_segmentation) }) : "")),
    failingRows.length
      ? more(t("parity.below"), table(t("parity.below"), head, failingRows.map(cells), { hideCaption: true, className: "parity-below" }),
        { count: t("parity.belowCount", { n: formats.length - ready.length, w: fmt.num(worst) }) })
      : null,
    more(t("parity.allVariants"), table(t("parity.f1"), head, rows.map(cells), { hideCaption: true }), { count: formats.length }),
    latency.length ? more(t("parity.latency"), table(t("parity.latency"), [t("parity.col.backend"), t("parity.col.audio"), t("parity.col.load"), t("parity.col.median"), t("parity.col.rtf"), t("parity.col.rss")], latency, { hideCaption: true }))
      : h("p", { class: "hint" }, t("parity.noLatency")),
    more(t("parity.more"), [
      r._file ? h("p", {}, t("parity.file"), h("code", {}, fmt.path(String(r._file)))) : null,
      typeof r.command === "string" ? h("p", {}, t("parity.command"), h("code", {}, r.command)) : null,
      r.artifacts ? table(t("parity.artifacts"), [t("run.col.file"), t("run.col.size"), t("run.col.sha")], Object.entries(r.artifacts).map(([k, v]) => [h("span", { class: "mono" }, k), fmt.bytes(v.size_bytes), h("span", { class: "mono" }, fmt.hash(v.sha256))])) : null,
    ]));
  return { el, notReady };
}

/** Latency per backend from the report's `benchmarks` block (timed on `audio_s` seconds of audio). */
function latencyRows(r: ParityReport): (string | HTMLElement)[][] {
  const b = (r as { benchmarks?: Record<string, Record<string, unknown>> }).benchmarks ?? {};
  return Object.entries(b).map(([name, m]) => {
    const rss = num(m.peak_rss_mb);
    return [h("span", { class: "mono" }, String(m.backend ?? name)), fmt.num(num(m.audio_s), 1), fmt.num(num(m.load_s)),
      fmt.num(num(m.median_s)), fmt.num(num(m.rtf), 4), rss !== null ? `${Math.round(rss)} MB` : "–"];
  });
}
