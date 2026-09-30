// Runs: start a pipeline on a file, capture or dataset item; list and search runs.
import { api, MissingEndpoint } from "../api/client";
import type { Job, ProfileInfo, Source } from "../api/types";
import { locale, t } from "../i18n";
import { announce, clear, errorNotice, filePicker, fmt, h, infoTip, loading, more, pill, table, viewHead } from "../ui/dom";

const short = (d: Date, time: boolean) =>
  d.toLocaleString(locale(), time ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short" });

/**
 * A run's display title: the given title; or, when there is none or it is a bare
 * timestamp (a phone's file name), the recording's date plus the run's own time,
 * so re-runs of one recording can be told apart ("Recording of 15 Aug, run 26 Sep 19:02").
 */
export function runTitle(j: Job): string {
  const raw = (j.title ?? "").trim();
  const m = raw.match(/^(\d{4})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})?$/);
  if (raw && !m) return raw;
  const run = short(new Date(j.created * 1000), true);
  return m ? t("runs.untitled", { rec: short(new Date(+m[1], +m[2] - 1, +m[3]), false), run }) : t("runs.untitledRun", { run });
}

const PAGE = 20;

export function runLink(j: Job): HTMLAnchorElement {
  return h("a", { href: `#/runs/${encodeURIComponent(j.id)}`, class: "run-link" }, runTitle(j));
}

type Filter = "all" | "failed" | "running";

export function runsView(root: HTMLElement): void {
  const listEl = h("div", {}, loading());
  const formEl = h("div", {}, loading());
  const search = h("input", { type: "search", id: "run-search", placeholder: t("runs.searchPlaceholder") });
  const chips = h("div", { class: "chips", role: "group", "aria-label": t("runs.filter") });
  let jobs: Job[] = [];
  let filter: Filter = "all";
  let limit = PAGE; // 20 rows, then "Show more"
  const matches = (j: Job, f: Filter) => f === "all" || (f === "failed" ? j.status === "failed" || j.status === "cancelled" : j.status === "running" || j.status === "queued");

  // The chips are made once and updated in place, so the one just pressed keeps focus.
  const chipEls = (["all", "failed", "running"] as Filter[]).map((f) => {
    const count = h("span", { class: "count" });
    const b = h("button", { type: "button", class: "chip", onclick: () => { filter = f; limit = PAGE; renderList(); } }, t(`runs.filter.${f}`), count);
    return { f, b, count };
  });
  clear(chips, chipEls.map((c) => c.b));
  const renderChips = () => {
    for (const { f, b, count } of chipEls) {
      b.setAttribute("aria-pressed", String(filter === f));
      count.textContent = String(jobs.filter((j) => matches(j, f)).length);
    }
  };

  const renderList = () => {
    renderChips();
    if (!jobs.length) {
      clear(listEl, h("div", { class: "empty" },
        h("p", {}, h("strong", {}, t("runs.none"))),
        h("p", { class: "hint" }, t("runs.noneBody")),
        h("p", {}, h("a", { class: "button primary", href: `#/viewer?src=${encodeURIComponent(api.referenceFileUrl("mikkel-arranged-band", "brass-band.musicxml"))}&name=${encodeURIComponent("Mikkel")}` }, t("runs.demo")))));
      formEl.querySelector("button[type=submit]")?.classList.remove("primary");
      return;
    }
    const q = search.value.trim().toLowerCase();
    const shown = jobs.filter((j) => matches(j, filter) && (!q || [j.id, runTitle(j), j.profile, j.status].some((s) => s.toLowerCase().includes(q))));
    const page = shown.slice(0, limit);
    const left = shown.length - page.length;
    clear(listEl,
      h("p", { class: "hint", role: "status" }, t("runs.count", { shown: shown.length, total: jobs.length })),
      table(t("runs.title"), [t("runs.col.run"), t("runs.col.status"), t("runs.col.profile"), t("runs.col.stages"), t("runs.col.created")], page.map((j) => {
        const cached = j.stages.filter((s) => s.status === "cached" || s.status === "imported").length;
        const ran = j.stages.filter((s) => s.status === "ran").length;
        return [
          h("span", {}, runLink(j), h("span", { class: "sub mono" }, j.id)),
          pill(j.status),
          j.profile,
          t("runs.stages", { n: j.stages.length, ran, cached }),
          fmt.date(j.created),
        ];
      }), { hideCaption: true, className: "runs-table" }),
      left > 0 ? h("p", { class: "actions" }, h("button", { type: "button", class: "ghost", id: "runs-more", onclick: () => {
        const next = listEl.querySelectorAll(".runs-table tbody tr").length;
        limit += PAGE;
        renderList();
        // Keep the keyboard where the new rows start.
        listEl.querySelectorAll<HTMLAnchorElement>(".runs-table a.run-link")[next]?.focus();
      } }, t("runs.showMore", { n: Math.min(PAGE, left), left }))) : null);
  };
  search.addEventListener("input", () => {
    limit = PAGE;
    renderList();
  });

  clear(root,
    viewHead(t("runs.title"), t("runs.purpose")),
    h("section", { class: "card new-run", "aria-labelledby": "new-run-h" }, h("h2", { id: "new-run-h" }, t("runs.start")), formEl),
    h("section", { "aria-labelledby": "runs-h" },
      h("h2", { id: "runs-h" }, t("runs.all")),
      h("div", { class: "row list-tools" }, chips, h("div", { class: "field" }, h("label", { for: "run-search" }, t("runs.search")), search)),
      listEl));

  const loaded = api.jobs().then((j) => {
    jobs = j;
  });
  Promise.all([api.profiles(), api.sources().catch((e) => e as Error)]).then(([profiles, sources]) => {
    clear(formEl, newRunForm(profiles, sources));
  }).catch((e) => clear(formEl, errorNotice(e))).finally(() => loaded.then(renderList, () => undefined));
  loaded.then(renderList).catch((e) => clear(listEl, errorNotice(e)));
}

