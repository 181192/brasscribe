// Conversion parity: converted models (Core ML, ONNX, LiteRT) against PyTorch
// or the reference runtime, note F1 and latency per device.
import { api } from "../api/client";
import type { ParityReport } from "../api/types";
import { clear, errorNotice, fmt, h, loading, pill, table } from "../ui/dom";

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

export function parityView(root: HTMLElement): void {
  const el = h("div", {}, loading());
  clear(root, h("h1", {}, "Conversion parity"),
    h("p", {}, "Each converted model is compared with its reference runtime on the eval sets. A variant is ready for on-device use when its note F1 against the reference meets the report's threshold."),
    el);
  api.parity().then((reports) => clear(el, reports.length ? reports.map(report) : h("p", {}, "No parity reports yet (models/convert/reports/*.json)."))).catch((e) => clear(el, errorNotice(e)));
}

function report(r: ParityReport): HTMLElement {
  const thr = num(r.threshold_f1);
  const variants = Object.entries(r.parity ?? {});
  const metricRows = variants.flatMap(([variant, metrics]) =>
    Object.entries(metrics).filter(([, v]) => v && typeof v === "object" && "f1" in (v as object)).map(([metric, v]) => {
      const m = v as Record<string, unknown>;
      const f1 = num(m.f1);
      const minF1 = num(m.min_f1);
      const ok = thr === null ? null : (minF1 ?? f1 ?? 0) >= thr;
      return [h("span", { class: "mono small" }, variant), metric, fmt.num(f1), fmt.num(num(m.p)), fmt.num(num(m.r)), fmt.num(minF1),
        h("span", { class: "small" }, String(m.min_clip ?? "–")), String(m.n_clips ?? "–"), ok === null ? "–" : pill(ok ? "pass" : "fail")];
    }));
  const latency = collectLatency(r);
  const ref = r.reference ?? {};
  return h("section", { class: "card stack", "aria-label": `Parity for ${r.model ?? r._file}` },
    h("h2", { class: "row" }, h("span", {}, r.model ?? "model"), h("span", { class: "small muted" }, `${r.device ?? ""} · threshold F1 ${thr ?? "–"}`)),
    h("p", { class: "small" }, `Reference: ${[ref.runtime, ref.model].filter(Boolean).join(", ")}${ref.note_segmentation ? `; notes by ${ref.note_segmentation}` : ""}`,
      r._file ? h("span", { class: "muted" }, ` · ${r._file}`) : null),
    table("Note F1 against the reference", ["Variant", "Set", "F1", "P", "R", "Worst clip F1", "Worst clip", "Clips", "Meets threshold"], metricRows),
    latency.length ? table("Latency", ["Variant", "Measure", "Value"], latency) : h("p", { class: "hint" }, "This report has no latency figures."),
    r.artifacts ? table("Converted artifacts", ["File", "Size", "SHA-256"], Object.entries(r.artifacts).map(([k, v]) => [h("span", { class: "mono small" }, k), fmt.bytes(v.size_bytes), h("span", { class: "mono small" }, fmt.hash(v.sha256))])) : null);
}

/** Latency may sit at the top level or inside each variant; pick out keys that look like timings. */
function collectLatency(r: ParityReport): (string | HTMLElement)[][] {
  const rows: (string | HTMLElement)[][] = [];
  const walk = (variant: string, o: unknown, path: string) => {
    if (!o || typeof o !== "object") return;
    for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
      const p = path ? `${path}.${k}` : k;
      if (typeof v === "number" && /(ms|latency|seconds|rtf|time)/i.test(p)) rows.push([h("span", { class: "mono small" }, variant), p, fmt.num(v, 3)]);
      else if (v && typeof v === "object" && !("f1" in (v as object))) walk(variant, v, p);
    }
  };
  if (r.latency) walk("–", r.latency, "");
  for (const [variant, m] of Object.entries(r.parity ?? {})) walk(variant, m, "");
  return rows.slice(0, 60);
}
