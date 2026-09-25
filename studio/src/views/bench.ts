// Benchmarks: run suites, see the regression gate and the trend per metric.
import { api } from "../api/client";
import type { BenchRun, SuiteInfo, SuiteResult, SuiteRun } from "../api/types";
import { announce, clear, errorNotice, fmt, h, loading, pill, table, token } from "../ui/dom";

export function benchView(root: HTMLElement): void {
  const suitesEl = h("div", {}, loading());
  const lastEl = h("div", { "aria-live": "polite" });
  const trendEl = h("div", {}, loading());
  clear(root,
    h("h1", {}, "Benchmarks"),
    h("p", {}, "Each suite scores model outputs against the baselines in ", h("code", {}, "eval/baselines.json"),
      " (the numbers in docs/research/10-benchmark-results.md). The gate fails when a metric moves more than its tolerance (±0.01 F1)."),
    h("section", { "aria-labelledby": "suites-h" }, h("h2", { id: "suites-h" }, "Suites"), suitesEl),
    h("section", { "aria-labelledby": "last-h" }, h("h2", { id: "last-h" }, "Latest result"), lastEl),
    h("section", { "aria-labelledby": "trend-h" }, h("h2", { id: "trend-h" }, "Trend"), trendEl));

  const loadTrend = () => api.suiteHistory().then((hist) => clear(trendEl, trend(hist))).catch((e) => clear(trendEl, errorNotice(e)));
  api.suites().then((suites) => {
    clear(suitesEl, suiteTable(suites, async (name, mode, btn) => {
      btn.disabled = true;
      clear(lastEl, loading(`Running ${name} (${mode})…`));
      try {
        const run = await api.runSuite(name, mode);
        clear(lastEl, benchResult(run));
        announce(`${name}: gate ${run.passed ? "passed" : "failed"}`);
        void loadTrend();
      } catch (e) {
        clear(lastEl, errorNotice(e));
      } finally {
        btn.disabled = false;
      }
    }));
  }).catch((e) => clear(suitesEl, errorNotice(e)));
  void loadTrend();
  clear(lastEl, h("p", { class: "hint" }, "Run a suite to see its gate here. Earlier results are in the trend below."));
}

function suiteTable(suites: SuiteInfo[], run: (name: string, mode: "cached" | "live", btn: HTMLButtonElement) => void): HTMLElement {
  const groups = ["cpu", "all"];
  const btn = (name: string, mode: "cached" | "live", label?: string) => {
    const b: HTMLButtonElement = h("button", { type: "button", "aria-label": label ? null : `${mode === "cached" ? "Run" : "Run live"} ${name}`, onclick: () => run(name, mode, b) },
      label ?? (mode === "cached" ? "Run" : "Run live"));
    return b;
  };
  return h("div", {},
    h("div", { class: "row" }, groups.map((g) => btn(g, "cached", `Run all ${g === "cpu" ? "CPU suites" : "suites"}`))),
    table("Suites", ["Suite", "Runs on", "Description", "Needs", ""], suites.map((s) => [
      h("span", { class: "mono" }, s.name), s.cpu ? "CPU (cached model outputs)" : "GPU (runs models)", s.description,
      h("span", { class: "small mono" }, s.requires.join(", ") || "–"),
      h("span", { class: "row" }, btn(s.name, "cached"), s.cpu ? null : btn(s.name, "live")),
    ])));
}

export function benchResult(run: BenchRun): HTMLElement {
  return h("div", { class: "stack" },
    h("p", { class: "row" }, pill(run.passed ? "pass" : "fail"), `Gate ${run.passed ? "passed" : "failed"} for ${run.target} (${run.mode})`,
      h("span", { class: "small muted" }, `${fmt.date(run.created)} · git ${fmt.hash(run.git_sha)} · ${run.device ?? "–"}`)),
    run.suites.map(suiteResult));
}

function suiteResult(r: SuiteResult): HTMLElement {
  return h("div", { class: "card" },
    h("h3", { class: "row" }, h("span", { class: "mono" }, r.suite), pill(r.status), h("span", { class: "small muted" }, fmt.seconds(r.seconds))),
    r.reason ? h("p", { class: "small" }, r.reason) : null,
    r.checks?.length ? table(`Checks for ${r.suite}`, ["Metric", "Value", "Baseline", "Δ", "Tolerance", "Status"],
      r.checks.map((c) => [h("span", { class: "mono small" }, c.metric), fmt.num(c.value), fmt.num(c.baseline),
        c.value !== null && c.baseline !== null ? fmt.signed(c.value - c.baseline) : "–", `±${c.tolerance}`, pill(c.status)]), { hideCaption: true })
      : h("p", { class: "hint" }, "No checks (no baseline for this suite)."));
}

