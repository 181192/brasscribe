// One run: live stage graph over SSE and the stage inspector.
import { api, fetchBytes, fetchText, isAbort, subscribe, type StreamState } from "../api/client";
import type { Composition, FileRef, Job, Manifest, Reference, StageFiles, ValidationIssue } from "../api/types";
import { audioPanel, type AudioSource } from "../components/audio";
import { BeatView } from "../components/beats";
import { PianoRoll, type RollLayer } from "../components/pianoroll";
import type { ScoreElement } from "../components/score";
import { stageLabel, StageGraph } from "../components/stagegraph";
import { StemsMixer } from "../components/stems";
import { runTitle } from "./runs";
import { compositionBeats, compositionFreeTime, parseBeats, tickTime } from "../lib/beats";
import { maxOf, minOf } from "../lib/extent";
import { fromJob, reduce, totals, type RunView } from "../lib/events";
import { parseMidi } from "../lib/midi";
import { stageTime, waitNote } from "../lib/stagetime";
import { parseMusicXml, type XmlScore } from "../lib/musicxml";
import { pitchName, validateScore } from "../lib/validate";
import { t } from "../i18n";
import { announce, clear, errorNotice, fmt, h, infoTip, loading, menu, more, panel, pill, rebuild, table, tabs } from "../ui/dom";
import { icon } from "../ui/icons";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const TAB_FOR_KIND: Record<string, string> = {
  beats: "beats", stems: "stems", separate: "stems", layers: "audio", transcribe: "roll", vote: "roll",
  arrange: "score", export: "musicxml",
};
const MODEL_STYLE: Record<string, { colour: string; style: RollLayer["style"]; label: string }> = {
  muscriptor: { colour: "bc-model-1", style: "line", label: "MuScriptor" },
  "basic-pitch": { colour: "bc-model-2", style: "dashed", label: "Basic Pitch" },
  "swift-f0": { colour: "bc-model-3", style: "dotted", label: "SwiftF0" },
};
const AUDIO = /\.(wav|flac|mp3|ogg|m4a|aiff?)$/i;

interface Ctx {
  id: string;
  job: Job;
  stages: StageFiles[] | Error;
  composition: Promise<Composition>;
  musicxml: Promise<string>;
}

