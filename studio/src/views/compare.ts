// Compare two runs (or a run and a reference such as data/golden): note-level
// diff, both scores side by side with the differing notes marked, a
// piano-roll overlay and metric deltas.
import { api, fetchText, isAbort } from "../api/client";
import type { Composition, Job, Reference } from "../api/types";
import { PianoRoll, type RollLayer, type RollNote } from "../components/pianoroll";
import { tokenColour, type NoteMark } from "../components/score";
import { lang, t } from "../i18n";
import { tickTime } from "../lib/beats";
import { diffCompositions, type ChangeKind, type CompositionDiff } from "../lib/diff";
import { parseMusicXml, type XmlScore } from "../lib/musicxml";
import { partNameNb } from "../lib/talkingxml";
import { pitchName } from "../lib/validate";
import { diffParts, type MarkKind } from "../lib/xmldiff";
import { runTitle } from "./runs";
import { announce, clear, errorNotice, fmt, h, infoTip, loading, more, pill, table, viewHead } from "../ui/dom";

interface Side {
  key: string;
  label: string;
  composition: Composition;
  xmlText: string | null;
  xml: XmlScore | null;
}

async function loadSide(key: string, jobs: Job[], signal: AbortSignal): Promise<Side> {
  const parse = (x: string | null) => {
    try {
      return x ? parseMusicXml(x) : null;
    } catch {
      return null;
    }
  };
  if (key.startsWith("ref:")) {
    const name = key.slice(4);
    const [c, x] = await Promise.all([
      fetchText(api.referenceFileUrl(name, "composition.json"), undefined, { signal }).then((s) => JSON.parse(s) as Composition),
      fetchText(api.referenceFileUrl(name, "brass-band.musicxml"), undefined, { signal }).catch(() => null),
    ]);
    return { key, label: t("cmp.reference", { name }), composition: c, xmlText: x, xml: parse(x) };
  }
  const job = jobs.find((j) => j.id === key);
  const [c, x] = await Promise.all([api.composition(key, { signal }), fetchText(api.musicxmlUrl(key), undefined, { signal }).catch(() => null)]);
  return { key, label: job ? runTitle(job) : key, composition: c, xmlText: x, xml: parse(x) };
}

