// Benchmarks: run suites, see the regression gate and the trend per metric.
import { api, TimedOut } from "../api/client";
import type { BenchRun, SuiteInfo, SuiteResult, SuiteRun } from "../api/types";
import { t } from "../i18n";
import { announce, clear, errorNotice, fmt, h, infoTip, loading, pill, rebuild, table, token, viewHead } from "../ui/dom";

export function benchView(root: HTMLElement): void {
  const suitesEl = h("div", {}, loading());
  const lastEl = h("div", { "aria-live": "polite" });
  const trendEl = h("div", {}, loading());
  clear(root,
    viewHead(t("nav.bench"), [t("bench.purpose"), " ", infoTip(t("bench.gateTerm"), t("bench.gateTip"))]),
    h("section", { "aria-labelledby": "suites-h" }, h("h2", { id: "suites-h" }, t("bench.suites")), suitesEl),
    lastEl,
    h("section", { "aria-labelledby": "trend-h" }, h("h2", { id: "trend-h" }, t("bench.trend")), trendEl));

  let hist: SuiteRun[] = [];
  let suites: SuiteInfo[] = [];
  // One suite runs at a time; while it does, every Run button is disabled, whenever the table is redrawn.
  let running = false;
  const renderSuites = () => rebuild([suitesEl], () => clear(suitesEl, suiteTable(suites, hist, running, async (name, mode) => {
    if (running) return;
    running = true;
    renderSuites();
    clear(lastEl, h("section", { "aria-labelledby": "last-h" }, h("h2", { id: "last-h" }, t("bench.latest")), loading(t("bench.running", { name, mode }))));
    try {
      const run = await api.runSuite(name, mode);
      clear(lastEl, h("section", { "aria-labelledby": "last-h" }, h("h2", { id: "last-h" }, t("bench.latest")), benchResult(run)));
      announce(t("bench.gateAnnounce", { name, state: run.passed ? t("bench.passed") : t("bench.failed") }));
      await loadTrend();
    } catch (e) {
      // Studio stopped waiting, but the engine carries on: the result lands in the history.
      clear(lastEl, e instanceof TimedOut ? h("div", { class: "notice", role: "status" },
        h("p", { class: "notice-title" }, h("strong", {}, t("bench.stillRunning", { name }))),
        h("p", {}, t("bench.stillRunningBody", { min: Math.round(e.seconds / 60) }))) : errorNotice(e));
      if (e instanceof TimedOut) void loadTrend();
    } finally {
      running = false;
      renderSuites();
    }
  })));
  const loadTrend = () => api.suiteHistory().then((hh) => {
    hist = hh;
    clear(trendEl, trend(hh));
    if (suites.length) renderSuites();
  }).catch((e) => clear(trendEl, errorNotice(e)));
  api.suites().then((s) => {
    suites = s;
    renderSuites();
  }).catch((e) => clear(suitesEl, errorNotice(e)));
  void loadTrend();
}

function suiteTable(suites: SuiteInfo[], hist: SuiteRun[], running: boolean, run: (name: string, mode: "cached" | "live") => void): HTMLElement {
  const btn = (name: string, mode: "cached" | "live", label?: string, cls = "ghost") =>
    h("button", { type: "button", class: cls, "data-key": `run:${name}:${mode}`, "aria-disabled": running ? "true" : null, "aria-label": label ? null : mode === "cached" ? t("bench.runName", { name }) : t("bench.runLiveName", { name }), onclick: () => run(name, mode) },
      label ?? (mode === "cached" ? t("bench.run") : t("bench.runLive")));
  const latest = (name: string) => [...hist].filter((r) => r.suite === name).sort((a, b) => b.time - a.time)[0];
  const rows = (list: SuiteInfo[]) => list.map((s) => {
    const last = latest(s.name);
    return [
      // Compact rows: the id and what the suite needs sit in the info tip.
      h("span", { class: "suite" }, h("span", {}, s.description.charAt(0).toUpperCase() + s.description.slice(1)),
        infoTip(s.name, `${s.name}${s.requires.length ? ` · ${t("bench.needsTip", { r: s.requires.join(", ") })}` : ""}`)),
      last ? h("span", { class: "row last" }, pill(last.status), h("span", { class: "muted" }, fmt.date(last.time))) : h("span", { class: "muted" }, t("bench.never")),
      h("span", { class: "row" }, btn(s.name, "cached"), s.cpu ? null : btn(s.name, "live")),
    ];
  });
  const head = [t("bench.col.suite"), t("bench.col.last"), ""];
  const cpu = suites.filter((s) => s.cpu);
  const gpu = suites.filter((s) => !s.cpu);
  return h("div", {},
    h("div", { class: "actions" }, btn("cpu", "cached", t("bench.runAllCpu"), "primary"), btn("all", "cached", t("bench.runAllGpu"))),
    cpu.length ? [h("h3", {}, t("bench.cpuGroup")), table(t("bench.cpuGroup"), head, rows(cpu), { hideCaption: true })] : null,
    gpu.length ? [h("h3", {}, t("bench.gpuGroup")), table(t("bench.gpuGroup"), head, rows(gpu), { hideCaption: true })] : null);
}