export function runView(root: HTMLElement, id: string, tab?: string, _q?: URLSearchParams): () => void {
  const heading = h("h1", {}, t("run.title"));
  const header = h("div", {}, loading());
  // While the progress stream is down: the browser reconnects by itself, or (once it gives up) Try again.
  const streamNote = h("div", { class: "hint", role: "status", hidden: true });
  const graph = h("bs-stage-graph", {}) as StageGraph;
  const stageInfo = h("div", {});
  const inspectorH = h("h2", { id: "inspector-h", class: "visually-hidden" }, t("run.inspector"));
  const inspector = h("section", { "aria-labelledby": "inspector-h" }, inspectorH, loading());
  const actions = h("div", { class: "actions" });
  // The page is for the score: header, then the inspector (score first), then the
  // stage graph as a disclosure, closed when the run succeeded and open when it failed.
  const stagesCount = h("span", { class: "count" });
  const stagesBox = h("details", { class: "more stages-box" },
    h("summary", {}, h("h2", { id: "graph-h", class: "in-summary" }, t("run.stages")), stagesCount),
    h("div", { class: "graph-head" },
      h("p", { class: "graph-legend" },
        h("span", {}, h("span", { class: "key ran", "aria-hidden": "true" }), t("run.legend.ran")),
        h("span", {}, h("span", { class: "key cache", "aria-hidden": "true" }), t("run.legend.cache")),
        h("span", {}, h("span", { class: "key thick", "aria-hidden": "true" }), t("run.legend.thick"))),
      infoTip(t("run.stages"), t("run.stagesTip"))),
    h("div", { class: "graph-scroll" }, graph),
    h("p", { class: "hint" }, t("run.stagesChoose")),
    stageInfo);
  clear(root,
    h("a", { class: "back-link", href: "#/runs" }, icon("back"), t("run.back")),
    h("div", { class: "view-head" }, h("div", { class: "view-title" }, heading, header, streamNote), actions),
    inspector,
    h("section", { "aria-labelledby": "graph-h", class: "stages-section" }, stagesBox));
  let stagesOpened = false;

  let stop: (() => void) | null = null;
  // Leaving the page cancels what is still loading; nothing is shown or subscribed after that.
  const ctl = new AbortController();
  const { signal } = ctl;
  let view: RunView | null = null;
  let stages: StageFiles[] | Error = new Error("not loaded");
  let tabsEl: HTMLElement | null = null;
  // The inspector tab last chosen; the inspector is rebuilt on it when the run finishes.
  let currentTab = tab ?? "score";
  let selectTab: ((id: string) => void) | null = null;

  // The progress line changes with every stage; the rest of the header and the actions only when
  // the run's status or outputs do, so a control someone is using stays where it is.
  const summary = h("p", { class: "run-summary" });
  const headRest = h("div", {});
  // What went wrong with an action (Re-run), apart from the rest so it survives the next update.
  const actionNote = h("div", {});
  let restKey = "";
  const renderHeader = (job: Job, m: Manifest | null) => {
    heading.textContent = runTitle(job);
    const tot = view ? totals(view) : null;
    // Essentials first: status and progress; ids, git and devices sit behind "Run details".
    clear(summary, pill(job.status),
      tot ? h("span", {}, t("run.progressShort", { done: tot.done, total: tot.total, cached: tot.cached, seconds: fmt.seconds(tot.seconds) })) : null,
      tot && !TERMINAL.has(job.status) ? h("progress", { class: "progress", max: tot.total, value: tot.done, "aria-label": t("run.stagesFinished") }) : null);
    if (tot) stagesCount.textContent = ` · ${t("run.progressShort", { done: tot.done, total: tot.total, cached: tot.cached, seconds: fmt.seconds(tot.seconds) })}`;
    if (header.firstChild !== summary) clear(header, summary, headRest, actionNote);
    const key = JSON.stringify([job.id, job.status, job.error ?? null, job.outputs ?? [], job.previous_run_id ?? null, m?.run_id ?? null]);
    if (key !== restKey) {
      restKey = key;
      rebuild([headRest, actions], () => renderRest(job, m));
    }
    // Open the stages on failure, with the failing stage selected (once, so a user's choice stands).
    if (!stagesOpened && job.status !== "succeeded") {
      stagesOpened = true;
      stagesBox.open = true;
      const bad = view?.stages.find((s) => s.status === "failed");
      if (bad) queueMicrotask(() => showStage(bad.name, false));
    }
  };

  const renderRest = (job: Job, m: Manifest | null) => {
    clear(headRest,
      job.error ? errorSummary(job.error) : null,
      job.previous_run_id ? h("p", {}, h("a", { href: `#/compare?a=${encodeURIComponent(job.previous_run_id)}&b=${encodeURIComponent(job.id)}` }, t("run.compareRerun"))) : null,
      more(t("run.details"), h("dl", { class: "kv run-details" },
        h("dt", {}, t("run.kv.id")), h("dd", { class: "mono" }, job.id),
        h("dt", {}, t("runs.profile")), h("dd", {}, job.profile),
        m?.git ? [h("dt", {}, "Git"), h("dd", { class: "mono" }, fmt.hash(m.git.sha).slice(0, 7), m.git.dirty ? t("run.dirty") : "")] : null,
        m?.devices?.length ? [h("dt", {}, t("manifest.kv.devices")), h("dd", {}, m.devices.join(", "))] : null,
        lineupRow(job.profile, m?.params),
        seatRows(m?.params),
        h("dt", {}, t("run.kv.created")), h("dd", {}, fmt.date(job.created)))));
    // Built on demand: the same links also sit in More on narrow screens, and a node lives in one place only.
    const downloads = (cls = "") => [
      job.outputs?.includes("brass-band.musicxml") ? h("a", { class: `button ${cls}`, href: api.musicxmlUrl(job.id), download: "" }, icon("file"), t("run.dl.musicxml")) : null,
      job.outputs?.includes("brass-band.pdf") ? h("a", { class: `button ${cls}`, href: api.pdfUrl(job.id) }, icon("file"), t("run.dl.pdf")) : null,
      job.outputs?.includes("brass-band.mid") ? h("a", { class: `button ${cls}`, href: api.midiUrl(job.id), download: "" }, icon("file"), t("run.dl.midi")) : null,
    ].filter(Boolean);
    const compare = (cls = "") => h("a", { class: `button ${cls === "narrow-only" ? "" : "ghost"} ${cls}`, href: `#/compare?a=${encodeURIComponent(job.id)}` }, t("run.compare"));
    // Re-run is the page's primary only when the run failed; otherwise Play (in the score) is.
    const rerun = TERMINAL.has(job.status) ? h("button", { type: "button", class: job.status === "succeeded" ? "ghost" : "primary", onclick: async (e: Event) => {
      const b = e.currentTarget as HTMLButtonElement;
      b.disabled = true;
      clear(actionNote);
      try {
        const j = await api.rerun(job.id, { allow_heavy: false, cold: [] });
        announce(t("manifest.rerunStarted", { id: j.id }));
        location.hash = `#/runs/${encodeURIComponent(j.id)}`;
      } catch (x) {
        b.disabled = false;
        clear(actionNote, errorNotice(x));
      }
    } }, icon("retry"), t("manifest.rerunBtn")) : null;
    clear(actions,
      !TERMINAL.has(job.status) ? h("button", { type: "button", class: "ghost", onclick: async (e: Event) => {
        const b = e.currentTarget as HTMLButtonElement;
        b.disabled = true;
        clear(actionNote);
        try {
          await api.cancel(job.id);
          announce(t("run.cancelRequested"));
        } catch (x) {
          clear(actionNote, errorNotice(x));
        } finally {
          b.disabled = false;
        }
      } }, icon("close"), t("run.cancel")) : null,
      // Below 600 px the row is Re-run and More only; Download and Compare move into More.
      downloads().length ? menu([icon("export"), t("run.download")], downloads(), { className: "wide-only" }) : null,
      compare("wide-only"),
      rerun,
      TERMINAL.has(job.status) ? menu(t("run.moreActions"), [...downloads("narrow-only"), compare("narrow-only"), deleteButton(job.id)]) : null);
  };

  const showStage = (name: string, switchTab = true) => {
    graph.select(name);
    const s = view?.stages.find((x) => x.name === name);
    const files = Array.isArray(stages) ? stages.find((x) => x.stage === name) : undefined;
    const status = s?.status ?? files?.status ?? "unknown";
    clear(stageInfo, h("div", { class: "card", role: "region", "aria-label": t("run.stage", { name: stageLabel(name) }) },
      h("h3", {}, stageLabel(name), " ", h("span", { class: "mono muted" }, name)),
      h("dl", { class: "kv" },
        h("dt", {}, t("run.kv.status")), h("dd", {}, pill(status)),
        h("dt", {}, t("run.kv.time")), h("dd", {}, stageTime(s?.seconds != null ? s : files)),
        h("dt", {}, t("run.kv.device")), h("dd", {}, s?.device ?? files?.device ?? "–")),
      waitNote(s?.seconds != null ? s : files),
      status === "failed" && view?.error ? errorSummary(view.error) : null,
      files ? more(t("run.filesKey"), [
        h("dl", { class: "kv" }, h("dt", {}, t("run.kv.key")), h("dd", { class: "mono" }, fmt.hash(files.key))),
        fileTable(files.files)], { count: files.files.length }) : Array.isArray(stages) ? null : errorNotice(stages)));
    const kind = s?.kind ?? files?.kind ?? name.split(".")[0];
    const tab = TAB_FOR_KIND[kind];
    if (switchTab && tab && selectTab) selectTab(tab);
  };
  graph.addEventListener("select", (e) => showStage((e as CustomEvent<string>).detail));

  const start = async () => {
    const job = await api.job(id, { signal });
    if (signal.aborted) return;
    view = fromJob(job);
    graph.update(view);
    const [m, st] = await Promise.all([api.manifest(id, { signal }).catch(() => null), api.stages(id, { signal }).catch((e) => e as Error)]);
    if (signal.aborted) return;
    stages = st;
    renderHeader(job, m);
    if (!TERMINAL.has(job.status)) {
      stop = subscribe(id, (e) => {
        view = reduce(view!, e);
        graph.update(view);
        if (e.type === "job" && e.status && TERMINAL.has(e.status)) {
          announce(t("run.ended", { status: t(`status.${e.status}`) }));
          stop?.();
          stop = null;
          void load(); // reload outputs and the inspector
        } else if (e.type !== "log") renderHeader({ ...job, status: view.status as Job["status"] }, m);
      }, (s) => showStream(s));
    }
    const ctx: Ctx = {
      id, job, stages: st,
      composition: api.composition(id, { signal }),
      musicxml: fetchText(`/v1/jobs/${encodeURIComponent(id)}/musicxml`, undefined, { signal }),
    };
    ctx.composition.catch(() => undefined);
    ctx.musicxml.catch(() => undefined);
    const items = [
      { id: "score", label: t("tab.score"), render: (p: HTMLElement) => scoreTab(p, ctx) },
      { id: "audio", label: t("tab.audio"), render: (p: HTMLElement) => audioTab(p, ctx) },
      { id: "stems", label: t("tab.stems"), render: (p: HTMLElement) => stemsTab(p, ctx) },
      { id: "roll", label: t("tab.roll"), render: (p: HTMLElement) => rollTab(p, ctx) },
      { id: "beats", label: t("tab.beats"), render: (p: HTMLElement) => beatsTab(p, ctx) },
      { id: "voices", label: t("tab.voices"), render: (p: HTMLElement) => voicesTab(p, ctx) },
      { id: "musicxml", label: t("tab.musicxml"), render: (p: HTMLElement) => musicxmlTab(p, ctx) },
      { id: "manifest", label: t("tab.manifest"), render: (p: HTMLElement) => manifestTab(p, ctx, m) },
    ];
    tabsEl = tabs(t("run.inspectorViews"), items, currentTab, (sel) => {
      currentTab = sel;
      history.replaceState(null, "", `#/runs/${encodeURIComponent(id)}/${sel}`);
    });
    selectTab = (sel) => tabsEl?.querySelector<HTMLButtonElement>(`[role=tab][data-id="${sel}"]`)?.click();
    clear(inspector, inspectorH, tabsEl);
  };
  const showStream = (s: StreamState) => {
    streamNote.hidden = s === "open";
    if (s === "reconnecting") clear(streamNote, t("run.reconnecting"));
    else if (s === "closed") {
      stop?.();
      stop = null;
      clear(streamNote, h("p", {}, t("run.streamLost")),
        h("p", {}, h("button", { type: "button", class: "ghost", onclick: () => {
          streamNote.hidden = true;
          void load();
        } }, t("err.retry"))));
    }
  };
  const load = () => start().catch((e) => {
    if (!signal.aborted && !isAbort(e)) clear(header, errorNotice(e));
  });
  void load();
  return () => {
    ctl.abort();
    stop?.();
    stop = null;
  };
}