export function compareView(root: HTMLElement, q: URLSearchParams): () => void {
  const form = h("div", {}, loading());
  const out = h("div", {});
  // One comparison at a time: a new one (or leaving the page) cancels the one still loading.
  let pending: AbortController | null = null;
  let disposed = false;
  clear(root, viewHead(t("title.compare"), [t("cmp.purpose"), " ", infoTip(t("cmp.how"), t("cmp.intro"))]), form, out);

  Promise.all([api.jobs(), api.references().catch(() => [] as Reference[])]).then(([jobs, refs]) => {
    const done = jobs.filter((j) => j.outputs?.includes("composition.json"));
    const opts = (sel: string | null) => [
      h("optgroup", { label: t("cmp.runs") }, done.map((j) => h("option", { value: j.id, selected: j.id === sel, title: j.id }, `${runTitle(j)} · ${j.profile} · ${fmt.date(j.created)}`))),
      h("optgroup", { label: t("cmp.refs") }, refs.map((r) => h("option", { value: `ref:${r.name}`, selected: `ref:${r.name}` === sel }, r.name))),
    ];
    const a = h("select", { id: "cmp-a" }, opts(q.get("a") ?? done[0]?.id ?? null));
    const b = h("select", { id: "cmp-b" }, opts(q.get("b") ?? (refs[0] ? `ref:${refs[0].name}` : done[1]?.id ?? null)));
    const tol = h("input", { type: "number", id: "cmp-tol", min: 0, max: 4, step: 0.25, value: 1 });
    const f = h("form", { class: "row form-row card" },
      h("div", { class: "field" }, h("label", { for: "cmp-a" }, t("cmp.a")), a),
      h("div", { class: "field" }, h("label", { for: "cmp-b" }, t("cmp.b")), b),
      h("div", { class: "field" }, h("span", {}, h("label", { for: "cmp-tol" }, t("cmp.tol")), infoTip(t("cmp.tol"), t("cmp.tolTip"))), tol),
      h("button", { type: "submit", class: "primary" }, t("cmp.go")));
    f.addEventListener("submit", (e) => {
      e.preventDefault();
      history.replaceState(null, "", `#/compare?a=${encodeURIComponent(a.value)}&b=${encodeURIComponent(b.value)}`);
      void run(a.value, b.value, Number(tol.value));
    });
    clear(form, f);
    const run = async (ka: string, kb: string, tolerance: number) => {
      pending?.abort();
      const ctl = new AbortController();
      pending = ctl;
      const { signal } = ctl;
      clear(out, loading(t("cmp.loading")));
      try {
        const [sa, sb] = await Promise.all([loadSide(ka, jobs, signal), loadSide(kb, jobs, signal)]);
        const diff = diffCompositions(sa.composition, sb.composition, tolerance);
        const engine = !ka.startsWith("ref:")
          ? await api.compare(ka, kb.startsWith("ref:") ? { reference: kb.slice(4) } : { job: kb }, { signal }).catch((x) => x as Error)
          : null;
        if (signal.aborted) return;
        clear(out, renderDiff(sa, sb, diff, engine, tolerance));
      } catch (x) {
        if (signal.aborted || isAbort(x)) return;
        clear(out, errorNotice(x));
      }
    };
    if (disposed) return;
    if (a.value && b.value && (q.get("a") || q.get("b"))) void run(a.value, b.value, 1);
  }).catch((e) => {
    if (!disposed) clear(form, errorNotice(e));
  });
  return () => {
    disposed = true;
    pending?.abort();
  };
}

const KINDS: ChangeKind[] = ["same", "added", "removed", "moved", "octave"];

// Each kind of change has a token colour and its own notehead (shape repeats the colour).
const MARK_TOKEN: Record<MarkKind, { token: string; head: NoteMark["head"] }> = {
  removed: { token: "scribe-error", head: "x" },
  added: { token: "scribe-success", head: "diamond" },
  octave: { token: "bc-model-2", head: "triangle" },
  moved: { token: "bc-model-4", head: "square" },
};
const mark = (k: MarkKind): NoteMark => ({ colour: tokenColour(MARK_TOKEN[k].token), head: MARK_TOKEN[k].head });

