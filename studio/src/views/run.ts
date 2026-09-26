// One run: live stage graph over SSE and the stage inspector.
import { api, fetchBytes, fetchText, subscribe } from "../api/client";
import type { Composition, FileRef, Job, Manifest, Reference, StageFiles } from "../api/types";
import { audioPanel, type AudioSource } from "../components/audio";
import { BeatView } from "../components/beats";
import { PianoRoll, type RollLayer } from "../components/pianoroll";
import type { ScoreElement } from "../components/score";
import { StageGraph } from "../components/stagegraph";
import { StemsMixer } from "../components/stems";
import { compositionBeats, compositionFreeTime, parseBeats, tickTime } from "../lib/beats";
import { fromJob, reduce, totals, type RunView } from "../lib/events";
import { parseMidi } from "../lib/midi";
import { parseMusicXml, type XmlScore } from "../lib/musicxml";
import { pitchName, validateScore } from "../lib/validate";
import { t } from "../i18n";
import { announce, clear, errorNotice, fmt, h, loading, panel, pill, table, tabs } from "../ui/dom";
import { icon } from "../ui/icons";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const TAB_FOR_KIND: Record<string, string> = {
  beats: "beats", stems: "stems", separate: "stems", layers: "audio", transcribe: "roll", vote: "roll",
  arrange: "score", export: "musicxml",
};
const MODEL_STYLE: Record<string, { colour: string; style: RollLayer["style"]; label: string }> = {
  muscriptor: { colour: "m1", style: "line", label: "MuScriptor" },
  "basic-pitch": { colour: "m2", style: "dashed", label: "Basic Pitch" },
  "swift-f0": { colour: "m3", style: "dotted", label: "SwiftF0" },
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
  const graph = h("bs-stage-graph", {}) as StageGraph;
  const stageInfo = h("div", {});
  const inspector = h("section", { "aria-labelledby": "inspector-h" }, h("h2", { id: "inspector-h" }, t("run.inspector")), loading());
  const actions = h("div", { class: "actions" });
  clear(root,
    h("div", { class: "run-head" },
      h("div", { class: "run-title" },
        h("p", {}, h("a", { class: "back-link", href: "#/runs" }, icon("back"), t("run.back"))),
        heading, header),
      actions),
    h("section", { "aria-labelledby": "graph-h" },
      h("div", { class: "graph-head" }, h("h2", { id: "graph-h" }, t("run.stages")),
        h("p", { class: "graph-legend" }, h("span", {}, t("run.legend.ran")), h("span", {}, t("run.legend.cache")), h("span", {}, t("run.legend.thick")))),
      graph,
      h("p", { class: "hint" }, t("run.stagesChoose")),
      stageInfo),
    inspector);

  let stop: (() => void) | null = null;
  let view: RunView | null = null;
  let stages: StageFiles[] | Error = new Error("not loaded");
  let tabsEl: HTMLElement | null = null;
  let selectTab: ((id: string) => void) | null = null;

  const renderHeader = (job: Job, m: Manifest | null) => {
    heading.textContent = job.title || job.id;
    const tot = view ? totals(view) : null;
    clear(header,
      h("p", { class: "meta" }, pill(job.status), h("span", { class: "mono" }, job.id), h("span", {}, t("run.profile", { p: "" }), h("b", {}, job.profile)),
        m?.git ? h("span", {}, "git ", h("b", { class: "mono" }, fmt.hash(m.git.sha).slice(0, 7)), m.git.dirty ? t("run.dirty") : "") : null),
      tot ? h("p", { class: "meta" },
        TERMINAL.has(job.status) ? null : h("progress", { class: "progress", max: tot.total, value: tot.done, "aria-label": t("run.stagesFinished") }),
        h("span", {}, t("run.progress", { done: tot.done, total: tot.total, cached: tot.cached, seconds: fmt.seconds(tot.seconds) }),
          m?.devices?.length ? t("run.devices", { d: m.devices.join(", ") }) : "")) : null,
      job.error ? h("pre", { class: "notice notice-error small", role: "alert", style: "white-space:pre-wrap;overflow-wrap:anywhere" }, job.error) : null,
      job.previous_run_id ? h("p", { class: "small" }, h("a", { href: `#/compare?a=${encodeURIComponent(job.previous_run_id)}&b=${encodeURIComponent(job.id)}` }, t("run.compareRerun"))) : null);
    clear(actions,
      !TERMINAL.has(job.status) ? h("button", { type: "button", class: "ghost", onclick: async () => { await api.cancel(job.id); announce(t("run.cancelRequested")); } }, icon("close"), t("run.cancel")) : null,
      job.outputs?.includes("brass-band.musicxml") ? h("a", { class: "button", href: api.musicxmlUrl(job.id), download: "" }, icon("file"), "MusicXML") : null,
      job.outputs?.includes("brass-band.pdf") ? h("a", { class: "button", href: api.pdfUrl(job.id) }, icon("file"), "PDF") : null,
      job.outputs?.includes("brass-band.mid") ? h("a", { class: "button", href: api.midiUrl(job.id), download: "" }, icon("file"), "MIDI") : null,
      h("a", { class: "button ghost", href: `#/compare?a=${encodeURIComponent(job.id)}` }, t("run.compare")),
      TERMINAL.has(job.status) ? h("button", { type: "button", class: "ghost", onclick: async (e: Event) => {
        const b = e.currentTarget as HTMLButtonElement;
        b.disabled = true;
        try {
          const j = await api.rerun(job.id, { allow_heavy: false, cold: [] });
          announce(t("manifest.rerunStarted", { id: j.id }));
          location.hash = `#/runs/${encodeURIComponent(j.id)}`;
        } catch (x) {
          b.disabled = false;
          clear(header, errorNotice(x));
        }
      } }, icon("retry"), t("manifest.rerunBtn")) : null,
      TERMINAL.has(job.status) ? deleteButton(job.id) : null);
  };

  const showStage = (name: string) => {
    graph.select(name);
    const s = view?.stages.find((x) => x.name === name);
    const files = Array.isArray(stages) ? stages.find((x) => x.stage === name) : undefined;
    clear(stageInfo, h("div", { class: "card", role: "region", "aria-label": t("run.stage", { name }) },
      h("h3", {}, t("run.stage", { name })),
      h("dl", { class: "kv" },
        h("dt", {}, t("run.kv.status")), h("dd", {}, pill(s?.status ?? files?.status ?? "unknown")),
        h("dt", {}, t("run.kv.kind")), h("dd", {}, s?.kind ?? files?.kind ?? "–"),
        h("dt", {}, t("run.kv.time")), h("dd", {}, fmt.seconds(s?.seconds ?? files?.seconds)),
        h("dt", {}, t("run.kv.device")), h("dd", {}, s?.device ?? files?.device ?? "–"),
        h("dt", {}, t("run.kv.key")), h("dd", { class: "mono" }, fmt.hash(files?.key))),
      files ? fileTable(files.files) : Array.isArray(stages) ? null : errorNotice(stages)));
    const kind = s?.kind ?? files?.kind ?? name.split(".")[0];
    const tab = TAB_FOR_KIND[kind];
    if (tab && selectTab) selectTab(tab);
  };
  graph.addEventListener("select", (e) => showStage((e as CustomEvent<string>).detail));

  const start = async () => {
    const job = await api.job(id);
    view = fromJob(job);
    graph.update(view);
    const [m, st] = await Promise.all([api.manifest(id).catch(() => null), api.stages(id).catch((e) => e as Error)]);
    stages = st;
    renderHeader(job, m);
    if (!TERMINAL.has(job.status)) {
      stop = subscribe(id, (e) => {
        view = reduce(view!, e);
        graph.update(view);
        if (e.type === "job" && e.status && TERMINAL.has(e.status)) {
          announce(t("run.ended", { status: t(`status.${e.status}`) }));
          stop?.();
          void start(); // reload outputs and the inspector
        } else renderHeader({ ...job, status: view.status as Job["status"] }, m);
      });
    }
    const ctx: Ctx = {
      id, job, stages: st,
      composition: api.composition(id),
      musicxml: fetchText(`/v1/jobs/${encodeURIComponent(id)}/musicxml`),
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
    tabsEl = tabs(t("run.inspectorViews"), items, tab ?? "score", (sel) => {
      history.replaceState(null, "", `#/runs/${encodeURIComponent(id)}/${sel}`);
    });
    selectTab = (sel) => tabsEl?.querySelector<HTMLButtonElement>(`[role=tab][data-id="${sel}"]`)?.click();
    clear(inspector, h("h2", { id: "inspector-h" }, t("run.inspector")), tabsEl);
  };
  start().catch((e) => clear(header, errorNotice(e)));
  return () => stop?.();
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
  const score = h("bs-score", {}) as ScoreElement;
  const status = h("p", { class: "hint", role: "status" }, t("score.loading"));
  const warnings = h("section", { "aria-labelledby": "warn-h" }, h("h3", { id: "warn-h" }, t("warn.title")), loading());
  clear(p, status, score, warnings);
  ctx.musicxml.then(async (xml) => {
    const t0 = performance.now();
    await score.load(xml, ctx.job.title ?? ctx.id);
    status.textContent = t("score.rendered", { bars: score.bars.length, parts: score.api?.score?.tracks.length ?? 0, ms: Math.round(performance.now() - t0) });
    renderWarnings(warnings, ctx, parseMusicXml(xml), score);
  }).catch((e) => clear(p, errorNotice(e)));
}

async function renderWarnings(el: HTMLElement, ctx: Ctx, xml: XmlScore, score: ScoreElement): Promise<void> {
  const engine = await api.validation(ctx.id).catch((e) => e as Error);
  const local = validateScore(xml);
  const rows = [
    ...(Array.isArray(engine) ? engine.map((w) => ({ ...w, source: t("warn.arranger") })) : []),
    ...local.filter((w) => w.kind === "crossing" || !Array.isArray(engine)).map((w) => ({ ...w, source: t("warn.studio") })),
  ];
  const counts = (k: string) => rows.filter((r) => r.kind === k).length;
  const go = (bar: number | null | undefined) => h("button", { type: "button", onclick: () => { score.goBar((bar ?? 1) - 1); score.focusScore(); } }, t("warn.barBtn", { n: bar ?? "?" }));
  clear(el, h("h3", { id: "warn-h" }, t("warn.title")),
    Array.isArray(engine) ? null : errorNotice(engine),
    h("p", {}, t("warn.summary", { n: rows.length, range: counts("range"), crossing: counts("crossing"), other: counts("other") }),
      h("span", { class: "hint" }, t("warn.hint"))),
    table(t("warn.title"), [t("warn.col.bar"), t("warn.col.beat"), t("warn.col.part"), t("warn.col.kind"), t("warn.col.severity"), t("warn.col.message"), t("warn.col.source")],
      rows.slice(0, 300).map((r) => [go(r.bar), r.beat ? String(Math.round(r.beat * 100) / 100) : "–", r.part ?? "–", r.kind, pill(r.severity === "error" ? "error" : "warning"), r.message, r.source]),
      { hideCaption: true }),
    rows.length > 300 ? h("p", { class: "hint" }, t("warn.first", { n: 300, total: rows.length })) : null);
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
  const show = async () => {
    const g = sel.value;
    clear(holder, loading());
    const layers: RollLayer[] = comp.voices.filter((v) => layerGroup(v.layer ?? v.id) === g).map((v) => ({
      id: v.id, label: t("roll.final", { id: v.id, role: v.role }), colour: "ink", style: "block" as const,
      notes: v.notes.map((n) => ({
        pitch: n.pitch,
        start: n.onset_s ?? tickTime(comp, n.start),
        end: n.offset_s ?? tickTime(comp, n.start + n.dur),
        confidence: n.confidence,
      })),
    }));
    for (const { stage, file } of transcribes.filter(({ stage }) => (stage.stage.split(".")[1] ?? "all") === g)) {
      const model = stage.stage.split(".").slice(2).join(".") || file.name;
      const st = MODEL_STYLE[model] ?? { colour: "m4", style: "outline" as const, label: model };
      try {
        const midi = parseMidi(await fetchBytes(file.url));
        layers.push({ id: stage.stage, label: `${st.label} (${file.name})`, colour: st.colour, style: st.style,
          notes: midi.notes.map((n) => ({ pitch: n.pitch, start: n.start, end: n.end })) });
      } catch {
        /* skip unreadable files */
      }
    }
    const roll = h("bs-pianoroll", {}) as PianoRoll;
    roll.data = layers;
    clear(holder, roll);
  };
  sel.addEventListener("change", show);
  clear(p,
    h("p", {}, t("roll.intro")),
    Array.isArray(ctx.stages) ? null : errorNotice(ctx.stages),
    h("div", { class: "row" }, h("label", { for: "roll-group" }, t("roll.layer")), sel),
    holder);
  void show();
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
            ps.length ? `${Math.min(...ps)}–${Math.max(...ps)}` : "–",
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
            String(pt.notes.filter((n) => n.color).length), pt.percussion ? t("mx.unpitched") : w.length ? `${pitchName(Math.min(...w))}–${pitchName(Math.max(...w))}` : "–"];
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
    h("div", { class: "row" }, stageNames.map((s) => h("label", {}, h("input", { type: "checkbox", name: "cold", value: s }), h("span", { class: "mono small" }, s)))));
  const result = h("div", { "aria-live": "polite" });
  const form = h("form", { class: "stack card" },
    h("h3", {}, t("manifest.rerun")),
    h("p", { class: "hint" }, t("manifest.rerunHint")),
    h("label", {}, heavy, t("runs.allowHeavy")), cold,
    h("button", { type: "submit", class: "primary" }, t("manifest.rerunBtn")), result);
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
  const kv = (label: string, v: unknown) => [h("dt", {}, label), h("dd", { class: typeof v === "string" && v.length > 30 ? "mono small" : "" }, v === undefined || v === null ? "–" : typeof v === "object" ? JSON.stringify(v) : String(v))];
  clear(p,
    h("dl", { class: "kv" },
      kv(t("manifest.kv.run"), m.run_id), kv(t("manifest.kv.profile"), `${m.profile} (${m.pipeline ?? "?"})`), kv(t("manifest.kv.status"), m.status),
      kv(t("manifest.kv.input"), m.input ? `${m.input.path} (${fmt.bytes(m.input.bytes)}, sha256 ${fmt.hash(m.input.sha256)})` : undefined),
      kv(t("manifest.kv.git"), m.git ? `${m.git.sha}${m.git.branch ? ` on ${m.git.branch}` : ""}${m.git.dirty ? ", dirty" : ""}` : undefined),
      kv(t("manifest.kv.host"), m.host), kv(t("manifest.kv.params"), m.params), kv(t("manifest.kv.options"), m.options),
      kv(t("manifest.kv.devices"), m.devices?.join(", ")), kv(t("manifest.kv.time"), fmt.seconds(m.seconds))),
    table(t("manifest.stages"), [t("manifest.col.stage"), t("manifest.col.status"), t("manifest.col.time"), t("manifest.col.adapter"), t("manifest.col.device"), t("manifest.col.models"), t("manifest.col.key"), t("manifest.col.provenance")],
      (m.stages ?? []).map((s) => [
        h("span", { class: "mono small" }, s.stage), pill(s.status), fmt.seconds(s.seconds),
        s.adapter ? `${s.adapter.name} ${s.adapter.version ?? ""}` : "–", s.adapter?.device ?? "–",
        s.adapter?.models?.length ? h("ul", { style: "margin:0;padding-left:1rem" }, s.adapter.models.map((x) => h("li", { class: "small" }, `${x.name} `, h("span", { class: "mono" }, fmt.hash(x.sha256))))) : "–",
        h("span", { class: "mono small" }, fmt.hash(s.key)),
        s.provenance ? JSON.stringify(s.provenance) : s.matches_cache === false ? t("manifest.differs") : "–",
      ])),
    form,
    h("details", {}, h("summary", {}, t("manifest.json")), h("pre", { class: "json", tabindex: 0 }, JSON.stringify(m, null, 1))));
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