/** A failed run: the first line of the error in words; the traceback behind "Full error". */
function errorSummary(error: string): HTMLElement {
  const [first, ...rest] = error.trim().split("\n");
  const m = first.match(/^([\w.-]+): (\w+): (.*)$/);
  return h("div", { class: "notice notice-error", role: "alert" },
    h("p", { class: "notice-title" }, h("strong", {}, m ? t("run.failedAt", { stage: stageLabel(m[1]) }) : t("run.failedShort"))),
    h("p", {}, (m ? m[3] : first).replace(/:?\s*Traceback \(most recent call last\):?\s*$/, "")),
    rest.length ? more(t("run.fullError"), h("pre", { class: "json", tabindex: 0 }, error)) : null);
}

function fileTable(files: FileRef[]): HTMLElement {
  return table(t("run.files"), [t("run.col.file"), t("run.col.size"), t("run.col.sha")], files.map((f) => [
    h("a", { href: f.url }, f.name), fmt.bytes(f.bytes), h("span", { class: "mono small" }, fmt.hash(f.sha256)),
  ]));
}

function stageFiles(ctx: Ctx, pred: (s: StageFiles) => boolean): { stage: StageFiles; file: FileRef }[] {
  if (!Array.isArray(ctx.stages)) return [];
  return ctx.stages.filter(pred).flatMap((s) => s.files.map((file) => ({ stage: s, file })));
}

// ---------------------------------------------------------------- tabs