function renderDiff(a: Side, b: Side, d: CompositionDiff, engine: Awaited<ReturnType<typeof api.compare>> | Error | null, tolerance: number): HTMLElement[] {
  const tt = d.totals;
  const changed = tt.added + tt.removed + tt.moved + tt.octave;
  const out: HTMLElement[] = [
    h("h2", {}, t("cmp.summary")),
    h("p", { class: "row" }, pill(changed ? "different" : "identical"), t("cmp.scoreA", { label: a.label }), h("span", { "aria-hidden": "true" }, "·"), t("cmp.scoreB", { label: b.label })),
    h("p", {}, t("cmp.totals", tt)),
  ];
  if (engine instanceof Error) out.push(errorNotice(engine));
  else if (engine) {
    out.push(h("p", {}, t("cmp.engine", {
      comp: engine.composition_identical ? t("mx.identical") : t("mx.different"), xml: engine.musicxml_identical ? t("mx.identical") : t("mx.different"),
      pi: engine.parts_identical, pt: engine.parts_total,
    })));
  }
  out.push(table(t("cmp.perVoice"), [t("cmp.col.voice"), t("cmp.col.same"), t("cmp.col.added"), t("cmp.col.removed"), t("cmp.col.moved"), t("cmp.col.octave")],
    d.voices.map((v) => [v.voice, ...KINDS.map((k) => h("span", { class: `diff-${k}` }, String(v.counts[k])))])));

  if (a.xml && b.xml && a.xmlText && b.xmlText) out.push(notation(a, b, tolerance));

  // Metric deltas.
  const vm = (c: Composition, id: string) => {
    const v = c.voices.find((x) => x.id === id);
    const n = v?.notes ?? [];
    return { notes: n.length, conf: n.length ? n.reduce((s, x) => s + (x.confidence ?? 1), 0) / n.length : null, dur: n.length ? n.reduce((s, x) => s + x.dur, 0) / n.length / (c.ticks_per_beat ?? 24) : null };
  };
  const ids = d.voices.map((v) => v.voice);
  out.push(more(t("cmp.deltas"), table(t("cmp.deltas"), [t("cmp.col.voice"), t("cmp.col.notesA"), t("cmp.col.notesB"), t("cmp.col.dNotes"), t("cmp.col.dConf"), t("cmp.col.dLen")],
    ids.map((id) => {
      const x = vm(a.composition, id);
      const y = vm(b.composition, id);
      return [id, String(x.notes), String(y.notes), fmt.signed(y.notes - x.notes, 0),
        x.conf !== null && y.conf !== null ? fmt.signed(y.conf - x.conf, 3) : "–",
        x.dur !== null && y.dur !== null ? fmt.signed(y.dur - x.dur, 3) : "–"];
    }), { hideCaption: true })));
  if (a.xml && b.xml) {
    const names = [...new Set([...a.xml.parts.map((p) => p.name), ...b.xml.parts.map((p) => p.name)])];
    out.push(more(t("cmp.parts"), table(t("cmp.parts"), [t("cmp.col.part"), t("cmp.col.notesA"), t("cmp.col.notesB"), t("cmp.col.delta"), t("cmp.col.uncA"), t("cmp.col.uncB")],
      names.map((n) => {
        const pa = a.xml!.parts.find((p) => p.name === n);
        const pb = b.xml!.parts.find((p) => p.name === n);
        const na = pa?.notes.length ?? 0;
        const nb = pb?.notes.length ?? 0;
        return [partLabel(n), String(na), String(nb), fmt.signed(nb - na, 0), String(pa?.notes.filter((x) => x.color).length ?? 0), String(pb?.notes.filter((x) => x.color).length ?? 0)];
      }), { hideCaption: true })));
  }

  // Piano-roll overlay: A as filled blocks, B as outlines, changed notes marked.
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
      { id: "a", label: t("cmp.scoreA", { label: a.label }), colour: "m1", style: "block", notes: la },
      { id: "b", label: t("cmp.scoreB", { label: b.label }), colour: "m2", style: "outline", notes: lb },
    ];
    const roll = h("bs-pianoroll", {}) as PianoRoll;
    roll.data = layers;
    const list = v.changes.filter((c) => c.kind !== "same");
    const fmtNote = (n?: { pitch: number; start: number; dur: number }) => (n ? `${pitchName(n.pitch)} @${n.start} (${n.dur})` : "–");
    clear(holder, roll,
      more(t("cmp.changes", { voice: v.voice }), table(t("cmp.changes", { voice: v.voice }), [t("cmp.col.kind"), t("cmp.col.aNote"), t("cmp.col.bNote")],
        list.slice(0, 400).map((c) => [h("span", { class: `diff-${c.kind}` }, t(`cmp.kind.${c.kind}`)), fmtNote(c.a), fmtNote(c.b)]), { hideCaption: true }), { count: list.length }),
      list.length > 400 ? h("p", { class: "hint" }, t("cmp.firstChanges", { n: 400, total: list.length })) : null);
  };
  voiceSel.addEventListener("change", showOverlay);
  out.push(h("h2", {}, t("cmp.overlay")),
    h("p", { class: "hint" }, t("cmp.overlayHint")),
    h("div", { class: "row" }, h("label", { for: "cmp-voice" }, t("cmp.voice")), voiceSel), holder);
  queueMicrotask(showOverlay);
  return out;
}

