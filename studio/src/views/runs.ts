// Runs: start a pipeline on a file, capture or dataset item; list and search runs.
import { api, MissingEndpoint } from "../api/client";
import type { Job, ProfileInfo, Source } from "../api/types";
import { t } from "../i18n";
import { announce, clear, errorNotice, filePicker, fmt, h, loading, pill, table } from "../ui/dom";

export function runLink(j: Job): HTMLAnchorElement {
  return h("a", { href: `#/runs/${encodeURIComponent(j.id)}` }, j.title || j.id);
}

export function runsView(root: HTMLElement): void {
  const listEl = h("div", {}, loading());
  const formEl = h("div", {}, loading());
  const search = h("input", { type: "search", id: "run-search", placeholder: t("runs.searchPlaceholder") });
  let jobs: Job[] = [];

  const renderList = () => {
    const q = search.value.trim().toLowerCase();
    const shown = jobs.filter((j) => !q || [j.id, j.title ?? "", j.profile, j.status].some((s) => s.toLowerCase().includes(q)));
    clear(listEl,
      h("p", { class: "hint", role: "status" }, t("runs.count", { shown: shown.length, total: jobs.length })),
      table(t("runs.title"), [t("runs.col.run"), t("runs.col.profile"), t("runs.col.status"), t("runs.col.stages"), t("runs.col.created")], shown.map((j) => {
        const cached = j.stages.filter((s) => s.status === "cached" || s.status === "imported").length;
        const ran = j.stages.filter((s) => s.status === "ran").length;
        return [
          h("span", {}, runLink(j), h("br", {}), h("span", { class: "small muted mono" }, j.id)),
          j.profile,
          pill(j.status),
          t("runs.stages", { n: j.stages.length, ran, cached }),
          fmt.date(j.created),
        ];
      }), { hideCaption: true }));
  };
  search.addEventListener("input", renderList);

  clear(root,
    h("h1", {}, t("runs.title")),
    h("section", { "aria-labelledby": "new-run-h" }, h("h2", { id: "new-run-h" }, t("runs.start")), formEl),
    h("section", { "aria-labelledby": "runs-h" },
      h("h2", { id: "runs-h" }, t("runs.all")),
      h("div", { class: "row" }, h("label", { for: "run-search" }, t("runs.search")), search),
      listEl));

  api.jobs().then((j) => {
    jobs = j;
    renderList();
  }).catch((e) => clear(listEl, errorNotice(e)));

  Promise.all([api.profiles(), api.sources().catch((e) => e as Error)]).then(([profiles, sources]) => {
    clear(formEl, newRunForm(profiles, sources));
  }).catch((e) => clear(formEl, errorNotice(e)));
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
  const showDesc = () => {
    const p = profiles.find((x) => x.name === profile.value);
    desc.textContent = p ? t("runs.profileDesc", { desc: p.description, stages: p.stages.join(" → ") }) : "";
  };
  profile.addEventListener("change", showDesc);
  showDesc();
  const title = h("input", { type: "text", id: "run-title", autocomplete: "off" });
  const audio = h("input", { type: "checkbox", id: "run-audio", checked: true });
  const heavy = h("input", { type: "checkbox", id: "run-heavy", checked: true });
  const submit = h("button", { type: "submit", class: "primary" }, t("runs.submit"));

  const form = h("form", { class: "stack", "aria-describedby": "run-error" },
    h("fieldset", {}, h("legend", {}, t("runs.source")),
      h("div", { class: "row" }, kind("file", t("runs.file"), true), kind("source", t("runs.sourceItem"))),
      h("div", { class: "row" }, h("label", { for: "run-file" }, t("runs.file")), filePicker(file)),
      h("div", { class: "row" }, h("label", { for: "run-source" }, t("runs.sourceItem")), sourceSel),
      haveSources ? null : errorNotice(sources)),
    h("div", { class: "row" }, h("label", { for: "run-profile" }, t("runs.profile")), profile),
    desc,
    h("div", { class: "row" }, h("label", { for: "run-title" }, t("runs.titleField")), title),
    h("div", { class: "row" },
      h("label", {}, audio, t("runs.renderAudio")),
      h("label", {}, heavy, t("runs.allowHeavy"))),
    err,
    submit);
  const sync = () => {
    const useFile = (form.querySelector("input[name=source-kind]:checked") as HTMLInputElement).value === "file";
    file.disabled = !useFile;
    sourceSel.disabled = useFile || !haveSources || !sourceSel.options.length;
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