function scoreTab(p: HTMLElement, ctx: Ctx): void {
  if (TERMINAL.has(ctx.job.status) && !ctx.job.outputs?.includes("brass-band.musicxml")) {
    clear(p, h("div", { class: "empty", role: "note" }, h("p", {}, h("strong", {}, t("run.noScore"))), h("p", { class: "hint" }, t("run.noScoreBody"))));
    return;
  }
  const score = h("bs-score", {}) as ScoreElement;
  const status = h("p", { class: "hint", role: "status" }, t("score.loading"));
  const checks = h("section", { "aria-labelledby": "checks-h", class: "checks" }, h("h3", { id: "checks-h" }, t("side.checks")), loading());
  clear(p, status, score, checks);
  ctx.musicxml.then(async (xml) => {
    const t0 = performance.now();
    await score.load(xml, ctx.job.title ?? ctx.id);
    // Where each part comes from; an older engine without the endpoint just shows the names.
    api.partSources(ctx.id).then((r) => { score.sources = r.parts; }).catch(() => undefined);
    status.textContent = t("score.rendered", { bars: score.bars.length, parts: score.api?.score?.tracks.length ?? 0, ms: Math.round(performance.now() - t0) });
    await renderChecks(checks, ctx, parseMusicXml(xml), score);
  }).catch((e) => clear(p, errorNotice(e)));
}

/** Notes per transcription model (Piano roll tab). */
async function notesBySource(el: HTMLElement, ctx: Ctx): Promise<void> {
  const models = stageFiles(ctx, (s) => s.kind === "transcribe").filter(({ file }) => /\.midi?$/i.test(file.name));
  const pattern: Record<string, string> = {
    muscriptor: "background:var(--bc-model-1)",
    "basic-pitch": "background:repeating-linear-gradient(45deg,var(--bc-model-2) 0 3px,transparent 3px 5px);box-shadow:inset 0 0 0 1px var(--bc-model-2)",
    "swift-f0": "background:repeating-linear-gradient(90deg,var(--bc-model-3) 0 2px,transparent 2px 4px);box-shadow:inset 0 0 0 1px var(--bc-model-3)",
  };
  const rows: (string | HTMLElement)[][] = [];
  for (const { stage, file } of models) {
    const model = stage.stage.split(".").slice(2).join(".");
    const layer = stage.stage.split(".")[1] ?? "";
    try {
      const n = parseMidi(await fetchBytes(file.url)).notes.length;
      rows.push([h("span", {}, h("span", { class: "sw", "aria-hidden": "true", style: pattern[model] ?? "background:var(--bc-model-4)" }), `${MODEL_STYLE[model]?.label ?? model}`),
        layer, h("span", { class: "num" }, String(n))]);
    } catch {
      /* skip unreadable files */
    }
  }
  clear(el, h("h3", {}, t("side.bySource")),
    rows.length ? table(t("side.bySource"), [t("side.model"), t("side.layer"), t("side.notes")], rows, { hideCaption: true }) : h("p", { class: "hint" }, t("side.noModels")));
}

type Issue = ValidationIssue & { source: string; upper?: string };

/** Engine messages speak in ticks; say bar and beat instead. */
/** The job's seat options (seat, reads, lead) as run details, when the job has them. */
export function seatRows(params: Record<string, unknown> | undefined): HTMLElement[] {
  const p = params ?? {};
  const rows: HTMLElement[] = [];
  if (typeof p.seat === "string") rows.push(h("dt", {}, t("run.kv.seat")), h("dd", {}, seatName(p.seat)));
  if (p.reads === "treble" || p.reads === "bass") rows.push(h("dt", {}, t("run.kv.reads")), h("dd", {}, t(`run.reads.${p.reads}`)));
  if (p.lead === "seat") rows.push(h("dt", {}, t("run.kv.lead")), h("dd", {}, t("run.lead.seat")));
  return rows;
}

/**
 * The band the job's score is made for, as the engine arranges it: a brass-band or pop recording is
 * always the small band or the quartet (only the layered arranger writes the full band), a solo take
 * for a seat is that one part.
 */
export function madeLineup(profile: string, params: Record<string, unknown> | undefined): "full" | "minimal" | "quartet" | "one" {
  const p = params ?? {};
  if (profile === "brass-band" || profile === "pop-rock") return p.lineup === "quartet" ? "quartet" : "minimal";
  if (profile === "solo") return typeof p.seat === "string" ? "one" : "minimal";
  return p.lineup === "minimal" || p.lineup === "quartet" ? p.lineup : "full";
}

export function lineupRow(profile: string, params: Record<string, unknown> | undefined): HTMLElement[] {
  return [h("dt", {}, t("run.kv.lineup")), h("dd", {}, t(`run.lineup.${madeLineup(profile, params)}`))];
}

