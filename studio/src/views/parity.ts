// Conversion parity: converted models (Core ML, ONNX, LiteRT) against PyTorch
// or the reference runtime, note F1 and latency per device.
import { api } from "../api/client";
import type { ParityReport } from "../api/types";
import { t } from "../i18n";
import { clear, errorNotice, fmt, h, loading, pill, table } from "../ui/dom";

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

export function parityView(root: HTMLElement): void {
  const el = h("div", {}, loading());
  clear(root, h("h1", {}, t("nav.parity")),
    h("p", {}, t("parity.intro")),
    el);
  api.parity().then((reports) => clear(el, reports.length ? reports.map(report) : h("p", {}, t("parity.none")))).catch((e) => clear(el, errorNotice(e)));
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
  return h("section", { class: "card stack", "aria-label": t("parity.for", { model: r.model ?? r._file ?? "" }) },
    h("h2", { class: "row" }, h("span", {}, r.model ?? "model"), typeof verdict === "boolean" ? pill(verdict ? "pass" : "fail") : null, h("span", { class: "small muted" }, `${r.device ?? ""} · ${t("parity.threshold", { t: thr ?? "–" })}`)),
    h("p", { class: "small" }, t("parity.reference", { ref: [ref.runtime, ref.model].filter(Boolean).join(", ") }) + (ref.note_segmentation ? t("parity.notesBy", { seg: String(ref.note_segmentation) }) : ""),
      r._file ? h("span", { class: "muted" }, ` · ${r._file}`) : null),
    table(t("parity.f1"), [t("parity.col.variant"), t("parity.col.set"), "F1", "P", "R", t("parity.col.worst"), t("parity.col.worstClip"), t("parity.col.clips"), t("parity.col.meets")], metricRows),
    latency.length ? table(t("parity.latency"), [t("parity.col.backend"), t("parity.col.audio"), t("parity.col.load"), t("parity.col.median"), t("parity.col.rtf"), t("parity.col.rss")], latency)
      : h("p", { class: "hint" }, t("parity.noLatency")),
    typeof r.command === "string" ? h("p", { class: "small" }, t("parity.command"), h("code", {}, r.command)) : null,
    r.artifacts ? table(t("parity.artifacts"), [t("run.col.file"), t("run.col.size"), t("run.col.sha")], Object.entries(r.artifacts).map(([k, v]) => [h("span", { class: "mono small" }, k), fmt.bytes(v.size_bytes), h("span", { class: "mono small" }, fmt.hash(v.sha256))])) : null);
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
