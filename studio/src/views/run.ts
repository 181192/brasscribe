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
import { validateScore } from "../lib/validate";
import { announce, clear, errorNotice, fmt, h, loading, panel, pill, table, tabs } from "../ui/dom";

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
  const heading = h("h1", {}, "Run");
  const header = h("div", {}, loading());
  const graph = h("bs-stage-graph", {}) as StageGraph;
  const stageInfo = h("div", {});
  const inspector = h("section", { "aria-labelledby": "inspector-h" }, h("h2", { id: "inspector-h" }, "Inspector"), loading());
  clear(root,
    h("p", { class: "small" }, h("a", { href: "#/runs" }, "← All runs")),
    heading, header,
    h("section", { "aria-labelledby": "graph-h" }, h("h2", { id: "graph-h" }, "Stages"),
      h("p", { class: "hint" }, "Solid border: ran. Dashed: taken from the cache. Thick: running or failed. Choose a stage to inspect it."),
      graph, stageInfo),
    inspector);

  let stop: (() => void) | null = null;
  let view: RunView | null = null;
  let stages: StageFiles[] | Error = new Error("not loaded");
  let tabsEl: HTMLElement | null = null;
  let selectTab: ((id: string) => void) | null = null;

  const renderHeader = (job: Job, m: Manifest | null) => {
    heading.textContent = job.title || job.id;
    const t = view ? totals(view) : null;
    clear(header,
      h("p", { class: "row" }, pill(job.status), h("span", { class: "mono small" }, job.id), h("span", {}, `profile ${job.profile}`),
        m?.git ? h("span", { class: "small" }, `git ${fmt.hash(m.git.sha)}${m.git.dirty ? " (dirty)" : ""}`) : null),
      t ? h("p", {},
        h("progress", { class: "progress", max: t.total, value: t.done, "aria-label": "Stages finished" }), " ",
        `${t.done} of ${t.total} stages finished, ${t.cached} from the cache, ${fmt.seconds(t.seconds)} stage time`,
        m?.devices?.length ? `, devices ${m.devices.join(", ")}` : "") : null,
      job.error ? h("p", { class: "notice notice-error", role: "alert" }, job.error) : null,
      h("div", { class: "row" },
        !TERMINAL.has(job.status) ? h("button", { type: "button", onclick: async () => { await api.cancel(job.id); announce("Cancel requested"); } }, "Cancel run") : null,
        job.outputs?.includes("brass-band.musicxml") ? h("a", { class: "button", href: api.musicxmlUrl(job.id), download: "" }, "MusicXML") : null,
        job.outputs?.includes("brass-band.pdf") ? h("a", { class: "button", href: api.pdfUrl(job.id) }, "PDF") : null,
        job.outputs?.includes("brass-band.mid") ? h("a", { class: "button", href: api.midiUrl(job.id), download: "" }, "MIDI") : null,
        h("a", { class: "button", href: `#/compare?a=${encodeURIComponent(job.id)}` }, "Compare…"),
        job.previous_run_id ? h("a", { href: `#/compare?a=${encodeURIComponent(job.previous_run_id)}&b=${encodeURIComponent(job.id)}` }, "Compare with the run it re-ran") : null));
  };

  const showStage = (name: string) => {
    graph.select(name);
    const s = view?.stages.find((x) => x.name === name);
    const files = Array.isArray(stages) ? stages.find((x) => x.stage === name) : undefined;
    clear(stageInfo, h("div", { class: "card", role: "region", "aria-label": `Stage ${name}` },
      h("h3", {}, `Stage ${name}`),
      h("dl", { class: "kv" },
        h("dt", {}, "Status"), h("dd", {}, pill(s?.status ?? files?.status ?? "unknown")),
        h("dt", {}, "Kind"), h("dd", {}, s?.kind ?? files?.kind ?? "–"),
        h("dt", {}, "Time"), h("dd", {}, fmt.seconds(s?.seconds ?? files?.seconds)),
        h("dt", {}, "Device"), h("dd", {}, s?.device ?? files?.device ?? "–"),
        h("dt", {}, "Cache key"), h("dd", { class: "mono" }, fmt.hash(files?.key))),
      files ? fileTable(files.files) : Array.isArray(stages) ? null : errorNotice(stages)));
    const kind = s?.kind ?? files?.kind ?? name.split(".")[0];
    const t = TAB_FOR_KIND[kind];
    if (t && selectTab) selectTab(t);
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
          announce(`Run ${e.status}`);
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
      { id: "score", label: "Score", render: (p: HTMLElement) => scoreTab(p, ctx) },
      { id: "audio", label: "Audio", render: (p: HTMLElement) => audioTab(p, ctx) },
      { id: "stems", label: "Stems", render: (p: HTMLElement) => stemsTab(p, ctx) },
      { id: "roll", label: "Piano roll", render: (p: HTMLElement) => rollTab(p, ctx) },
      { id: "beats", label: "Beats", render: (p: HTMLElement) => beatsTab(p, ctx) },
      { id: "voices", label: "Voices", render: (p: HTMLElement) => voicesTab(p, ctx) },
      { id: "musicxml", label: "MusicXML", render: (p: HTMLElement) => musicxmlTab(p, ctx) },
      { id: "manifest", label: "Manifest", render: (p: HTMLElement) => manifestTab(p, ctx, m) },
    ];
    tabsEl = tabs("Inspector views", items, tab ?? "score", (t) => {
      history.replaceState(null, "", `#/runs/${encodeURIComponent(id)}/${t}`);
    });
    selectTab = (t) => tabsEl?.querySelector<HTMLButtonElement>(`[role=tab][data-id="${t}"]`)?.click();
    clear(inspector, h("h2", { id: "inspector-h" }, "Inspector"), tabsEl);
  };
  start().catch((e) => clear(header, errorNotice(e)));
  return () => stop?.();
}

