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
  const latency = latencyRows(r);
  const verdict = (r as { pass?: unknown }).pass;
  const ref = r.reference ?? {};
  return h("section", { class: "card stack", "aria-label": `Parity for ${r.model ?? r._file}` },
    h("h2", { class: "row" }, h("span", {}, r.model ?? "model"), typeof verdict === "boolean" ? pill(verdict ? "pass" : "fail") : null, h("span", { class: "small muted" }, `${r.device ?? ""} · threshold F1 ${thr ?? "–"}`)),
    h("p", { class: "small" }, `Reference: ${[ref.runtime, ref.model].filter(Boolean).join(", ")}${ref.note_segmentation ? `; notes by ${ref.note_segmentation}` : ""}`,
      r._file ? h("span", { class: "muted" }, ` · ${r._file}`) : null),
    table("Note F1 against the reference", ["Variant", "Set", "F1", "P", "R", "Worst clip F1", "Worst clip", "Clips", "Meets threshold"], metricRows),
    latency.length ? table("Latency on this device", ["Backend", "Audio (s)", "Load (s)", "Median run (s)", "Real-time factor", "Peak memory"], latency)
      : h("p", { class: "hint" }, "This report has no latency figures."),
    typeof r.command === "string" ? h("p", { class: "small" }, "Produced by ", h("code", {}, r.command)) : null,
    r.artifacts ? table("Converted artifacts", ["File", "Size", "SHA-256"], Object.entries(r.artifacts).map(([k, v]) => [h("span", { class: "mono small" }, k), fmt.bytes(v.size_bytes), h("span", { class: "mono small" }, fmt.hash(v.sha256))])) : null);
}

/** Latency per backend from the report's `benchmarks` block (timed on `audio_s` seconds of audio). */
function latencyRows(r: ParityReport): (string | HTMLElement)[][] {
  const b = (r as { benchmarks?: Record<string, Record<string, unknown>> }).benchmarks ?? {};
  return Object.entries(b).map(([name, m]) => {
    const rss = num(m.peak_rss_mb);
    return [h("span", { class: "mono small" }, String(m.backend ?? name)), fmt.num(num(m.audio_s), 1), fmt.num(num(m.load_s)),
      fmt.num(num(m.median_s)), fmt.num(num(m.rtf), 4), rss !== null ? `${Math.round(rss)} MB` : "–"];
  });
}
