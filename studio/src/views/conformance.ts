// Core conformance: the Rust core against the Python reference on the golden
// sets. Summary reports are listed as written; wherever an item has both a
// py/ and a rust/ output, Studio diffs them itself.
import { api } from "../api/client";
import type { Composition, ConformanceReport } from "../api/types";
import { diffCompositions } from "../lib/diff";
import { clear, errorNotice, h, loading, pill, table } from "../ui/dom";

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

export function conformanceView(root: HTMLElement): void {
  const el = h("div", {}, loading());
  clear(root, h("h1", {}, "Core conformance"),
    h("p", {}, "The Rust core must reproduce the Python reference (brasscribe_music) on the golden sets: quantisation, layers, songs and the full arrangement."),
    el);
  api.conformance().then((reports) => clear(el, render(reports))).catch((e) => clear(el, errorNotice(e)));
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
  return h("section", { class: "stack", "aria-label": `Report ${r._file ?? ""}` },
    h("p", { class: "row" }, pill(count("fail") ? "fail" : count("missing") ? "missing" : "pass"),
      `${count("pass")} of ${r.sets.length} cases identical, ${count("fail")} different, ${count("missing")} missing`,
      h("span", { class: "small muted" }, `core ${r.core_version ?? "?"} · git ${String(r.git_sha ?? "–").slice(0, 12)} · ${r.time ? fmtTime(r.time) : "–"} · ${r._file ?? ""}`)),
    table("Cases per set", ["Set", "Cases", "Identical", "Different", "Missing"], sets.map((s) => {
      const cs = r.sets.filter((c) => c.set === s);
      return [s, String(cs.length), String(cs.filter((c) => c.status === "pass").length), String(cs.filter((c) => c.status === "fail").length), String(cs.filter((c) => c.status === "missing").length)];
    })),
    table("Cases", ["Set", "Item", "Stage", "Status", "Diffs", "MuseScore", "Detail"],
      [...r.sets].sort((a, b) => (a.status === "pass" ? 1 : 0) - (b.status === "pass" ? 1 : 0)).map((c) => [
        c.set, h("span", { class: "mono small" }, c.item), c.stage, pill(c.status), String(c.diffs ?? "–"),
        c.musescore ? (c.musescore.written ? (c.musescore.pitches_match ? "read back, pitches match" : "read back, pitches differ") : "not written") : "–",
        c.detail ?? "–",
      ])));
}

function fmtTime(t: string | number): string {
  const d = typeof t === "number" ? new Date(t * 1000) : new Date(t);
  return Number.isNaN(d.getTime()) ? String(t) : d.toLocaleString();
}

function render(reports: ConformanceReport[]): HTMLElement[] {
  const summaries = reports.filter(isSummary);
  if (summaries.length) {
    return [
      ...summaries.map(summaryView),
      h("p", { class: "hint" }, `Regenerate with `, h("code", {}, "cd core/conformance && uv run python -m brasscribe_conformance.run"), " (add ", h("code", {}, "--musescore"), " for the round trip)."),
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
      `${count("pass")} identical, ${count("fail")} different, ${count("missing")} without a Rust output yet (${rows.length} items).`),
    summaries.length ? h("section", {}, h("h2", {}, "Reports"), summaries.map((s) => h("details", {},
      h("summary", {}, String(s._file ?? "report")), h("pre", { class: "json", tabindex: 0 }, JSON.stringify(s, null, 1).slice(0, 20000))))) : null,
    table("Items", ["Set / item / stage / file", "Python", "Rust", "Status", "Detail"],
      rows.map((r) => [h("span", { class: "mono small" }, r.p.key), r.p.py ? "yes" : "–", r.p.rust ? "yes" : "–", pill(r.status), r.detail])),
  ].filter(Boolean) as HTMLElement[];
}