function fileTable(files: FileRef[]): HTMLElement {
  return table("Files", ["File", "Size", "SHA-256"], files.map((f) => [
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
  const status = h("p", { class: "hint", role: "status" }, "Loading the score…");
  const warnings = h("section", { "aria-labelledby": "warn-h" }, h("h3", { id: "warn-h" }, "Validator warnings"), loading());
  clear(p, status, score, warnings);
  ctx.musicxml.then(async (xml) => {
    const t0 = performance.now();
    await score.load(xml, ctx.job.title ?? ctx.id);
    status.textContent = `${score.bars.length} bars, ${score.api?.score?.tracks.length ?? 0} parts, rendered in ${Math.round(performance.now() - t0)} ms.`;
    renderWarnings(warnings, ctx, parseMusicXml(xml), score);
  }).catch((e) => clear(p, errorNotice(e)));
}

async function renderWarnings(el: HTMLElement, ctx: Ctx, xml: XmlScore, score: ScoreElement): Promise<void> {
  const engine = await api.validation(ctx.id).catch((e) => e as Error);
  const local = validateScore(xml);
  const rows = [
    ...(Array.isArray(engine) ? engine.map((w) => ({ ...w, source: "arranger" })) : []),
    ...local.filter((w) => w.kind === "crossing" || !Array.isArray(engine)).map((w) => ({ ...w, source: "Studio check" })),
  ];
  const counts = (k: string) => rows.filter((r) => r.kind === k).length;
  const go = (bar: number | null | undefined) => h("button", { type: "button", onclick: () => { score.goBar((bar ?? 1) - 1); score.focusScore(); } }, `Bar ${bar ?? "?"}`);
  clear(el, h("h3", { id: "warn-h" }, "Validator warnings"),
    Array.isArray(engine) ? null : errorNotice(engine),
    h("p", {}, `${rows.length} warnings: ${counts("range")} range, ${counts("crossing")} crossing, ${counts("other")} other. `,
      h("span", { class: "hint" }, "Range warnings come from the arranger; voice crossing between adjacent parts of a section is checked by Studio on the MusicXML.")),
    table("Validator warnings", ["Bar", "Beat", "Part", "Kind", "Severity", "Message", "Source"],
      rows.slice(0, 300).map((r) => [go(r.bar), r.beat ? String(Math.round(r.beat * 100) / 100) : "–", r.part ?? "–", r.kind, pill(r.severity === "error" ? "error" : "warning"), r.message, r.source]),
      { hideCaption: true }),
    rows.length > 300 ? h("p", { class: "hint" }, `First 300 of ${rows.length} shown.`) : null);
}

function audioTab(p: HTMLElement, ctx: Ctx): void {
  const sources: AudioSource[] = [];
  if (ctx.job.outputs?.includes("brass-band.mp3")) sources.push({ label: "rendered score (MP3)", url: api.renderedAudioUrl(ctx.id) });
  for (const { stage, file } of stageFiles(ctx, (s) => s.kind === "layers" || s.kind === "stems" || s.kind === "separate")) {
    if (AUDIO.test(file.name)) sources.push({ label: `${stage.stage}/${file.name}`, url: file.url });
  }
  const original: AudioSource = { label: "original recording", url: api.inputAudioUrl(ctx.id) };
  const sel = h("select", { id: "audio-a" }, sources.map((s, i) => h("option", { value: String(i) }, s.label)));
  const holder = h("div", {});
  const show = () => {
    const a = sources[Number(sel.value)];
    clear(holder, audioPanel(a ? [a, original] : [original]));
  };
  sel.addEventListener("change", show);
  clear(p,
    h("p", {}, "Compare a stage's audio (A) with the original recording (B). Switching keeps the position."),
    Array.isArray(ctx.stages) ? null : errorNotice(ctx.stages),
    sources.length ? h("div", { class: "row" }, h("label", { for: "audio-a" }, "Source A"), sel) : null,
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
    .map(({ stage, file }) => ({ name: file.name, url: file.url, bytes: file.bytes, group: stage.stage }));
  if (!stems.length) {
    clear(p, h("p", {}, "This run has no stem or layer audio."));
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
      id: v.id, label: `final: ${v.id} (${v.role})`, colour: "ink", style: "block" as const,
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
    h("p", {}, "Final voices (filled by confidence) against the raw output of each transcription model for the same layer."),
    Array.isArray(ctx.stages) ? null : errorNotice(ctx.stages),
    h("div", { class: "row" }, h("label", { for: "roll-group" }, "Layer"), sel),
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
      rows.push({ label: "Beat tracker (mix.beats)", beats: parseBeats(await fetchText(beatFile.file.url)) });
    } catch {
      /* shown as missing below */
    }
  }
  let free: ReturnType<typeof compositionFreeTime> = [];
  try {
    const comp = await ctx.composition;
    rows.push({ label: "Score beat grid (Composition)", beats: compositionBeats(comp) });
    free = compositionFreeTime(comp);
  } catch {
    /* no composition yet */
  }
  if (!rows.length) {
    clear(p, h("p", {}, "No beat data for this run."));
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
      h("p", {}, `${c.title} · ${c.voices.length} voices · ${c.voices.reduce((a, v) => a + v.notes.length, 0)} notes · `,
        `metre ${c.meters.map((m) => `${m.beats}/${m.beat_unit ?? 4}`).join(", ") || "–"} · key ${c.keys.map((k) => `${k.fifths >= 0 ? "+" : ""}${k.fifths} ${k.mode ?? ""}`).join(", ") || "–"}`),
      table("Voices", ["Voice", "Role", "Layer", "Instrument hint", "Notes", "Range", "Mean confidence", "Uncertain (< 0.7)", "Sources"],
        c.voices.map((v) => {
          const ps = v.notes.map((n) => n.pitch);
          const conf = v.notes.map((n) => n.confidence ?? 1);
          const srcs = [...new Set(v.notes.flatMap((n) => n.sources ?? []))];
          return [v.id, v.role, v.layer ?? "–", v.instrument_hint ?? "–", String(v.notes.length),
            ps.length ? `${Math.min(...ps)}–${Math.max(...ps)}` : "–",
            conf.length ? fmt.num(conf.reduce((a, b) => a + b, 0) / conf.length, 2) : "–",
            String(conf.filter((x) => x < 0.7).length), srcs.join(", ") || "–"];
        })),
      table("Voices by role and layer", ["Role", ...layers], roles.map((r) => [
        r, ...layers.map((l) => c.voices.filter((v) => v.role === r && (v.layer ?? "–") === l).map((v) => `${v.id} (${v.notes.length})`).join(", ") || "–"),
      ])),
    ];
  });
}

async function musicxmlTab(p: HTMLElement, ctx: Ctx): Promise<void> {
  const rt = h("section", { "aria-labelledby": "rt-h" }, h("h3", { id: "rt-h" }, "MuseScore round trip"), loading());
  const parts = h("section", { "aria-labelledby": "parts-h" }, h("h3", { id: "parts-h" }, "Parts"), loading());
  const golden = h("section", { "aria-labelledby": "gold-h" }, h("h3", { id: "gold-h" }, "Against a reference"), loading());
  clear(p, rt, golden, parts);

  const renderRt = async (run = false) => {
    clear(rt, h("h3", { id: "rt-h" }, "MuseScore round trip"), loading(run ? "Running MuseScore…" : undefined));
    try {
      const r = run ? await api.runRoundtrip(ctx.id) : await api.roundtrip(ctx.id);
      clear(rt, h("h3", { id: "rt-h" }, "MuseScore round trip"),
        h("p", { class: "row" }, pill(r.status), r.notes_in != null ? `${r.notes_in} notes written, ${r.notes_out ?? "?"} read back by MuseScore` : "",
          r.parts != null ? ` · ${r.parts} parts` : ""),
        r.detail ? h("p", { class: "small" }, r.detail) : null,
        r.part_results?.length ? table("Round trip per part", ["Part", "Notes", "Sound", "Match"],
          r.part_results.map((x) => [x.name, String(x.notes), x.sound ?? "–", x.match == null ? "–" : pill(x.match ? "pass" : "fail")])) : null,
        h("button", { type: "button", onclick: () => renderRt(true) }, r.status === "not_run" ? "Run the round trip" : "Run again"));
      if (run) announce(`Round trip ${r.status}`);
    } catch (e) {
      clear(rt, h("h3", { id: "rt-h" }, "MuseScore round trip"), errorNotice(e));
    }
  };
  void renderRt();

  const refs = await api.references().catch((e) => e as Error);
  const renderGolden = async (ref: Reference) => {
    const out = h("div", {}, loading());
    const sel = h("select", { id: "gold-ref", onchange: () => { const r = (refs as Reference[]).find((x) => x.name === sel.value); if (r) void renderGolden(r); } },
      (refs as Reference[]).map((r) => h("option", { value: r.name, selected: r.name === ref.name }, r.name)));
    clear(golden, h("h3", { id: "gold-h" }, "Against a reference"), h("div", { class: "row" }, h("label", { for: "gold-ref" }, "Reference"), sel,
      h("a", { href: `#/compare?a=${encodeURIComponent(ctx.id)}&b=${encodeURIComponent(`ref:${ref.name}`)}` }, "Note-level diff")), out);
    try {
      const c = await api.compare(ctx.id, { reference: ref.name });
      clear(out,
        h("p", { class: "row" }, pill(c.ok ? "identical" : "different"),
          `composition.json ${c.composition_identical ? "identical" : "different"}; MusicXML ${c.musicxml_identical ? "identical" : "different"} (ids and date canonicalised); `,
          `${c.parts_identical}/${c.parts_total} parts identical, ${c.notes_identical}/${c.notes_total} notes in identical parts`),
        table("Parts against the reference", ["Part", "Notes", "Reference notes", "Identical"],
          c.parts.map((x) => [x.name, String(x.notes), String(x.reference_notes), pill(x.identical ? "identical" : "different")])));
    } catch (e) {
      clear(out, errorNotice(e));
    }
  };
  if (Array.isArray(refs) && refs.length) void renderGolden(refs.find((r) => r.name.includes("mikkel")) ?? refs[0]);
  else clear(golden, h("h3", { id: "gold-h" }, "Against a reference"), Array.isArray(refs) ? h("p", {}, "No references in the data directory.") : errorNotice(refs));

  try {
    const xml = parseMusicXml(await ctx.musicxml);
    clear(parts, h("h3", { id: "parts-h" }, "Parts"),
      h("p", {}, `${xml.parts.length} parts, ${xml.bars} bars. `, h("a", { href: api.musicxmlUrl(ctx.id), download: "" }, "Download MusicXML"), " · ",
        h("a", { href: `#/viewer?src=${encodeURIComponent(`/v1/jobs/${ctx.id}/musicxml`)}&name=${encodeURIComponent(ctx.job.title ?? ctx.id)}` }, "Open in the score viewer")),
      table("Parts", ["Part", "Transposition", "Bars", "Notes", "Uncertain (coloured)", "Written range"],
        xml.parts.map((pt) => {
          const w = pt.notes.map((n) => n.written);
          return [pt.name, pt.transpose ? `${pt.transpose > 0 ? "+" : ""}${pt.transpose} semitones` : "concert", String(pt.bars), String(pt.notes.length),
            String(pt.notes.filter((n) => n.color).length), w.length ? `${Math.min(...w)}–${Math.max(...w)}` : "–"];
        })));
  } catch (e) {
    clear(parts, h("h3", { id: "parts-h" }, "Parts"), errorNotice(e));
  }
}

function manifestTab(p: HTMLElement, ctx: Ctx, m: Manifest | null): void {
  if (!m) {
    clear(p, h("p", {}, "This run has no manifest yet."));
    return;
  }
  const stageNames = (m.stages ?? []).map((s) => s.stage);
  const heavy = h("input", { type: "checkbox", id: "rerun-heavy", checked: false });
  const cold = h("fieldset", {}, h("legend", {}, "Run these stages even on a cache hit"),
    h("div", { class: "row" }, stageNames.map((s) => h("label", {}, h("input", { type: "checkbox", name: "cold", value: s }), h("span", { class: "mono small" }, s)))));
  const result = h("div", { "aria-live": "polite" });
  const form = h("form", { class: "stack card" },
    h("h3", {}, "Re-run from this manifest"),
    h("p", { class: "hint" }, "Uses the same input, profile and parameters. Stages whose inputs are unchanged come from the cache unless ticked below."),
    h("label", {}, heavy, "Allow heavy models on cache misses"), cold,
    h("button", { type: "submit", class: "primary" }, "Re-run"), result);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const picked = Array.from(form.querySelectorAll<HTMLInputElement>("input[name=cold]:checked")).map((x) => x.value);
    clear(result, loading("Starting…"));
    try {
      const job = await api.rerun(ctx.id, { allow_heavy: heavy.checked, cold: picked });
      announce(`Re-run ${job.id} started`);
      location.hash = `#/runs/${encodeURIComponent(job.id)}`;
    } catch (x) {
      clear(result, errorNotice(x));
    }
  });
  const kv = (label: string, v: unknown) => [h("dt", {}, label), h("dd", { class: typeof v === "string" && v.length > 30 ? "mono small" : "" }, v === undefined || v === null ? "–" : typeof v === "object" ? JSON.stringify(v) : String(v))];
  clear(p,
    h("dl", { class: "kv" },
      kv("Run", m.run_id), kv("Profile", `${m.profile} (${m.pipeline ?? "?"})`), kv("Status", m.status),
      kv("Input", m.input ? `${m.input.path} (${fmt.bytes(m.input.bytes)}, sha256 ${fmt.hash(m.input.sha256)})` : undefined),
      kv("Git", m.git ? `${m.git.sha}${m.git.branch ? ` on ${m.git.branch}` : ""}${m.git.dirty ? ", dirty" : ""}` : undefined),
      kv("Host", m.host), kv("Parameters", m.params), kv("Options", m.options),
      kv("Devices", m.devices?.join(", ")), kv("Time", fmt.seconds(m.seconds))),
    table("Stages in the manifest", ["Stage", "Status", "Time", "Adapter", "Device", "Models", "Cache key", "Provenance"],
      (m.stages ?? []).map((s) => [
        h("span", { class: "mono small" }, s.stage), pill(s.status), fmt.seconds(s.seconds),
        s.adapter ? `${s.adapter.name} ${s.adapter.version ?? ""}` : "–", s.adapter?.device ?? "–",
        s.adapter?.models?.length ? h("ul", { style: "margin:0;padding-left:1rem" }, s.adapter.models.map((x) => h("li", { class: "small" }, `${x.name} `, h("span", { class: "mono" }, fmt.hash(x.sha256))))) : "–",
        h("span", { class: "mono small" }, fmt.hash(s.key)),
        s.provenance ? JSON.stringify(s.provenance) : s.matches_cache === false ? "differs from cache" : "–",
      ])),
    form,
    h("details", {}, h("summary", {}, "Manifest JSON"), h("pre", { class: "json", tabindex: 0 }, JSON.stringify(m, null, 1))));
}