function newRunForm(profiles: ProfileInfo[], sources: Source[] | Error): HTMLElement {
  const err = h("div", { id: "run-error", "aria-live": "assertive" });
  const kind = (v: string, label: string, checked = false) =>
    h("label", {}, h("input", { type: "radio", name: "source-kind", value: v, checked }), label);
  const file = h("input", { type: "file", id: "run-file", accept: "audio/*,.wav,.flac,.mp3,.m4a,.aiff" });
  const sourceSel = h("select", { id: "run-source" });
  const haveSources = Array.isArray(sources);
  if (haveSources) {
    for (const k of ["capture", "dataset"] as const) {
      const items = sources.filter((s) => s.kind === k);
      if (!items.length) continue;
      sourceSel.append(h("optgroup", { label: k === "capture" ? t("runs.captures") : t("runs.datasetItems") },
        items.map((s) => h("option", { value: s.id }, s.dataset ? `${s.dataset}: ${s.name}` : s.name))));
    }
  }
  const profile = h("select", { id: "run-profile", "aria-describedby": "run-profile-desc" },
    profiles.map((p) => h("option", { value: p.name, selected: p.name === "orchestra-with-soloist" }, `${p.name}${p.validated ? ` (${t("runs.validated")})` : ""}`)));
  const desc = h("p", { id: "run-profile-desc", class: "hint" });
  const chain = h("p", {});
  const showDesc = () => {
    const p = profiles.find((x) => x.name === profile.value);
    // One plain sentence per known profile; the engine's own description and the stage chain sit under "Stages".
    const plain = p ? t(`runs.profile.${p.name}`) : "";
    desc.textContent = p ? (plain === `runs.profile.${p.name}` ? p.description : plain) : "";
    clear(chain, p ? [h("span", {}, p.description), h("br", {}), h("span", { class: "mono" }, p.stages.join(" → "))] : null);
  };
  profile.addEventListener("change", showDesc);
  showDesc();
  const title = h("input", { type: "text", id: "run-title", autocomplete: "off" });
  const audio = h("input", { type: "checkbox", id: "run-audio", checked: true });
  const heavy = h("input", { type: "checkbox", id: "run-heavy", checked: true });
  const submit = h("button", { type: "submit", class: "primary", id: "run-submit" }, t("runs.submit"));

  // Only the control for the chosen source is shown.
  const fileRow = h("div", { class: "row" }, h("label", { for: "run-file", class: "visually-hidden" }, t("runs.file")), filePicker(file));
  const sourceRow = h("div", { class: "row" }, h("label", { for: "run-source", class: "visually-hidden" }, t("runs.sourceItem")), sourceSel);
  const form = h("form", { class: "stack", "aria-describedby": "run-error" },
    h("fieldset", { class: "source" }, h("legend", {}, t("runs.source")),
      h("div", { class: "row" }, kind("file", t("runs.file"), true), kind("source", t("runs.sourceItem"))),
      fileRow, sourceRow,
      haveSources ? null : errorNotice(sources)),
    h("div", { class: "field" },
      h("span", {}, h("label", { for: "run-profile" }, t("runs.profile")), infoTip(t("runs.profile"), t("runs.profileTip"))),
      profile, desc,
      more(t("runs.profileStages"), chain)),
    h("div", { class: "field" }, h("label", { for: "run-title" }, t("runs.titleField")), title),
    more(t("runs.options"), h("div", {},
      h("div", {}, h("label", {}, audio, t("runs.renderAudio"))),
      h("div", {}, h("label", {}, heavy, t("runs.allowHeavy")), infoTip(t("runs.heavyTerm"), t("runs.heavyTip"))))),
    err,
    h("div", { class: "actions" }, submit));
  const sync = () => {
    const useFile = (form.querySelector("input[name=source-kind]:checked") as HTMLInputElement).value === "file";
    file.disabled = !useFile;
    sourceSel.disabled = useFile || !haveSources || !sourceSel.options.length;
    fileRow.hidden = !useFile;
    sourceRow.hidden = useFile;
  };
  form.addEventListener("change", sync);
  sync();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(err);
    submit.disabled = true;
    try {
      const useFile = !file.disabled;
      let job: Job;
      if (useFile) {
        const f = file.files?.[0];
        if (!f) throw new Error(t("runs.chooseFile"));
        const ref = await api.upload(f);
        job = await api.createJob({ audio_id: ref.audio_id, profile: profile.value, title: title.value || null, render_audio: audio.checked, allow_heavy: heavy.checked });
      } else {
        if (!sourceSel.value) throw new Error(t("runs.chooseSource"));
        job = await api.createJob({ source_id: sourceSel.value, profile: profile.value, title: title.value || null, render_audio: audio.checked, allow_heavy: heavy.checked });
      }
      announce(t("runs.started", { id: job.id }));
      location.hash = `#/runs/${encodeURIComponent(job.id)}`;
    } catch (x) {
      clear(err, x instanceof MissingEndpoint || !(x instanceof Error) ? errorNotice(x)
        : h("p", { class: "notice notice-error", role: "alert" }, x.message));
      submit.disabled = false;
    }
  });
  return form;
}
