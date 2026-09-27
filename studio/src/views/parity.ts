// Conversion parity: converted models (Core ML, ONNX, LiteRT) against PyTorch
// or the reference runtime, note F1 and latency per device.
import { api } from "../api/client";
import type { ParityReport } from "../api/types";
import { t } from "../i18n";
import { clear, errorNotice, fmt, h, infoTip, loading, more, pill, table, viewHead } from "../ui/dom";

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

export function parityView(root: HTMLElement): void {
  const el = h("div", {}, loading());
  clear(root, viewHead(t("page.parity"), [t("parity.purpose"), " ", infoTip("F1", t("parity.f1Tip"))]),
    el);
  api.parity().then((reports) => {
    if (!reports.length) {
      clear(el, h("div", { class: "empty", role: "note" }, h("p", {}, h("strong", {}, t("parity.none"))), h("p", { class: "hint" }, t("parity.noneBody"))));
      return;
    }
    // Failures first and open; passing models collapse to their summary line.
    const built = reports.map(report).sort((a, b) => Number(b.failed) - Number(a.failed));
    const failing = built.filter((b) => b.failed).length;
    clear(el,
      h("p", { class: "run-summary" }, pill(failing ? "fail" : "pass"), t(failing ? "parity.summaryFail" : "parity.summaryPass", { n: built.length, f: failing })),
      built.map((b) => b.el));
  }).catch((e) => clear(el, errorNotice(e)));
}

function report(r: ParityReport): { el: HTMLElement; failed: boolean } {
  const thr = num(r.threshold_f1);
  const variants = Object.entries(r.parity ?? {});
  const metricRows = variants.flatMap(([variant, metrics]) =>
    Object.entries(metrics).filter(([, v]) => v && typeof v === "object" && "f1" in (v as object)).map(([metric, v]) => {
      const m = v as Record<string, unknown>;
      const f1 = num(m.f1);
      const minF1 = num(m.min_f1);
      const ok = thr === null ? null : (minF1 ?? f1 ?? 0) >= thr;
      return { passed: ok !== false, cells: [h("span", { class: "mono" }, variant), metric, fmt.num(f1), fmt.num(num(m.p)), fmt.num(num(m.r)), fmt.num(minF1),
        String(m.min_clip ?? "–"), String(m.n_clips ?? "–"), ok === null ? "–" : pill(ok ? "pass" : "fail")] };
    }));
  const latency = latencyRows(r);
  const verdict = (r as { pass?: unknown }).pass;
  const ref = r.reference ?? {};
  const meets = metricRows.length;
  const passing = metricRows.filter((row) => row.passed).length;
  const failed = verdict === false || passing < meets;
  const model = r.model ?? r._file ?? "model";
  const f1Head = [t("parity.col.variant"), t("parity.col.set"), "F1", "P", "R", t("parity.col.worst"), t("parity.col.worstClip"), t("parity.col.clips"), t("parity.col.meets")];
  const el = h("details", { class: "card", open: failed, "aria-label": t("parity.for", { model }) },
    h("summary", {}, h("span", { class: "row" }, h("h2", { class: "in-summary" }, model), pill(failed ? "fail" : "pass"),
      h("span", { class: "muted" }, t("parity.line", { p: passing, n: meets, t: thr ?? "–", device: r.device ?? "–" })))),
    h("p", {}, t("parity.reference", { ref: [ref.runtime, ref.model].filter(Boolean).join(", ") }) + (ref.note_segmentation ? t("parity.notesBy", { seg: String(ref.note_segmentation) }) : "")),
    // Variants below the threshold in view; every variant behind "Show all".
    passing < meets ? table(t("parity.below"), f1Head, metricRows.filter((row) => !row.passed).map((row) => row.cells)) : null,
    more(t("parity.allVariants"), table(t("parity.f1"), f1Head, metricRows.map((row) => row.cells), { hideCaption: true }), { count: meets }),
    latency.length ? table(t("parity.latency"), [t("parity.col.backend"), t("parity.col.audio"), t("parity.col.load"), t("parity.col.median"), t("parity.col.rtf"), t("parity.col.rss")], latency)
      : h("p", { class: "hint" }, t("parity.noLatency")),
    more(t("parity.more"), [
      r._file ? h("p", {}, t("parity.file"), h("code", {}, fmt.path(String(r._file)))) : null,
      typeof r.command === "string" ? h("p", {}, t("parity.command"), h("code", {}, r.command)) : null,
      r.artifacts ? table(t("parity.artifacts"), [t("run.col.file"), t("run.col.size"), t("run.col.sha")], Object.entries(r.artifacts).map(([k, v]) => [h("span", { class: "mono" }, k), fmt.bytes(v.size_bytes), h("span", { class: "mono" }, fmt.hash(v.sha256))])) : null,
    ]));
  return { el, failed };
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
