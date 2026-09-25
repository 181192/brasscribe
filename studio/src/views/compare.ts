// Compare two runs (or a run and a reference such as data/golden): note-level
// diff, a piano-roll overlay and metric deltas.
import { api, fetchText } from "../api/client";
import type { Composition, Job, Reference } from "../api/types";
import { PianoRoll, type RollLayer, type RollNote } from "../components/pianoroll";
import { tickTime } from "../lib/beats";
import { diffCompositions, type ChangeKind, type CompositionDiff } from "../lib/diff";
import { parseMusicXml, type XmlScore } from "../lib/musicxml";
import { pitchName } from "../lib/validate";
import { clear, errorNotice, fmt, h, loading, pill, table } from "../ui/dom";

interface Side {
  key: string;
  label: string;
  composition: Composition;
  xml: XmlScore | null;
}

async function loadSide(key: string, jobs: Job[]): Promise<Side> {
  if (key.startsWith("ref:")) {
    const name = key.slice(4);
    const [c, x] = await Promise.all([
      fetchText(api.referenceFileUrl(name, "composition.json")).then((t) => JSON.parse(t) as Composition),
      fetchText(api.referenceFileUrl(name, "brass-band.musicxml")).then(parseMusicXml).catch(() => null),
    ]);
    return { key, label: `reference ${name}`, composition: c, xml: x };
  }
  const job = jobs.find((j) => j.id === key);
  const [c, x] = await Promise.all([
    api.composition(key),
    fetchText(api.musicxmlUrl(key)).then(parseMusicXml).catch(() => null),
  ]);
  return { key, label: job?.title ? `${job.title} (${key})` : key, composition: c, xml: x };
}

export function compareView(root: HTMLElement, q: URLSearchParams): void {
  const form = h("div", {}, loading());
  const out = h("div", {});
  clear(root, h("h1", {}, "Compare runs"),
    h("p", {}, "Pick a base (A) and another run or a reference (B). Notes are matched voice by voice: identical, octave shift, moved (same pitch within a beat) or added and removed."),
    form, out);

  Promise.all([api.jobs(), api.references().catch(() => [] as Reference[])]).then(([jobs, refs]) => {
    const done = jobs.filter((j) => j.outputs?.includes("composition.json"));
    const opts = (sel: string | null) => [
      h("optgroup", { label: "Runs" }, done.map((j) => h("option", { value: j.id, selected: j.id === sel }, `${j.title ?? j.id} · ${j.id}`))),
      h("optgroup", { label: "References" }, refs.map((r) => h("option", { value: `ref:${r.name}`, selected: `ref:${r.name}` === sel }, r.name))),
    ];
    const a = h("select", { id: "cmp-a" }, opts(q.get("a") ?? done[0]?.id ?? null));
    const b = h("select", { id: "cmp-b" }, opts(q.get("b") ?? (refs[0] ? `ref:${refs[0].name}` : done[1]?.id ?? null)));
    const tol = h("input", { type: "number", id: "cmp-tol", min: 0, max: 4, step: 0.25, value: 1 });
    const f = h("form", { class: "row" },
      h("label", { for: "cmp-a" }, "A (base)"), a, h("label", { for: "cmp-b" }, "B"), b,
      h("label", { for: "cmp-tol" }, "Moved within (beats)"), tol,
      h("button", { type: "submit", class: "primary" }, "Compare"));
    f.addEventListener("submit", (e) => {
      e.preventDefault();
      history.replaceState(null, "", `#/compare?a=${encodeURIComponent(a.value)}&b=${encodeURIComponent(b.value)}`);
      void run(a.value, b.value, Number(tol.value));
    });
    clear(form, f);
    const run = async (ka: string, kb: string, tolerance: number) => {
      clear(out, loading("Loading both runs…"));
      try {
        const [sa, sb] = await Promise.all([loadSide(ka, jobs), loadSide(kb, jobs)]);
        const diff = diffCompositions(sa.composition, sb.composition, tolerance);
        const engine = !ka.startsWith("ref:")
          ? await api.compare(ka, kb.startsWith("ref:") ? { reference: kb.slice(4) } : { job: kb }).catch((x) => x as Error)
          : null;
        clear(out, renderDiff(sa, sb, diff, engine));
      } catch (x) {
        clear(out, errorNotice(x));
      }
    };
    if (a.value && b.value && (q.get("a") || q.get("b"))) void run(a.value, b.value, 1);
  }).catch((e) => clear(form, errorNotice(e)));
}

const KINDS: ChangeKind[] = ["same", "added", "removed", "moved", "octave"];

