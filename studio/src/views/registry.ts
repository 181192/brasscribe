// Datasets and models: licences, sizes, presence and the device each adapter uses.
// Hashes, fingerprints and paths sit behind disclosures; paths are shown relative to the repository.
import { api } from "../api/client";
import { t } from "../i18n";
import { clear, errorNotice, fmt, h, infoTip, loading, more, pill, table, viewHead } from "../ui/dom";

/** "Not stated" licences are a warning, with the reason in an info tip. */
function licence(l: string | null | undefined): HTMLElement | string {
  if (l && !/^not stated$/i.test(l.trim())) return l;
  return h("span", {}, h("span", { class: "pill pill-warning" }, t("common.notStated")), infoTip(t("reg.col.licence"), t("reg.licenceTip")));
}

export function registryView(root: HTMLElement): void {
  const models = h("div", {}, loading());
  const data = h("div", {}, loading());
  clear(root, viewHead(t("page.registry"), t("reg.purpose")),
    h("section", { "aria-labelledby": "ad-h" }, h("h2", { id: "ad-h" }, t("reg.adapters")), models),
    h("section", { "aria-labelledby": "ds-h" }, h("h2", { id: "ds-h" }, t("reg.datasets")), data));

  api.adapters().then((list) => {
    const files = list.flatMap((a) => a.models.map((m) => ({ a, m })));
    const missing = files.filter(({ m }) => !m.present).length;
    clear(models,
      table(t("reg.adapterTable"), [t("reg.col.adapter"), t("reg.col.version"), t("reg.col.device"), t("reg.col.heavy"), t("reg.col.licence"), t("reg.col.files")], list.map((a) => [
        h("span", { class: "mono" }, a.name), a.version ?? "–", a.device, a.heavy ? t("reg.heavyYes") : t("common.no"), licence(a.licence),
        a.models.length ? (a.models.every((m) => m.present) ? pill("ok") : pill("missing")) : "–",
      ]), { hideCaption: true }),
      h("p", {}, missing ? t("reg.filesMissing", { n: files.length, m: missing }) : t("reg.filesAll", { n: files.length })),
      more(t("reg.models"), table(t("reg.models"), [t("reg.col.adapter"), t("reg.col.file"), t("reg.col.size"), "SHA-256", t("reg.col.revision"), t("reg.col.licence"), t("reg.col.present")], files.map(({ a, m }) => [
        h("span", { class: "mono" }, a.name), h("span", { class: "mono" }, m.name), fmt.bytes(m.bytes), h("span", { class: "mono" }, fmt.hash(m.sha256)),
        m.revision ?? "–", licence(m.licence), pill(m.present ? "ok" : "missing"),
      ]), { hideCaption: true }), { count: files.length }),
      more(t("reg.fingerprints"), table(t("reg.fingerprints"), [t("reg.col.adapter"), t("reg.col.fingerprint")], list.map((a) => [
        h("span", { class: "mono" }, a.name), h("span", { class: "mono" }, fmt.hash(a.fingerprint)),
      ]), { hideCaption: true })));
  }).catch((e) => clear(models, errorNotice(e)));

  api.datasets().then((list) => clear(data,
    table(t("reg.datasets"), [t("reg.col.dataset"), t("reg.col.items"), t("reg.col.size"), t("reg.col.licence"), t("reg.col.present")], list.map((d) => [
      h("span", { class: "mono" }, d.name), String(d.items), fmt.bytes(d.bytes), licence(d.licence), pill(d.present ? "ok" : "missing"),
    ]), { hideCaption: true }),
    more(t("reg.paths"), table(t("reg.paths"), [t("reg.col.dataset"), t("reg.col.path"), t("reg.col.files"), t("reg.col.source"), t("reg.col.cached")], list.map((d) => [
      h("span", { class: "mono" }, d.name), h("span", { class: "mono" }, fmt.path(d.path)), String(d.files),
      d.source_url ? h("a", { href: d.source_url }, t("common.source")) : "–",
      d.cached_outputs.length ? d.cached_outputs.join(", ") : "–",
    ]), { hideCaption: true })),
    list.some((d) => d.download) ? more(t("reg.download"),
      list.filter((d) => d.download).map((d) => h("div", {}, h("h4", { class: "mono" }, d.name), h("pre", { class: "json", tabindex: 0 }, d.download!)))) : null,
  )).catch((e) => clear(data, errorNotice(e)));
}
