// Core conformance: the Rust core against the Python reference on the golden
// sets. Summary reports are listed as written; wherever an item has both a
// py/ and a rust/ output, Studio diffs them itself.
import { api } from "../api/client";
import type { Composition, ConformanceReport, ConformanceRun } from "../api/types";
import { diffCompositions } from "../lib/diff";
import { locale, t } from "../i18n";
import { announce, clear, errorNotice, fmt, h, infoTip, loading, more, pill, table, viewHead } from "../ui/dom";
import { icon } from "../ui/icons";

interface Pair {
  key: string; // set/item/stage/file
  py?: ConformanceReport;
  rust?: ConformanceReport;
}

/** Split ".../<set>/<item>/<stage>/<py|rust>/<file>.json" into a pair key and side. */
export function pairKey(file: string): { key: string; side: "py" | "rust" } | null {
  const parts = file.split("/");
  const i = parts.findIndex((p) => p === "py" || p === "rust");
  if (i < 1) return null;
  return { key: [...parts.slice(Math.max(0, i - 3), i), parts[parts.length - 1]].join("/"), side: parts[i] as "py" | "rust" };
}

function isComposition(x: unknown): x is Composition {
  return !!x && typeof x === "object" && Array.isArray((x as Composition).voices);
}

export function comparePair(p: Pair): { status: "pass" | "fail" | "missing"; detail: string } {
  if (!p.py || !p.rust) return { status: "missing", detail: p.py ? "no Rust output" : "no Python reference" };
  const strip = (o: ConformanceReport) => {
    const { _file: _, ...rest } = o;
    return rest;
  };
  if (isComposition(p.py) && isComposition(p.rust)) {
    const d = diffCompositions(p.py, p.rust, 0);
    const changed = d.totals.added + d.totals.removed + d.totals.moved + d.totals.octave;
    const same = JSON.stringify(strip(p.py)) === JSON.stringify(strip(p.rust));
    return { status: same ? "pass" : "fail", detail: same ? `${d.totals.same} notes identical` : `${changed} notes differ (${d.totals.added} added, ${d.totals.removed} removed, ${d.totals.moved} moved, ${d.totals.octave} octave)${changed ? "" : "; other fields differ"}` };
  }
  const same = JSON.stringify(strip(p.py)) === JSON.stringify(strip(p.rust));
  return { status: same ? "pass" : "fail", detail: same ? "identical" : "JSON differs" };
}

export function conformanceView(root: HTMLElement): () => void {
  const el = h("div", {}, loading());
  const runner = h("div", { class: "conf-run" });
  clear(root, viewHead(t("page.conformance"), [t("conf.purpose"), " ", infoTip(t("conf.term"), t("conf.intro"))]),
    runner,
    el);
  let timer = 0;
  // Leaving the page cancels what is loading and stops the polling.
  const ctl = new AbortController();
  const { signal } = ctl;
  const load = () => api.conformance({ signal }).then((reports) => {
    if (!signal.aborted) clear(el, render(reports));
  }).catch((e) => {
    if (!signal.aborted) clear(el, errorNotice(e, { retry: load }));
  });
  const poll = () => api.conformanceRun({ signal }).then((r) => {
    if (!signal.aborted) showRun(r);
    return r;
  }, () => {
    if (!signal.aborted) showRun(null);
    return null;
  });
  // "Run conformance" when the engine can start the core's conformance run; otherwise the command is shown.
  const showRun = (r: ConformanceRun | null) => {
    window.clearTimeout(timer);
    if (signal.aborted) return;
    if (!r || !r.available) {
      clear(runner);
      return;
    }
    const running = r.status === "running";
    const btn = h("button", { type: "button", class: "primary", disabled: running, onclick: async () => {
      btn.disabled = true;
      try {
        showRun(await api.startConformanceRun());
        announce(t("conf.started"));
      } catch (e) {
        if (!signal.aborted) clear(runner, errorNotice(e, { retry: () => void poll() }));
      }
    } }, icon("retry"), running ? t("conf.running") : t("conf.run"));
    const state = r.status === "idle" ? null : h("span", { class: "hint", role: "status" },
      running ? t("conf.runningSince", { when: fmtTime(r.started ?? 0) })
        : t(r.status === "succeeded" ? (r.exit_code === 0 ? "conf.doneSame" : "conf.doneDiff") : "conf.failed", { when: fmtTime(r.finished ?? 0) }));
    clear(runner, h("div", { class: "row" }, btn, state),
      r.log_tail ? more(t("conf.log"), h("pre", { class: "json", tabindex: 0 }, r.log_tail)) : null);
    if (running) {
      timer = window.setTimeout(() => void poll().then((n) => {
        if (n && !signal.aborted && n.status !== "running") {
          announce(t(n.status === "succeeded" ? "conf.finished" : "conf.failedShort"));
          void load();
        }
      }), 3000);
    }
  };
  void load();
  void poll();
  return () => {
    ctl.abort();
    window.clearTimeout(timer);
  };
}

interface CaseRow {
  set: string;
  item: string;
  stage: string;
  status: "pass" | "fail" | "missing";
  diffs?: number;
  detail?: string;
  py?: string;
  rust?: string;
  musescore?: { written?: boolean; pitches_match?: boolean };
  golden?: { file?: boolean };
}

function isSummary(r: ConformanceReport): r is ConformanceReport & { sets: CaseRow[]; time?: string | number; git_sha?: string; core_version?: string } {
  return Array.isArray((r as { sets?: unknown }).sets);
}