function renderDiff(a: Side, b: Side, d: CompositionDiff, engine: Awaited<ReturnType<typeof api.compare>> | Error | null): HTMLElement[] {
  const t = d.totals;
  const changed = t.added + t.removed + t.moved + t.octave;
  const out: HTMLElement[] = [
    h("h2", {}, "Summary"),
    h("p", { class: "row" }, pill(changed ? "different" : "identical"),
      `A: ${a.label}`, h("span", { "aria-hidden": "true" }, "·"), `B: ${b.label}`),
    h("p", {}, `${t.same} notes identical, ${t.added} added, ${t.removed} removed, ${t.moved} moved, ${t.octave} octave shifts.`),
  ];
  if (engine instanceof Error) out.push(errorNotice(engine));
  else if (engine) {
    out.push(h("p", {}, `Engine check: composition.json ${engine.composition_identical ? "identical" : "different"}, MusicXML ${engine.musicxml_identical ? "identical" : "different"}; ${engine.parts_identical}/${engine.parts_total} parts identical.`));
  }
  out.push(table("Note diff per voice", ["Voice", ...KINDS.map((k) => k[0].toUpperCase() + k.slice(1))],
    d.voices.map((v) => [v.voice, ...KINDS.map((k) => h("span", { class: `diff-${k}` }, String(v.counts[k])))])));

  // Metric deltas.
  const vm = (c: Composition, id: string) => {
    const v = c.voices.find((x) => x.id === id);
    const n = v?.notes ?? [];
    return { notes: n.length, conf: n.length ? n.reduce((s, x) => s + (x.confidence ?? 1), 0) / n.length : null, dur: n.length ? n.reduce((s, x) => s + x.dur, 0) / n.length / (c.ticks_per_beat ?? 24) : null };
  };
  const ids = d.voices.map((v) => v.voice);
  out.push(table("Metric deltas (B − A)", ["Voice", "Notes A", "Notes B", "Δ notes", "Mean confidence Δ", "Mean length Δ (beats)"],
    ids.map((id) => {
      const x = vm(a.composition, id);
      const y = vm(b.composition, id);
      return [id, String(x.notes), String(y.notes), fmt.signed(y.notes - x.notes, 0),
        x.conf !== null && y.conf !== null ? fmt.signed(y.conf - x.conf, 3) : "–",
        x.dur !== null && y.dur !== null ? fmt.signed(y.dur - x.dur, 3) : "–"];
    })));
  if (a.xml && b.xml) {
    const names = [...new Set([...a.xml.parts.map((p) => p.name), ...b.xml.parts.map((p) => p.name)])];
    out.push(table("Score parts (MusicXML)", ["Part", "Notes A", "Notes B", "Δ", "Uncertain A", "Uncertain B"],
      names.map((n) => {
        const pa = a.xml!.parts.find((p) => p.name === n);
        const pb = b.xml!.parts.find((p) => p.name === n);
        const na = pa?.notes.length ?? 0;
        const nb = pb?.notes.length ?? 0;
        return [n, String(na), String(nb), fmt.signed(nb - na, 0), String(pa?.notes.filter((x) => x.color).length ?? 0), String(pb?.notes.filter((x) => x.color).length ?? 0)];
      })));
  }

  // Overlay: A as filled blocks, B as outlines, changed notes marked.
  const voiceSel = h("select", { id: "cmp-voice" }, ids.map((id) => h("option", { value: id }, id)));
  const holder = h("div", {});
  const showOverlay = () => {
    const v = d.voices.find((x) => x.voice === voiceSel.value);
    if (!v) return;
    const toRoll = (c: Composition, n: { pitch: number; start: number; dur: number; onset_s?: number | null; offset_s?: number | null; confidence?: number }, mark?: RollNote["mark"]): RollNote => ({
      pitch: n.pitch, start: n.onset_s ?? tickTime(c, n.start), end: n.offset_s ?? tickTime(c, n.start + n.dur), confidence: n.confidence, mark,
    });
    const la: RollNote[] = [];
    const lb: RollNote[] = [];
    for (const ch of v.changes) {
      const mark = ch.kind === "same" ? undefined : ch.kind;
      if (ch.a) la.push(toRoll(a.composition, ch.a, mark === "added" ? undefined : mark));
      if (ch.b) lb.push(toRoll(b.composition, ch.b, mark === "removed" ? undefined : mark));
    }
    const layers: RollLayer[] = [
      { id: "a", label: `A: ${a.label}`, colour: "m1", style: "block", notes: la },
      { id: "b", label: `B: ${b.label}`, colour: "m2", style: "outline", notes: lb },
    ];
    const roll = h("bs-pianoroll", {}) as PianoRoll;
    roll.data = layers;
    const list = v.changes.filter((c) => c.kind !== "same");
    const fmtNote = (n?: { pitch: number; start: number; dur: number }) => (n ? `${pitchName(n.pitch)} @${n.start} (${n.dur})` : "–");
    clear(holder, roll,
      table(`Changes in ${v.voice}`, ["Kind", "A: pitch @tick (length)", "B: pitch @tick (length)"],
        list.slice(0, 400).map((c) => [h("span", { class: `diff-${c.kind}` }, c.kind), fmtNote(c.a), fmtNote(c.b)])),
      list.length > 400 ? h("p", { class: "hint" }, `First 400 of ${list.length} changes shown.`) : null);
  };
  voiceSel.addEventListener("change", showOverlay);
  out.push(h("h2", {}, "Overlay"),
    h("p", { class: "hint" }, "A is drawn filled, B outlined. Marks: + added, − removed, ↔ moved, 8 octave."),
    h("div", { class: "row" }, h("label", { for: "cmp-voice" }, "Voice"), voiceSel), holder);
  queueMicrotask(showOverlay);
  return out;
}