/** A seat id as its band part name ("1st-baritone" -> "1st Baritone"; "eb-bass" -> "E♭ Bass"). */
export function seatName(seat: string): string {
  const special: Record<string, string> = { "eb-bass": "E♭ Bass", "bb-bass": "B♭ Bass" };
  return special[seat] ?? seat.split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

export function plainMessage(w: ValidationIssue): string {
  const where = w.bar ? t("warn.where", { bar: w.bar, beat: w.beat ? Math.round(w.beat * 100) / 100 : 1 }) : "";
  if (/phrase at tick \d+ (needed per-note octave fitting|split at its leaps to fit the range)|moved \d+ to \d+ at tick \d+/.test(w.message) && w.part) return t("warn.octaveFit", { part: w.part, where });
  return where ? w.message.replace(/\bat tick \d+/, where) : w.message.replace(/\s*at tick \d+/, "");
}

/**
 * Below the score: the round trip, then one line per kind of problem and part
 * ("12 crossings: 2nd Trombone above 1st Trombone, bars 47–126"), each with a
 * button to its first bar; the full table sits behind "Show all".
 */
async function renderChecks(el: HTMLElement, ctx: Ctx, xml: XmlScore, score: ScoreElement): Promise<void> {
  const [engine, rt] = await Promise.all([api.validation(ctx.id).catch((e) => e as Error), api.roundtrip(ctx.id).catch(() => null)]);
  const local = validateScore(xml);
  const rows: Issue[] = [
    ...(Array.isArray(engine) ? engine.map((w) => ({ ...w, source: t("warn.arranger") })) : []),
    ...local.filter((w) => w.kind === "crossing" || !Array.isArray(engine)).map((w) => ({ ...w, source: t("warn.studio") })),
  ];
  const go = (bar: number | null | undefined, label?: string) => h("button", { type: "button", class: "ghost", onclick: () => { score.goBar((bar ?? 1) - 1); score.focusScore(); } }, label ?? t("warn.barBtn", { n: bar ?? "?" }));
  const groups = new Map<string, Issue[]>();
  for (const r of rows) {
    const k = `${r.kind}|${r.part ?? ""}|${r.upper ?? ""}`;
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(r);
  }
  const lines = [...groups.values()].sort((a, b) => b.length - a.length).map((g) => {
    const r = g[0];
    const bars = g.map((x) => x.bar ?? 0).filter(Boolean);
    const lo = minOf(bars, (b) => b);
    const hi = maxOf(bars, (b) => b);
    const who = r.kind === "crossing" && r.upper ? t("checks.above", { lower: r.part ?? "?", upper: r.upper }) : r.part ?? "–";
    const kind = t(`checks.kind.${r.kind}${g.length === 1 ? "1" : ""}`) === `checks.kind.${r.kind}${g.length === 1 ? "1" : ""}` ? r.kind : t(`checks.kind.${r.kind}${g.length === 1 ? "1" : ""}`);
    const range = !bars.length ? "" : lo === hi ? t("checks.bar", { n: lo }) : t("checks.bars", { a: lo, b: hi });
    return h("li", {}, h("span", { class: "pill-warning", "aria-hidden": "true" }, icon("error")),
      h("span", {}, t("checks.line", { n: g.length, kind, who }), range ? `, ${range}` : ""),
      bars.length ? go(lo) : null);
  });
  const rtLine = h("li", {},
    !rt || rt.status === "not_run" ? h("span", { class: "muted", "aria-hidden": "true" }, "–") : rt.status === "pass" ? h("span", { class: "diff-added", "aria-hidden": "true" }, icon("done")) : h("span", { class: "pill-warning", "aria-hidden": "true" }, icon("error")),
    h("span", {}, !rt || rt.status === "not_run" ? t("side.rtNotRun") : rt.status === "pass" ? t("side.rtPass") : t("side.rtFail")));
  clear(el, h("h3", { id: "checks-h" }, t("side.checks"), infoTip(t("side.checks"), t("warn.hint"))),
    Array.isArray(engine) ? null : errorNotice(engine),
    h("ul", { class: "check-lines" },
      rows.length ? lines : h("li", {}, h("span", { class: "diff-added", "aria-hidden": "true" }, icon("done")), h("span", {}, t("checks.none"))),
      rtLine),
    rows.length ? more(t("checks.all"), [
      table(t("warn.title"), [t("warn.col.bar"), t("warn.col.part"), t("warn.col.kind"), t("warn.col.message"), t("warn.col.source")],
        rows.slice(0, 300).map((r) => [go(r.bar), r.part ?? "–", r.kind, plainMessage(r), r.source]),
        { hideCaption: true }),
      rows.length > 300 ? h("p", { class: "hint" }, t("warn.first", { n: 300, total: rows.length })) : null,
    ], { count: rows.length }) : null);
}

function audioTab(p: HTMLElement, ctx: Ctx): void {
  const sources: AudioSource[] = [];
  if (ctx.job.outputs?.includes("brass-band.mp3")) sources.push({ label: t("audio.rendered"), url: api.renderedAudioUrl(ctx.id) });
  for (const { stage, file } of stageFiles(ctx, (s) => s.kind === "layers" || s.kind === "stems" || s.kind === "separate")) {
    if (AUDIO.test(file.name)) sources.push({ label: `${stage.stage}/${file.name}`, url: file.url });
  }
  const original: AudioSource = { label: t("audio.original"), url: api.inputAudioUrl(ctx.id) };
  const sel = h("select", { id: "audio-a" }, sources.map((s, i) => h("option", { value: String(i) }, s.label)));
  const holder = h("div", {});
  const show = () => {
    const a = sources[Number(sel.value)];
    clear(holder, audioPanel(a ? [a, original] : [original]));
  };
  sel.addEventListener("change", show);
  clear(p,
    h("p", {}, t("audio.intro")),
    Array.isArray(ctx.stages) ? null : errorNotice(ctx.stages),
    sources.length ? h("div", { class: "row" }, h("label", { for: "audio-a" }, t("audio.sourceA")), sel) : null,
    holder);
  show();
}

function stemsTab(p: HTMLElement, ctx: Ctx): void {
  if (!Array.isArray(ctx.stages)) {
    clear(p, errorNotice(ctx.stages));
    return;
  }
  const stems = stageFiles(ctx, (s) => s.kind === "layers" || s.kind === "stems" || s.kind === "separate")
    .filter(({ file }) => AUDIO.test(file.name))
    .map(({ stage, file }) => ({ name: file.name, url: file.url, bytes: file.bytes, group: stage.stage }))
    .sort((a, b) => Number(b.group === "layers") - Number(a.group === "layers"));
  if (!stems.length) {
    clear(p, h("p", {}, t("stems.none")));
    return;
  }
  const mixer = h("bs-stems", {}) as StemsMixer;
  mixer.data = stems;
  clear(p, mixer);
  const layers = stems.find((s) => s.group === "layers");
  if (layers) void mixer.preload("layers");
}

async function rollTab(p: HTMLElement, ctx: Ctx): Promise<void> {
  clear(p, loading());
  let comp: Composition;
  try {
    comp = await ctx.composition;
  } catch (e) {
    clear(p, errorNotice(e));
    return;
  }
  const transcribes = stageFiles(ctx, (s) => s.kind === "transcribe").filter(({ file }) => /\.midi?$/i.test(file.name));
  const groups = [...new Set([...transcribes.map(({ stage }) => stage.stage.split(".")[1] ?? "all"), ...comp.voices.map((v) => layerGroup(v.layer ?? v.id))])];
  const sel = h("select", { id: "roll-group" }, groups.map((g) => h("option", { value: g }, g)));
  const holder = h("div", {});
  let pending: AbortController | null = null;
  const show = async () => {
    const g = sel.value;
    // A newer choice cancels the files still loading for the one before.
    pending?.abort();
    const ctl = new AbortController();
    pending = ctl;
    clear(holder, loading());
    const layers: RollLayer[] = comp.voices.filter((v) => layerGroup(v.layer ?? v.id) === g).map((v) => ({
      id: v.id, label: t("roll.final", { id: v.id, role: v.role }), colour: "scribe-ink", style: "block" as const,
      notes: v.notes.map((n) => ({
        pitch: n.pitch,
        start: n.onset_s ?? tickTime(comp, n.start),
        end: n.offset_s ?? tickTime(comp, n.start + n.dur),
        confidence: n.confidence,
      })),
    }));
    for (const { stage, file } of transcribes.filter(({ stage }) => (stage.stage.split(".")[1] ?? "all") === g)) {
      const model = stage.stage.split(".").slice(2).join(".") || file.name;
      const st = MODEL_STYLE[model] ?? { colour: "bc-model-4", style: "outline" as const, label: model };
      try {
        const midi = parseMidi(await fetchBytes(file.url, undefined, { signal: ctl.signal }));
        layers.push({ id: stage.stage, label: `${st.label} (${file.name})`, colour: st.colour, style: st.style,
          notes: midi.notes.map((n) => ({ pitch: n.pitch, start: n.start, end: n.end })) });
      } catch {
        /* skip unreadable files */
      }
      if (ctl.signal.aborted) return;
    }
    if (ctl.signal.aborted) return;
    const roll = h("bs-pianoroll", {}) as PianoRoll;
    roll.data = layers;
    clear(holder, roll);
  };
  sel.addEventListener("change", show);
  const sources = h("section", {});
  clear(p,
    h("p", {}, t("roll.intro")),
    Array.isArray(ctx.stages) ? null : errorNotice(ctx.stages),
    h("div", { class: "row" }, h("label", { for: "roll-group" }, t("roll.layer")), sel),
    holder,
    sources);
  void show();
  void notesBySource(sources, ctx);
}

function layerGroup(layer: string): string {
  return ["strings", "brass", "keys", "orchestra"].includes(layer) ? "orchestra" : layer;
}

async function beatsTab(p: HTMLElement, ctx: Ctx): Promise<void> {
  clear(p, loading());
  const rows: { label: string; beats: ReturnType<typeof parseBeats> }[] = [];
  const beatFile = stageFiles(ctx, (s) => s.kind === "beats").find(({ file }) => file.name.endsWith(".beats"));
  if (beatFile) {
    try {
      rows.push({ label: t("beats.tracker"), beats: parseBeats(await fetchText(beatFile.file.url)) });
    } catch {
      /* shown as missing below */
    }
  }
  let free: ReturnType<typeof compositionFreeTime> = [];
  try {
    const comp = await ctx.composition;
    rows.push({ label: t("beats.grid"), beats: compositionBeats(comp) });
    free = compositionFreeTime(comp);
  } catch {
    /* no composition yet */
  }
  if (!rows.length) {
    clear(p, h("p", {}, t("beats.none")));
    return;
  }
  const v = h("bs-beats", {}) as BeatView;
  clear(p, Array.isArray(ctx.stages) ? null : errorNotice(ctx.stages), v);
  v.setData(rows, free);
}

async function voicesTab(p: HTMLElement, ctx: Ctx): Promise<void> {
  await panel(p, () => ctx.composition, (c) => {
    const roles = [...new Set(c.voices.map((v) => v.role))];
    const layers = [...new Set(c.voices.map((v) => v.layer ?? "–"))];
    return [
      h("p", {}, t("voices.summary", { title: c.title, voices: c.voices.length, notes: c.voices.reduce((a, v) => a + v.notes.length, 0),
        metre: c.meters.map((m) => `${m.beats}/${m.beat_unit ?? 4}`).join(", ") || "–", key: c.keys.map((k) => `${k.fifths >= 0 ? "+" : ""}${k.fifths} ${k.mode ?? ""}`).join(", ") || "–" })),
      table(t("voices.title"), [t("voices.col.voice"), t("voices.col.role"), t("voices.col.layer"), t("voices.col.hint"), t("voices.col.notes"), t("voices.col.range"), t("voices.col.conf"), t("voices.col.uncertain"), t("voices.col.sources")],
        c.voices.map((v) => {
          const ps = v.notes.map((n) => n.pitch);
          const conf = v.notes.map((n) => n.confidence ?? 1);
          const srcs = [...new Set(v.notes.flatMap((n) => n.sources ?? []))];
          return [v.id, v.role, v.layer ?? "–", v.instrument_hint ?? "–", String(v.notes.length),
            ps.length ? `${minOf(ps, (p) => p)}–${maxOf(ps, (p) => p)}` : "–",
            conf.length ? fmt.num(conf.reduce((a, b) => a + b, 0) / conf.length, 2) : "–",
            String(conf.filter((x) => x < 0.7).length), srcs.join(", ") || "–"];
        })),
      table(t("voices.byRole"), [t("voices.col.role"), ...layers], roles.map((r) => [
        r, ...layers.map((l) => c.voices.filter((v) => v.role === r && (v.layer ?? "–") === l).map((v) => `${v.id} (${v.notes.length})`).join(", ") || "–"),
      ])),
    ];
  });
}

async function musicxmlTab(p: HTMLElement, ctx: Ctx): Promise<void> {
  const rt = h("section", { "aria-labelledby": "rt-h" }, h("h3", { id: "rt-h" }, t("mx.roundtrip")), loading());
  const parts = h("section", { "aria-labelledby": "parts-h" }, h("h3", { id: "parts-h" }, t("mx.partsTitle")), loading());
  const golden = h("section", { "aria-labelledby": "gold-h" }, h("h3", { id: "gold-h" }, t("mx.reference")), loading());
  clear(p, rt, golden, parts);

  const renderRt = async (run = false) => {
    clear(rt, h("h3", { id: "rt-h" }, t("mx.roundtrip")), loading(run ? t("mx.running") : undefined));
    try {
      const r = run ? await api.runRoundtrip(ctx.id) : await api.roundtrip(ctx.id);
      clear(rt, h("h3", { id: "rt-h" }, t("mx.roundtrip")),
        h("p", { class: "row" }, pill(r.status), r.notes_in != null ? t("mx.readBack", { a: r.notes_in, b: r.notes_out ?? "?" }) : "",
          r.parts != null ? t("mx.parts", { n: r.parts }) : ""),
        r.detail ? h("p", { class: "small" }, r.detail) : null,
        r.part_results?.length ? table(t("mx.rtPerPart"), [t("mx.col.part"), t("mx.col.notes"), t("mx.col.sound"), t("mx.col.match")],
          r.part_results.map((x) => [x.name, String(x.notes), x.sound ?? "–", x.match == null ? "–" : pill(x.match ? "pass" : "fail")])) : null,
        h("button", { type: "button", onclick: () => renderRt(true) }, r.status === "not_run" ? t("mx.run") : t("mx.again")));
      if (run) announce(t("mx.rtDone", { status: t(`status.${r.status}`) }));
    } catch (e) {
      clear(rt, h("h3", { id: "rt-h" }, t("mx.roundtrip")), errorNotice(e));
    }
  };
  void renderRt();

  const refs = await api.references().catch((e) => e as Error);
  const renderGolden = async (ref: Reference) => {
    const out = h("div", {}, loading());
    const sel = h("select", { id: "gold-ref", onchange: () => { const r = (refs as Reference[]).find((x) => x.name === sel.value); if (r) void renderGolden(r); } },
      (refs as Reference[]).map((r) => h("option", { value: r.name, selected: r.name === ref.name }, r.name)));
    clear(golden, h("h3", { id: "gold-h" }, t("mx.reference")), h("div", { class: "row" }, h("label", { for: "gold-ref" }, t("mx.referenceLabel")), sel,
      h("a", { href: `#/compare?a=${encodeURIComponent(ctx.id)}&b=${encodeURIComponent(`ref:${ref.name}`)}` }, t("mx.noteDiff"))), out);
    try {
      const c = await api.compare(ctx.id, { reference: ref.name });
      clear(out,
        h("p", { class: "row" }, pill(c.ok ? "identical" : "different"),
          t("mx.compareSummary", { comp: c.composition_identical ? t("mx.identical") : t("mx.different"), xml: c.musicxml_identical ? t("mx.identical") : t("mx.different"),
            pi: c.parts_identical, pt: c.parts_total, ni: c.notes_identical, nt: c.notes_total })),
        table(t("mx.partsVsRef"), [t("mx.col.part"), t("mx.col.notes"), t("mx.col.refNotes"), t("mx.col.identical")],
          c.parts.map((x) => [x.name, String(x.notes), String(x.reference_notes), pill(x.identical ? "identical" : "different")])));
    } catch (e) {
      clear(out, errorNotice(e));
    }
  };
  if (Array.isArray(refs) && refs.length) void renderGolden(refs.find((r) => r.name.includes("mikkel")) ?? refs[0]);
  else clear(golden, h("h3", { id: "gold-h" }, t("mx.reference")), Array.isArray(refs) ? h("p", {}, t("mx.noRefs")) : errorNotice(refs));

  try {
    const xml = parseMusicXml(await ctx.musicxml);
    clear(parts, h("h3", { id: "parts-h" }, t("mx.partsTitle")),
      h("p", {}, t("mx.partsSummary", { parts: xml.parts.length, bars: xml.bars }), h("a", { href: api.musicxmlUrl(ctx.id), download: "" }, t("mx.download")), " · ",
        h("a", { href: `#/viewer?src=${encodeURIComponent(`/v1/jobs/${ctx.id}/musicxml`)}&name=${encodeURIComponent(ctx.job.title ?? ctx.id)}` }, t("mx.openViewer"))),
      table(t("mx.partsTitle"), [t("mx.col.part"), t("mx.col.transpose"), t("mx.col.bars"), t("mx.col.notes"), t("mx.col.uncertain"), t("mx.col.range")],
        xml.parts.map((pt) => {
          const w = pt.notes.map((n) => n.written);
          return [pt.name, pt.transpose ? t("mx.semitones", { n: `${pt.transpose > 0 ? "+" : ""}${pt.transpose}` }) : t("mx.concert"), String(pt.bars), String(pt.notes.length),
            String(pt.notes.filter((n) => n.color).length), pt.percussion ? t("mx.unpitched") : w.length ? `${pitchName(minOf(w, (p) => p))}–${pitchName(maxOf(w, (p) => p))}` : "–"];
        })));
  } catch (e) {
    clear(parts, h("h3", { id: "parts-h" }, t("mx.partsTitle")), errorNotice(e));
  }
}

function manifestTab(p: HTMLElement, ctx: Ctx, m: Manifest | null): void {
  if (!m) {
    clear(p, h("p", {}, t("manifest.none")));
    return;
  }
  const stageNames = (m.stages ?? []).map((s) => s.stage);
  const heavy = h("input", { type: "checkbox", id: "rerun-heavy", checked: false });
  const cold = h("fieldset", {}, h("legend", {}, t("manifest.cold")),
    h("div", { class: "row" }, stageNames.map((s) => h("label", {}, h("input", { type: "checkbox", name: "cold", value: s }), h("span", { class: "mono" }, s)))));
  const result = h("div", { "aria-live": "polite" });
  const form = h("form", { class: "stack card" },
    h("h3", {}, t("manifest.rerun")),
    h("p", { class: "hint" }, t("manifest.rerunHint")),
    h("div", {}, h("label", {}, heavy, t("runs.allowHeavy")), infoTip(t("runs.heavyTerm"), t("runs.heavyTip"))),
    more(t("manifest.coldMore"), cold),
    h("div", { class: "actions" }, h("button", { type: "submit", class: ctx.job.status === "succeeded" ? "primary" : "" }, t("manifest.rerunBtn"))), result);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const picked = Array.from(form.querySelectorAll<HTMLInputElement>("input[name=cold]:checked")).map((x) => x.value);
    clear(result, loading(t("manifest.starting")));
    try {
      const job = await api.rerun(ctx.id, { allow_heavy: heavy.checked, cold: picked });
      announce(t("manifest.rerunStarted", { id: job.id }));
      location.hash = `#/runs/${encodeURIComponent(job.id)}`;
    } catch (x) {
      clear(result, errorNotice(x));
    }
  });
  const kv = (label: string, v: unknown, mono = false) => [h("dt", {}, label), h("dd", { class: mono ? "mono" : "" }, v === undefined || v === null ? "–" : typeof v === "object" ? JSON.stringify(v) : String(v))];
  // Essentials visible; host, parameters, options, per-stage detail and the JSON behind disclosures.
  clear(p,
    h("p", {}, t("manifest.purpose")),
    h("dl", { class: "kv" },
      kv(t("manifest.kv.run"), m.run_id, true), kv(t("manifest.kv.profile"), `${m.profile} (${m.pipeline ?? "?"})`), kv(t("manifest.kv.status"), m.status),
      kv(t("manifest.kv.input"), m.input ? `${fmt.path(m.input.path)} (${fmt.bytes(m.input.bytes)})` : undefined),
      kv(t("manifest.kv.git"), m.git ? `${m.git.branch ? t("manifest.gitOn", { sha: m.git.sha.slice(0, 12), branch: m.git.branch }) : m.git.sha.slice(0, 12)}${m.git.dirty ? t("run.dirty") : ""}` : undefined),
      kv(t("manifest.kv.time"), fmt.seconds(m.seconds))),
    more(t("manifest.moreDetails"), h("dl", { class: "kv" },
      kv(t("manifest.kv.inputSha"), m.input?.sha256, true),
      kv(t("manifest.kv.host"), m.host), kv(t("manifest.kv.params"), m.params, true), kv(t("manifest.kv.options"), m.options, true),
      kv(t("manifest.kv.devices"), m.devices?.join(", ")),
      m.tuning ? kv(t("manifest.kv.tuning"), Object.entries(m.tuning).map(([stage, d]) =>
        `${stage} ${d.tuning_cents > 0 ? "+" : ""}${d.tuning_cents} c${d.retuned ? ` (${t("manifest.tuningRetuned")})` : ""}`).join(", ")) : null)),
    more(t("manifest.stages"), table(t("manifest.stages"), [t("manifest.col.stage"), t("manifest.col.status"), t("manifest.col.time"), t("manifest.col.adapter"), t("manifest.col.device"), t("manifest.col.models"), t("manifest.col.key"), t("manifest.col.provenance")],
      (m.stages ?? []).map((s) => [
        h("span", { class: "mono" }, s.stage), pill(s.status), stageTime(s),
        s.adapter ? `${s.adapter.name} ${s.adapter.version ?? ""}` : "–", s.adapter?.device ?? "–",
        s.adapter?.models?.length ? h("ul", { style: "margin:0;padding-left:1rem" }, s.adapter.models.map((x) => h("li", {}, `${x.name} `, h("span", { class: "mono" }, fmt.hash(x.sha256))))) : "–",
        h("span", { class: "mono" }, fmt.hash(s.key)),
        s.provenance ? JSON.stringify(s.provenance) : s.matches_cache === false ? t("manifest.differs") : "–",
      ]), { hideCaption: true }), { count: stageNames.length }),
    more(t("manifest.json"), h("pre", { class: "json", tabindex: 0 }, JSON.stringify(m, null, 1))),
    form);
}

/** "Delete run" with an inline confirmation (no browser dialog). */
function deleteButton(id: string): HTMLElement {
  const box = h("span", { class: "row" });
  const start = (): HTMLButtonElement => h("button", { type: "button", class: "danger", onclick: ask }, icon("delete"), t("run.delete"));
  function ask(): void {
    const yes = h("button", { type: "button", class: "danger confirm", onclick: async () => {
      try {
        await api.deleteRun(id);
        announce(t("run.deleted", { id }));
        location.hash = "#/runs";
      } catch (e) {
        clear(box, errorNotice(e));
      }
    } }, t("run.deleteYes"));
    const no = h("button", { type: "button", class: "ghost", onclick: () => {
      const b = start();
      clear(box, b);
      b.focus();
    } }, t("run.deleteNo"));
    clear(box, h("span", { role: "alert" }, t("run.deleteConfirm")), yes, no);
    yes.focus();
  }
  box.append(start());
  return box;
}