function partLabel(name: string): string {
  return lang() === "nb" ? partNameNb(name) ?? name : name;
}

/** Both scores for one part, stacked, with differing notes coloured and given another notehead. */
function notation(a: Side, b: Side, tolerance: number): HTMLElement {
  const names = a.xml!.parts.map((p) => p.name).filter((n) => b.xml!.parts.some((p) => p.name === n));
  const firstDiff = names.find((n) => diffParts(a.xml!.parts.find((p) => p.name === n), b.xml!.parts.find((p) => p.name === n), tolerance).bars.length) ?? names[0];
  const partSel = h("select", { id: "cmp-part" }, names.map((n) => h("option", { value: n, selected: n === firstDiff }, partLabel(n))));
  const status = h("p", { role: "status", class: "hint", id: "cmp-notation-status" });
  const scoreA = h("bs-score", { "data-play": "secondary" });
  const scoreB = h("bs-score", { "data-play": "secondary" });
  const prev = h("button", { type: "button" }, t("cmp.prevDiff"));
  const next = h("button", { type: "button" }, t("cmp.nextDiff"));
  let bars: number[] = [];
  let perBar = new Map<number, { a: number; b: number }>();
  let at = -1;
  const go = (i: number) => {
    if (!bars.length) return;
    at = (i + bars.length) % bars.length;
    const bar = bars[at];
    scoreA.goBar(bar, false);
    scoreB.goBar(bar, false);
    const c = perBar.get(bar) ?? { a: 0, b: 0 };
    const msg = t("cmp.atBar", { n: bar + 1, a: c.a, b: c.b });
    status.textContent = msg;
    announce(msg);
  };
  prev.addEventListener("click", () => go(at - 1));
  next.addEventListener("click", () => go(at + 1));
  const load = async () => {
    const name = partSel.value;
    const ia = a.xml!.parts.findIndex((p) => p.name === name);
    const ib = b.xml!.parts.findIndex((p) => p.name === name);
    const pd = diffParts(a.xml!.parts[ia], b.xml!.parts[ib], tolerance);
    bars = pd.bars;
    perBar = pd.perBar;
    at = -1;
    status.textContent = bars.length ? t("cmp.diffBars", { n: bars.length, part: partLabel(name) }) : t("cmp.noDiff", { part: partLabel(name) });
    prev.hidden = next.hidden = !bars.length;
    scoreA.tracks = [ia];
    scoreB.tracks = [ib];
    scoreA.decorate = (track, i) => (track === ia && pd.a[i] ? mark(pd.a[i]!) : null);
    scoreB.decorate = (track, i) => (track === ib && pd.b[i] ? mark(pd.b[i]!) : null);
    await Promise.all([scoreA.load(a.xmlText!, a.label), scoreB.load(b.xmlText!, b.label)]);
  };
  partSel.addEventListener("change", () => void load());
  const legend = h("ul", { class: "legend" },
    (["removed", "added", "octave", "moved"] as MarkKind[]).map((k) => h("li", {},
      h("span", { class: "sw", "aria-hidden": "true", style: `background:var(--${MARK_TOKEN[k].token});border-color:var(--${MARK_TOKEN[k].token})` }), t(`cmp.legend.${k}`))));
  queueMicrotask(() => void load());
  return h("section", { "aria-labelledby": "cmp-notation-h", class: "stack" },
    h("h2", { id: "cmp-notation-h" }, t("cmp.notation"), infoTip(t("cmp.notation"), t("cmp.notationHint"))),
    legend,
    h("div", { class: "row" }, h("label", { for: "cmp-part" }, t("cmp.part")), partSel, prev, next),
    status,
    h("h3", {}, t("cmp.scoreA", { label: a.label })), scoreA,
    h("h3", {}, t("cmp.scoreB", { label: b.label })), scoreB);
}