/** The conformance runner's report.json: one row per set, item and stage. */
function summaryView(r: ConformanceReport & { sets: CaseRow[]; time?: string | number; git_sha?: string; core_version?: string }): HTMLElement {
  const count = (s: string) => r.sets.filter((c) => c.status === s).length;
  const sets = [...new Set(r.sets.map((c) => c.set))];
  return h("section", { class: "stack", "aria-label": t("conf.report", { file: r._file ?? "" }) },
    h("p", { class: "row" }, pill(count("fail") ? "fail" : count("missing") ? "missing" : "pass"),
      t("conf.summary", { pass: count("pass"), total: r.sets.length, fail: count("fail"), missing: count("missing") }),
      h("span", { class: "muted" }, t("conf.meta", { v: r.core_version ?? "?", sha: String(r.git_sha ?? "–").slice(0, 12), time: r.time ? fmtTime(r.time) : "–", file: fmt.path(String(r._file ?? "")) }))),
    table(t("conf.perSet"), [t("conf.col.set"), t("conf.col.cases"), t("conf.col.identical"), t("conf.col.different"), t("conf.col.missing")], sets.map((s) => {
      const cs = r.sets.filter((c) => c.set === s);
      return [s, String(cs.length), String(cs.filter((c) => c.status === "pass").length), String(cs.filter((c) => c.status === "fail").length), String(cs.filter((c) => c.status === "missing").length)];
    })),
    caseTables(r.sets));
}

/** Failing and missing cases in view; every case behind "Show all". */
function caseTables(cases: CaseRow[]): HTMLElement[] {
  const head = [t("conf.col.set"), t("conf.col.item"), t("conf.col.stage"), t("conf.col.status"), t("conf.col.diffs"), t("conf.col.musescore"), t("conf.col.detail")];
  const row = (c: CaseRow) => [
    c.set, h("span", { class: "mono" }, c.item), c.stage, pill(c.status), String(c.diffs ?? "–"),
    c.musescore ? (c.musescore.written ? (c.musescore.pitches_match ? t("conf.ms.match") : t("conf.ms.differ")) : t("conf.ms.not")) : "–",
    c.detail ?? "–",
  ];
  const bad = cases.filter((c) => c.status !== "pass");
  return [
    bad.length ? h("h3", {}, t("conf.needsAttention")) : h("p", {}, t("conf.allIdentical")),
    bad.length ? table(t("conf.needsAttention"), head, bad.map(row), { hideCaption: true }) : null,
    more(t("conf.showAll"), table(t("conf.cases"), head, cases.map(row), { hideCaption: true }), { count: cases.length }),
  ].filter(Boolean) as HTMLElement[];
}

function fmtTime(v: string | number): string {
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString(locale());
}

const RUN_CMD = "cd core/conformance && uv run python -m brasscribe_conformance.run";

function render(reports: ConformanceReport[]): HTMLElement[] {
  const summaries = reports.filter(isSummary);
  if (!reports.length) {
    const retry = h("button", { type: "button", class: "ghost", onclick: () => window.dispatchEvent(new CustomEvent("studio:retry")) }, t("err.retry"));
    const [before, after] = t("conf.noneBody").split("{cmd}");
    return [h("div", { class: "empty", role: "note" },
      h("p", {}, h("strong", {}, t("conf.none"))),
      h("p", {}, before, h("code", {}, RUN_CMD), after),
      h("p", {}, retry))];
  }
  if (summaries.length) {
    return [
      ...summaries.map(summaryView),
      h("p", { class: "hint" }, t("conf.regen"), h("code", {}, RUN_CMD), t("conf.regen2"), h("code", {}, "--musescore"), t("conf.regen3")),
    ];
  }
  return pairsView(reports);
}

function pairsView(reports: ConformanceReport[]): HTMLElement[] {
  const pairs = new Map<string, Pair>();
  const summaries: ConformanceReport[] = [];
  for (const r of reports) {
    const f = String(r._file ?? "");
    const k = pairKey(f);
    if (k) {
      const p = pairs.get(k.key) ?? { key: k.key };
      p[k.side] = r;
      pairs.set(k.key, p);
    } else summaries.push(r);
  }
  const rows = [...pairs.values()].sort((a, b) => a.key.localeCompare(b.key)).map((p) => ({ p, ...comparePair(p) }));
  const count = (s: string) => rows.filter((r) => r.status === s).length;
  return [
    h("p", { class: "row" }, pill(count("fail") ? "fail" : count("pass") ? "pass" : "missing"),
      t("conf.pairs", { pass: count("pass"), fail: count("fail"), missing: count("missing"), n: rows.length })),
    summaries.length ? h("section", {}, h("h2", {}, t("conf.reports")), summaries.map((s) => h("details", {},
      h("summary", {}, String(s._file ?? "report")), h("pre", { class: "json", tabindex: 0 }, JSON.stringify(s, null, 1).slice(0, 20000))))) : null,
    rows.some((r) => r.status !== "pass") ? table(t("conf.needsAttention"), [t("conf.col.key"), t("conf.col.py"), t("conf.col.rust"), t("conf.col.status"), t("conf.col.detail")],
      rows.filter((r) => r.status !== "pass").map((r) => [h("span", { class: "mono" }, r.p.key), r.p.py ? t("common.yes") : "–", r.p.rust ? t("common.yes") : "–", pill(r.status), r.detail])) : null,
    more(t("conf.showAll"), table(t("conf.items"), [t("conf.col.key"), t("conf.col.py"), t("conf.col.rust"), t("conf.col.status"), t("conf.col.detail")],
      rows.map((r) => [h("span", { class: "mono" }, r.p.key), r.p.py ? t("common.yes") : "–", r.p.rust ? t("common.yes") : "–", pill(r.status), r.detail])), { count: rows.length }),
  ].filter(Boolean) as HTMLElement[];
}