/** Per suite: each metric's latest gate check with a sparkline over all stored runs (baseline band shaded). */
function trend(hist: SuiteRun[]): HTMLElement {
  if (!hist.length) return h("p", {}, "No suite results stored yet. Run a suite above.");
  const bySuite = new Map<string, SuiteRun[]>();
  for (const r of [...hist].sort((a, b) => a.time - b.time)) (bySuite.get(r.suite) ?? bySuite.set(r.suite, []).get(r.suite)!).push(r);
  const out: HTMLElement[] = [];
  for (const [suite, runs] of bySuite) {
    const last = runs[runs.length - 1];
    const metrics = [...new Set(runs.flatMap((r) => r.checks.map((c) => c.metric)))];
    // Suites that pass start collapsed; failing ones open.
    out.push(h("details", { class: "card", open: last.status !== "pass" },
      h("summary", {}, h("span", { class: "row", style: "display:inline-flex" }, h("strong", { class: "mono" }, suite), pill(last.status), h("span", { class: "small muted" }, `${runs.length} ${runs.length === 1 ? "run" : "runs"}, last ${fmt.date(last.time)}`))),
      table(`Gate for ${suite} over time`, ["Metric", "Latest", "Baseline", "Δ", "Status", "Trend"], metrics.map((m) => {
        const c = last.checks.find((x) => x.metric === m);
        return [h("span", { class: "mono small" }, m), fmt.num(c?.value), c?.baseline != null ? `${fmt.num(c.baseline)} ± ${c.tolerance}` : "–",
          c && c.value !== null && c.baseline !== null ? fmt.signed(c.value - c.baseline) : "–", c ? pill(c.status) : "–", sparkline(m, runs)];
      }), { hideCaption: true }),
      h("details", {}, h("summary", {}, `All ${runs.length} results for ${suite}`),
        table(`History of ${suite}`, ["When", "Status", "Git", "Device", ...metrics], runs.slice().reverse().map((r) => [
          fmt.date(r.time), pill(r.status), h("span", { class: "mono small" }, fmt.hash(r.git_sha)), r.device ?? "–",
          ...metrics.map((m) => {
            const c = r.checks.find((x) => x.metric === m);
            return c ? `${fmt.num(c.value)}${c.status !== "pass" ? ` (${c.status})` : ""}` : "–";
          }),
        ])))));
  }
  return h("div", { class: "stack" }, out);
}

function sparkline(metric: string, runs: SuiteRun[]): HTMLElement {
  const pts = runs.map((r) => ({ t: r.time, c: r.checks.find((x) => x.metric === metric) })).filter((p) => p.c && p.c.value !== null);
  const W = 180;
  const H = 40;
  const vals = pts.map((p) => p.c!.value!);
  const base = pts.find((p) => p.c!.baseline !== null)?.c;
  const lo = Math.min(...vals, base?.baseline != null ? base.baseline - base.tolerance : Infinity);
  const hi = Math.max(...vals, base?.baseline != null ? base.baseline + base.tolerance : -Infinity);
  const pad = (hi - lo) * 0.15 || 0.01;
  const y = (v: number) => H - 4 - ((v - (lo - pad)) / (hi - lo + 2 * pad)) * (H - 8);
  const x = (i: number) => (pts.length === 1 ? W / 2 : 8 + (i / (pts.length - 1)) * (W - 16));
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  const lastV = vals[vals.length - 1];
  svg.setAttribute("aria-label", `${metric}: ${pts.length} results, latest ${fmt.num(lastV)}${base?.baseline != null ? `, baseline ${fmt.num(base.baseline)} ± ${base.tolerance}` : ""}`);
  svg.style.width = `${W}px`;
  svg.style.height = `${H}px`;
  const add = (tag: string, attrs: Record<string, string | number>) => {
    const el = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    svg.append(el);
    return el;
  };
  if (base?.baseline != null) {
    add("rect", { x: 0, y: y(base.baseline + base.tolerance), width: W, height: Math.max(1, y(base.baseline - base.tolerance) - y(base.baseline + base.tolerance)), fill: token("adlib-tint"), stroke: token("staff"), "stroke-dasharray": "4 3" });
    add("line", { x1: 0, x2: W, y1: y(base.baseline), y2: y(base.baseline), stroke: token("staff"), "stroke-width": 1 });
  }
  add("polyline", { points: pts.map((p, i) => `${x(i)},${y(p.c!.value!)}`).join(" "), fill: "none", stroke: token("m1"), "stroke-width": 2 });
  pts.forEach((p, i) => {
    const bad = p.c!.status === "regressed";
    add(bad ? "rect" : "circle", bad
      ? { x: x(i) - 4, y: y(p.c!.value!) - 4, width: 8, height: 8, fill: token("error") }
      : { cx: x(i), cy: y(p.c!.value!), r: 3, fill: token("m1") });
  });
  return svg as unknown as HTMLElement;
}