export function benchResult(run: BenchRun): HTMLElement {
  return h("div", { class: "stack" },
    h("p", { class: "row" }, pill(run.passed ? "pass" : "fail"), t("bench.gate", { state: run.passed ? t("bench.passed") : t("bench.failed"), target: run.target, mode: run.mode }),
      h("span", { class: "small muted" }, `${fmt.date(run.created)} · git ${fmt.hash(run.git_sha)} · ${run.device ?? "–"}`)),
    run.suites.map(suiteResult));
}

function suiteResult(r: SuiteResult): HTMLElement {
  return h("div", { class: "card" },
    h("h3", { class: "row" }, h("span", { class: "mono" }, r.suite), pill(r.status), h("span", { class: "small muted" }, fmt.seconds(r.seconds))),
    r.reason ? h("p", { class: "small" }, r.reason) : null,
    r.checks?.length ? table(t("bench.checks", { suite: r.suite }), [t("bench.col.metric"), t("bench.col.value"), t("bench.col.baseline"), t("bench.col.delta"), t("bench.col.tol"), t("bench.col.status")],
      r.checks.map((c) => [h("span", { class: "mono small" }, c.metric), fmt.num(c.value), fmt.num(c.baseline),
        c.value !== null && c.baseline !== null ? fmt.signed(c.value - c.baseline) : "–", `±${c.tolerance}`, pill(c.status)]), { hideCaption: true })
      : h("p", { class: "hint" }, t("bench.noChecks")));
}

/** Per suite: each metric's latest gate check with a sparkline over all stored runs (baseline band shaded). */
function trend(hist: SuiteRun[]): HTMLElement {
  if (!hist.length) return h("p", {}, t("bench.noHistory"));
  const bySuite = new Map<string, SuiteRun[]>();
  for (const r of [...hist].sort((a, b) => a.time - b.time)) (bySuite.get(r.suite) ?? bySuite.set(r.suite, []).get(r.suite)!).push(r);
  const out: HTMLElement[] = [];
  for (const [suite, runs] of bySuite) {
    const last = runs[runs.length - 1];
    const metrics = [...new Set(runs.flatMap((r) => r.checks.map((c) => c.metric)))];
    // Suites that pass start collapsed; failing ones open.
    out.push(h("details", { class: "card", open: last.status !== "pass" },
      h("summary", {}, h("span", { class: "row", style: "display:inline-flex" }, h("strong", { class: "mono" }, suite), pill(last.status), h("span", { class: "small muted" }, runs.length === 1 ? t("bench.run1", { when: fmt.date(last.time) }) : t("bench.runs", { n: runs.length, when: fmt.date(last.time) })))),
      table(t("bench.gateOver", { suite }), [t("bench.col.metric"), t("bench.col.latest"), t("bench.col.baseline"), t("bench.col.delta"), t("bench.col.status"), t("bench.col.trend")], metrics.map((m) => {
        const c = last.checks.find((x) => x.metric === m);
        return [h("span", { class: "mono small" }, m), fmt.num(c?.value), c?.baseline != null ? `${fmt.num(c.baseline)} ± ${c.tolerance}` : "–",
          c && c.value !== null && c.baseline !== null ? fmt.signed(c.value - c.baseline) : "–", c ? pill(c.status) : "–", sparkline(m, runs)];
      }), { hideCaption: true }),
      h("details", {}, h("summary", {}, t("bench.allResults", { n: runs.length, suite })),
        table(t("bench.history", { suite }), [t("bench.col.when"), t("bench.col.status"), t("bench.col.git"), t("bench.col.device"), ...metrics], runs.slice().reverse().map((r) => [
          fmt.date(r.time), pill(r.status), h("span", { class: "mono small" }, fmt.hash(r.git_sha)), r.device ?? "–",
          ...metrics.map((m) => {
            const c = r.checks.find((x) => x.metric === m);
            return c ? `${fmt.num(c.value)}${c.status !== "pass" ? ` (${t(`status.${c.status}`)})` : ""}` : "–";
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
  svg.setAttribute("aria-label", t("bench.spark", { metric, n: pts.length, v: fmt.num(lastV) }) + (base?.baseline != null ? t("bench.sparkBase", { b: fmt.num(base.baseline), t: base.tolerance }) : ""));
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
